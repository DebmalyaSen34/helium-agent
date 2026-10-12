from __future__ import annotations

import fnmatch
import logging
import shlex
import subprocess
from collections.abc import Callable
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT_SECONDS = 120
MAX_TIMEOUT_SECONDS = 600
OUTPUT_HEAD_CHARS = 8_000
OUTPUT_TAIL_CHARS = 8_000


def _project_root() -> Path:
    from tools import file_ops

    return file_ops.PROJECT_ROOT


def _cap_output(text: str) -> str:
    limit = OUTPUT_HEAD_CHARS + OUTPUT_TAIL_CHARS
    if len(text) <= limit:
        return text
    omitted = len(text) - limit
    return (
        text[:OUTPUT_HEAD_CHARS]
        + f"\n... [{omitted} characters omitted] ...\n"
        + text[-OUTPUT_TAIL_CHARS:]
    )


def _decode(value) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode(errors="replace")
    return str(value)


def execute_bash(command: str, timeout: int = DEFAULT_TIMEOUT_SECONDS) -> str:
    try:
        timeout = max(1, min(int(timeout), MAX_TIMEOUT_SECONDS))
    except (TypeError, ValueError):
        timeout = DEFAULT_TIMEOUT_SECONDS

    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(_project_root()),
        )

        output_parts = [f"exit_code: {result.returncode}"]
        if result.stdout:
            output_parts.append(result.stdout)
        if result.stderr:
            output_parts.append(f"[stderr]\n{result.stderr}")
        if len(output_parts) == 1:
            output_parts.append("(no output)")

        return _cap_output("\n".join(output_parts))

    except subprocess.TimeoutExpired as e:
        err_msg = f"Error: Command timed out after {timeout} seconds."
        stdout_captured = _decode(e.stdout)
        stderr_captured = _decode(e.stderr)
        if stdout_captured:
            err_msg += f"\nStdout captured so far:\n{stdout_captured}"
        if stderr_captured:
            err_msg += f"\nStderr captured so far:\n{stderr_captured}"
        return _cap_output(err_msg)

    except Exception as e:
        logger.error(f"Error executing command: {e}", exc_info=True)
        return f"Error executing command: {str(e)}"


# ---------------------------------------------------------------------------
# Read-only command classification
# ---------------------------------------------------------------------------
#
# A command is "safe" (runs without confirmation) only when every segment is a
# known read-only program, none of its arguments can write, execute, or reach
# outside the project, and no shell feature (substitution, redirection,
# background jobs, multi-line scripts) is used. Anything else is "risky" and
# goes through the confirmation prompt.

FORBIDDEN_SUBSTRINGS = ("\n", "\r", "`", "$(", "${", "<", ">", "|&")
SEGMENT_OPERATORS = {"&&", "||", "|", ";"}
GLOB_CHARS = ("*", "?", "[")

SENSITIVE_PATTERNS = (
    ".env",
    ".env.*",
    "*.env",
    "id_rsa*",
    "id_dsa*",
    "id_ecdsa*",
    "id_ed25519*",
    "*.pem",
    "*.key",
    "*.p12",
    ".ssh",
    ".aws",
    ".gnupg",
    ".netrc",
    ".npmrc",
    ".pypirc",
    ".git-credentials",
    "credentials*",
    "helium-agent",
)


def _no_restrictions(args: list[str]) -> bool:
    return True


def _no_globs(args: list[str]) -> bool:
    return not any(ch in arg for arg in args for ch in GLOB_CHARS)


def _find_ok(args: list[str]) -> bool:
    banned = {"-delete", "-exec", "-execdir", "-ok", "-okdir", "-fprint", "-fprint0", "-fprintf", "-fls"}
    return not any(arg in banned for arg in args)


def _sort_ok(args: list[str]) -> bool:
    return not any(arg == "-o" or arg.startswith("--output") or (arg.startswith("-o") and not arg.startswith("--")) for arg in args)


def _uniq_ok(args: list[str]) -> bool:
    positional = [arg for arg in args if not arg.startswith("-")]
    return len(positional) <= 1


def _tree_ok(args: list[str]) -> bool:
    return "-o" not in args


def _rg_ok(args: list[str]) -> bool:
    return not any(arg.startswith("--pre") for arg in args)


GIT_READ_ONLY_SUBCOMMANDS = {"status", "diff", "log", "show", "blame", "rev-parse", "ls-files", "grep", "branch"}
GIT_BRANCH_READ_FLAGS = {"-a", "--all", "-r", "--remotes", "-v", "-vv", "--verbose", "--list", "--show-current"}


def _git_ok(args: list[str]) -> bool:
    if not args:
        return False
    subcommand, rest = args[0], args[1:]
    if subcommand not in GIT_READ_ONLY_SUBCOMMANDS:
        return False
    for arg in rest:
        if arg.startswith("--output") or arg in {"--ext-diff", "-c"} or arg.startswith("--exec"):
            return False
    if subcommand == "branch":
        return all(arg in GIT_BRANCH_READ_FLAGS for arg in rest)
    return True


SAFE_COMMANDS: dict[str, Callable[[list[str]], bool]] = {
    "ls": _no_restrictions,
    "pwd": _no_restrictions,
    "echo": _no_restrictions,
    "which": _no_restrictions,
    "uname": _no_restrictions,
    "du": _no_restrictions,
    "df": _no_restrictions,
    "cat": _no_globs,
    "head": _no_globs,
    "tail": _no_globs,
    "wc": _no_globs,
    "file": _no_globs,
    "stat": _no_globs,
    "grep": _no_restrictions,
    "rg": _rg_ok,
    "find": _find_ok,
    "tree": _tree_ok,
    "sort": _sort_ok,
    "uniq": _uniq_ok,
    "git": _git_ok,
}


def _is_sensitive(arg: str) -> bool:
    parts = Path(arg).parts
    return any(fnmatch.fnmatch(part, pattern) for part in parts for pattern in SENSITIVE_PATTERNS)


def _looks_like_path(arg: str) -> bool:
    return arg.startswith(("/", "~")) or ".." in Path(arg).parts


def _inside_project(arg: str, root: Path) -> bool:
    candidate = Path(arg).expanduser()
    if not candidate.is_absolute():
        candidate = root / candidate
    try:
        candidate.resolve().relative_to(root.resolve())
        return True
    except (ValueError, OSError):
        return False


def _split_segments(command: str) -> list[list[str]] | None:
    lexer = shlex.shlex(command, posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    try:
        tokens = list(lexer)
    except ValueError:
        return None

    segments: list[list[str]] = [[]]
    for token in tokens:
        if token in SEGMENT_OPERATORS:
            segments.append([])
            continue
        if set(token) <= set("&|;()"):
            # Background "&", subshells, or other operators we don't allow.
            return None
        segments[-1].append(token)
    return segments


def is_command_safe(command: str) -> bool:
    """Classify a bash command as safe (read-only, project-confined) or risky."""
    if not command or not command.strip():
        return False
    if any(fragment in command for fragment in FORBIDDEN_SUBSTRINGS):
        return False

    segments = _split_segments(command)
    if segments is None:
        return False

    root = _project_root()
    for segment in segments:
        if not segment:
            return False
        program, args = segment[0], segment[1:]
        if "=" in program:
            # Leading VAR=value assignments can change program behaviour.
            return False
        validator = SAFE_COMMANDS.get(program)
        if validator is None or not validator(args):
            return False
        for arg in args:
            if _is_sensitive(arg):
                return False
            if arg.startswith("-"):
                continue
            if _looks_like_path(arg) and not _inside_project(arg, root):
                return False

    return True
