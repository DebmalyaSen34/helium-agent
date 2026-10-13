"""Terminal look and feel: welcome header, atom logo, prompt chrome, and status bar."""

from __future__ import annotations

import random
import shutil
from collections import Counter
from collections.abc import Callable
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

# Pixel art for the logo: a helium atom. A nucleus of protons (P) and neutrons
# (N) inside one orbital (O) carrying helium's two electrons (E).
ATOM = [
    "......OOOOOO..EE..",
    "...OOO......OOEE..",
    ".OO............OO.",
    "OO......PN......OO",
    "OO.....NPNP.....OO",
    "OO.....PNPN.....OO",
    "OO......NP......OO",
    ".OO............OO.",
    "..EEOO......OOO...",
    "..EE..OOOOOO......",
]
_PIXEL_COLORS = {"O": "#3b6e8f", "P": DANGER, "N": "#c9d1d9", "E": ACCENT}

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


def logo_lines() -> list[Text]:
    """Render ATOM with half-block characters: two pixel rows per text line."""
    width = max(len(row) for row in ATOM)
    rows = [row.ljust(width, ".") for row in ATOM]
    if len(rows) % 2:
        rows.append("." * len(rows[0]))
    lines: list[Text] = []
    for top_row, bottom_row in zip(rows[0::2], rows[1::2]):
        line = Text()
        for top, bottom in zip(top_row, bottom_row):
            top_color = _PIXEL_COLORS.get(top)
            bottom_color = _PIXEL_COLORS.get(bottom)
            if top_color and bottom_color:
                line.append("▀", style=f"{top_color} on {bottom_color}")
            elif top_color:
                line.append("▀", style=top_color)
            elif bottom_color:
                line.append("▄", style=bottom_color)
            else:
                line.append(" ")
        lines.append(line)
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


def welcome_header(*, workspace: Path, model: str, api_url: str | None, notes: list[str] | None = None) -> RenderableType:
    """Atom logo on the left; name, model, and folder on the right; notes underneath."""
    info = [
        Text.assemble(("Helium Agent", "bold"), (f" v{app_version()}", "dim")),
        Text.assemble((model or "no model set", ""), (" · ", "dim"), (endpoint_label(api_url), "dim")),
        Text(short_path(workspace), style="dim"),
    ]
    art = logo_lines()
    grid = Table.grid(padding=(0, 3))
    grid.add_column(no_wrap=True)
    grid.add_column()
    for index in range(max(len(art), len(info))):
        grid.add_row(
            art[index] if index < len(art) else Text(""),
            info[index] if index < len(info) else Text(""),
        )

    parts: list[RenderableType] = [Text(""), grid]
    if notes:
        parts.append(Text(""))
        for note in notes:
            parts.append(Text.assemble(("  ⎿  ", "dim"), (note, "dim")))
    parts.append(Text(""))
    return Group(*parts)


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
    "logo_lines",
    "prompt_message",
    "random_tip",
    "summarize_tool_counts",
    "tool_line",
    "welcome_header",
]
