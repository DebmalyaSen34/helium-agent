import atexit
import logging
import os
import re
import select
import sys
import argparse
from pathlib import Path
from typing import Any

try:
    import openwakeword
    import speech_recognition as sr
    from kokoro import KPipeline
    from openwakeword.model import Model
    HAS_VOICE_DEP = True
except ImportError:
    HAS_VOICE_DEP = False
    openwakeword = None
    class DummySpeechRecognition:
        class Recognizer:
            pass
        class WaitTimeoutError(Exception):
            pass
        class UnknownValueError(Exception):
            pass
    sr = DummySpeechRecognition
    KPipeline = None
    Model = None
from rich import box
from rich.console import Console, Group
from rich.logging import RichHandler
from rich.markdown import Markdown
from rich.markup import escape
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table
from rich.text import Text

from config.settings import ASSISTANT_SETTINGS, SPEECH_SETTINGS, WAKE_WORD_SETTINGS
from core.llm import generate_response
from core.coding_workflow import run_coding_workflow
from tools.research.pipeline import research_query
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
try:
    from engine.stt import build_speech_config, speech_to_text
    from engine.tts import text_to_speech
    from engine.wake_word import build_wake_config, calibrate_microphone, wake_word_detection
    HAS_VOICE_ENGINES = True
except ImportError:
    HAS_VOICE_ENGINES = False
    build_speech_config = None
    speech_to_text = None
    text_to_speech = None
    build_wake_config = None
    calibrate_microphone = None
    wake_word_detection = None
from rag_service.client import RagServiceClient
from rag_service.config import load_config as load_rag_service_config
from rag_service.models import RagError
from rag_service.terminal import resolve_single_mention
from utils.start_animation import render_startup_intro
from utils.audio import play_status_sound
from utils.health import run_startup_health_checks
from utils.history import last_heard, record_command
from tools.file_ops import set_project_root
from prompt_toolkit import PromptSession, HTML
from prompt_toolkit.history import FileHistory
from utils.completer import WorkspaceFileCompleter

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
for logger_name in ["urllib3", "httpx", "requests", "playwright", "filelock"]:
    logging.getLogger(logger_name).setLevel(logging.WARNING)

logger = logging.getLogger("rich")
console = Console()
_last_state_key: tuple[str, str | None] | None = None
_active_status = None


def app_panel(renderable, *, title: str, border_style: str = "cyan") -> Panel:
    return Panel(
        renderable,
        title=f" {title} ",
        border_style=border_style,
        box=box.ROUNDED,
        padding=(0, 1),
    )


def print_header(mode: str) -> None:
    console.print()
    render_startup_intro()
    console.rule(
        f"[bold cyan]HELIUM AGENT[/bold cyan] [dim]{mode} mode / local assistant[/dim]",
        style="bright_black",
    )


def reset_state() -> None:
    global _last_state_key
    _last_state_key = None


def print_goodbye() -> None:
    console.print(app_panel(Text("Goodbye.", style="bold yellow"), title="Session", border_style="yellow"))


def set_state(state: str, detail: str | None = None) -> None:
    global _last_state_key
    key = (state, detail)
    if key == _last_state_key:
        return
    _last_state_key = key

    message = f"[dim]::[/dim] [cyan]{escape(state)}[/cyan]"
    if detail:
        message += f" [dim]{escape(detail)}[/dim]"
    console.print(message)


def print_chat_message(speaker: str, message: str, *, style: str, markdown: bool = False) -> None:
    if speaker in {"You", "Heard"}:
        text = Text()
        text.append(f"{speaker} ", style=f"bold {style}")
        text.append("> ", style="dim")
        text.append(message)
        console.print(text)
        return

    content = Markdown(message) if markdown else Text(message)
    label = Text(speaker, style=f"bold {style}")
    panel = Panel(content, border_style="bright_black", box=box.ROUNDED, padding=(0, 1))
    console.print(Group(label, panel))


