from unittest.mock import patch

import pytest
from prompt_toolkit.document import Document
from rich.console import Console

import main
from utils.code_render import DiffView, diff_rows
from utils.completer import WorkspaceFileCompleter
from utils.theme import (
    BUILTIN_THEMES,
    COLOR_FIELDS,
    ThemeError,
    available_themes,
    create_theme_file,
    current_theme,
    load_saved_theme,
    load_user_themes,
    make_console,
    parse_theme,
    set_theme,
    syntax_theme,
    themes_dir,
)
from utils.tui import theme_preview


def ansi(renderable, console=None) -> str:
    console = console or Console(width=80, force_terminal=True, color_system="truecolor")
    with console.capture() as capture:
        console.print(renderable)
    return capture.get()


def rgb(hex_color: str) -> str:
    return ";".join(str(int(hex_color[i:i + 2], 16)) for i in (1, 3, 5))


def test_famous_themes_are_built_in():
    for name in ("dracula", "nord", "gruvbox-dark", "tokyo-night", "catppuccin-mocha", "one-dark", "monokai", "solarized-dark", "solarized-light", "github-light"):
        assert name in BUILTIN_THEMES


@pytest.mark.parametrize("name", list(BUILTIN_THEMES))
def test_every_builtin_theme_renders(name):
    set_theme(name, persist=False)
    out = ansi(theme_preview())
    assert "total" in out
    assert rgb(BUILTIN_THEMES[name].accent_alt) in out  # tool names use the theme colour


def test_switching_restyles_existing_consoles():
    console = make_console(width=40, force_terminal=True, color_system="truecolor")
    set_theme("dracula", persist=False)
    assert rgb(BUILTIN_THEMES["dracula"].accent) in ansi("[accent]hi[/]", console)
    set_theme("nord", persist=False)
    assert rgb(BUILTIN_THEMES["nord"].accent) in ansi("[accent]hi[/]", console)


def test_diffs_follow_the_theme():
    set_theme("github-light", persist=False)
    out = ansi(DiffView(diff_rows("a = 1\n", "a = 2\n"), "x.py"))
    assert rgb(BUILTIN_THEMES["github-light"].add_bg) in out


def test_token_colours_build_a_syntax_theme():
    theme = syntax_theme(BUILTIN_THEMES["tokyo-night"])
    assert not isinstance(theme, str)
    assert syntax_theme(BUILTIN_THEMES["dracula"]) == "dracula"


def test_choice_is_saved_and_restored():
    set_theme("nord")
    set_theme("helium", persist=False)
    assert load_saved_theme() is None
    assert current_theme().name == "nord"


def test_env_var_overrides_saved_theme(monkeypatch):
    set_theme("nord")
    monkeypatch.setenv("HELIUM_THEME", "monokai")
    load_saved_theme()
    assert current_theme().name == "monokai"


def test_unknown_saved_theme_falls_back_with_a_warning(monkeypatch):
    monkeypatch.setenv("HELIUM_THEME", "nope")
    assert "not found" in load_saved_theme()
    assert current_theme().name == "helium"


# ── user themes ───────────────────────────────────────────────────

def test_created_theme_file_loads_and_matches_its_base():
    path = create_theme_file("mine", "dracula")
    assert path.parent == themes_dir()
    themes, errors = load_user_themes()
    assert errors == {}
    mine = themes["mine"]
    for key in COLOR_FIELDS[:10]:
        assert getattr(mine, key) == getattr(BUILTIN_THEMES["dracula"], key)
    assert mine.source == path


def test_partial_theme_inherits_from_base():
    theme = parse_theme({"base": "nord", "colors": {"accent": "#ff00ff"}, "syntax": {"keyword": "bold #00ff00"}}, "pink")
    assert theme.accent == "#ff00ff"
    assert theme.success == BUILTIN_THEMES["nord"].success
    assert theme.syntax == "nord" and theme.tokens == {"keyword": "bold #00ff00"}


