from pathlib import Path

from prompt_toolkit.formatted_text import fragment_list_to_text
from rich.console import Console

from core.session import SessionState
from utils.tui import (
    MASCOT,
    make_bottom_toolbar,
    mascot_lines,
    summarize_tool_counts,
    welcome_header,
)


def test_mascot_uses_two_pixel_rows_per_line():
    lines = mascot_lines()
    assert len(lines) == (len(MASCOT) + 1) // 2
    assert all(len(line.plain) == len(MASCOT[0]) for line in lines)


def test_welcome_header_shows_model_provider_and_folder():
    console = Console(record=True, width=100)
    console.print(
        welcome_header(
            workspace=Path.home() / "proj",
            model="deepseek-flash",
            api_url="https://api.deepseek.com/chat/completions",
            notes=["Following HELIUM.md"],
        )
    )
    text = console.export_text()
    assert "Helium Agent" in text
    assert "deepseek-flash · DeepSeek" in text
    assert "~/proj" in text
    assert "Following HELIUM.md" in text


def test_tool_counts_are_compressed():
    assert summarize_tool_counts("read_file, read_file, git_status, read_file") == "read_file ×3, git_status"
    assert summarize_tool_counts("None") == ""


def test_toolbar_shows_mode_and_drops_hints_when_narrow(monkeypatch):
    import utils.tui as tui

    toolbar = make_bottom_toolbar(lambda: {"mode": "accept-edits", "model": "deepseek-flash", "tokens": "1,234"})
    monkeypatch.setattr(tui, "_columns", lambda: 200)
    wide = fragment_list_to_text(toolbar())
    assert "accept edits on" in wide and "1,234 tokens" in wide and "@ to attach a file" in wide

    monkeypatch.setattr(tui, "_columns", lambda: 60)
    narrow = fragment_list_to_text(toolbar()).splitlines()[-1]
    assert len(narrow) < 60
    assert "accept edits on" in narrow


def test_permission_mode_cycles():
    state = SessionState()
    assert state.permission_mode == "ask"
    assert state.cycle_permission_mode() == "accept-edits"
    assert state.cycle_permission_mode() == "ask"


def test_accept_edits_mode_auto_approves_file_edits_only(monkeypatch):
    import main
    from config.settings import ASSISTANT_SETTINGS
    from core.session import SESSION

    monkeypatch.setitem(ASSISTANT_SETTINGS, "confirm_risky_tools", True)
    monkeypatch.setattr(SESSION, "permission_mode", "accept-edits")
    monkeypatch.setattr(main.Prompt, "ask", lambda *a, **k: "n")
    monkeypatch.setattr(main.console, "print", lambda *a, **k: None)

    assert main.confirm_tool("edit_file", {"path": "a.py"}, "risky") is True
    assert main.confirm_tool("execute_bash", {"command": "rm -rf build"}, "risky") is False
    assert main.confirm_tool("delete_file", {"path": "a.py"}, "risky") is False
