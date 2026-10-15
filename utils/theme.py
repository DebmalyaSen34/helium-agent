"""Colour themes: built-in palettes, user themes from TOML files, and the active theme.

Everything that draws colour asks this module at render time, so switching themes
takes effect immediately:

- Rich output uses named styles (``accent``, ``warning``, ``danger``, ``muted`` …)
  that every console made with `make_console` resolves against the active theme.
- prompt_toolkit chrome uses `prompt_style()` through a DynamicStyle.
- Code and diffs read `current_theme()` and `syntax_theme()` while rendering.

A theme only needs a handful of colours; the rest (diff tints, code block
background, logo colours) are derived from them unless set explicitly.
"""

from __future__ import annotations

import os
import re
import weakref
from dataclasses import dataclass, field, fields, replace
from functools import lru_cache
from pathlib import Path
from typing import Any

from rich.color import Color, ColorParseError
from rich.console import Console
from rich.syntax import PygmentsSyntaxTheme, SyntaxTheme
from rich.theme import Theme as RichTheme

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python < 3.11
    import tomli as tomllib

try:
    from platformdirs import user_config_dir
except ModuleNotFoundError:  # pragma: no cover - optional dependency fallback
    user_config_dir = None

APP_NAME = "helium-agent"
DEFAULT_THEME = "helium"
_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,39}$")

# Colour fields a theme file may set under [colors].
COLOR_FIELDS = (
    "background", "text", "accent", "accent_alt", "success", "warning", "danger",
    "muted", "faint", "subtle",
    # Optional: derived from the colours above when left out.
    "code_bg", "add_bg", "del_bg", "add_word_bg", "del_word_bg", "proton", "neutron",
)
# Token colours a theme may set under [syntax]; each also accepts "bold"/"italic" words.
TOKEN_FIELDS = ("text", "keyword", "string", "comment", "function", "number", "type", "operator", "builtin", "constant", "decorator")


class ThemeError(Exception):
    """A theme file is malformed or a theme name is unknown."""


@dataclass(frozen=True)
class Theme:
    name: str
    description: str
    dark: bool
    background: str
    text: str
    accent: str
    accent_alt: str
    success: str
    warning: str
    danger: str
    muted: str
    faint: str
    subtle: str
    # Pygments style name for code, optionally refined by `tokens`.
    syntax: str | None = None
    tokens: dict[str, str] = field(default_factory=dict)
    code_bg: str | None = None
    add_bg: str | None = None
    del_bg: str | None = None
    add_word_bg: str | None = None
    del_word_bg: str | None = None
    proton: str | None = None
    neutron: str | None = None
    source: Path | None = None  # set for user themes

    # ── derived colours ──

    def _tint(self, color: str, amount: float) -> str:
        return blend(self.background, color, amount)

    @property
    def code_block_bg(self) -> str:
        return self.code_bg or self._tint(self.text, 0.06)

    @property
    def diff_add_bg(self) -> str:
        return self.add_bg or self._tint(self.success, 0.16 if self.dark else 0.14)

    @property
    def diff_del_bg(self) -> str:
        return self.del_bg or self._tint(self.danger, 0.16 if self.dark else 0.12)

    @property
    def diff_add_word_bg(self) -> str:
        return self.add_word_bg or self._tint(self.success, 0.38 if self.dark else 0.32)

    @property
    def diff_del_word_bg(self) -> str:
        return self.del_word_bg or self._tint(self.danger, 0.38 if self.dark else 0.28)

    @property
    def logo_colors(self) -> dict[str, str]:
        """Nucleus pixel colours: upper case is the body, lower case the highlight."""
        proton = self.proton or self.danger
        neutron = self.neutron or self.muted
        lift = "#ffffff" if self.dark else self.background
        return {"P": proton, "p": blend(proton, lift, 0.55), "N": neutron, "n": blend(neutron, lift, 0.7)}


