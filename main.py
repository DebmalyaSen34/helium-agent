import atexit
import logging
import os
import re
import sys
import argparse
from pathlib import Path
from typing import Any

from rich import box
from rich.console import Group, RenderableType
from rich.logging import RichHandler
from rich.markup import escape
from rich.panel import Panel
from rich.syntax import Syntax
from rich.prompt import Prompt
from rich.table import Table
from rich.text import Text

from config.settings import ASSISTANT_SETTINGS
from core.llm import generate_response
from skills.loader import Skill, discover_skills, match_skill_trigger
from skills.manager import list_skills as format_skill_list, create_skill, remove_skill
from config.runtime_config import (
    RuntimeConfigError,
    import_legacy_runtime_config,
    load_llm_runtime_config,
    parse_legacy_env_file,
    save_llm_runtime_config,
)
from utils.system_check import check_llm_api
from utils.start_animation import render_startup_intro
from tools.file_ops import set_project_root
from tools.registry import research_query, tools_for
from prompt_toolkit import PromptSession
from prompt_toolkit.formatted_text import FormattedText
from prompt_toolkit.filters import has_completions
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.history import FileHistory
from utils.code_render import CodeMarkdown, DiffView, diff_rows, lexer_for, parse_unified_diff
from utils.theme import make_console, syntax_theme
from utils.commands import BUILTIN_COMMANDS, EXIT_COMMANDS, parse_command
from utils.completer import WorkspaceFileCompleter
from utils.stream_render import LiveReply
from utils.tui import (
    NUCLEUS_FPS,
    PROMPT_STYLE,
    HeaderInfo,
    assistant_block,
    make_bottom_toolbar,
    make_prompt_message,
    random_tip,
    summarize_tool_counts,
    theme_preview,
    theme_swatch,
    welcome_header,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    datefmt="[%X]",
    handlers=[
        RichHandler(
            show_time=False,
            show_level=False,
            show_path=False,
            markup=True,
            rich_tracebacks=True,
        )
    ],
)

# Silence verbose third-party loggers
for logger_name in ["urllib3", "httpx", "requests", "filelock"]:
    logging.getLogger(logger_name).setLevel(logging.WARNING)

logger = logging.getLogger("rich")
console = make_console()
_last_state_key: tuple[str, str | None] | None = None
_active_status = None


def app_panel(renderable, *, title: str, border_style: str = "accent") -> Panel:
    return Panel(
        renderable,
        title=f" {title} ",
        border_style=border_style,
        box=box.ROUNDED,
        padding=(0, 1),
    )


def header_info(workspace: Path | None = None, notes: list[str] | None = None) -> HeaderInfo:
    from core.session import get_active_model

    runtime_config = load_llm_runtime_config()
    return HeaderInfo(
        workspace=workspace or Path.cwd(),
        model=get_active_model(),
        api_url=runtime_config.api_url,
        notes=tuple(notes or ()),
    )


def animated_header_supported() -> bool:
    return sys.stdin.isatty() and sys.stdout.isatty()


def print_header(workspace: Path | None = None, notes: list[str] | None = None) -> None:
    """Static header. Interactive sessions show an animated one in the first prompt instead."""
    if ASSISTANT_SETTINGS.get("startup_animation", False):
        render_startup_intro()

    info = header_info(workspace, notes)
    console.print(welcome_header(workspace=info.workspace, model=info.model, api_url=info.api_url, notes=list(info.notes)))


def reset_state() -> None:
    global _last_state_key
    _last_state_key = None


def print_goodbye() -> None:
    from core.session import SESSION

    usage = SESSION.usage
    summary = f"  {usage.total_tokens:,} tokens · {usage.tool_calls} tool calls this session" if usage.requests else ""
    console.print(Text.assemble(("\n● ", "accent"), ("Goodbye.", "bold"), (summary, "dim")))


def set_state(state: str, detail: str | None = None) -> None:
    global _last_state_key
    key = (state, detail)
    if key == _last_state_key:
        return
    _last_state_key = key

    message = f"[warning]✻[/] [bold]{escape(state)}[/bold]"
    if detail:
        message += f" [dim]{escape(detail)}[/dim]"
    console.print(message)


def print_chat_message(speaker: str, message: str, *, style: str, markdown: bool = False) -> None:
    # Callers pass a plain colour word; the active theme decides the actual colour.
    theme_style = {"red": "danger", "green": "success", "yellow": "warning"}.get(style, "accent")
    if speaker == "You":
        text = Text()
        text.append(f"{speaker} ", style=f"{theme_style}.bold")
        text.append("> ", style="dim")
        text.append(message)
        console.print(text)
        return

    body = CodeMarkdown(message) if markdown else Text(message)
    if speaker != "Helium":
        body = Group(Text(speaker, style=f"{theme_style}.bold"), body)
    console.print(assistant_block(body, bullet_style=theme_style))
    console.print()


def print_metrics(metrics: dict[str, Any]) -> None:
    tools = summarize_tool_counts(str(metrics["tools_used"]))
    parts = [
        f"{metrics['total_time']:.1f}s",
        f"{int(metrics['tokens']):,} tokens",
        f"{metrics['tps']:.0f} tok/s",
    ]
    if tools:
        parts.append(tools)
    console.print(Text("  ✻ " + " · ".join(parts), style="dim"))


