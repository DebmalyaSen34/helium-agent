"""Interactive theme picker: browse themes with the arrow keys and see each one live."""

from __future__ import annotations

import io
import shutil

from prompt_toolkit.application import Application
from prompt_toolkit.formatted_text import ANSI, FormattedText, to_formatted_text
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import HSplit, Layout, VSplit, Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.layout.dimension import Dimension
from prompt_toolkit.styles import DynamicStyle, Style
from rich.console import Console, Group
from rich.text import Text

from utils.theme import Theme, apply_theme, available_themes, current_theme, load_user_themes, rich_theme, set_theme

LIST_WIDTH = 34
PREVIEW_HEIGHT = 24


def render_preview(theme: Theme, width: int) -> FormattedText:
    """The sample reply/diff/code in `theme`, as prompt_toolkit fragments on the theme's background."""
    from utils.tui import theme_preview

    previous = current_theme()
    apply_theme(theme)
    try:
        console = Console(file=io.StringIO(), width=max(30, width), force_terminal=True, color_system="truecolor", legacy_windows=False)
        console.push_theme(rich_theme(theme))
        heading = Text.assemble((theme.name, f"bold {theme.accent}"), ("  ", ""), (theme.description, theme.muted))
        if not theme.dark:
            heading.append("  · light", style=theme.faint)
        if theme.source is not None:
            heading.append("  · custom", style=theme.faint)
        with console.capture() as capture:
            console.print(Group(heading, Text(""), theme_preview()))
        ansi = capture.get()
    finally:
        apply_theme(previous)
    # Rich marks unstyled cells "default background"; drop that so the pane's background shows through.
    return FormattedText([(style.replace("bg:ansidefault", ""), text) for style, text in to_formatted_text(ANSI(ansi))])


def _picker_style(theme: Theme) -> Style:
    return Style.from_dict(
        {
            "picker": f"bg:{theme.background} {theme.text}",
            "picker.title": f"bold {theme.accent}",
            "picker.item": theme.text,
            "picker.selected": f"bold {theme.background} bg:{theme.accent}",
            "picker.active": theme.accent,
            "picker.tag": theme.faint,
            "picker.hint": theme.faint,
            "picker.key": f"bold {theme.warning}",
            "picker.error": theme.danger,
            "picker.rule": theme.subtle,
        }
    )


def pick_theme() -> Theme | None:
    """Run the picker. Returns the chosen theme (already applied and saved), or None if cancelled."""
    themes = list(available_themes().values())
    _, errors = load_user_themes()
    original = current_theme()
    names = [theme.name for theme in themes]
    state = {"index": names.index(original.name) if original.name in names else 0}
    cache: dict[tuple[str, int], FormattedText] = {}

    def selected() -> Theme:
        return themes[state["index"]]

    def preview_width() -> int:
        try:
            from prompt_toolkit.application import get_app

            columns = get_app().output.get_size().columns
        except Exception:
            columns = shutil.get_terminal_size((100, 24)).columns
        return columns - LIST_WIDTH - 3

    def list_fragments() -> FormattedText:
        out: list[tuple[str, str]] = [("class:picker.title", " Themes\n"), ("", "\n")]
        for index, theme in enumerate(themes):
            is_selected = index == state["index"]
            marker = "❯ " if is_selected else "  "
            style = "class:picker.selected" if is_selected else "class:picker.item"
            out.append((style, f" {marker}{theme.name:<18}"))
            for color in (theme.accent, theme.accent_alt, theme.success, theme.warning, theme.danger):
                out.append((color, "█"))
            if theme.name == original.name:
                out.append(("class:picker.active", " ●"))
            out.append(("", "\n"))
        if errors:
            out.append(("", "\n"))
            for name in errors:
                out.append(("class:picker.error", f"  ✗ {name}.toml has errors\n"))
        return FormattedText(out)

    def preview_fragments() -> FormattedText:
        key = (selected().name, preview_width())
        if key not in cache:
            cache[key] = render_preview(selected(), key[1] - 2)
        return cache[key]

    hints = FormattedText(
        [
            ("class:picker.key", " ↑↓"), ("class:picker.hint", " browse   "),
            ("class:picker.key", "enter"), ("class:picker.hint", " use this theme   "),
            ("class:picker.key", "esc"), ("class:picker.hint", " keep "), ("class:picker.active", original.name),
            ("class:picker.hint", "   ·   /theme create <name> to make your own"),
        ]
    )

    bindings = KeyBindings()

    def move(step: int) -> None:
        state["index"] = (state["index"] + step) % len(themes)
        apply_theme(selected())  # the picker's own colours follow too

    @bindings.add("up")
    @bindings.add("k")
    def _up(event) -> None:
        move(-1)

    @bindings.add("down")
    @bindings.add("j")
    @bindings.add("tab")
    def _down(event) -> None:
        move(1)

    @bindings.add("enter")
    def _choose(event) -> None:
        event.app.exit(result=selected())

    @bindings.add("escape", eager=True)
    @bindings.add("q")
    @bindings.add("c-c")
    def _cancel(event) -> None:
        event.app.exit(result=None)

    body = VSplit(
        [
            Window(FormattedTextControl(list_fragments), width=LIST_WIDTH, style="class:picker"),
            Window(width=1, char="│", style="class:picker class:picker.rule"),
            Window(FormattedTextControl(preview_fragments), wrap_lines=False, left_margins=[], style="class:picker"),
        ],
        height=Dimension(preferred=max(PREVIEW_HEIGHT, len(themes) + 4)),
    )
    app: Application[Theme | None] = Application(
        layout=Layout(HSplit([body, Window(FormattedTextControl(hints), height=1, style="class:picker")])),
        key_bindings=bindings,
        style=DynamicStyle(lambda: _picker_style(selected())),
        full_screen=False,
        erase_when_done=True,
    )

    apply_theme(selected())
    choice = None
    try:
        choice = app.run()
    finally:
        if choice is None:
            apply_theme(original)
    if choice is None:
        return None
    return set_theme(choice.name)


__all__ = ["pick_theme", "render_preview"]