def blend(base: str, color: str, amount: float) -> str:
    """Mix `amount` of `color` into `base` (both #rrggbb)."""
    b, c = Color.parse(base).get_truecolor(), Color.parse(color).get_truecolor()
    mixed = (round(bv + (cv - bv) * amount) for bv, cv in zip(b, c))
    return "#" + "".join(f"{v:02x}" for v in mixed)


# ── built-in themes ───────────────────────────────────────────────

BUILTIN_THEMES: dict[str, Theme] = {
    theme.name: theme
    for theme in (
        Theme(
            "helium", "Helium's own cyan on GitHub dark", True,
            background="#0d1117", text="#e6edf3", accent="#5fd7ff", accent_alt="#2a9fd6",
            success="#3fb950", warning="#e3b341", danger="#ff6b6b",
            muted="#8b949e", faint="#6e7681", subtle="#30363d",
            syntax="github-dark", code_bg="#161b22",
            add_bg="#12261e", del_bg="#2d1619", add_word_bg="#1f5130", del_word_bg="#6b2a2e",
            neutron="#9aa5b1",
        ),
        Theme(
            "dracula", "Dracula: purple, pink and neon on charcoal", True,
            background="#282a36", text="#f8f8f2", accent="#bd93f9", accent_alt="#ff79c6",
            success="#50fa7b", warning="#ffb86c", danger="#ff5555",
            muted="#a4abc9", faint="#6272a4", subtle="#44475a",
            syntax="dracula",
        ),
        Theme(
            "nord", "Nord: arctic, north-bluish calm", True,
            background="#2e3440", text="#eceff4", accent="#88c0d0", accent_alt="#81a1c1",
            success="#a3be8c", warning="#ebcb8b", danger="#bf616a",
            muted="#a3abbc", faint="#616e88", subtle="#434c5e",
            syntax="nord",
        ),
        Theme(
            "gruvbox-dark", "Gruvbox: retro groove, warm and earthy", True,
            background="#282828", text="#ebdbb2", accent="#83a598", accent_alt="#8ec07c",
            success="#b8bb26", warning="#fabd2f", danger="#fb4934",
            muted="#a89984", faint="#928374", subtle="#504945",
            syntax="gruvbox-dark", proton="#fe8019",
        ),
        Theme(
            "tokyo-night", "Tokyo Night: neon city lights after dark", True,
            background="#1a1b26", text="#c0caf5", accent="#7aa2f7", accent_alt="#bb9af7",
            success="#9ece6a", warning="#e0af68", danger="#f7768e",
            muted="#9aa5ce", faint="#565f89", subtle="#292e42",
            tokens={
                "text": "#c0caf5", "keyword": "italic #bb9af7", "string": "#9ece6a", "comment": "italic #565f89",
                "function": "#7aa2f7", "number": "#ff9e64", "type": "#2ac3de", "operator": "#89ddff",
                "builtin": "#e0af68", "constant": "#ff9e64", "decorator": "#7dcfff",
            },
        ),
        Theme(
            "catppuccin-mocha", "Catppuccin Mocha: soothing pastels", True,
            background="#1e1e2e", text="#cdd6f4", accent="#cba6f7", accent_alt="#89b4fa",
            success="#a6e3a1", warning="#fab387", danger="#f38ba8",
            muted="#a6adc8", faint="#6c7086", subtle="#313244",
            tokens={
                "text": "#cdd6f4", "keyword": "#cba6f7", "string": "#a6e3a1", "comment": "italic #6c7086",
                "function": "#89b4fa", "number": "#fab387", "type": "#f9e2af", "operator": "#89dceb",
                "builtin": "#f38ba8", "constant": "#fab387", "decorator": "#f5c2e7",
            },
        ),
        Theme(
            "one-dark", "One Dark: Atom's classic editor theme", True,
            background="#282c34", text="#abb2bf", accent="#61afef", accent_alt="#c678dd",
            success="#98c379", warning="#e5c07b", danger="#e06c75",
            muted="#8b929e", faint="#5c6370", subtle="#3e4451",
            syntax="one-dark",
        ),
        Theme(
            "monokai", "Monokai: the Sublime Text original", True,
            background="#272822", text="#f8f8f2", accent="#66d9ef", accent_alt="#ae81ff",
            success="#a6e22e", warning="#e6db74", danger="#f92672",
            muted="#a59f85", faint="#75715e", subtle="#3e3d32",
            syntax="monokai",
        ),
        Theme(
            "solarized-dark", "Solarized Dark: precision colours for machines and people", True,
            background="#002b36", text="#93a1a1", accent="#268bd2", accent_alt="#2aa198",
            success="#859900", warning="#b58900", danger="#dc322f",
            muted="#839496", faint="#586e75", subtle="#073642",
            syntax="solarized-dark",
        ),
        Theme(
            "solarized-light", "Solarized Light: for light terminal backgrounds", False,
            background="#fdf6e3", text="#586e75", accent="#268bd2", accent_alt="#2aa198",
            success="#859900", warning="#b58900", danger="#dc322f",
            muted="#657b83", faint="#93a1a1", subtle="#eee8d5",
            syntax="solarized-light",
        ),
        Theme(
            "github-light", "GitHub Light: for light terminal backgrounds", False,
            background="#ffffff", text="#1f2328", accent="#0969da", accent_alt="#8250df",
            success="#1a7f37", warning="#9a6700", danger="#cf222e",
            muted="#59636e", faint="#818b98", subtle="#d1d9e0",
            code_bg="#f6f8fa", add_bg="#dafbe1", del_bg="#ffebe9", add_word_bg="#aceebb", del_word_bg="#ffcecb",
            tokens={
                "text": "#1f2328", "keyword": "#cf222e", "string": "#0a3069", "comment": "italic #59636e",
                "function": "#8250df", "number": "#0550ae", "type": "#953800", "operator": "#1f2328",
                "builtin": "#0550ae", "constant": "#0550ae", "decorator": "#8250df",
            },
        ),
    )
}