def print_metrics(metrics: dict[str, Any]) -> None:
    tools = str(metrics["tools_used"])
    text = Text("   ", style="dim")
    text.append(f"{metrics['total_time']:.2f}s", style="cyan")
    text.append(" total  |  ", style="dim")
    text.append(f"{metrics['tokens']}", style="cyan")
    text.append(" tokens  |  ", style="dim")
    text.append(f"{metrics['tps']:.1f}", style="cyan")
    text.append(" tps", style="dim")
    if tools != "None":
        text.append("  |  tool ", style="dim")
        text.append(tools, style="cyan")
    console.print(text)


def extract_web_sources(tool_result: str, limit: int = 5) -> list[dict[str, str]]:
    sources: list[dict[str, str]] = []
    pattern = re.compile(
        r"Result\s+\d+:\s*Title:\s*(?P<title>.*?)\s*URL:\s*(?P<url>.*?)\s*Snippet:",
        re.DOTALL,
    )
    for match in pattern.finditer(tool_result):
        title = " ".join(match.group("title").split())
        url = " ".join(match.group("url").split())
        if title and url and url != "No URL":
            sources.append({"title": title, "url": url})
        if len(sources) >= limit:
            break
    return sources


def print_sources(sources: list[dict[str, str]]) -> None:
    if not sources:
        return

    text = Text("   sources ", style="dim")
    text.append(f"{len(sources)}", style="cyan")
    console.print(text)
    for index, source in enumerate(sources, start=1):
        line = Text(f"   [{index}] ", style="dim")
        line.append(source["title"], style="dim")
        line.append(" - ", style="dim")
        line.append(source["url"], style="cyan")
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


def stdin_pressed() -> bool:
    if not sys.stdin.isatty():
        return False
    ready, _, _ = select.select([sys.stdin], [], [], 0)
    if not ready:
        return False
    sys.stdin.readline()
    return True


def confirm_tool(tool_name: str, args: dict, permission: str) -> bool:
    if not ASSISTANT_SETTINGS.get("confirm_risky_tools", True):
        return True

    global _active_status
    if _active_status is not None:
        _active_status.stop()

    try:
        body = Text()
        body.append("Tool: ", style="dim")
        body.append(tool_name, style="bold")
        body.append("\nPermission: ", style="dim")
        body.append(permission, style="yellow")
        body.append("\nArgs: ", style="dim")
        body.append(repr(args))
        console.print(app_panel(body, title="Confirm Tool", border_style="yellow"))
        answer = Prompt.ask("Allow tool?", choices=["y", "n"], default="n")
    finally:
        if _active_status is not None:
            _active_status.start()

    return answer == "y"


def capture_command(
    recognizer: sr.Recognizer,
    speech_config,
    *,
    follow_up: bool = False,
) -> str | None:
    attempts = max(1, speech_config.retry_attempts + 1)
    timeout = speech_config.follow_up_timeout_seconds if follow_up else speech_config.timeout_seconds

    for attempt in range(attempts):
        result = speech_to_text(
            recognizer,
            speech_config,
            timeout_seconds=timeout,
            status_label="Follow-up" if follow_up else "Listening",
        )
        transcript = Text(result.text or "No speech detected.", style="white")
        transcript.append(f"\nAudio {result.audio_seconds:.1f}s / RMS {result.rms:.3f}", style="dim")
        print_chat_message("Heard", transcript.plain, style="blue")

        if result.text:
            record_command(result.text)
            return result.text

        if attempt < attempts - 1:
            console.print("[yellow]I didn't catch that. Listening one more time...[/yellow]")
            play_status_sound("wake")

    return None