def extract_web_sources(tool_result: str, limit: int = 5) -> list[dict[str, str]]:
    """Read the `Sources:` section that search_web returns ("- Title: https://...")."""
    sources: list[dict[str, str]] = []
    if "Sources:" not in tool_result:
        return sources
    section = tool_result.split("Sources:", 1)[1]
    for line in section.splitlines():
        line = line.strip()
        if not line.startswith("- "):
            if sources or line.endswith(":"):
                break
            continue
        match = re.match(r"- (?P<title>.*?):\s+(?P<url>https?://\S+)\s*$", line)
        if match:
            sources.append({"title": match.group("title").strip() or match.group("url"), "url": match.group("url")})
        if len(sources) >= limit:
            break
    return sources


def print_sources(sources: list[dict[str, str]]) -> None:
    if not sources:
        return

    text = Text("   sources ", style="dim")
    text.append(f"{len(sources)}", style="accent")
    console.print(text)
    for index, source in enumerate(sources, start=1):
        line = Text(f"   [{index}] ", style="dim")
        line.append(source["title"], style="dim")
        line.append(" - ", style="dim")
        line.append(source["url"], style="accent")
        console.print(line)

def smart_join(current: str, chunk: str) -> str:
    if not current:
        return chunk

    if not chunk:
        return current

    # punctuation attaches directly
    if chunk[0] in ".,!?;:%)]}":
        return current + chunk

    # apostrophe contractions
    if chunk.startswith("'"):
        return current + chunk

    # preserve existing whitespace
    if current[-1].isspace():
        return current + chunk

    if chunk[0].isspace():
        return current + chunk

    # hyphenated continuation
    if current.endswith("-"):
        return current + chunk

    # em dash continuation
    if current.endswith("—"):
        return current + chunk

    # default word spacing
    return current + " " + chunk


def stream_reply(reply_generator) -> str:
    full_reply = ""

    for chunk in reply_generator:
        if not chunk:
            continue

        full_reply = smart_join(full_reply, chunk)

    if full_reply:
        print_chat_message(
            "Helium",
            full_reply.strip(),
            style="cyan",
            markdown=True
        )

    return full_reply


def _format_confirm_args(tool_name: str, args: dict) -> list:
    """Build rich renderables for tool args — syntax-highlighted where possible."""
    renderables = []

    # ── file content tools ─────────────────────────────────────
    if tool_name in ("write_file", "create_file", "append_file") and "content" in args:
        path = args.get("path") or args.get("filename", "file")
        note = "  (append)" if tool_name == "append_file" else ""
        renderables.append(Text(f"path: {path}{note}", style="dim"))
        renderables.append(Syntax(args["content"], lexer_for(path, args["content"]), theme=syntax_theme(),
                                  background_color="default", line_numbers=True, word_wrap=True))

    elif tool_name == "replace_text" and "old" in args and "new" in args:
        path = args.get("path", "file")
        renderables.append(Text(f"path: {path}", style="dim"))
        renderables.append(DiffView(diff_rows(args["old"], args["new"], context=1000), path, line_numbers=False))

    elif tool_name == "edit_file" and isinstance(args.get("edits"), list):
        path = args.get("path", "file")
        renderables.append(Text(f"path: {path}", style="dim"))
        for number, edit in enumerate(args["edits"], 1):
            if not isinstance(edit, dict):
                continue
            label = f"edit {number} of {len(args['edits'])}" + ("  (replace all)" if edit.get("replace_all") else "")
            renderables.append(Text(label, style="dim italic"))
            rows = diff_rows(str(edit.get("old", "")), str(edit.get("new", "")), context=1000)
            renderables.append(DiffView(rows, path, line_numbers=False))

    elif tool_name == "patch_file" and "patch" in args:
        path = args.get("path", "file")
        renderables.append(Text(f"path: {path}", style="dim"))
        renderables.append(DiffView(parse_unified_diff(args["patch"]), path))

    # ── bash ───────────────────────────────────────────────────
    elif tool_name == "execute_bash" and "command" in args:
        renderables.append(Syntax(args["command"], "bash", theme=syntax_theme(), background_color="default", word_wrap=True))

    # ── anything else — clean key: value ───────────────────────
    else:
        for key, val in args.items():
            t = Text()
            t.append(f"{key}: ", style="dim")
            t.append(str(val))
            renderables.append(t)

    return renderables


def _approval_key(tool_name: str, args: dict) -> str:
    """Session "always allow" scope: the exact command for shell tools, else the tool."""
    if tool_name in ("execute_bash", "run_tests"):
        return f"{tool_name}:{args.get('command') or ''}"
    return tool_name


