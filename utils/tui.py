"""Terminal look and feel: welcome header, atom logo, prompt chrome, and status bar."""

from __future__ import annotations

import random
import shutil
import time
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from prompt_toolkit.formatted_text import FormattedText
from prompt_toolkit.styles import Style
from rich.console import Group, RenderableType
from rich.markdown import Markdown
from rich.table import Table
from rich.text import Text

ACCENT = "#5fd7ff"          # helium cyan
ACCENT_DARK = "#2a9fd6"
AMBER = "#e3b341"
DANGER = "#ff6b6b"

# The logo is a helium-4 nucleus: two protons (P) and two neutrons (N), each a
# small round blob. Every animation frame jostles the nucleons by a pixel so the
# nucleus wiggles like it is about to decay.
NUCLEUS_WIDTH, NUCLEUS_HEIGHT = 10, 10
# A shaded ball: H is the highlight, X the body.
NUCLEON_SHAPE = (".HX.", "HXXX", "XXXX", ".XX.")
NUCLEONS = (("P", 1, 1), ("N", 5, 1), ("N", 1, 5), ("P", 5, 5))
NUCLEUS_FPS = 8
# Upper case = body, lower case = highlight.
_PIXEL_COLORS = {"P": DANGER, "p": "#ffb3b3", "N": "#9aa5b1", "n": "#e6edf3"}
_JITTER = (-1, 0, 0, 1)

TIPS = (
    'Try "explain how this project is structured"',
    'Try "/code add a test for the parser"',
    'Try "@README.md what does this project do?"',
    'Try "/init" to write a HELIUM.md for this project',
    'Try "/deep-research compare local and cloud coding agents"',
    'Try "find where the config is loaded"',
)

PERMISSION_MODES = ("ask", "accept-edits")
PERMISSION_LABELS = {
    "ask": "ask before risky tools",
    "accept-edits": "accept edits on",
    "nuclear": "nuclear mode · no confirmations",
}


def nucleus_pixels(frame: int = 0) -> list[str]:
    """Pixel rows for one animation frame; frame 0 is the resting nucleus."""
    grid = [["."] * NUCLEUS_WIDTH for _ in range(NUCLEUS_HEIGHT)]
    rng = random.Random(frame) if frame else None
    nucleons = list(NUCLEONS)
    if rng is not None:
        rng.shuffle(nucleons)  # which nucleon is drawn in front changes too
    for kind, x0, y0 in nucleons:
        dx, dy = (rng.choice(_JITTER), rng.choice(_JITTER)) if rng is not None else (0, 0)
        for sy, row in enumerate(NUCLEON_SHAPE):
            for sx, cell in enumerate(row):
                if cell != ".":
                    grid[y0 + dy + sy][x0 + dx + sx] = kind if cell == "X" else kind.lower()
    return ["".join(row) for row in grid]


def current_frame() -> int:
    """Frame number for the wiggle animation, derived from the clock (never 0)."""
    return int(time.monotonic() * NUCLEUS_FPS) % 100_000 + 1


def _pixel_cells(rows: list[str]) -> list[list[tuple[str, str | None, str | None]]]:
    """Fold pixel rows into terminal cells (char, fg, bg) using half blocks."""
    if len(rows) % 2:
        rows = [*rows, "." * len(rows[0])]
    lines = []
    for top_row, bottom_row in zip(rows[0::2], rows[1::2]):
        cells = []
        for top, bottom in zip(top_row, bottom_row):
            top_color, bottom_color = _PIXEL_COLORS.get(top), _PIXEL_COLORS.get(bottom)
            if top_color and bottom_color:
                cells.append(("▀", top_color, bottom_color))
            elif top_color:
                cells.append(("▀", top_color, None))
            elif bottom_color:
                cells.append(("▄", bottom_color, None))
            else:
                cells.append((" ", None, None))
        lines.append(cells)
    return lines


def logo_lines(frame: int = 0) -> list[Text]:
    """The nucleus as Rich text lines (two pixel rows per line)."""
    lines = []
    for cells in _pixel_cells(nucleus_pixels(frame)):
        line = Text()
        for char, fg, bg in cells:
            style = f"{fg} on {bg}" if fg and bg else (fg or "")
            line.append(char, style=style)
        lines.append(line)
    return lines