# ── where things live ─────────────────────────────────────────────


def config_dir() -> Path:
    override = os.getenv("HELIUM_CONFIG_DIR")
    if override:
        return Path(override).expanduser()
    if user_config_dir is None:
        return Path.home() / ".config" / APP_NAME
    return Path(user_config_dir(APP_NAME))


def themes_dir() -> Path:
    return config_dir() / "themes"


def _ui_config_path() -> Path:
    return config_dir() / "ui.toml"


# ── user themes ───────────────────────────────────────────────────


def _check_color(value: Any, where: str) -> str:
    text = str(value).strip()
    try:
        Color.parse(text)
    except ColorParseError:
        raise ThemeError(f"{where}: {text!r} is not a colour (use #rrggbb)") from None
    if not text.startswith("#"):
        # Named colours can't be blended; resolve them to hex.
        text = Color.parse(text).get_truecolor().hex
    return text


def _check_token(value: Any, where: str) -> str:
    words = str(value).split()
    colors = [word for word in words if word not in ("bold", "italic", "underline")]
    if len(colors) > 1:
        raise ThemeError(f"{where}: use one colour plus optional bold/italic/underline")
    return " ".join([*(w for w in words if w not in colors), *(_check_color(c, where) for c in colors)])


def parse_theme(data: dict[str, Any], name: str, *, source: Path | None = None, known: dict[str, Theme] | None = None) -> Theme:
    """Build a Theme from a theme file's contents, layered over its `base` theme."""
    known = known if known is not None else BUILTIN_THEMES
    base_name = str(data.get("base", DEFAULT_THEME))
    base = known.get(base_name)
    if base is None:
        raise ThemeError(f"{name}: unknown base theme {base_name!r}")
    colors = data.get("colors", {})
    syntax = data.get("syntax", {})
    if not isinstance(colors, dict) or not isinstance(syntax, dict):
        raise ThemeError(f"{name}: [colors] and [syntax] must be tables")
    unknown = set(colors) - set(COLOR_FIELDS)
    unknown |= {f"syntax.{key}" for key in set(syntax) - set(TOKEN_FIELDS) - {"style"}}
    if unknown:
        raise ThemeError(f"{name}: unknown setting(s) {', '.join(sorted(unknown))}")

    changes: dict[str, Any] = {key: _check_color(value, f"{name} colors.{key}") for key, value in colors.items()}
    style = syntax.get("style")
    if style is not None:
        _check_syntax_style(str(style), name)
        changes["syntax"] = str(style)
        changes["tokens"] = {}
    tokens = {key: _check_token(value, f"{name} syntax.{key}") for key, value in syntax.items() if key != "style"}
    if tokens:
        changes["tokens"] = {**(changes.get("tokens", base.tokens)), **tokens}
    return replace(
        base,
        name=name,
        description=str(data.get("description", f"Custom theme based on {base.name}")),
        dark=bool(data.get("dark", base.dark)),
        source=source,
        **changes,
    )