def confirm_tool(tool_name: str, args: dict, permission: str) -> bool:
    if not ASSISTANT_SETTINGS.get("confirm_risky_tools", True):
        return True

    from core.session import SESSION

    approval_key = _approval_key(tool_name, args)
    if approval_key in SESSION.allow_list:
        return True
    if SESSION.permission_mode == "accept-edits":
        from tools.registry import EDIT_TOOLS

        if tool_name in EDIT_TOOLS:
            return True

    global _active_status
    if _active_status is not None:
        _active_status.stop()

    try:
        header = Text()
        header.append("Tool: ", style="dim")
        header.append(tool_name, style="bold")
        header.append("   Permission: ", style="dim")
        header.append(permission, style="warning")
        body = Group(header, *_format_confirm_args(tool_name, args))
        console.print(app_panel(body, title="Confirm Tool", border_style="warning"))
        answer = Prompt.ask("Allow tool? (a = always this session)", choices=["y", "n", "a"], default="n")
    finally:
        if _active_status is not None:
            _active_status.start()

    if answer == "a":
        SESSION.allow_list.add(approval_key)
        return True
    return answer == "y"


def parse_deep_research_command(user_text: str) -> str | None:
    stripped = user_text.strip()
    if stripped == "/deep-research":
        return ""
    if not stripped.startswith("/deep-research "):
        return None
    return stripped[len("/deep-research "):].strip()

def parse_help_command(user_text: str) -> bool:
    return user_text.strip() == "/help"

def build_help_text(discovered_skills: list[Skill] | None = None) -> str:
    skill_lines = ""
    if discovered_skills:
        slash_skills = [s for s in discovered_skills if s.trigger]
        if slash_skills:
            skill_lines = "\n" + "\n".join(
                f"- `{s.trigger}` - {s.description[:60]}" for s in slash_skills
            )

    command_lines = "\n".join(f"- `{command.usage}` - {command.description}" for command in BUILTIN_COMMANDS)

    return f"""# Helium Help

Helium is a coding agent that works in your project. Describe a task in plain words and it explores the code, edits files, runs your tests, and tells you what changed. It also answers everyday questions and does deep research.

## Commands

{command_lines}
- `@path/to/file <question>` - Point Helium at a file; it reads the file to answer.
- `quit`, `exit`, or `stop` - Also end the session (same as `/exit`).
{skill_lines}
## What You Can Ask

- Coding: fix bugs, add features and tests, refactor, explain how the project fits together, and run commands.
- File work: read, create, edit, search, and summarize project files.
- Everyday chat: ask questions, draft text, summarize ideas, or reason through decisions.
- Deep research: request cited reports, comparisons, market/policy analysis, or current-event research.
- Web work: search the web, fetch pages, and synthesize evidence with source URLs.
- Memory: ask Helium to remember preferences or facts; memory persists across sessions.

## Coding

Just say what you want done; no command needed:

```text
fix the failing parser test and run the focused test file
```

Helium reads the relevant files first, makes targeted edits, runs the smallest useful check, and finishes with a short summary of what changed and how it was verified. Follow-ups build on the same conversation.

## Deep Research

Use `/deep-research` when you want the research pipeline explicitly:

```text
/deep-research compare local-first AI agents with cloud coding agents and include sources
```

Helium will plan searches, collect evidence, synthesize findings, and cite sources.

## Tool safety

Read/search tools can run automatically. Risky actions such as destructive file operations, unsafe shell commands, and opening apps ask for confirmation; answer `a` to allow the same tool (or exact shell command) for the rest of the session. Press shift+tab to switch to "accept edits", which approves file edits without asking while shell commands, deletes, and moves stay guarded. Use `/undo` to revert Helium's last file change.

## Examples

```text
Summarize this project.
@README.md explain how to run Helium locally
/deep-research why are local AI agents becoming popular?
add a focused test for /help command parsing
```
"""

class _Rendering:
    """Run a LiveReply and expose it as the active status so confirmations can pause it."""

    def __init__(self, *, stream_text: bool | None = None) -> None:
        self.reply = LiveReply(console, stream_text=stream_text)

    def __enter__(self) -> LiveReply:
        global _active_status
        self.reply.start()
        _active_status = self.reply
        return self.reply

    def __exit__(self, *exc_info) -> None:
        global _active_status
        _active_status = None
        self.reply.finish()


def _remember_command_turn(user_text: str, reply: str) -> None:
    try:
        from core.llm import remember_turn

        remember_turn(user_text, reply)
    except Exception:
        logger.debug("Could not record %s turn", user_text.split()[0], exc_info=True)


def handle_init_command(user_text: str, confirm_tool) -> bool:
    args = parse_command(user_text, "/init")
    if args is None:
        return False

    from core.project_context import INIT_TASK, INIT_UPDATE_TASK, find_project_instructions
    from tools import file_ops

    existing = find_project_instructions(file_ops.PROJECT_ROOT)
    task = INIT_TASK
    if existing is not None:
        choice = Prompt.ask(
            f"{existing.name} already exists. Update it, overwrite it, or cancel?",
            choices=["update", "overwrite", "cancel"],
            default="update",
        )
        if choice == "cancel":
            print_chat_message("Helium", "Cancelled /init.", style="cyan")
            return True
        if choice == "update":
            task = INIT_UPDATE_TASK

    set_state("Init", "writing HELIUM.md")
    run_main_turn(task, confirm_tool=confirm_tool, history_prompt="/init")
    if find_project_instructions(file_ops.PROJECT_ROOT) is not None:
        console.print("[dim]:: HELIUM.md will be included in every prompt. Use /undo to revert it.[/dim]")
    return True

