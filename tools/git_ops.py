"""Read-only git helpers for the agent. Commands run without a shell."""

from __future__ import annotations

import subprocess

from tools.bash_ops import _cap_output, _project_root


def _git(args: list[str], timeout: int = 20) -> tuple[int, str]:
    try:
        completed = subprocess.run(
            ["git", *args],
            cwd=str(_project_root()),
            capture_output=True,
            text=True,
            timeout=timeout,
            stdin=subprocess.DEVNULL,
        )
    except FileNotFoundError:
        return 127, "git is not installed."
    except subprocess.TimeoutExpired:
        return 124, f"git {' '.join(args)} timed out."
    output = completed.stdout
    if completed.stderr.strip():
        output += ("\n" if output else "") + completed.stderr
    return completed.returncode, output


def _not_a_repo(output: str) -> bool:
    return "not a git repository" in output.lower()


def git_status() -> str:
    """Current branch plus short status of changed and untracked files."""
    code, output = _git(["status", "--short", "--branch"])
    if code != 0:
        return "Not a git repository." if _not_a_repo(output) else output.strip()
    return output.strip() or "Working tree clean."


def git_diff(path: str | None = None, staged: bool = False, max_chars: int = 20000) -> str:
    """Unified diff of uncommitted changes, optionally for one path or only staged changes."""
    args = ["diff", "--no-color", "--no-ext-diff"]
    if staged:
        args.append("--cached")
    if path:
        args.extend(["--", path])
    code, output = _git(args)
    if code != 0:
        return "Not a git repository." if _not_a_repo(output) else output.strip()
    if not output.strip():
        return "No differences."
    if len(output) > max_chars:
        return output[:max_chars] + f"\n... [diff truncated at {max_chars} characters]"
    return output


def git_log(max_count: int = 10, path: str | None = None) -> str:
    """Recent commits as one line each."""
    args = ["log", "--oneline", "--no-color", f"-n{max(1, min(int(max_count), 100))}"]
    if path:
        args.extend(["--", path])
    code, output = _git(args)
    if code != 0:
        return "Not a git repository." if _not_a_repo(output) else output.strip()
    return _cap_output(output.strip() or "No commits yet.")


__all__ = ["git_diff", "git_log", "git_status"]