def _logo_fragments(frame: int) -> list[list[tuple[str, str]]]:
    """The nucleus as prompt_toolkit fragments, one list per terminal line."""
    lines = []
    for cells in _pixel_cells(nucleus_pixels(frame)):
        fragments = []
        for char, fg, bg in cells:
            style = " ".join(part for part in (f"fg:{fg}" if fg else "", f"bg:{bg}" if bg else "") if part)
            fragments.append((style, char))
        lines.append(fragments)
    return lines


def app_version() -> str:
    try:
        from importlib.metadata import version

        return version("helium-agent")
    except Exception:
        return "dev"


def short_path(path: Path) -> str:
    try:
        return "~/" + str(Path(path).resolve().relative_to(Path.home()))
    except ValueError:
        return str(path)


def endpoint_label(api_url: str | None) -> str:
    from urllib.parse import urlsplit

    from config.providers import provider_for_url

    provider = provider_for_url(api_url)
    if provider is not None:
        return {"deepseek": "DeepSeek", "openrouter": "OpenRouter", "ollama": "Ollama"}.get(provider.name, provider.name)
    host = urlsplit(api_url or "").netloc
    if host.startswith(("localhost", "127.0.0.1")):
        return f"local · {host}"
    return host or "no endpoint configured"


@dataclass(frozen=True)
class HeaderInfo:
    workspace: Path
    model: str
    api_url: str | None
    notes: tuple[str, ...] = ()

    def info_lines(self) -> list[list[tuple[str, str]]]:
        """Right-hand column as (style, text) pairs, shared by Rich and prompt_toolkit."""
        return [
            [("bold", "Helium Agent"), ("dim", f" v{app_version()}")],
            [("", self.model or "no model set"), ("dim", " · "), ("dim", endpoint_label(self.api_url))],
            [("dim", short_path(self.workspace))],
        ]