def handle_deep_research_command(user_text: str) -> bool:
    task = parse_deep_research_command(user_text)
    if task is None:
        return False
    if not task:
        print_chat_message("Helium", "Usage: /deep-research <research task>", style="cyan")
        return True

    set_state("Deep Research")
    with _Rendering(stream_text=False) as live:
        live.update("[accent]Planning searches and collecting sources…[/]")
        result = research_query(task, max_sources=8)
    print_chat_message("Helium", result, style="cyan", markdown=True)
    _remember_command_turn(f"/deep-research {task}", result)
    return True

def handle_help_command(user_text: str, discovered_skills: list[Skill] | None = None) -> bool:
    if not parse_help_command(user_text):
        return False

    print_chat_message("Helium", build_help_text(discovered_skills), style="cyan", markdown=True)
    return True


def handle_skill_management_command(user_text: str, workspace: Path, discovered_skills: list[Skill]) -> bool:
    """Handle /skills management commands. Returns True if consumed."""
    stripped = user_text.strip()
    if not stripped.startswith("/skills"):
        return False

    parts = stripped.split(maxsplit=2)
    subcmd = parts[1] if len(parts) > 1 else "list"

    if subcmd == "list":
        format_skill_list(discovered_skills)
        return True

    if subcmd == "create":
        if len(parts) < 3 or not parts[2].strip():
            print_chat_message("Helium", "Usage: /skills create <name>", style="cyan")
            return True
        name = parts[2].strip().lower().replace(" ", "-")
        path = create_skill(name, workspace)
        # Refresh the cached skill list
        discovered_skills.clear()
        discovered_skills.extend(discover_skills(workspace))
        print_chat_message("Helium", f"Created skill [bold]{name}[/bold] at `{path}`\nEdit the SKILL.md to customize it.", style="cyan")
        return True

    if subcmd == "remove":
        if len(parts) < 3 or not parts[2].strip():
            print_chat_message("Helium", "Usage: /skills remove <name>", style="cyan")
            return True
        name = parts[2].strip()
        ok, msg = remove_skill(name, workspace)
        if ok:
            # Refresh the cached skill list
            discovered_skills.clear()
            discovered_skills.extend(discover_skills(workspace))
        style = "green" if ok else "red"
        print_chat_message("Helium", msg, style=style)
        return True

    if subcmd == "help":
        help_text = """# Skills Help

- `/skills` - List all installed skills
- `/skills create <name>` - Create a new skill scaffold
- `/skills remove <name>` - Remove a skill
- `/skills help` - Show this help

Skills are SKILL.md files with YAML frontmatter.
Place them in `~/.config/helium-agent/skills/<name>/SKILL.md` (user) or `.helium/skills/<name>/SKILL.md` (project).
"""
        print_chat_message("Helium", help_text, style="cyan", markdown=True)
        return True

    print_chat_message("Helium", f"Unknown /skills subcommand: [bold]{subcmd}[/bold]. Try `/skills help`.", style="cyan")
    return True


def handle_clear_command(user_text: str) -> bool:
    if parse_command(user_text, "/clear") is None:
        return False
    from core.llm import conversation_history

    conversation_history.clear()
    print_chat_message("Helium", "Conversation cleared. Memories and files are unchanged.", style="cyan")
    return True


def handle_usage_command(user_text: str) -> bool:
    if parse_command(user_text, "/usage") is None:
        return False
    from core.session import SESSION

    usage = SESSION.usage
    table = Table(box=box.SIMPLE, show_header=False)
    table.add_column("Metric", style="dim")
    table.add_column("Value", style="accent", justify="right")
    table.add_row("Requests", str(usage.requests))
    table.add_row("Prompt tokens", f"{usage.prompt_tokens:,}")
    table.add_row("Completion tokens", f"{usage.completion_tokens:,}")
    table.add_row("Total tokens", f"{usage.total_tokens:,}")
    table.add_row("Tool calls", str(usage.tool_calls))
    console.print(app_panel(table, title="Session usage"))
    return True


def _effective_tool_mode(model_name: str, api_url: str | None) -> str:
    from config.settings import LLM_SETTINGS
    from core.model_client import tools_supported

    mode = str(LLM_SETTINGS.get("tool_mode", "auto"))
    if mode != "auto":
        return mode
    return "auto (native)" if tools_supported((str(api_url or ""), model_name)) else "auto (text fallback)"


