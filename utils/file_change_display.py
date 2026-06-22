"""Compact git-diff-style panels for file operations.

Shown in the terminal when the agent creates, edits, or deletes files
so the user always sees what changed.  Code lines are syntax-highlighted
via pygments, with diff colours layered on top.
"""

from __future__ import annotations

import difflib
from pathlib import Path

from pygments import lex
from pygments.lexers import TextLexer, guess_lexer_for_filename
from pygments.styles import get_style_by_name
from pygments.token import Token
from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

console = Console()

# ── limits ────────────────────────────────────────────────────────
MAX_DIFF_LINES = 60
CONTEXT_LINES = 3

# pygments style – one lookup, reused for every file
_STYLE = get_style_by_name("monokai")

# ── operation metadata ────────────────────────────────────────────
_OP_META: dict[str, tuple[str, str]] = {
    # (icon, border_color)
    "write_file":   ("✏", "yellow"),
    "create_file":  ("+", "green"),
    "replace_text": ("✏", "yellow"),
    "patch_file":   ("✏", "yellow"),
    "delete_file":  ("🗑", "red"),
    "append_file":  ("+", "green"),
    "copy_file":    ("→", "cyan"),
    "move_file":    ("→", "cyan"),
    "mkdir":        ("📁", "dim"),
    "touch_file":   ("📄", "dim"),
}


# ── syntax highlighting ──────────────────────────────────────────

def _guess_lexer(text: str, path: str):
    """Pick a pygments lexer from the filename, falling back to plain text."""
    try:
        return guess_lexer_for_filename(path, text)
    except Exception:
        return TextLexer()


def _style_lines(text: str, path: str) -> list[Text]:
    """Tokenise *text* with pygments and return one `Text` per line."""
    if not text:
        return []
    lexer = _guess_lexer(text, path)
    lines: list[Text] = [Text()]
    for ttype, value in lex(text, lexer):
        style = _STYLE.style_for_token(ttype)
        # build a Rich style string from the pygments token style
        parts: list[str] = []
        if style.get("color"):
            parts.append(f"#{style['color']}")
        if style.get("bold"):
            parts.append("bold")
        if style.get("italic"):
            parts.append("italic")
        if style.get("underline"):
            parts.append("underline")
        rich_style = " ".join(parts) if parts else ""

        for char in value:
            if char == "\n":
                lines.append(Text())
            else:
                lines[-1].append(char, style=rich_style)

    # drop trailing empty line if the text ended with \n
    if lines and not lines[-1].plain:
        lines.pop()
    return lines


# ── diff helpers ──────────────────────────────────────────────────

def _diff_lines(old: str, new: str, context: int = CONTEXT_LINES) -> list[str]:
    """Return unified-diff lines."""
    return list(
        difflib.unified_diff(
            old.splitlines(keepends=True),
            new.splitlines(keepends=True),
            fromfile="a",
            tofile="b",
            n=context,
        )
    )


def _build_diff_body(
    raw_diff: list[str],
    old_styled: list[Text],
    new_styled: list[Text],
) -> Text:
    """Merge syntax-highlighted lines with diff markers and colours."""
    old_map = {line.plain: line for line in old_styled}
    new_map = {line.plain: line for line in new_styled}

    body = Text()
    for raw in raw_diff:
        stripped = raw.rstrip("\n")

        # headers / hunk markers – keep as-is
        if stripped.startswith("+++") or stripped.startswith("---"):
            body.append(stripped + "\n", style="bold dim")
            continue
        if stripped.startswith("@@"):
            body.append(stripped + "\n", style="bold cyan")
            continue

        # deletion
        if stripped.startswith("-"):
            content = stripped[1:]
            code = old_map.get(content)
            if code is None:
                code = Text(content)
            body.append("-", style="red")
            for span in code._spans:
                # merge: syntax colour + red tint
                combined = f"{span.style} red" if span.style else "red"
                body.append(code.plain[span.start:span.end], style=combined)
            body.append("\n")
            continue

        # addition
        if stripped.startswith("+"):
            content = stripped[1:]
            code = new_map.get(content)
            if code is None:
                code = Text(content)
            body.append("+", style="green")
            for span in code._spans:
                combined = f"{span.style} green" if span.style else "green"
                body.append(code.plain[span.start:span.end], style=combined)
            body.append("\n")
            continue

        # context line
        content = stripped.lstrip(" ") if stripped.startswith(" ") else stripped
        code = new_map.get(content) or old_map.get(content)
        if code is None:
            code = Text(content)
        body.append(" ", style="dim")
        for span in code._spans:
            combined = f"{span.style} dim" if span.style else "dim"
            body.append(code.plain[span.start:span.end], style=combined)
        body.append("\n")

    return body