def parse_code_command(user_text: str) -> str | None:
    stripped = user_text.strip()
    if stripped == "/code":
        return ""
    if not stripped.startswith("/code "):
        return None
    return stripped[len("/code "):].strip()

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
        skill_lines += "\n- `/skills` - List, create, or remove skills.\n"

    return f"""# Helium Help

Helium is a local AI assistant for everyday questions, deep research, file-aware chat, and agentic coding.

## Commands

- `/help` - Show this help guide.
- `/code <task>` - Agentic coding workflow: inspect files, plan, edit, verify, and report changes.
- `/deep-research <task>` - Run the deep research pipeline directly with multi-source evidence.
- `@path/to/file <question>` - Attach one local file for RAG-backed answers.
- `quit`, `exit`, or `stop` - End the current text session.
{skill_lines}
## What You Can Ask

## What You Can Ask

- Everyday chat: ask questions, draft text, summarize ideas, or reason through decisions.
- Deep research: request cited reports, comparisons, market/policy analysis, or current-event research.
- Agentic coding: fix bugs, add tests, inspect project architecture, refactor focused code, and run verification.
- File work: read, create, patch, search, and summarize project files through tools.
- Web work: search the web, fetch pages, and synthesize evidence with source URLs.
- Memory: ask Helium to remember preferences or facts for the current session.

## Agentic Coding

Use `/code` when you want Helium to work like a coding agent:

```text
/code fix the failing parser test and run the focused test file
```

Helium will inspect relevant files first, make targeted edits, ask before risky shell commands, run verification when useful, and finish with:

- Changed files
- Verification
- Remaining risks

## Deep Research

Use `/deep-research` when you want the research pipeline explicitly:

```text
/deep-research compare local-first AI agents with cloud coding agents and include sources
```

Helium will plan searches, collect evidence, synthesize findings, and cite sources.

## Tool safety

Read/search tools can run automatically. Risky actions such as destructive file operations, unsafe shell commands, and opening apps may ask for confirmation. In `/code`, common file edits are auto-approved so coding tasks can move smoothly, while destructive actions still stay guarded.

## Examples

```text
Summarize this project.
@README.md explain how to run Helium locally
/deep-research why are local AI agents becoming popular?
/code add a focused test for /help command parsing
```
"""

def format_code_workflow_report(result) -> str:
    answer = str(getattr(result, "final_answer", "")).strip()
    sections = [answer] if answer else []

    if "Changed files:" not in answer:
        changed_files = getattr(result, "changed_files", []) or []
        files_text = "\n".join(f"- {path}" for path in changed_files) if changed_files else "- None recorded"
        sections.append(f"Changed files:\n{files_text}")

    if "Verification:" not in answer:
        verification_commands = getattr(result, "verification_commands", []) or []
        verification_text = (
            "\n".join(f"- {command}" for command in verification_commands)
            if verification_commands
            else "- Not run or not recorded"
        )
        sections.append(f"Verification:\n{verification_text}")

    if "Remaining risks:" not in answer:
        sections.append("Remaining risks:\n- Not reported")

    if getattr(result, "stop_reason", "") == "max_turns":
        sections.append(
            "\n[bold red]Warning: The coding workflow reached the maximum turn limit and had to stop. "
            "The task might be incomplete.[/bold red]"
        )

    return "\n\n".join(sections)

def handle_code_command(user_text: str, confirm_tool) -> bool:
    task = parse_code_command(user_text)
    if task is None:
        return False
    if not task:
        print_chat_message("Helium", "Usage: /code <coding task>", style="cyan")
        return True

    set_state("Coding Workflow")
    result = run_coding_workflow(task, confirm_tool=confirm_tool)
    print_chat_message("Helium", format_code_workflow_report(result), style="cyan", markdown=True)
    return True

def handle_deep_research_command(user_text: str) -> bool:
    task = parse_deep_research_command(user_text)
    if task is None:
        return False
    if not task:
        print_chat_message("Helium", "Usage: /deep-research <research task>", style="cyan")
        return True

    set_state("Deep Research")
    result = research_query(task, max_sources=8)
    print_chat_message("Helium", result, style="cyan", markdown=True)
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