def _info_row_index(logo_height: int, info_count: int) -> int:
    return max(0, (logo_height - info_count) // 2)


def welcome_header(
    *, workspace: Path, model: str, api_url: str | None, notes: list[str] | None = None, frame: int = 0
) -> RenderableType:
    """Static header for scrollback: nucleus, then name/model/folder, then notes."""
    header = HeaderInfo(workspace, model, api_url, tuple(notes or ()))
    art = logo_lines(frame)
    info = [Text.assemble(*[(text, style) for style, text in line]) for line in header.info_lines()]
    offset = _info_row_index(len(art), len(info))
    grid = Table.grid(padding=(0, 3))
    grid.add_column(no_wrap=True)
    grid.add_column()
    for index, logo_line in enumerate(art):
        info_index = index - offset
        grid.add_row(logo_line, info[info_index] if 0 <= info_index < len(info) else Text(""))

    parts: list[RenderableType] = [Text(""), grid]
    if header.notes:
        parts.append(Text(""))
        for note in header.notes:
            parts.append(Text.assemble(("  ⎿  ", "dim"), (note, "dim")))
    parts.append(Text(""))
    return Group(*parts)


def header_fragments(header: HeaderInfo, frame: int) -> list[tuple[str, str]]:
    """The same header as prompt_toolkit fragments, redrawn each frame to animate."""
    styles = {"bold": "bold", "dim": "#8b949e", "": ""}
    art = _logo_fragments(frame)
    info = header.info_lines()
    offset = _info_row_index(len(art), len(info))
    out: list[tuple[str, str]] = [("", "\n")]
    for index, logo_line in enumerate(art):
        out.extend(logo_line)
        info_index = index - offset
        if 0 <= info_index < len(info):
            out.append(("", "   "))
            out.extend((styles.get(style, style), text) for style, text in info[info_index])
        out.append(("", "\n"))
    if header.notes:
        out.append(("", "\n"))
        for note in header.notes:
            out.append(("#8b949e", f"  ⎿  {note}\n"))
    out.append(("", "\n"))
    return out


def assistant_block(content: str | RenderableType, *, markdown: bool = True, bullet_style: str = ACCENT) -> RenderableType:
    """A reply rendered as `● text`, with wrapped lines aligned under the text."""
    body = Markdown(content) if markdown and isinstance(content, str) else (Text(content) if isinstance(content, str) else content)
    grid = Table.grid(padding=(0, 1))
    grid.add_column(width=1, no_wrap=True)
    grid.add_column(ratio=1)
    grid.add_row(Text("●", style=bullet_style), body)
    return grid


def tool_line(name: str, summary: str) -> Text:
    line = Text("  ⎿  ", style="dim")
    line.append(name, style=f"bold {ACCENT_DARK}")
    if summary:
        line.append(f"  {summary}", style="dim")
    return line


def summarize_tool_counts(tools_used: str | list[str]) -> str:
    """'read_file, read_file, git_status' -> 'read_file ×2, git_status'."""
    names = [t.strip() for t in tools_used.split(",")] if isinstance(tools_used, str) else list(tools_used)
    names = [name for name in names if name and name != "None"]
    if not names:
        return ""
    counts = Counter(names)
    return ", ".join(f"{name} ×{count}" if count > 1 else name for name, count in counts.most_common())


def random_tip() -> str:
    return random.choice(TIPS)


# ── prompt_toolkit chrome ────────────────────────────────────────────────────

PROMPT_STYLE = Style.from_dict(
    {
        "rule": "#30363d",
        "prompt-arrow": f"bold {ACCENT}",
        "placeholder": "#6e7681 italic",
        "bottom-toolbar": "noreverse bg:default #8b949e",
        "bottom-toolbar.text": "noreverse",
        "mode": f"bold {AMBER}",
        "mode-danger": f"bold {DANGER}",
        "mode-edits": f"bold {ACCENT}",
        "hint": "#6e7681",
        "model": "#8b949e",
    }
)


def _columns() -> int:
    try:
        from prompt_toolkit.application import get_app

        return get_app().output.get_size().columns
    except Exception:
        return shutil.get_terminal_size((80, 24)).columns


def _width(fragments: list[tuple[str, str]]) -> int:
    return sum(len(text) for _, text in fragments)


def prompt_message() -> FormattedText:
    return FormattedText([("class:rule", "─" * _columns() + "\n"), ("class:prompt-arrow", "❯ ")])


def make_prompt_message(header: HeaderInfo | None = None) -> Callable[[], FormattedText]:
    """Prompt chrome, optionally with the animated header above it.

    prompt_toolkit redraws the message on every refresh, so the nucleus keeps
    wiggling while the user is typing. Once the input is accepted, the header is
    drawn in its resting frame and stays in the scrollback.
    """
    if header is None:
        return prompt_message

    def message() -> FormattedText:
        try:
            from prompt_toolkit.application import get_app

            done = get_app().is_done
        except Exception:
            done = True
        frame = 0 if done else current_frame()
        return FormattedText([*header_fragments(header, frame), *prompt_message()])

    return message


def make_bottom_toolbar(status: Callable[[], dict[str, str]]) -> Callable[[], FormattedText]:
    """Status bar under the input: permission mode, model, usage, and key hints."""

    def toolbar() -> FormattedText:
        info = status()
        mode = info.get("mode", "ask")
        mode_class = {"nuclear": "class:mode-danger", "accept-edits": "class:mode-edits"}.get(mode, "class:mode")
        columns = _columns()
        status_line = [(mode_class, f" ⏵⏵ {PERMISSION_LABELS.get(mode, mode)}")]
        if mode != "nuclear":
            status_line.append(("class:hint", " (shift+tab to cycle)"))
        # Optional segments, dropped from the end when the terminal is narrow.
        optional: list[list[tuple[str, str]]] = []
        if info.get("model"):
            optional.append([("class:hint", "  ·  "), ("class:model", info["model"])])
        if info.get("tokens"):
            optional.append([("class:hint", f"  ·  {info['tokens']} tokens")])
        optional.append([("class:hint", "  ·  /help")])
        optional.append([("class:hint", "  ·  @ to attach a file")])
        for segment in optional:
            if _width(status_line) + _width(segment) > columns - 1:
                break
            status_line.extend(segment)
        return FormattedText([("class:rule", "─" * columns + "\n"), *status_line])

    return toolbar


__all__ = [
    "PERMISSION_MODES",
    "PROMPT_STYLE",
    "assistant_block",
    "make_bottom_toolbar",
    "HeaderInfo",
    "NUCLEUS_FPS",
    "header_fragments",
    "logo_lines",
    "make_prompt_message",
    "nucleus_pixels",
    "prompt_message",
    "random_tip",
    "summarize_tool_counts",
    "tool_line",
    "welcome_header",
]
