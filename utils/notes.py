"""Scratch notes: a per-workspace notes file and a full-screen editor for it."""

from __future__ import annotations

import time
from pathlib import Path

from prompt_toolkit.application import Application
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import HSplit, Layout, Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.styles import Style
from prompt_toolkit.widgets import Frame, TextArea

from config.paths import workspace_data_dir
from utils.tui import ACCENT, AMBER

NOTES_FILENAME = "notes.md"

NOTES_STYLE = Style.from_dict(
    {
        "frame.border": ACCENT,
        "frame.label": f"bold {ACCENT}",
        "hint": "#6e7681",
        "hint.key": f"bold {AMBER}",
    }
)


def notes_path(workspace: Path) -> Path:
    return workspace_data_dir(workspace) / NOTES_FILENAME


def read_notes(workspace: Path) -> str:
    path = notes_path(workspace)
    return path.read_text(encoding="utf-8") if path.exists() else ""


def write_notes(workspace: Path, text: str) -> Path:
    path = notes_path(workspace)
    path.write_text(text.rstrip() + "\n" if text.strip() else "", encoding="utf-8")
    return path


def append_note(workspace: Path, note: str) -> Path:
    """Add one timestamped line to the end of the notes."""
    existing = read_notes(workspace).rstrip()
    line = f"- {time.strftime('%Y-%m-%d %H:%M')} {note.strip()}"
    return write_notes(workspace, f"{existing}\n{line}" if existing else line)


def edit_notes(workspace: Path) -> bool | None:
    """Open the notes in a full-screen editor. True if saved, False if discarded, None if unchanged."""
    original = read_notes(workspace)
    editor = TextArea(text=original, multiline=True, scrollbar=True, line_numbers=True, focus_on_click=True)
    editor.buffer.cursor_position = len(original)

    hint = FormattedTextControl(
        [
            ("class:hint.key", " Ctrl+S"), ("class:hint", " save & close   "),
            ("class:hint.key", "Esc"), ("class:hint", " save & close   "),
            ("class:hint.key", "Ctrl+C"), ("class:hint", " discard changes"),
        ]
    )
    bindings = KeyBindings()

    @bindings.add("c-s")
    @bindings.add("escape", eager=True)
    def _save(event) -> None:
        event.app.exit(result=True)

    @bindings.add("c-c")
    def _discard(event) -> None:
        event.app.exit(result=False)

    app: Application[bool] = Application(
        layout=Layout(HSplit([Frame(editor, title="Notes"), Window(hint, height=1)]), focused_element=editor),
        key_bindings=bindings,
        style=NOTES_STYLE,
        full_screen=True,
        mouse_support=True,
    )
    save = app.run()
    if not save:
        return False
    if editor.text == original:
        return None
    write_notes(workspace, editor.text)
    return True


__all__ = ["append_note", "edit_notes", "notes_path", "read_notes", "write_notes"]