def _check_syntax_style(style: str, name: str) -> None:
    from pygments.styles import get_style_by_name
    from pygments.util import ClassNotFound

    try:
        get_style_by_name(style)
    except ClassNotFound:
        raise ThemeError(f"{name}: unknown syntax style {style!r}") from None


def load_user_themes() -> tuple[dict[str, Theme], dict[str, str]]:
    """Themes from the themes folder, plus an error message for each file that failed."""
    themes: dict[str, Theme] = {}
    errors: dict[str, str] = {}
    directory = themes_dir()
    if not directory.is_dir():
        return themes, errors
    known = dict(BUILTIN_THEMES)
    for path in sorted(directory.glob("*.toml")):
        name = path.stem.lower()
        try:
            data = tomllib.loads(path.read_text(encoding="utf-8"))
            if not _NAME_RE.match(name):
                raise ThemeError(f"{name}: file names may only use a-z, 0-9, - and _")
            theme = parse_theme(data, name, source=path, known=known)
        except (OSError, tomllib.TOMLDecodeError, ThemeError) as exc:
            errors[name] = str(exc)
            continue
        themes[name] = theme
        known[name] = theme  # later files may build on earlier ones
    return themes, errors


def available_themes() -> dict[str, Theme]:
    """Built-in themes followed by user themes (a user theme may replace a built-in)."""
    user, _ = load_user_themes()
    return {**BUILTIN_THEMES, **user}


# ── the active theme ──────────────────────────────────────────────

_active: Theme = BUILTIN_THEMES[DEFAULT_THEME]
_consoles: "weakref.WeakSet[Console]" = weakref.WeakSet()


def current_theme() -> Theme:
    return _active


def rich_theme(theme: Theme) -> RichTheme:
    """Named Rich styles for the theme, including overrides for Rich's Markdown defaults."""
    t = theme
    styles = {
        "accent": t.accent,
        "accent.bold": f"bold {t.accent}",
        "accent.alt": t.accent_alt,
        "success": t.success,
        "success.bold": f"bold {t.success}",
        "warning": t.warning,
        "warning.bold": f"bold {t.warning}",
        "danger": t.danger,
        "danger.bold": f"bold {t.danger}",
        "muted": t.muted,
        "faint": t.faint,
        "subtle": t.subtle,
        "title": f"bold {t.text}",
        "status.spinner": t.accent,
        "prompt.choices": f"bold {t.accent}",
        "prompt.default": f"bold {t.muted}",
        "markdown.code": f"{t.accent} on {t.code_block_bg}",
        "markdown.h1": f"bold {t.accent}",
        "markdown.h1.border": t.accent,
        "markdown.h2": f"bold underline {t.text}",
        "markdown.link": t.accent,
        "markdown.link_url": f"underline {t.accent_alt}",
        "markdown.block_quote": f"italic {t.muted}",
        "markdown.item.bullet": f"bold {t.accent}",
        "markdown.item.number": f"bold {t.accent}",
        "markdown.hr": t.subtle,
        "markdown.table.border": t.subtle,
        "rule.line": t.subtle,
    }
    return RichTheme(styles)


def resolve(style: str) -> str:
    """A theme style name ("accent", "danger.bold", …) as a concrete style; other styles pass through.

    Shared renderers use this so they also work on consoles that don't carry the theme.
    """
    found = rich_theme(_active).styles.get(style)
    return str(found) if found is not None else style