def handle_model_command(user_text: str) -> bool:
    args = parse_command(user_text, "/model")
    if args is None:
        return False

    from urllib.parse import urlparse

    from config.runtime_config import update_llm_runtime_config
    from core.model_client import reset_tool_support
    from core.session import SESSION, get_active_model

    runtime_config = load_llm_runtime_config()
    parts = args.split()
    save = "--save" in parts
    names = [part for part in parts if part != "--save"]

    if not names:
        model_name = get_active_model()
        host = urlparse(runtime_config.api_url or "").netloc or (runtime_config.api_url or "not set")
        source = "session override" if SESSION.model_override else "saved config"
        message = (
            f"Model: `{model_name}` ({source})\n\n"
            f"Endpoint: `{host}`\n\n"
            f"Tool calling: {_effective_tool_mode(model_name, runtime_config.api_url)}\n\n"
            "Switch with `/model <name>`, add `--save` to keep it for future sessions."
        )
        print_chat_message("Helium", message, style="cyan", markdown=True)
        return True

    new_model = names[0]
    SESSION.model_override = new_model
    reset_tool_support((str(runtime_config.api_url or ""), new_model))
    message = f"Switched to `{new_model}` for this session."
    if save:
        try:
            update_llm_runtime_config(model=new_model)
            message = f"Switched to `{new_model}` and saved it as the default model."
        except RuntimeConfigError as exc:
            message += f" Could not save it: {exc}"
    print_chat_message("Helium", message, style="cyan", markdown=True)
    return True


def handle_undo_command(user_text: str) -> bool:
    if parse_command(user_text, "/undo") is None:
        return False
    from core.llm import remember_turn
    from tools import file_ops
    from tools.edit_journal import JOURNAL

    result = JOURNAL.undo()
    if result is None:
        print_chat_message("Helium", "Nothing to undo. Only file changes made by Helium's file tools can be undone.", style="cyan")
        return True

    def display(path: Path) -> str:
        try:
            return path.relative_to(file_ops.PROJECT_ROOT).as_posix()
        except ValueError:
            return str(path)

    restored = ", ".join(display(path) for path in result.restored) or "nothing"
    message = f"Reverted `{result.label}` (restored: {restored})."
    if result.skipped:
        message += " Skipped files too large to snapshot: " + ", ".join(display(path) for path in result.skipped) + "."
    print_chat_message("Helium", message, style="cyan", markdown=True)
    remember_turn(f"[The user ran /undo] {message}", "Noted. I will treat that change as reverted.", persist=False)
    return True


def handle_notes_command(user_text: str, workspace: Path) -> bool:
    args = parse_command(user_text, "/notes")
    if args is None:
        return False
    from utils.notes import append_note, edit_notes

    if args:
        append_note(workspace, args)
        print_chat_message("Helium", "Added to your notes. Open them with `/notes`.", style="cyan", markdown=True)
        return True

    result = edit_notes(workspace)
    message = {True: "Notes saved.", False: "Discarded your changes to the notes.", None: "Notes unchanged."}[result]
    console.print(Text(f"  {message}", style="dim"))
    return True


def _theme_list() -> RenderableType:
    from utils.theme import BUILTIN_THEMES, current_theme, load_user_themes, themes_dir

    user, errors = load_user_themes()
    active = current_theme().name
    table = Table(box=None, show_header=False, padding=(0, 1))
    table.add_column(width=1)
    table.add_column(style="bold", no_wrap=True)
    table.add_column(no_wrap=True)
    table.add_column(style="muted")
    for theme in {**BUILTIN_THEMES, **user}.values():
        tags = [tag for tag, on in (("light", not theme.dark), ("custom", theme.source is not None)) if on]
        description = theme.description + (f"  ({', '.join(tags)})" if tags else "")
        table.add_row(Text("●", style="accent") if theme.name == active else Text(""), theme.name, theme_swatch(theme), description)
    parts: list[RenderableType] = [table]
    for name, error in errors.items():
        parts.append(Text(f"  ✗ {name}.toml: {error}", style="danger"))
    parts.append(Text(""))
    parts.append(Text.from_markup(
        "  [accent]/theme[/] browse with live previews   ·   [accent]/theme <name>[/] switch and save   ·   [accent]/theme preview <name>[/] try without switching\n"
        "  [accent]/theme create <name> [from <base>][/] start your own   ·   "
        f"your themes live in [muted]{themes_dir()}[/]"
    ))
    return app_panel(Group(*parts), title="Themes")


def _interactive_terminal() -> bool:
    return sys.stdin.isatty() and sys.stdout.isatty()


def handle_theme_command(user_text: str) -> bool:
    args = parse_command(user_text, "/theme")
    if args is None:
        return False
    from utils.theme import ThemeError, apply_theme, create_theme_file, current_theme, find_theme, set_theme

    parts = args.split()
    try:
        if not parts and _interactive_terminal():
            from utils.theme_picker import pick_theme

            before = current_theme().name
            theme = pick_theme()
            if theme is None:
                console.print(Text(f"  Kept {before}.", style="dim"))
            else:
                console.print(Text.assemble(("  Theme set to ", "dim"), (theme.name, "accent.bold"), (" and saved for future sessions.", "dim")))
        elif not parts or parts == ["list"]:
            console.print(_theme_list())
        elif parts[0] == "create":
            if len(parts) not in (2, 4) or (len(parts) == 4 and parts[2] != "from"):
                print_chat_message("Helium", "Usage: `/theme create <name> [from <base>]`", style="cyan", markdown=True)
                return True
            path = create_theme_file(parts[1], parts[3] if len(parts) == 4 else current_theme().name)
            print_chat_message(
                "Helium",
                f"Created `{path}` with every colour filled in. Edit it, save, then run `/theme {path.stem}` "
                "(run it again after each edit to reload).",
                style="cyan",
                markdown=True,
            )
        elif parts[0] == "preview":
            if len(parts) != 2:
                print_chat_message("Helium", "Usage: `/theme preview <name>`", style="cyan", markdown=True)
                return True
            previous, theme = current_theme(), find_theme(parts[1])
            apply_theme(theme)
            try:
                console.print(app_panel(theme_preview(), title=f"Preview: {theme.name}"))
            finally:
                apply_theme(previous)
            console.print(Text(f"  Still using {previous.name}. Run /theme {theme.name} to switch.", style="dim"))
        elif len(parts) == 1:
            theme = set_theme(parts[0])
            console.print(app_panel(theme_preview(), title=f"Theme: {theme.name}"))
            console.print(Text(f"  Switched to {theme.name} and saved it for future sessions.", style="dim"))
        else:
            print_chat_message("Helium", "Usage: `/theme [name | preview <name> | create <name> [from <base>]]`", style="cyan", markdown=True)
    except ThemeError as exc:
        print_chat_message("Error", str(exc), style="red")
    return True


