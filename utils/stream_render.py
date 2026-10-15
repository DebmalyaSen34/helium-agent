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

from utils.code_render import git_diff_view, looks_like_git_diff
from utils.parser import strip_reasoning
from utils.theme import current_theme

# A reply that starts with a text-protocol tool call (optionally after a <thought>).
# Tools whose output may be a git diff worth showing to the user.
DIFF_TOOLS = frozenset({"git_diff", "execute_bash"})

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


_FENCE_RE = re.compile(r"^ {0,3}(`{3,}|~{3,})")


def stable_split(text: str) -> int:
    """Index where the last finished Markdown block ends.

    Blocks are separated by a blank line outside a code fence. A split is only made
    before an unindented line, so list continuations and indented code stay whole.
    Everything before the index can be rendered once and reused.
    """
    split = 0
    fence: str | None = None
    blank = False
    pos = 0
    for line in text.splitlines(keepends=True):
        stripped = line.strip()
        if fence is None and blank and stripped and not line[0].isspace():
            split = pos
        match = _FENCE_RE.match(line)
        if match:
            marker = match.group(1)
            if fence is None:
                fence = marker
            elif marker[0] == fence[0] and len(marker) >= len(fence) and not line.strip()[len(marker):]:
                fence = None
        blank = fence is None and not stripped
        pos += len(line)
    return split


class _TailView:
    """Live renderable that only shows the last screenful of the streamed panel.

    Rich can't redraw a live region taller than the terminal (it would scroll and
    duplicate output), so while streaming we keep the region within the screen and
    print the complete answer once streaming ends.

    Re-rendering the whole reply on every refresh grows with its length, so finished
    blocks are rendered once and cached; each refresh renders only the block still
    being written.
    """

    def __init__(self, reply: "LiveReply") -> None:
        self.reply = reply
        self._done_text = ""
        self._done_width = 0
        self._done_lines: list = []

    def _render(self, console, options, text: str, first: bool) -> list:
        from rich.padding import Padding

        from utils.code_render import CodeMarkdown

        renderable = self.reply._panel(text) if first else Padding(CodeMarkdown(text), (0, 0, 0, 2))
        return console.render_lines(renderable, options, pad=False)

    def __rich_console__(self, console, options):
        text = self.reply._shown
        split = stable_split(text)
        done, tail = text[:split], text[split:]
        if options.max_width != self._done_width or not done.startswith(self._done_text):
            self._done_text, self._done_width, self._done_lines = "", options.max_width, []
        if len(done) > len(self._done_text):
            new = done[len(self._done_text):]
            if self._done_lines:
                self._done_lines = self._done_lines + [[]] + self._render(console, options, new, first=False)
            else:
                self._done_lines = self._render(console, options, new, first=True)
            self._done_text = done
        lines = list(self._done_lines)
        if tail.strip():
            if lines:
                lines += [[]] + self._render(console, options, tail, first=False)
            else:
                lines = self._render(console, options, tail, first=True)
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
        self._status_message = f"[{current_theme().accent}]Thinking…[/]"
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
            self._status = self.console.status(self._status_message, spinner="dots", spinner_style=current_theme().accent)
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
            self.on_tool_end(payload.get("name", "tool"), payload.get("result"))
            self.update(f"[{current_theme().accent}]Thinking…[/]")

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
        self._status_message = f"[{current_theme().warning}]Running {name}…[/]"
        self.start()

    @_locked
    def on_tool_end(self, name: str, result: Any) -> None:
        """Show diffs the agent looked at, so the user sees them too."""
        if name not in DIFF_TOOLS or not isinstance(result, str) or not looks_like_git_diff(result):
            return
        view = git_diff_view(result)
        if view is None:
            return
        self.stop()
        self.console.print(view)
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


__all__ = ["LiveReply", "should_stream", "stable_split", "summarize_args", "visible_text"]
