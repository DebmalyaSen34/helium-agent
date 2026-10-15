"""Shared rendering for code: syntax-highlighted diffs, git diffs, and Markdown code blocks.

Diffs are drawn the way a code review tool shows them: line numbers in a gutter,
syntax colours kept on every line, a tinted background on added and removed lines,
and a brighter tint on the exact words that changed.
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field

from rich import box
from rich.console import Console, ConsoleOptions, Group, RenderableType, RenderResult
from rich.markdown import CodeBlock, Markdown
from rich.panel import Panel
from rich.style import Style
from rich.syntax import Syntax
from rich.text import Text

from utils.theme import current_theme, resolve, syntax_theme

# Colours come from the active theme (utils.theme) at render time; these are its style names.
BORDER = "subtle"
GUTTER = "faint"
ADD_FG, DEL_FG = "success", "danger"
CONTEXT_LINES = 3
# Word-level highlights only help when the two lines are mostly alike.
_WORD_DIFF_MIN_RATIO = 0.4
_TOKEN_RE = re.compile(r"\w+|\s+|[^\w\s]")
_HUNK_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@(.*)$")


# ── diff model ────────────────────────────────────────────────────


@dataclass
class DiffRow:
    kind: str  # " ", "+", "-", or "…" for a gap between hunks
    text: str
    old_no: int | None = None
    new_no: int | None = None


@dataclass
class FileDiff:
    path: str
    rows: list[DiffRow] = field(default_factory=list)
    status: str = "modified"  # modified, added, deleted, renamed, binary
    old_path: str | None = None

    @property
    def added(self) -> int:
        return sum(row.kind == "+" for row in self.rows)

    @property
    def removed(self) -> int:
        return sum(row.kind == "-" for row in self.rows)


def diff_rows(old: str, new: str, context: int = CONTEXT_LINES) -> list[DiffRow]:
    """Rows for the changes between two versions of a file, with gaps between hunks."""
    old_lines, new_lines = old.splitlines(), new.splitlines()
    rows: list[DiffRow] = []
    matcher = difflib.SequenceMatcher(None, old_lines, new_lines, autojunk=False)
    for index, group in enumerate(matcher.get_grouped_opcodes(context)):
        if index or group[0][1] > 0:
            rows.append(DiffRow("…", ""))
        for tag, i1, i2, j1, j2 in group:
            if tag == "equal":
                rows.extend(DiffRow(" ", old_lines[i], i + 1, j1 + k + 1) for k, i in enumerate(range(i1, i2)))
                continue
            rows.extend(DiffRow("-", old_lines[i], old_no=i + 1) for i in range(i1, i2))
            rows.extend(DiffRow("+", new_lines[j], new_no=j + 1) for j in range(j1, j2))
    return rows


def parse_unified_diff(text: str) -> list[DiffRow]:
    """Rows from the hunks of a unified diff (file headers are ignored)."""
    rows: list[DiffRow] = []
    old_no = new_no = 0
    in_hunk = False
    for line in text.splitlines():
        match = _HUNK_RE.match(line)
        if match:
            if rows or int(match.group(1)) > 1:
                rows.append(DiffRow("…", match.group(5).strip()))
            old_no, new_no, in_hunk = int(match.group(1)), int(match.group(3)), True
            continue
        if not in_hunk or line.startswith("\\"):
            continue
        kind, body = (line[:1] or " "), line[1:]
        if kind == "+":
            rows.append(DiffRow("+", body, new_no=new_no))
            new_no += 1
        elif kind == "-":
            rows.append(DiffRow("-", body, old_no=old_no))
            old_no += 1
        elif kind == " ":
            rows.append(DiffRow(" ", body, old_no, new_no))
            old_no += 1
            new_no += 1
        else:
            in_hunk = False
    return rows


def _git_path(token: str) -> str:
    return token[2:] if token[:2] in ("a/", "b/") else token


def parse_git_diff(text: str) -> list[FileDiff]:
    """Split `git diff` output into one FileDiff per file."""
    files: list[FileDiff] = []
    chunks = re.split(r"^(?=diff --git )", text, flags=re.MULTILINE)
    for chunk in chunks:
        if not chunk.startswith("diff --git "):
            continue
        header = chunk.splitlines()[0]
        parts = header[len("diff --git "):].split(" b/", 1)
        path = parts[1] if len(parts) == 2 else _git_path(header.split()[-1])
        diff = FileDiff(path=path, rows=parse_unified_diff(chunk))
        if re.search(r"^new file mode", chunk, re.MULTILINE):
            diff.status = "added"
        elif re.search(r"^deleted file mode", chunk, re.MULTILINE):
            diff.status = "deleted"
        elif re.search(r"^Binary files", chunk, re.MULTILINE):
            diff.status = "binary"
        rename = re.search(r"^rename from (.+)$", chunk, re.MULTILINE)
        if rename:
            diff.status, diff.old_path = "renamed", rename.group(1)
        files.append(diff)
    return files


def looks_like_git_diff(text: str) -> bool:
    return bool(re.search(r"^diff --git ", text, re.MULTILINE)) and "\n@@ " in text


# ── highlighting ──────────────────────────────────────────────────


def lexer_for(path: str, code: str = "") -> str:
    return Syntax.guess_lexer(path, code) if path else "text"


def highlight(code: str, lexer: str) -> list[Text]:
    """Syntax-highlight `code` and return one Text per line (no background)."""
    syntax = Syntax(code, lexer, theme=syntax_theme(), background_color="default")
    lines = syntax.highlight(code).split("\n", allow_blank=True)
    expected = len(code.splitlines())
    return list(lines[:expected]) + [Text()] * (expected - len(lines))


def _changed_spans(a: str, b: str) -> tuple[list[tuple[int, int]], list[tuple[int, int]]] | None:
    """Character ranges that differ between two similar lines, or None if they barely match."""
    a_tokens, b_tokens = _TOKEN_RE.findall(a), _TOKEN_RE.findall(b)
    matcher = difflib.SequenceMatcher(None, a_tokens, b_tokens, autojunk=False)
    if matcher.ratio() < _WORD_DIFF_MIN_RATIO:
        return None

    def offsets(tokens: list[str]) -> list[int]:
        out, total = [0], 0
        for token in tokens:
            total += len(token)
            out.append(total)
        return out

    a_off, b_off = offsets(a_tokens), offsets(b_tokens)
    a_spans, b_spans = [], []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        if i2 > i1:
            a_spans.append((a_off[i1], a_off[i2]))
        if j2 > j1:
            b_spans.append((b_off[j1], b_off[j2]))
    return a_spans, b_spans


def _highlight_rows(rows: list[DiffRow], lexer: str) -> list[Text]:
    """Highlight the old and new sides separately so multi-line constructs colour correctly."""
    old_side = [row for row in rows if row.kind in " -"]
    new_side = [row for row in rows if row.kind in " +"]
    styled: dict[int, Text] = {}
    for side in (old_side, new_side):
        texts = highlight("\n".join(row.text for row in side) + "\n", lexer) if side else []
        for row, text in zip(side, texts):
            styled.setdefault(id(row), text)
    out = [styled.get(id(row), Text(row.text)).copy() for row in rows]
    theme = current_theme()

    # Pair each run of removed lines with the added run right after it for word highlights.
    index = 0
    while index < len(rows):
        if rows[index].kind != "-":
            index += 1
            continue
        start = index
        while index < len(rows) and rows[index].kind == "-":
            index += 1
        removed = range(start, index)
        add_start = index
        while index < len(rows) and rows[index].kind == "+":
            index += 1
        for r, a in zip(removed, range(add_start, index)):
            spans = _changed_spans(rows[r].text, rows[a].text)
            if spans is None:
                continue
            for begin, end in spans[0]:
                out[r].stylize(f"on {theme.diff_del_word_bg}", begin, end)
            for begin, end in spans[1]:
                out[a].stylize(f"on {theme.diff_add_word_bg}", begin, end)
    return out


# ── rendering ─────────────────────────────────────────────────────


class DiffView:
    """Renderable diff rows: gutter numbers, +/- markers, full-width tinted lines."""

    def __init__(self, rows: list[DiffRow], path: str = "", *, line_numbers: bool = True, max_rows: int | None = None) -> None:
        self.rows = rows
        self.lexer = lexer_for(path, "\n".join(row.text for row in rows[:50]))
        self.line_numbers = line_numbers
        self.max_rows = max_rows

    def __rich_console__(self, console: Console, options: ConsoleOptions) -> RenderResult:
        rows = self.rows
        hidden = 0
        if self.max_rows is not None and len(rows) > self.max_rows:
            hidden = len(rows) - self.max_rows
            rows = rows[: self.max_rows]
        texts = _highlight_rows(rows, self.lexer)
        theme = current_theme()
        numbers = [row.new_no if row.kind == "+" else row.old_no if row.kind == "-" else row.new_no for row in rows]
        width = max((len(str(n)) for n in numbers if n), default=1) if self.line_numbers else 0
        gutter = width + 1 if self.line_numbers else 0
        code_width = max(10, options.max_width - gutter - 2)

        for row, text, number in zip(rows, texts, numbers):
            if row.kind == "…":
                line = Text(" " * gutter + "⋯", style=theme.faint)
                if row.text:
                    line.append(f"  {row.text}", style=f"italic {theme.faint}")
                yield line
                continue
            bg = {"+": theme.diff_add_bg, "-": theme.diff_del_bg}.get(row.kind)
            marker_style = {"+": theme.success, "-": theme.danger}.get(row.kind, theme.faint)
            text.expand_tabs(4)
            wrapped = text.wrap(console, code_width, no_wrap=False) if text.cell_len > code_width else [text]
            for part_index, part in enumerate(wrapped or [Text()]):
                part.rstrip()
                line = Text()
                if self.line_numbers:
                    label = str(number) if number and part_index == 0 else ""
                    line.append(f"{label:>{width}} ", style=theme.faint)
                tint = f" on {bg}" if bg else ""
                line.append(f"{row.kind if part_index == 0 else ' '} ", style=marker_style + tint)
                if bg:
                    # The tint goes under the code so word highlights stay on top.
                    base = part.style if isinstance(part.style, Style) else Style.parse(part.style or "")
                    part.style = base + Style(bgcolor=bg)
                line.append_text(part)
                line.append(" " * max(0, code_width - part.cell_len), style=tint.strip())
                yield line
        if hidden:
            yield Text(f"{' ' * gutter}… {hidden} more line{'s' if hidden != 1 else ''}", style=f"italic {theme.faint}")


def change_summary(added: int, removed: int) -> Text:
    text = Text()
    if added:
        text.append(f"+{added}", style=f"bold {current_theme().success}")
    if removed:
        text.append(" " if added else "")
        text.append(f"−{removed}", style=f"bold {current_theme().danger}")
    return text


def diff_panel(title: str, rows: list[DiffRow], path: str, *, max_rows: int | None = None, border: str = BORDER) -> Panel:
    added = sum(row.kind == "+" for row in rows)
    removed = sum(row.kind == "-" for row in rows)
    heading = Text.assemble((f" {title}", f"bold {current_theme().text}"), "  ", change_summary(added, removed), " ")
    return Panel(
        DiffView(rows, path, max_rows=max_rows),
        title=heading,
        title_align="left",
        border_style=resolve(border),
        box=box.ROUNDED,
        padding=(0, 1),
    )


def git_diff_view(text: str, *, max_rows: int = 80) -> RenderableType | None:
    """Render `git diff` output as one panel per file, sharing a row budget."""
    files = parse_git_diff(text)
    if not files:
        return None
    renderables: list[RenderableType] = []
    budget = max_rows
    for diff in files:
        label = f"{diff.old_path} → {diff.path}" if diff.old_path else diff.path
        verb = {"added": "new", "deleted": "deleted", "renamed": "renamed", "binary": "binary"}.get(diff.status)
        title = f"{label} ({verb})" if verb else label
        if budget <= 0 or not diff.rows:
            line = Text.assemble("  ", (title, "bold"), "  ", change_summary(diff.added, diff.removed))
            renderables.append(line)
            continue
        renderables.append(diff_panel(title, diff.rows, diff.path, max_rows=budget))
        budget -= len(diff.rows)
    return Group(*renderables)


# ── Markdown code blocks ──────────────────────────────────────────


class _CodeFence(CodeBlock):
    """Fenced code with a language label; ```diff blocks get the diff treatment."""

    def __rich_console__(self, console: Console, options: ConsoleOptions) -> RenderResult:
        code = str(self.text).rstrip()
        lexer = (self.lexer_name or "text").lower()
        if lexer in ("diff", "patch", "udiff"):
            rows = parse_unified_diff(code) if _HUNK_RE.search(code) or "\n@@" in code else _loose_diff_rows(code)
            yield DiffView(rows, line_numbers=any(row.old_no or row.new_no for row in rows))
            return
        if lexer not in ("text", "default", ""):
            yield Text(f" {lexer}", style=f"{current_theme().faint} on {current_theme().code_block_bg}", end="\n")
        yield Syntax(code, lexer, theme=syntax_theme(), background_color=current_theme().code_block_bg, word_wrap=True, padding=(0, 1))


def _loose_diff_rows(code: str) -> list[DiffRow]:
    """A ```diff snippet without hunk headers: classify lines by their first character."""
    rows = []
    for line in code.splitlines():
        if line.startswith(("+++", "---")):
            continue
        kind = line[:1] if line[:1] in "+-" and line else " "
        rows.append(DiffRow(kind, line[1:] if kind != " " or line.startswith(" ") else line))
    return rows


class CodeMarkdown(Markdown):
    elements = {**Markdown.elements, "fence": _CodeFence, "code_block": _CodeFence}

    def __init__(self, markup: str, **kwargs) -> None:
        kwargs.setdefault("code_theme", syntax_theme())
        kwargs.setdefault("inline_code_lexer", None)
        super().__init__(markup, **kwargs)


__all__ = [
    "CodeMarkdown",
    "DiffRow",
    "DiffView",
    "FileDiff",
    "change_summary",
    "diff_panel",
    "diff_rows",
    "git_diff_view",
    "highlight",
    "lexer_for",
    "looks_like_git_diff",
    "parse_git_diff",
    "parse_unified_diff",
]