def _addition_body(styled_lines: list[Text]) -> Text:
    """Render new-file content: all lines prefixed with green ``+``."""
    body = Text()
    for line in styled_lines:
        body.append("+", style="green")
        for span in line._spans:
            combined = f"{span.style} green" if span.style else "green"
            body.append(line.plain[span.start:span.end], style=combined)
        body.append("\n")
    return body


def _deletion_body(styled_lines: list[Text]) -> Text:
    """Render deleted-file content: all lines prefixed with red ``-``."""
    body = Text()
    for line in styled_lines:
        body.append("-", style="red")
        for span in line._spans:
            combined = f"{span.style} red" if span.style else "red"
            body.append(line.plain[span.start:span.end], style=combined)
        body.append("\n")
    return body


# ── truncation / panel ────────────────────────────────────────────

def _truncate(text: Text, max_lines: int = MAX_DIFF_LINES) -> Text:
    """Trim to *max_lines* and append a notice if truncated."""
    lines = text.split("\n")
    if len(lines) <= max_lines + 1:
        return text
    kept = Text()
    for line in lines[:max_lines]:
        kept.append_text(line)
        kept.append("\n")
    remaining = len(lines) - max_lines - 1
    kept.append(
        f"\n… {remaining} more line{'s' if remaining != 1 else ''} truncated\n",
        style="bold dim",
    )
    return kept


def _panel(title: str, body: Text, border: str) -> Panel:
    return Panel(
        _truncate(body),
        title=f"[bold]{title}[/bold]",
        border_style=border,
        box=box.ROUNDED,
        expand=True,
        padding=(0, 1),
    )


# ── public API ────────────────────────────────────────────────────

def display_file_change(
    operation: str,
    path: str,
    old_content: str | None,
    new_content: str | None,
) -> None:
    """Show a syntax-highlighted diff panel for a file mutation."""
    icon, color = _OP_META.get(operation, ("✏", "yellow"))
    title = f"{icon} {operation} · {path}"

    # New file
    if old_content is None and new_content is not None:
        styled = _style_lines(new_content, path)
        body = _addition_body(styled)
        console.print(_panel(title, body, color))
        return

    # Deleted file
    if old_content is not None and new_content is None:
        styled = _style_lines(old_content, path)
        body = _deletion_body(styled)
        console.print(_panel(title, body, color))
        return

    # Edit
    if old_content is not None and new_content is not None:
        if old_content == new_content:
            return
        raw = _diff_lines(old_content, new_content)
        old_styled = _style_lines(old_content, path)
        new_styled = _style_lines(new_content, path)
        body = _build_diff_body(raw, old_styled, new_styled)
        console.print(_panel(title, body, color))
        return


def display_patch(path: str, patch_text: str) -> None:
    """Render a unified-diff patch string with colours (no syntax highlighting)."""
    icon, color = _OP_META.get("patch_file", ("✏", "yellow"))
    title = f"{icon} patch_file · {path}"
    text = Text()
    for line in patch_text.splitlines():
        stripped = line.rstrip("\n")
        if stripped.startswith("+++") or stripped.startswith("---"):
            text.append(stripped + "\n", style="bold dim")
        elif stripped.startswith("@@"):
            text.append(stripped + "\n", style="bold cyan")
        elif stripped.startswith("+"):
            text.append(stripped + "\n", style="green")
        elif stripped.startswith("-"):
            text.append(stripped + "\n", style="red")
        else:
            text.append(stripped + "\n", style="dim")
    console.print(_panel(title, text, color))


def display_file_status(operation: str, path: str, detail: str = "") -> None:
    """One-line status for non-diff ops (mkdir, touch, copy, move)."""
    icon, color = _OP_META.get(operation, ("·", "dim"))
    msg = f"[{color}]{icon} {operation} · {path}[/]"
    if detail:
        msg += f" [dim]{detail}[/]"
    console.print(msg)