def invoke_skill(skill: Skill, args: str, confirm_tool, workspace: Path) -> None:
    """Run a skill by injecting its body into the system prompt and running the agentic loop."""
    set_state(f"Skill: {skill.name}")

    from core.llm import call_llm_once, execute_agent_tool, AgenticLoop
    from config.settings import ASSISTANT_PERSONA
    from tools.registry import TOOL_PROMPT
    import time

    # Build skill-augmented system prompt
    system_prompt = (
        f"{ASSISTANT_PERSONA}\n\n"
        f"{TOOL_PROMPT}\n\n"
        f"<skill name=\"{skill.name}\">\n{skill.body}\n</skill>\n\n"
    )

    if skill.argument_hint:
        system_prompt += f"Argument hint: {skill.argument_hint}\n\n"

    if skill.allowed_tools:
        tools_list = ", ".join(skill.allowed_tools)
        system_prompt += f"Pre-approved tools for this skill: {tools_list}\n\n"

    user_prompt = args if args else f"Run the /{skill.name} skill."

    # Run agentic loop
    from core.llm import conversation_history, MAX_AGENTIC_TURNS, MAX_HISTORY

    token_count = 0

    def ask_model(loop_messages):
        nonlocal token_count
        reply_text, tokens = call_llm_once(loop_messages)
        token_count += tokens
        return reply_text

    def run_tool(action, confirm_tool=None):
        tool_name = str(action.get("tool", "unknown"))
        if skill.allowed_tools and tool_name not in skill.allowed_tools:
            return f"Tool '{tool_name}' is not allowed for this skill. Allowed: {', '.join(skill.allowed_tools)}"
        return execute_agent_tool(action, confirm_tool=confirm_tool)

    start = time.time()
    loop = AgenticLoop(
        ask_model=ask_model,
        execute_tool_call=run_tool,
        max_turns=MAX_AGENTIC_TURNS,
    )
    loop_result = loop.run(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        history=conversation_history,
        confirm_tool=confirm_tool,
    )
    reply = loop_result.final_answer

    # Save to conversation history
    conversation_history.append({"role": "user", "content": user_prompt})
    conversation_history.append({"role": "assistant", "content": reply})
    if len(conversation_history) > MAX_HISTORY:
        conversation_history[:] = conversation_history[-MAX_HISTORY:]

    if reply:
        print_chat_message("Helium", reply, style="cyan", markdown=True)

    elapsed = time.time() - start
    metrics = {
        "tokens": token_count,
        "time": round(elapsed, 2),
        "tools": loop_result.tools_used,
    }
    print_metrics(metrics)


def handle_local_command(user_text: str, pipeline, target_voice: str) -> bool:
    normalized = user_text.strip().lower()

    if normalized in {"stop", "cancel", "never mind", "nevermind"}:
        console.print("[dim]Cancelled. Going back to sleep.[/dim]")
        return True

    if "what did you hear" in normalized or "what was the last command" in normalized:
        heard = last_heard()
        reply = f"The last thing I heard was: {heard}" if heard else "I do not have any command history yet."
        print_chat_message("Helium", reply, style="cyan")
        text_to_speech(pipeline, [reply], target_voice, interrupt_checker=stdin_pressed)
        return True

    return False


def print_health_checks() -> None:
    set_state("Health check")
    table = Table(box=box.SIMPLE, show_header=True, header_style="bold")
    table.add_column("Status", width=8)
    table.add_column("Check")
    table.add_column("Detail", style="dim")
    for check in run_startup_health_checks():
        style = "green" if check.ok else "yellow"
        label = "OK" if check.ok else "WARN"
        table.add_row(f"[{style}]{label}[/{style}]", check.name, check.detail)
    console.print(app_panel(table, title="Health", border_style="green"))


def prepare_rag_prompt(user_text: str) -> str:
    config = load_rag_service_config()
    if not config.enabled or "@" not in user_text:
        return user_text

    mention = resolve_single_mention(user_text, config)
    if mention is None:
        return user_text

    set_state("Attachment", "extracting -> indexing -> retrieving")
    client = RagServiceClient(config)
    evidence = client.evidence_for_path(
        mention.file_path,
        mention.question,
        debug=config.rag_debug,
    )
    citations = evidence.get("citations") or []
    detail = f"{mention.file_path.name}"
    if citations:
        detail += f" / {len(citations)} citations"
    set_state("Attachment ready", detail)
    return str(evidence["prompt"])