def test_bad_theme_files_are_reported_not_fatal():
    themes_dir().mkdir(parents=True)
    (themes_dir() / "broken.toml").write_text('[colors]\naccent = "not-a-colour"\n')
    (themes_dir() / "typo.toml").write_text('[colors]\naccnet = "#ffffff"\n')
    (themes_dir() / "good.toml").write_text('base = "monokai"\n[colors]\naccent = "#123456"\n')
    themes, errors = load_user_themes()
    assert set(errors) == {"broken", "typo"}
    assert "accnet" in errors["typo"]
    assert themes["good"].accent == "#123456"
    assert "good" in available_themes()


def test_create_rejects_bad_names_and_overwrites():
    with pytest.raises(ThemeError):
        create_theme_file("../evil")
    create_theme_file("twice")
    with pytest.raises(ThemeError):
        create_theme_file("twice")


# ── /theme command ────────────────────────────────────────────────

@patch("main.console")
def test_theme_command_switches_and_saves(mock_console):
    assert main.handle_theme_command("/theme dracula")
    assert current_theme().name == "dracula"
    assert main.handle_theme_command("/theme")
    assert not main.handle_theme_command("/themes")


@patch("main.console")
def test_theme_preview_does_not_switch(mock_console):
    set_theme("nord", persist=False)
    main.handle_theme_command("/theme preview monokai")
    assert current_theme().name == "nord"


@patch("main.print_chat_message")
def test_theme_command_reports_errors(mock_print):
    main.handle_theme_command("/theme nope")
    assert "No theme named" in mock_print.call_args.args[1]
    main.handle_theme_command("/theme create mytheme from dracula")
    assert (themes_dir() / "mytheme.toml").exists()


def test_theme_names_complete():
    completer = WorkspaceFileCompleter()
    names = [c.text for c in completer.get_completions(Document("/theme dr"), None)]
    assert names == ["dracula"]
    names = [c.text for c in completer.get_completions(Document("/theme preview to"), None)]
    assert names == ["tokyo-night"]


# ── interactive picker ────────────────────────────────────────────

def _run_picker(keys: str):
    from prompt_toolkit.application.current import create_app_session
    from prompt_toolkit.input import create_pipe_input
    from prompt_toolkit.output import DummyOutput

    from utils.theme_picker import pick_theme

    with create_pipe_input() as pipe:
        pipe.send_text(keys)
        with create_app_session(input=pipe, output=DummyOutput()):
            return pick_theme()


def test_picker_enter_applies_and_saves_the_highlighted_theme():
    from utils.theme import saved_theme_name

    names = list(available_themes())
    chosen = _run_picker("\x1b[B\x1b[B\r")
    assert chosen.name == names[2]
    assert current_theme().name == names[2]
    assert saved_theme_name() == names[2]


def test_picker_escape_restores_the_original_theme():
    set_theme("nord", persist=False)
    assert _run_picker("\x1b[B\x1b[B\x1b") is None
    assert current_theme().name == "nord"


def test_picker_wraps_around_and_lists_user_themes():
    create_theme_file("zz-mine", "dracula")
    assert _run_picker("k\r").name == "zz-mine"  # up from the first theme wraps to the last


def test_picker_preview_paints_the_theme_background():
    from utils.theme_picker import render_preview

    fragments = render_preview(BUILTIN_THEMES["github-light"], 70)
    text = "".join(t for _, t in fragments)
    assert "github-light" in text and "total" in text
    assert not any("ansidefault" in style for style, _ in fragments)


@patch("main._interactive_terminal", return_value=True)
@patch("main.console")
def test_theme_command_opens_picker_in_a_terminal(mock_console, _tty):
    with patch("utils.theme_picker.pick_theme", return_value=None) as picker:
        assert main.handle_theme_command("/theme")
    picker.assert_called_once()
    assert "Kept" in str(mock_console.print.call_args.args[0])
