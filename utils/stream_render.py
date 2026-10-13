"""Live terminal rendering of agent replies: spinner, streamed Markdown, tool progress."""

from __future__ import annotations

import os
import re
import threading
from functools import wraps
from typing import Any

from rich.console import Console
from rich.live import Live
from rich.segment import Segment

from utils.parser import strip_reasoning

# A reply that starts with a text-protocol tool call (optionally after a <thought>).
LEADING_ACTION_RE = re.compile(r"^\s*(?:<thought>.*?</thought>\s*)?<action>", re.DOTALL)


def should_stream(console: Console) -> bool:
    if os.getenv("HELIUM_NO_STREAM", "").strip().lower() in {"1", "true", "yes", "on"}:
        return False
    return console.is_terminal


def visible_text(raw: str) -> str:
    """What to show while streaming.

    Hides a leading <think> block (still open or closed) and a reply that is only a
    text-protocol tool call. Tags mentioned inside an answer are shown as written.
    """
    if raw.lstrip().startswith("<think>") and "</think>" not in raw:
        return ""
    text = strip_reasoning(raw)
    if LEADING_ACTION_RE.match(text):
        return ""
    return text


def summarize_args(args: dict[str, Any], limit: int = 80) -> str:
    parts = []
    for key, value in (args or {}).items():
        if key in {"content", "edits", "patch", "new", "old", "proposed_content"}:
            value = f"<{len(str(value))} chars>"
        text = str(value).replace("\n", " ")
        parts.append(f"{key}={text}")
    summary = " ".join(parts)
    return summary if len(summary) <= limit else summary[: limit - 1] + "…"


class _TailView:
    """Live renderable that only shows the last screenful of the streamed panel.

    Rich can't redraw a live region taller than the terminal (it would scroll and
    duplicate output), so while streaming we keep the region within the screen and
    print the complete answer once streaming ends.
    """

    def __init__(self, reply: "LiveReply") -> None:
        self.reply = reply

    def __rich_console__(self, console, options):
        renderable = self.reply._panel(self.reply._shown)
        lines = console.render_lines(renderable, options, pad=False)
        max_lines = max(4, (options.height or console.height) - 2)
        if len(lines) > max_lines:
            lines = lines[-max_lines:]
        for line in lines:
            yield from line
            yield Segment.line()


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
        self._status_message = "[#5fd7ff]Thinking…[/]"
        self._live: Live | None = None
        self._raw = ""
        self._shown = ""
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
            self._status = self.console.status(self._status_message, spinner="dots", spinner_style="#5fd7ff")
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
            self.update("[#5fd7ff]Thinking…[/]")

    @_locked
    def on_text(self, delta: str) -> None:
        if not self.stream_text:
            return
        self._raw += delta
        shown = visible_text(self._raw)
        if not shown.strip():
            return
        self._shown = shown
        if self._live is None:
            if self._status is not None:
                self._status.stop()
                self._status = None
            self._live = Live(
                _TailView(self),
                console=self.console,
                refresh_per_second=8,
                vertical_overflow="crop",
                transient=True,
            )
            self._live.start()
        self._final_streamed = True

    @_locked
    def on_tool_start(self, name: str, args: dict[str, Any]) -> None:
        self.stop()
        from utils.tui import tool_line

        self.console.print(tool_line(name, summarize_args(args)))
        self._status_message = f"[#e3b341]Running {name}…[/]"
        self.start()

    @_locked
    def finish(self) -> bool:
        """Stop live output. Returns True when the final answer was already shown."""
        self._flush_live()
        if self._status is not None:
            self._status.stop()
            self._status = None
        return self._final_streamed

    # -- helpers -----------------------------------------------------------------

    def _flush_live(self) -> None:
        """Replace the transient live tail with the complete text, printed once."""
        if self._live is None:
            return
        self._live.stop()
        self._live = None
        if self._shown.strip():
            self.console.print(self._panel(self._shown))
            self.console.print()

    def _commit_text(self) -> None:
        """Freeze streamed narration in place; later text starts a new panel."""
        self._flush_live()
        self._raw = ""
        self._shown = ""
        self._final_streamed = False

    @staticmethod
    def _panel(text: str):
        from utils.tui import assistant_block

        return assistant_block(text)


__all__ = ["LiveReply", "should_stream", "summarize_args", "visible_text"]