def ensure_llm_runtime_config() -> bool:
    runtime_config = load_llm_runtime_config()
    needs_setup = not runtime_config.is_complete
    if not needs_setup and not check_llm_api(runtime_config):
        console.print("\n[yellow]Stored LLM configuration failed to connect. You may need to update your settings.[/yellow]")
        needs_setup = True

    if not needs_setup:
        return True

    legacy_values = parse_legacy_env_file()
    if legacy_values and not runtime_config.is_complete:
        import_choice = Prompt.ask(
            "[bold green]Import existing ~/.helium.env into secure storage?[/bold green]",
            choices=["yes", "no"],
            default="yes",
        )
        if import_choice == "yes":
            try:
                imported = import_legacy_runtime_config()
                console.print(
                    "[yellow]Imported legacy settings. ~/.helium.env may still contain secrets and was left untouched.[/yellow]"
                )
                if imported.is_complete and check_llm_api(imported):
                    return True
            except RuntimeConfigError as exc:
                console.print(f"[bold red]{exc}[/bold red]")

    console.print(app_panel(
        "[bold cyan]Welcome to Helium Agent![/bold cyan]\n\n"
        "Some required LLM settings are missing or unable to connect.\n"
        "All settings, including the API key, are saved to your user Helium config file\n"
        "with secure owner-only permissions.",
        title="Setup Wizard",
        border_style="cyan",
    ))

    entered_key = Prompt.ask(
        "\n[bold green]1. Enter your LLM API Key (e.g. OpenRouter key)[/bold green]",
        default=runtime_config.api_key or "",
    ).strip()
    if not entered_key:
        console.print("[yellow]Key setup skipped. Agent starting with active environment values.[/yellow]\n")
        return False

    entered_url = Prompt.ask(
        "[bold green]2. Enter LLM API Base URL (including /chat/completions if needed)[/bold green]",
        default=runtime_config.api_url or "https://openrouter.ai/api/v1/chat/completions",
    ).strip()
    entered_model = Prompt.ask(
        "[bold green]3. Enter default LLM Model[/bold green]",
        default=runtime_config.model or "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free",
    ).strip()
    use_playwright_default = "true" if runtime_config.use_playwright is not False else "false"
    use_playwright = Prompt.ask(
        "[bold green]4. Enable Playwright browser automation?[/bold green]",
        choices=["true", "false"],
        default=use_playwright_default,
    ).strip()

    try:
        save_llm_runtime_config(
            api_key=entered_key,
            api_url=entered_url,
            model=entered_model,
            use_playwright=use_playwright == "true",
        )
        console.print("\n[green]LLM API key saved to the user config file.[/green]\n")
        return True
    except RuntimeConfigError as exc:
        console.print(f"[bold red]{exc}[/bold red]\n")
        return False