SESSION_COMMAND_HANDLERS = (
    handle_theme_command,
    handle_clear_command,
    handle_usage_command,
    handle_model_command,
    handle_undo_command,
)


def run_main_turn(
    user_text: str,
    confirm_tool,
    *,
    skills: list[Skill] | None = None,
    history_prompt: str | None = None,
) -> None:
    """Run one request through the main agent and render the reply, sources, and metrics."""
    metrics: dict[str, Any] = {}
    sources: list[dict[str, str]] = []

    def collect_tool_result(tool_name: str, tool_result: str) -> None:
        if tool_name == "search_web":
            sources.extend(extract_web_sources(tool_result))

    rendering = _Rendering()
    with rendering as live:
        def set_state_spinner(state: str):
            if state.startswith("Using "):
                live.update(f"[warning]Running {escape(state[6:])}…[/]")
            elif state == "Responding":
                live.update("[success]Responding…[/]")
            else:
                live.update("[accent]Thinking…[/]")

        reply_list = list(
            generate_response(
                user_text,
                confirm_tool=confirm_tool,
                on_state=set_state_spinner,
                on_metrics=metrics.update,
                on_tool_result=collect_tool_result,
                print_metrics=False,
                skills=skills,
                on_event=live.handle_event,
                history_prompt=history_prompt,
            )
        )
    streamed = rendering.reply.finish()

    if not streamed:
        stream_reply(reply_list)
    print_sources(sources)
    if metrics.get("stop_reason") == "max_turns":
        console.print(Text(
            "  Stopped at the tool turn limit, so the task may be incomplete. "
            "Say \"continue\" to pick it up, or raise [agent] max_turns.",
            style="warning",
        ))
    if metrics:
        print_metrics(metrics)


def invoke_skill(skill: Skill, args: str, confirm_tool, workspace: Path) -> None:
    """Run a skill: its body joins the system prompt and the shared agent loop does the rest."""
    set_state(f"Skill: {skill.name}")

    import time
    from core.llm import conversation_history, execute_agent_tool, remember_turn, run_agent
    from core.prompts import build_system_prompt

    system_prompt = build_system_prompt("skill", user_prompt=args, skill=skill)
    user_prompt = args if args else f"Run the /{skill.name} skill."

    def run_tool(action, confirm_tool=None):
        tool_name = str(action.get("tool", "unknown"))
        if skill.allowed_tools and tool_name not in skill.allowed_tools:
            return f"Tool '{tool_name}' is not allowed for this skill. Allowed: {', '.join(skill.allowed_tools)}"
        return execute_agent_tool(action, confirm_tool=confirm_tool)

    start = time.time()
    rendering = _Rendering()
    with rendering as live:
        loop_result = run_agent(
            system_prompt,
            user_prompt,
            history=conversation_history,
            confirm_tool=confirm_tool,
            tool_names=skill.allowed_tools or tools_for("main"),
            execute_tool_call=run_tool,
            on_event=live.handle_event,
        )
    streamed = rendering.reply.finish()
    reply = loop_result.final_answer
    remember_turn(user_prompt, reply, reasoning=loop_result.final_reasoning)

    if reply and not streamed:
        print_chat_message("Helium", reply, style="cyan", markdown=True)

    elapsed = time.time() - start
    token_count = int(loop_result.usage.get("completion_tokens", 0))
    print_metrics(
        {
            "total_time": elapsed,
            "tokens": token_count,
            "tps": token_count / elapsed if elapsed > 0 else 0.0,
            "tools_used": ", ".join(loop_result.tools_used) or "None",
        }
    )