def make_console(**kwargs: Any) -> Console:
    """A Console that follows theme switches."""
    console = Console(**kwargs)
    # Exactly one theme is pushed on top of Rich's defaults; switching swaps it.
    console.push_theme(rich_theme(_active))
    _consoles.add(console)
    return console


def apply_theme(theme: Theme) -> None:
    """Make `theme` active for every themed console and renderer (not saved)."""
    global _active
    _active = theme
    styles = rich_theme(theme)
    for console in list(_consoles):
        console.pop_theme()
        console.push_theme(styles)


def find_theme(name: str) -> Theme:
    themes = available_themes()
    key = name.strip().lower()
    if key not in themes:
        raise ThemeError(f"No theme named {name!r}. Available: {', '.join(themes)}")
    return themes[key]


def set_theme(name: str, *, persist: bool = True) -> Theme:
    theme = find_theme(name)
    apply_theme(theme)
    if persist:
        save_theme_choice(theme.name)
    return theme


def save_theme_choice(name: str) -> None:
    path = _ui_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f'theme = "{name}"\n', encoding="utf-8")


def saved_theme_name() -> str | None:
    env = os.getenv("HELIUM_THEME")
    if env:
        return env.strip()
    path = _ui_config_path()
    try:
        return str(tomllib.loads(path.read_text(encoding="utf-8")).get("theme") or "") or None
    except (OSError, tomllib.TOMLDecodeError):
        return None


def load_saved_theme() -> str | None:
    """Apply the saved (or $HELIUM_THEME) theme at startup. Returns a warning if it couldn't be used."""
    name = saved_theme_name()
    if not name:
        return None
    try:
        set_theme(name, persist=False)
    except ThemeError:
        _, errors = load_user_themes()
        reason = errors.get(name.lower())
        return f"Theme {name!r} couldn't be loaded ({reason}); using {DEFAULT_THEME}" if reason else f"Theme {name!r} not found; using {DEFAULT_THEME}"
    return None


# ── syntax highlighting ───────────────────────────────────────────


def syntax_theme(theme: Theme | None = None) -> str | SyntaxTheme:
    """The Rich syntax theme for code: a Pygments style, refined by the theme's token colours."""
    theme = theme or _active
    if theme.syntax and not theme.tokens:
        return theme.syntax
    return _build_syntax_theme(theme.name, theme.syntax, tuple(sorted(theme.tokens.items())), theme.background, theme.text)


@lru_cache(maxsize=32)
def _build_syntax_theme(name: str, base: str | None, tokens: tuple[tuple[str, str], ...], background: str, text: str) -> SyntaxTheme:
    from pygments.style import Style as PygmentsStyle
    from pygments.styles import get_style_by_name
    from pygments.token import Comment, Generic, Keyword, Literal, Name, Number, Operator, String, Token

    groups = {
        "text": [Token, Name, Generic],
        "keyword": [Keyword, Operator.Word, Name.Tag],
        "string": [String, Literal.String],
        "comment": [Comment],
        "function": [Name.Function, Name.Attribute],
        "number": [Number],
        "type": [Keyword.Type, Name.Class, Name.Namespace],
        "operator": [Operator, Generic.Prompt],
        "builtin": [Name.Builtin, Name.Builtin.Pseudo],
        "constant": [Name.Constant, Keyword.Constant],
        "decorator": [Name.Decorator],
    }
    styles: dict[Any, str] = dict(get_style_by_name(base).styles) if base else {Token: text}
    for key, value in tokens:
        for token in groups.get(key, []):
            styles[token] = value
    class_name = "Helium_" + re.sub(r"\W", "_", name)
    style_class = type(class_name, (PygmentsStyle,), {"styles": styles, "background_color": background})
    return PygmentsSyntaxTheme(style_class)


# ── prompt_toolkit ────────────────────────────────────────────────