def main(mode: str = "text", target_path: str = ".", nuclear: bool = False):
    workspace = Path(target_path).resolve()
    os.chdir(workspace)
    set_project_root(workspace)

    if nuclear:
        ASSISTANT_SETTINGS["confirm_risky_tools"] = False
        warning_body = Text("Nuclear mode active. The agent will execute all risky tools without confirmation.", style="bold red")
        console.print(app_panel(warning_body, title="WARNING", border_style="red"))

    ensure_llm_runtime_config()

    from tools.memory_ops import initialize_session, shutdown_session
    initialize_session()
    atexit.register(shutdown_session)
    console.print(f"[dim]:: [Session] Persistent memory initialized for {workspace}.[/dim]")

    if mode == "text":
        print_header("text")

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
            console.print(f"[dim]:: [Skills] Loaded {' + '.join(parts)}.[/dim]")

        console.print("[dim]Type quit, exit, or stop to end.[/dim]\n")

        prompt_session = PromptSession(
            history=FileHistory(".helium_history"),
            completer=WorkspaceFileCompleter(skills=discovered_skills),
            complete_while_typing=True
        )
        
        while True:
            try:
                user_text = prompt_session.prompt(HTML("\n<b><green>You</green></b> > ")).strip()
                if not user_text:
                    continue
                if user_text.lower() in {"quit", "exit", "stop"}:
                    print_goodbye()
                    break

                reset_state()
                record_command(user_text)
                if handle_skill_management_command(user_text, workspace, discovered_skills):
                    continue
                if handle_help_command(user_text, discovered_skills):
                    continue
                # Check for skill trigger match
                skill_match = match_skill_trigger(user_text, discovered_skills)
                if skill_match:
                    skill, skill_args = skill_match
                    invoke_skill(skill, skill_args, confirm_tool, workspace)
                    continue
                if handle_code_command(user_text, confirm_tool=confirm_tool):
                    continue
                if handle_deep_research_command(user_text):
                    continue
                metrics: dict[str, Any] = {}
                sources: list[dict[str, str]] = []

                def collect_tool_result(tool_name: str, tool_result: str) -> None:
                    if tool_name == "search_web":
                        sources.extend(extract_web_sources(tool_result))

                try:
                    llm_prompt = prepare_rag_prompt(user_text)
                except RagError as exc:
                    set_state("Attachment error")
                    print_chat_message("Error", exc.message, style="red")
                    continue

                with console.status("[cyan]Thinking...[/cyan]", spinner="dots") as status:
                    global _active_status
                    _active_status = status
                    def set_state_spinner(state: str):
                        if "Using" in state or "Attachment" in state:
                            status.update(f"[yellow]{state}...[/yellow]")
                        elif "Responding" in state:
                            status.update("[green]Responding...[/green]")
                        elif "Thinking" in state:
                            status.update("[cyan]Thinking...[/cyan]")
                        else:
                            status.update(f"[dim]:: {state}[/dim]")

                    try:
                        reply_generator = generate_response(
                            llm_prompt,
                            confirm_tool=confirm_tool,
                            on_state=set_state_spinner,
                            on_metrics=metrics.update,
                            on_tool_result=collect_tool_result,
                            print_metrics=False,
                            skills=discovered_skills,
                        )
                        reply_list = list(reply_generator)
                    finally:
                        _active_status = None
                
                stream_reply(reply_list)
                print_sources(sources)
                if metrics:
                    print_metrics(metrics)
                
            except KeyboardInterrupt:
                print_goodbye()
                break
            except EOFError:
                print_goodbye()
                break
            except Exception as e:
                set_state("Error")
                print_chat_message("Error", str(e), style="red")
        return

    print_header("voice")
    if not HAS_VOICE_DEP or not HAS_VOICE_ENGINES:
        console.print(
            "\n[bold red]Error: Voice mode dependencies are not installed.[/bold red]\n"
            "To use voice mode, please install the optional voice packages:\n"
            "  [green]pip install helium-agent[voice][/green]\n"
        )
        return

    set_state("Starting voice engines")

    wake_config = build_wake_config(WAKE_WORD_SETTINGS)
    speech_config = build_speech_config(SPEECH_SETTINGS, wake_config.microphone_device_index)
    recognizer = sr.Recognizer()

    print_health_checks()

    set_state("Initializing TTS")
    pipeline = KPipeline(lang_code="a")
    target_voice = str(ASSISTANT_SETTINGS.get("tts_voice", "af_heart"))

    set_state("Preparing wake word model")
    openwakeword.utils.download_models()
    oww_model = Model(wakeword_models=list(wake_config.models), inference_framework="onnx")

    set_state("Calibrating microphone")
    try:
        ambient_rms, ambient_dbfs, recommended_threshold = calibrate_microphone(wake_config)
        console.print(
            "[dim]Mic ambient level "
            f"{ambient_dbfs:.0f} dBFS (rms {ambient_rms:.0f}). "
            f"Current wake threshold {wake_config.threshold:.2f}; recommended {recommended_threshold:.2f}.[/dim]"
        )
    except Exception as exc:
        console.print(f"[yellow]Microphone calibration skipped: {exc}[/yellow]")

    console.print("[dim]Say Helium or press Enter to talk.[/dim]")

    follow_up_mode = bool(ASSISTANT_SETTINGS.get("follow_up_mode", True))
    awaiting_follow_up = False

    while True:
        try:
            if awaiting_follow_up:
                set_state("Listening", "follow-up window")
            else:
                set_state("Sleeping", "say Helium or press Enter")
                diagnostics = wake_word_detection(oww_model, wake_config)
                play_status_sound("wake")
                set_state(
                    "Heard wake word",
                    f"trigger={diagnostics.trigger}, score={max(list(diagnostics.smoothed_scores.values()) or [0.0]):.2f}",
                )

            user_text = capture_command(recognizer, speech_config, follow_up=awaiting_follow_up)

            if not user_text:
                console.print("[dim]No speech detected. Going back to sleep.[/dim]")
                play_status_sound("sleep")
                awaiting_follow_up = False
                continue

            awaiting_follow_up = False
            if handle_local_command(user_text, pipeline, target_voice):
                play_status_sound("sleep")
                continue

            reset_state()
            print_chat_message("You", user_text, style="green")
            set_state("Thinking")

            metrics: dict[str, Any] = {}
            sources: list[dict[str, str]] = []

            def collect_tool_result(tool_name: str, tool_result: str) -> None:
                if tool_name == "search_web":
                    sources.extend(extract_web_sources(tool_result))

            reply_generator = generate_response(
                user_text,
                confirm_tool=confirm_tool,
                on_state=set_state,
                on_metrics=metrics.update,
                on_tool_result=collect_tool_result,
                print_metrics=False,
            )
            full_reply = ""
            started_speaking = False

            def intercept_generator(gen):
                nonlocal full_reply, started_speaking
                for chunk in gen:
                    if not started_speaking:
                        set_state("Speaking", "press Enter between chunks to interrupt")
                        started_speaking = True
                    full_reply += chunk + " "
                    yield chunk

            was_interrupted = text_to_speech(
                pipeline,
                intercept_generator(reply_generator),
                target_voice,
                interrupt_checker=stdin_pressed,
            )

            if was_interrupted:
                console.print("[yellow]Speech interrupted.[/yellow]")
            if full_reply.strip():
                print_chat_message("Helium", full_reply.strip(), style="cyan", markdown=True)
            print_sources(sources)
            if metrics:
                print_metrics(metrics)

            awaiting_follow_up = follow_up_mode and not was_interrupted
            if awaiting_follow_up:
                console.print(
                    f"[dim]Follow-up mode active for {speech_config.follow_up_timeout_seconds:.0f}s.[/dim]"
                )
            else:
                play_status_sound("sleep")
                console.print("\n[dim]\\[Sleeping..] Say Helium to wake me up.[/dim]")

        except sr.WaitTimeoutError:
            console.print("[dim]Timed out waiting for a command. Going back to sleep.[/dim]")
            awaiting_follow_up = False
            play_status_sound("sleep")
        except sr.UnknownValueError:
            console.print("[dim]Didn't catch that. Going back to sleep.[/dim]")
            awaiting_follow_up = False
            play_status_sound("sleep")
        except KeyboardInterrupt:
            print_goodbye()
            break
        except Exception as e:
            set_state("Error")
            print_chat_message("Error", str(e), style="red")
            awaiting_follow_up = False
            play_status_sound("sleep")


def cli_entrypoint():
    parser = argparse.ArgumentParser(description="Helium Agent")
    parser.add_argument("path", type=str, nargs="?", default=".", help="Target workspace path")
    parser.add_argument("--mode", type=str, choices=["voice", "text"], default="text", help="Interaction mode (voice or text)")
    parser.add_argument("--nuclear", action="store_true", help="Bypass all risky tool confirmations (run without asking permission)")
    args = parser.parse_args()
    
    main(mode=args.mode, target_path=args.path, nuclear=args.nuclear)


if __name__ == "__main__":
    cli_entrypoint()
