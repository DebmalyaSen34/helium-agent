"""Project instructions (HELIUM.md) loaded into every system prompt."""

from __future__ import annotations

from pathlib import Path

INSTRUCTION_FILES = ("HELIUM.md", ".helium/HELIUM.md")
MAX_INSTRUCTION_CHARS = 20_000

_cache: dict[Path, tuple[float, str]] = {}


def find_project_instructions(workspace: Path) -> Path | None:
    for name in INSTRUCTION_FILES:
        candidate = Path(workspace) / name
        if candidate.is_file():
            return candidate
    return None


def load_project_instructions(workspace: Path | None = None) -> str | None:
    if workspace is None:
        from tools import file_ops

        workspace = file_ops.PROJECT_ROOT
    path = find_project_instructions(workspace)
    if path is None:
        return None
    try:
        mtime = path.stat().st_mtime
        cached = _cache.get(path)
        if cached and cached[0] == mtime:
            return cached[1]
        text = path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return None
    if len(text) > MAX_INSTRUCTION_CHARS:
        text = text[:MAX_INSTRUCTION_CHARS] + "\n[HELIUM.md truncated]"
    _cache[path] = (mtime, text)
    return text or None


_snapshots: dict[Path, str] = {}


def gather_project_snapshot(root: Path, max_entries: int = 150) -> str:
    """Git status plus a shallow file tree, so the agent starts oriented."""
    from tools.file_service import IGNORED_DIRS
    from tools.git_ops import git_status

    entries: list[str] = []
    try:
        for child in sorted(root.iterdir()):
            if child.name in IGNORED_DIRS or child.name.startswith(".") and child.name not in {".github", ".helium"}:
                continue
            if child.is_dir():
                entries.append(f"{child.name}/")
                for grandchild in sorted(child.iterdir()):
                    if grandchild.name in IGNORED_DIRS or grandchild.name.startswith("."):
                        continue
                    entries.append(f"  {grandchild.name}{'/' if grandchild.is_dir() else ''}")
                    if len(entries) >= max_entries:
                        break
            else:
                entries.append(child.name)
            if len(entries) >= max_entries:
                entries.append("  ...")
                break
    except OSError:
        pass

    return f"Project root: {root}\n\nGit status:\n{git_status()}\n\nFiles (depth 2):\n" + "\n".join(entries)


def project_snapshot_section(workspace: Path | None = None) -> str | None:
    """The snapshot taken the first time it is asked for in this session.

    It is not refreshed per turn, so the system prompt stays byte-identical and
    servers that cache the prompt prefix (llama.cpp, Ollama) keep reusing it.
    """
    if workspace is None:
        from tools import file_ops

        workspace = file_ops.PROJECT_ROOT
    workspace = Path(workspace)
    if workspace not in _snapshots:
        try:
            _snapshots[workspace] = gather_project_snapshot(workspace)
        except Exception:
            _snapshots[workspace] = ""
    snapshot = _snapshots[workspace]
    if not snapshot:
        return None
    return (
        "<project_snapshot>\n"
        "Taken at the start of this session; it does not update as files change.\n\n"
        f"{snapshot}\n"
        "</project_snapshot>"
    )


def project_instructions_section(workspace: Path | None = None) -> str | None:
    text = load_project_instructions(workspace)
    if not text:
        return None
    return (
        '<project_instructions source="HELIUM.md">\n'
        "These are the user's instructions for this project. Follow them.\n\n"
        f"{text}\n"
        "</project_instructions>"
    )


INIT_TASK = """Create a HELIUM.md file in the project root that gives a coding agent the context it needs to work in this repository.

Investigate first: read the README, the package/build manifests (pyproject.toml, package.json, Cargo.toml, go.mod, Makefile, Dockerfile, CI workflows), the test configuration, and skim the main source directories.

Then write HELIUM.md (under 150 lines) with these sections:
- Overview: what the project is, in 2-4 sentences
- Build and run: exact commands
- Tests: exact commands, including how to run a single test
- Layout: the important directories and files and what they contain
- Conventions: code style, naming, patterns, and anything the repo does consistently
- Gotchas: non-obvious things that would trip up a newcomer

Only state facts you verified in the files. Prefer concrete commands and paths over generic advice."""


INIT_UPDATE_TASK = """Update the existing HELIUM.md in the project root so it accurately reflects the repository today.

Read the current HELIUM.md and investigate the repository (README, manifests, test config, CI, main source directories). Keep what is still accurate, fix what is outdated, and add anything important that is missing. Keep the same sections (Overview, Build and run, Tests, Layout, Conventions, Gotchas) and stay under 150 lines. Only state facts you verified in the files."""


__all__ = [
    "INIT_TASK",
    "INIT_UPDATE_TASK",
    "find_project_instructions",
    "gather_project_snapshot",
    "load_project_instructions",
    "project_instructions_section",
    "project_snapshot_section",
]
