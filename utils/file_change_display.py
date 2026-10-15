"""Diff panels for file operations.

Shown in the terminal when the agent creates, edits, or deletes files so the
user always sees what changed. Rendering lives in `utils.code_render`.
"""

from __future__ import annotations

from rich.text import Text

from utils.code_render import ADD_FG, BORDER, DEL_FG, GUTTER, DiffRow, diff_panel, diff_rows, parse_unified_diff
from utils.theme import make_console, resolve

console = make_console()

# ── limits ────────────────────────────────────────────────────────
MAX_DIFF_LINES = 60

# Verb shown in the panel title, and the border colour for the operation.
_OP_META: dict[str, tuple[str, str]] = {
    "write_file":   ("Wrote", BORDER),
    "create_file":  ("Created", ADD_FG),
    "edit_file":    ("Edited", BORDER),
    "replace_text": ("Edited", BORDER),
    "patch_file":   ("Patched", BORDER),
    "delete_file":  ("Deleted", DEL_FG),
    "append_file":  ("Appended to", BORDER),
    "copy_file":    ("Copied", GUTTER),
    "move_file":    ("Moved", GUTTER),
    "mkdir":        ("Created folder", GUTTER),
    "touch_file":   ("Touched", GUTTER),
}


def _whole_file_rows(content: str, kind: str) -> list[DiffRow]:
    lines = content.splitlines()
    if kind == "+":
        return [DiffRow("+", line, new_no=number) for number, line in enumerate(lines, 1)]
    return [DiffRow("-", line, old_no=number) for number, line in enumerate(lines, 1)]


# ── public API ────────────────────────────────────────────────────


def display_file_change(
    operation: str,
    path: str,
    old_content: str | None,
    new_content: str | None,
) -> None:
    """Show a syntax-highlighted diff panel for a file mutation."""
    verb, border = _OP_META.get(operation, ("Edited", BORDER))

    if old_content is None and new_content is not None:
        verb, border = "Created", ADD_FG
        rows = _whole_file_rows(new_content, "+")
    elif old_content is not None and new_content is None:
        rows = _whole_file_rows(old_content, "-")
    elif old_content is not None and new_content is not None:
        if old_content == new_content:
            return
        rows = diff_rows(old_content, new_content)
    else:
        return
    console.print(diff_panel(f"{verb} {path}", rows, path, max_rows=MAX_DIFF_LINES, border=border))


def display_patch(path: str, patch_text: str) -> None:
    """Render a unified-diff patch with syntax highlighting and line numbers."""
    rows = parse_unified_diff(patch_text)
    if not rows:
        return
    verb, border = _OP_META["patch_file"]
    console.print(diff_panel(f"{verb} {path}", rows, path, max_rows=MAX_DIFF_LINES, border=border))


def display_file_status(operation: str, path: str, detail: str = "") -> None:
    """One-line status for non-diff ops (mkdir, touch, copy, move)."""
    verb, _ = _OP_META.get(operation, (operation, GUTTER))
    line = Text("  ")
    line.append(verb, style=resolve(GUTTER))
    line.append(f" {path}", style="bold")
    if detail:
        line.append(f" {detail}", style=resolve(GUTTER))
    console.print(line)
