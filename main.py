import logging
import re
import select
import sys
import argparse
from typing import Any

import openwakeword
import speech_recognition as sr
from kokoro import KPipeline
from openwakeword.model import Model
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
from engine.stt import build_speech_config, speech_to_text
from engine.tts import text_to_speech
from engine.wake_word import build_wake_config, calibrate_microphone, wake_word_detection
from utils.start_animation import render_startup_intro
from utils.audio import play_status_sound
from utils.health import run_startup_health_checks
from utils.history import last_heard, record_command

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

logger = logging.getLogger("rich")
console = Console()
_last_state_key: tuple[str, str | None] | None = None


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


def stream_reply(reply_generator) -> str:
    full_reply = ""
    for chunk in reply_generator:
        chunk = chunk.strip()
        if not chunk:
            continue
        full_reply = f"{full_reply} {chunk}".strip()
    if full_reply:
        print_chat_message("Helium", full_reply, style="cyan", markdown=True)
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

    body = Text()
    body.append("Tool: ", style="dim")
    body.append(tool_name, style="bold")
    body.append("\nPermission: ", style="dim")
    body.append(permission, style="yellow")
    body.append("\nArgs: ", style="dim")
    body.append(repr(args))
    console.print(app_panel(body, title="Confirm Tool", border_style="yellow"))
    answer = Prompt.ask("Allow tool?", choices=["y", "n"], default="n")
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


def main(mode: str = "voice"):
    if mode == "text":
        print_header("text")
        console.print("[dim]Type quit, exit, or stop to end.[/dim]\n")
        
        while True:
            try:
                user_text = Prompt.ask("\n[bold green]You[/bold green]").strip()
                if not user_text:
                    continue
                if user_text.lower() in {"quit", "exit", "stop"}:
                    print_goodbye()
                    break

                reset_state()
                record_command(user_text)
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
                stream_reply(reply_generator)
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


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Helium Agent")
    parser.add_argument("--mode", type=str, choices=["voice", "text"], default="voice", help="Interaction mode (voice or text)")
    args = parser.parse_args()
    
    main(mode=args.mode)