def ensure_llm_runtime_config(force_setup: bool = False) -> bool:
    """Make sure LLM settings exist, running the setup wizard when they don't.

    Complete saved settings are trusted without a test request: that would be a paid
    completion on every launch. A bad key shows up on the first real request instead,
    and `helium --setup` reruns the wizard.
    """
    runtime_config = load_llm_runtime_config()
    if runtime_config.is_complete and not force_setup:
        return True

    legacy_values = parse_legacy_env_file()
    if legacy_values and not runtime_config.is_complete:
        import_choice = Prompt.ask(
            "[success.bold]Import existing ~/.helium.env into secure storage?[/success.bold]",
            choices=["yes", "no"],
            default="yes",
        )
        if import_choice == "yes":
            try:
                imported = import_legacy_runtime_config()
                console.print(
                    "[warning]Imported legacy settings. ~/.helium.env may still contain secrets and was left untouched.[/warning]"
                )
                if imported.is_complete and check_llm_api(imported):
                    return True
            except RuntimeConfigError as exc:
                console.print(f"[danger.bold]{exc}[/danger.bold]")

    console.print(app_panel(
        "[accent.bold]Welcome to Helium Agent![/accent.bold]\n\n"
        "Some required LLM settings are missing or unable to connect.\n"
        "All settings, including the API key, are saved to your user Helium config file\n"
        "with secure owner-only permissions.",
        title="Setup Wizard",
        border_style="accent",
    ))

    from config.providers import PROVIDERS, normalize_chat_url, provider_for_url

    current_provider = provider_for_url(runtime_config.api_url)
    provider_name = Prompt.ask(
        "\n[success.bold]1. LLM provider[/success.bold]",
        choices=[*PROVIDERS, "custom"],
        default=current_provider.name if current_provider else ("custom" if runtime_config.api_url else "openrouter"),
    ).strip()
    provider = PROVIDERS.get(provider_name)
    if provider and provider.note:
        console.print(f"[dim]{provider.note}[/dim]")

    same_provider = provider is not None and provider == current_provider
    entered_key = Prompt.ask(
        f"[success.bold]2. Enter your {provider_name if provider else 'LLM'} API key[/success.bold]",
        default=(runtime_config.api_key or "") if same_provider or provider is None else "",
        password=True,
    ).strip()
    if not entered_key:
        console.print("[warning]Key setup skipped. Agent starting with active environment values.[/warning]\n")
        return False

    default_url = provider.api_url if provider else (runtime_config.api_url or "")
    entered_url = Prompt.ask(
        "[success.bold]3. API URL (a base URL like https://api.example.com/v1 is fine)[/success.bold]",
        default=default_url,
    ).strip()
    entered_url = normalize_chat_url(entered_url) or entered_url
    default_model = (runtime_config.model if same_provider else None) or (provider.default_model if provider else runtime_config.model) or ""
    entered_model = Prompt.ask(
        "[success.bold]4. Default model[/success.bold]",
        default=default_model,
    ).strip()

    try:
        save_llm_runtime_config(
            api_key=entered_key,
            api_url=entered_url,
            model=entered_model,
        )
        console.print("\n[success]LLM API key saved to the user config file.[/success]\n")
        return True
    except RuntimeConfigError as exc:
        console.print(f"[danger.bold]{exc}[/danger.bold]\n")
        return False


def _prompt_key_bindings() -> KeyBindings:
    bindings = KeyBindings()

    @bindings.add("s-tab", filter=~has_completions)
    def _cycle_permission_mode(event) -> None:
        from core.session import SESSION

        if ASSISTANT_SETTINGS.get("confirm_risky_tools", True):
            SESSION.cycle_permission_mode()
        event.app.invalidate()

    return bindings