def prompt_style():
    """prompt_toolkit Style for the prompt rule, toolbar and placeholder."""
    t = _active
    return _prompt_style_for(t.subtle, t.accent, t.warning, t.danger, t.faint, t.muted, t.background)


@lru_cache(maxsize=32)
def _prompt_style_for(subtle, accent, warning, danger, faint, muted, background):
    from prompt_toolkit.styles import Style

    return Style.from_dict(
        {
            "rule": subtle,
            "prompt-arrow": f"bold {accent}",
            "placeholder": f"{faint} italic",
            "bottom-toolbar": f"noreverse bg:default {muted}",
            "bottom-toolbar.text": "noreverse",
            "mode": f"bold {warning}",
            "mode-danger": f"bold {danger}",
            "mode-edits": f"bold {accent}",
            "hint": faint,
            "model": muted,
            "info-dim": muted,
            "completion-menu.completion": f"bg:{subtle} {muted}",
            "completion-menu.completion.current": f"bg:{accent} {background} bold",
        }
    )


# ── creating a theme file ─────────────────────────────────────────


def theme_file_text(name: str, base: Theme) -> str:
    """A ready-to-edit theme file listing every setting with the base theme's values."""
    lines = [
        f"# Helium theme: {name}",
        "# Edit any colour (#rrggbb), save, then run /theme " + name,
        "# Remove a line to inherit it from the base theme.",
        "",
        f'description = "My theme, based on {base.name}"',
        f'base = "{base.name}"',
        f"dark = {'true' if base.dark else 'false'}  # false for light terminal backgrounds",
        "",
        "[colors]",
    ]
    notes = {
        "background": "your terminal's background; tints are mixed from it",
        "accent": "bullets, prompt arrow, links, headings",
        "accent_alt": "tool names",
        "muted": "secondary text",
        "faint": "hints and line numbers",
        "subtle": "borders and rules",
    }
    for key in COLOR_FIELDS[:10]:
        note = f"  # {notes[key]}" if key in notes else ""
        lines.append(f'{key} = "{getattr(base, key)}"{note}')
    lines += [
        "# Optional, derived from the colours above when left out:",
        f'# code_bg = "{base.code_block_bg}"',
        f'# add_bg = "{base.diff_add_bg}"',
        f'# del_bg = "{base.diff_del_bg}"',
        f'# add_word_bg = "{base.diff_add_word_bg}"',
        f'# del_word_bg = "{base.diff_del_word_bg}"',
        f'# proton = "{base.logo_colors["P"]}"',
        f'# neutron = "{base.logo_colors["N"]}"',
        "",
        "[syntax]",
        "# style picks a Pygments style for code (github-dark, dracula, nord, monokai, …);",
        "# token colours below refine it. Each may add bold/italic, e.g. \"italic #6a737d\".",
    ]
    lines.append(f'style = "{base.syntax}"' if base.syntax else '# style = "github-dark"')
    for key in TOKEN_FIELDS:
        if key in base.tokens:
            lines.append(f'{key} = "{base.tokens[key]}"')
        else:
            lines.append(f'# {key} = ""')
    return "\n".join(lines) + "\n"


def create_theme_file(name: str, base_name: str = DEFAULT_THEME) -> Path:
    key = name.strip().lower()
    if not _NAME_RE.match(key):
        raise ThemeError("Theme names may only use a-z, 0-9, - and _ (up to 40 characters).")
    path = themes_dir() / f"{key}.toml"
    if path.exists():
        raise ThemeError(f"{path} already exists. Edit it, or remove it first.")
    base = find_theme(base_name)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(theme_file_text(key, base), encoding="utf-8")
    return path


__all__ = [
    "BUILTIN_THEMES",
    "DEFAULT_THEME",
    "Theme",
    "ThemeError",
    "apply_theme",
    "available_themes",
    "blend",
    "create_theme_file",
    "current_theme",
    "find_theme",
    "load_saved_theme",
    "load_user_themes",
    "make_console",
    "parse_theme",
    "prompt_style",
    "resolve",
    "rich_theme",
    "set_theme",
    "syntax_theme",
    "themes_dir",
]
