"""Live terminal rendering of agent replies: spinner, streamed Markdown, tool progress."""

from __future__ import annotations

import os
import threading
from functools import wraps
from typing import Any

from rich import box
from rich.console import Console, Group
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.text import Text


def should_stream(console: Console) -> bool:
    if os.getenv("HELIUM_NO_STREAM", "").strip().lower() in {"1", "true", "yes", "on"}:
        return False
    return console.is_terminal


def visible_text(raw: str) -> str:
    """What to show while streaming: no <think> reasoning, no raw <action> blocks."""
    text = raw
    while "<think>" in text:
        start = text.index("<think>")
        end = text.find("</think>", start)
        if end == -1:
            text = text[:start]
            break
        text = text[:start] + text[end + len("</think>"):]
    if "</think>" in text:
        text = text.split("</think>", 1)[1]
    if "<action" in text:
        text = text[: text.index("<action")]
    return text.lstrip()


def summarize_args(args: dict[str, Any], limit: int = 80) -> str:
    parts = []
    for key, value in (args or {}).items():
        if key in {"content", "edits", "patch", "new", "old", "proposed_content"}:
            value = f"<{len(str(value))} chars>"
        text = str(value).replace("\n", " ")
        parts.append(f"{key}={text}")
    summary = " ".join(parts)
    return summary if len(summary) <= limit else summary[: limit - 1] + "…"


def _locked(method):
    @wraps(method)
    def wrapper(self, *args, **kwargs):
        with self._lock:
            return method(self, *args, **kwargs)

    return wrapper


class LiveReply:
    """Renders one agent run.

    Shows a spinner while the model thinks, streams answer text into a live
    Markdown panel, and prints a dim line for each tool call. It exposes
    `stop()`/`start()` so confirmation prompts can pause the live display.
    """

    def __init__(self, console: Console, *, label: str = "Helium", stream_text: bool | None = None) -> None:
        self.console = console
        self.label = label
        self.stream_text = should_stream(console) if stream_text is None else stream_text
        self._status = None
        self._status_message = "[cyan]Thinking...[/cyan]"
        self._live: Live | None = None
        self._raw = ""
        self._final_streamed = False
        # Parallel tool calls report progress from worker threads.
        self._lock = threading.RLock()

    # -- context manager -------------------------------------------------------

    def __enter__(self) -> "LiveReply":
        self.start()
        return self

    def __exit__(self, *exc_info) -> None:
        self.finish()

    # -- spinner -----------------------------------------------------------------

    @_locked
    def start(self) -> None:
        """Resume the spinner (used after a confirmation prompt)."""
        if self._status is None and self._live is None:
            self._status = self.console.status(self._status_message, spinner="dots")
            self._status.start()

    @_locked
    def stop(self) -> None:
        """Pause all live output so the terminal can be used for a prompt."""
        self._commit_text()
        if self._status is not None:
            self._status.stop()
            self._status = None

    @_locked
    def update(self, message: str) -> None:
        self._status_message = message
        if self._status is not None:
            self._status.update(message)

    # -- events ----------------------------------------------------------------

    @_locked
    def handle_event(self, kind: str, payload: Any) -> None:
        if kind == "text_delta":
            self.on_text(str(payload))
        elif kind == "tool_start":
            self.on_tool_start(payload.get("name", "tool"), payload.get("args") or {})
        elif kind == "tool_end":
            self.update("[cyan]Thinking...[/cyan]")

    @_locked
    def on_text(self, delta: str) -> None:
        if not self.stream_text:
            return
        self._raw += delta
        shown = visible_text(self._raw)
        if not shown.strip():
            return
        if self._live is None:
            if self._status is not None:
                self._status.stop()
                self._status = None
            self.console.print(Text(self.label, style="bold cyan"))
            self._live = Live(
                self._panel(shown),
                console=self.console,
                refresh_per_second=8,
                vertical_overflow="visible",
                transient=False,
            )
            self._live.start()
        else:
            self._live.update(self._panel(shown))
        self._final_streamed = True

    @_locked
    def on_tool_start(self, name: str, args: dict[str, Any]) -> None:
        self.stop()
        line = Text("   → ", style="dim")
        line.append(name, style="cyan")
        summary = summarize_args(args)
        if summary:
            line.append(f" {summary}", style="dim")
        self.console.print(line)
        self._status_message = f"[yellow]Using {name}...[/yellow]"
        self.start()

    @_locked
    def finish(self) -> bool:
        """Stop live output. Returns True when the final answer was already shown."""
        if self._live is not None:
            self._live.stop()
            self._live = None
        if self._status is not None:
            self._status.stop()
            self._status = None
        return self._final_streamed

    # -- helpers -----------------------------------------------------------------

    def _commit_text(self) -> None:
        """Freeze streamed narration in place; later text starts a new panel."""
        if self._live is not None:
            self._live.stop()
            self._live = None
        self._raw = ""
        self._final_streamed = False

    @staticmethod
    def _panel(text: str) -> Panel:
        return Panel(Group(Markdown(text)), border_style="bright_black", box=box.ROUNDED, padding=(0, 1))


__all__ = ["LiveReply", "should_stream", "summarize_args", "visible_text"]