def main(target_path: str = ".", nuclear: bool = False, setup: bool = False):
    workspace = Path(target_path).resolve()
    os.chdir(workspace)
    set_project_root(workspace)

    if nuclear:
        ASSISTANT_SETTINGS["confirm_risky_tools"] = False
        warning_body = Text("Nuclear mode active. The agent will execute all risky tools without confirmation.", style="danger.bold")
        console.print(app_panel(warning_body, title="WARNING", border_style="danger"))

    from utils.theme import load_saved_theme
    theme_warning = load_saved_theme()

    ensure_llm_runtime_config(force_setup=setup)

    from tools.memory_ops import get_session_summary, initialize_session, legacy_global_db, shutdown_session
    initialize_session(workspace=workspace)
    atexit.register(shutdown_session)
    from tools.edit_journal import JOURNAL
    atexit.register(JOURNAL.clear)
    notes: list[str] = [theme_warning] if theme_warning else []
    notes.append("Picked up where the last session in this folder left off" if get_session_summary() else "New memory for this folder")
    legacy_db = legacy_global_db()
    if legacy_db is not None:
        notes.append(f"Old shared memory at {legacy_db} is no longer used (left untouched)")

    from core.project_context import find_project_instructions
    instructions = find_project_instructions(workspace)
    if instructions is not None:
        notes.append(f"Following {instructions.relative_to(workspace)}")
    else:
        notes.append("Run /init to create a HELIUM.md with instructions for this project")

    # Discover skills from user and project directories
    discovered_skills = discover_skills(workspace)
    if discovered_skills:
        slash_count = sum(1 for s in discovered_skills if s.trigger)
        ctx_count = len(discovered_skills) - slash_count
        parts = []
        if slash_count:
            parts.append(f"{slash_count} slash command{'s' if slash_count != 1 else ''}")
        if ctx_count:
            parts.append(f"{ctx_count} contextual skill{'s' if ctx_count != 1 else ''}")
        notes.append(f"Skills: {' + '.join(parts)}")

    animated_header = header_info(workspace, notes) if animated_header_supported() else None
    if animated_header is None:
        print_header(workspace, notes)
    elif ASSISTANT_SETTINGS.get("startup_animation", False):
        render_startup_intro()

    from config.paths import workspace_data_dir
    from core.session import SESSION, get_active_model

    def status() -> dict[str, str]:
        mode = "nuclear" if not ASSISTANT_SETTINGS.get("confirm_risky_tools", True) else SESSION.permission_mode
        tokens = f"{SESSION.usage.total_tokens:,}" if SESSION.usage.requests else ""
        return {"mode": mode, "model": get_active_model(), "tokens": tokens}

    prompt_session = PromptSession(
        history=FileHistory(str(workspace_data_dir(workspace) / "prompt_history")),
        completer=WorkspaceFileCompleter(skills=discovered_skills),
        complete_while_typing=True,
        bottom_toolbar=make_bottom_toolbar(status),
        style=PROMPT_STYLE,
        key_bindings=_prompt_key_bindings(),
    )

    exit_armed = False
    while True:
        try:
            # The first prompt carries the header so its nucleus can keep wiggling.
            user_text = prompt_session.prompt(
                make_prompt_message(animated_header),
                placeholder=FormattedText([("class:placeholder", random_tip())]),
                refresh_interval=(1 / NUCLEUS_FPS) if animated_header else None,
            ).strip()
        except KeyboardInterrupt:
            animated_header = None
            if exit_armed:
                print_goodbye()
                break
            exit_armed = True
            console.print(Text("  Press Ctrl+C again to exit, or type exit.", style="dim"))
            continue
        except EOFError:
            print_goodbye()
            break
        exit_armed = False
        animated_header = None

        try:
            console.print()
            if not user_text:
                continue
            if user_text.lower() in EXIT_COMMANDS:
                print_goodbye()
                break

            reset_state()
            if handle_skill_management_command(user_text, workspace, discovered_skills):
                continue
            if handle_help_command(user_text, discovered_skills):
                continue
            if handle_notes_command(user_text, workspace):
                continue
            if any(handler(user_text) for handler in SESSION_COMMAND_HANDLERS):
                continue
            if handle_init_command(user_text, confirm_tool=confirm_tool):
                continue
            # Check for skill trigger match
            skill_match = match_skill_trigger(user_text, discovered_skills)
            if skill_match:
                skill, skill_args = skill_match
                invoke_skill(skill, skill_args, confirm_tool, workspace)
                continue
            if handle_deep_research_command(user_text):
                continue
            run_main_turn(user_text, confirm_tool=confirm_tool, skills=discovered_skills)

        except KeyboardInterrupt:
            # Ctrl+C during a turn cancels that turn, not the whole session.
            console.print(Text("\n  ✻ Interrupted. What should Helium do instead?", style="warning"))
        except EOFError:
            print_goodbye()
            break
        except Exception as e:
            set_state("Error")
            message = str(e)
            if getattr(e, "status_code", None) in (401, 403):
                message += "\n\nThe API key was rejected. Run `helium --setup` to update your LLM settings."
            print_chat_message("Error", message, style="red")


def cli_entrypoint():
    parser = argparse.ArgumentParser(description="Helium Agent")
    parser.add_argument("path", type=str, nargs="?", default=".", help="Target workspace path")
    parser.add_argument("--nuclear", action="store_true", help="Bypass all risky tool confirmations (run without asking permission)")
    parser.add_argument("--setup", action="store_true", help="Rerun the LLM setup wizard (provider, API key, URL, model)")
    headless = parser.add_argument_group("non-interactive mode")
    headless.add_argument("-p", "--print", dest="task", metavar="TASK", help="Run one task without the interactive UI, print the result, and exit")
    headless.add_argument("--json", action="store_true", help="With -p: print a JSON object with the result, stop reason, and usage")
    headless.add_argument("--accept-edits", action="store_true", help="With -p: allow file edits (other risky tools are denied)")
    headless.add_argument("--yes", action="store_true", help="With -p: allow every tool, including shell commands and deletes")
    headless.add_argument("--max-turns", type=int, help="With -p: tool turn limit for this run")
    headless.add_argument("--model", help="With -p: model to use for this run")
    headless.add_argument("--transcript", type=Path, metavar="FILE", help="With -p: write the full message transcript as JSON")
    headless.add_argument("--verbose", action="store_true", help="With -p: print each tool call to stderr")
    args = parser.parse_args()

    if args.task is not None:
        from core.headless import headless_main

        permission_mode = "all" if (args.yes or args.nuclear) else "accept-edits" if args.accept_edits else "deny"
        sys.exit(headless_main(
            Path(args.path),
            args.task,
            permission_mode=permission_mode,
            output_json=args.json,
            max_turns=args.max_turns,
            model_name=args.model,
            transcript_path=args.transcript,
            verbose=args.verbose,
        ))

    main(target_path=args.path, nuclear=args.nuclear, setup=args.setup)


if __name__ == "__main__":
    cli_entrypoint()
