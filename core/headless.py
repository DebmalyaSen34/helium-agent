"""Non-interactive runs: `helium -p "<task>"` does one task and exits.

Used for scripting, CI, and the benchmark in evals/bench. Nothing is asked: tools
that need approval are denied unless `--accept-edits` or `--yes` allows them.
Everything except the final output goes to stderr, so stdout stays parseable.
"""

from __future__ import annotations

import contextlib
import json
import sys
import time
from collections import Counter
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TextIO

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_MAX_TURNS = 2

PERMISSION_MODES = ("deny", "accept-edits", "all")


@dataclass
class HeadlessResult:
    result: str
    stop_reason: str  # "final", "max_turns", or "error"
    duration_s: float
    model: str
    usage: dict[str, int] = field(default_factory=dict)
    tools_used: list[str] = field(default_factory=list)
    denied_tools: list[str] = field(default_factory=list)
    messages: list[dict[str, Any]] = field(default_factory=list)

    @property
    def exit_code(self) -> int:
        return {"final": EXIT_OK, "max_turns": EXIT_MAX_TURNS}.get(self.stop_reason, EXIT_ERROR)

    def to_json(self) -> dict[str, Any]:
        return {
            "result": self.result,
            "stop_reason": self.stop_reason,
            "is_error": self.stop_reason == "error",
            "duration_s": round(self.duration_s, 2),
            "model": self.model,
            "num_requests": int(self.usage.get("requests", 0)),
            "num_tool_calls": len(self.tools_used),
            "usage": {
                "prompt_tokens": int(self.usage.get("prompt_tokens", 0)),
                "completion_tokens": int(self.usage.get("completion_tokens", 0)),
            },
            "tools_used": dict(Counter(self.tools_used)),
            "denied_tools": self.denied_tools,
        }


def make_headless_confirm(mode: str, denied: list[str]):
    """Approval callback for runs where nobody can answer a prompt."""
    from tools.registry import EDIT_TOOLS

    if mode not in PERMISSION_MODES:
        raise ValueError(f"permission mode must be one of {', '.join(PERMISSION_MODES)}")

    def confirm(tool_name: str, args: dict[str, Any], permission: str) -> bool:
        if mode == "all" or (mode == "accept-edits" and tool_name in EDIT_TOOLS):
            return True
        denied.append(tool_name)
        return False

    return confirm


def run_headless(
    task: str,
    *,
    permission_mode: str = "deny",
    max_turns: int | None = None,
    model: Any = None,
    on_event: Any = None,
) -> HeadlessResult:
    """Run `task` through the main agent once, with no conversation history."""
    from core.llm import MAX_AGENTIC_TURNS, run_agent
    from core.prompts import build_system_prompt
    from core.session import get_active_model
    from tools.registry import tools_for

    denied: list[str] = []
    started = time.time()
    model_name = getattr(model, "model", None) or get_active_model()
    try:
        loop_result = run_agent(
            build_system_prompt("main", user_prompt=task),
            task,
            confirm_tool=make_headless_confirm(permission_mode, denied),
            tool_names=tools_for("main"),
            max_turns=max_turns or MAX_AGENTIC_TURNS,
            on_event=on_event,
            model=model,
        )
    except Exception as exc:
        return HeadlessResult(
            result=f"{type(exc).__name__}: {exc}",
            stop_reason="error",
            duration_s=time.time() - started,
            model=str(model_name),
            denied_tools=denied,
        )
    return HeadlessResult(
        result=loop_result.final_answer,
        stop_reason=loop_result.stop_reason,
        duration_s=time.time() - started,
        model=str(model_name),
        usage=dict(loop_result.usage),
        tools_used=list(loop_result.tools_used),
        denied_tools=denied,
        messages=loop_result.messages,
    )


@contextlib.contextmanager
def stdout_to_stderr() -> Iterator[TextIO]:
    """Send everything printed during the run (diffs, logs) to stderr; yield the real stdout."""
    real_stdout = sys.stdout
    sys.stdout = sys.stderr
    try:
        yield real_stdout
    finally:
        sys.stdout = real_stdout


def _progress_printer(stream: TextIO):
    def on_event(kind: str, payload: Any) -> None:
        if kind == "tool_start":
            args = ", ".join(f"{k}={str(v)[:60]!r}" for k, v in (payload.get("args") or {}).items())
            print(f"● {payload['name']}({args})", file=stream, flush=True)

    return on_event


def headless_main(
    workspace: Path,
    task: str,
    *,
    permission_mode: str = "deny",
    output_json: bool = False,
    max_turns: int | None = None,
    model_name: str | None = None,
    transcript_path: Path | None = None,
    verbose: bool = False,
    model: Any = None,
) -> int:
    """Entry point behind `helium -p`. Returns the process exit code."""
    import logging
    import os

    from config.runtime_config import load_llm_runtime_config
    from core.session import SESSION
    from tools.file_ops import set_project_root
    from tools.memory_ops import initialize_session, shutdown_session

    root_logger = logging.getLogger()
    for handler in list(root_logger.handlers):
        root_logger.removeHandler(handler)
    logging.basicConfig(stream=sys.stderr, level=logging.INFO if verbose else logging.WARNING, format="%(message)s")

    if not task.strip():
        print("helium -p needs a task, e.g. helium -p \"fix the failing test\"", file=sys.stderr)
        return EXIT_ERROR
    if model is None and not load_llm_runtime_config().is_complete:
        print("LLM settings are missing. Run `helium --setup` once in a terminal first.", file=sys.stderr)
        return EXIT_ERROR

    workspace = workspace.resolve()
    os.chdir(workspace)
    set_project_root(workspace)
    if model_name:
        SESSION.model_override = model_name

    with stdout_to_stderr() as real_stdout:
        initialize_session(workspace=workspace)
        try:
            result = run_headless(
                task,
                permission_mode=permission_mode,
                max_turns=max_turns,
                model=model,
                on_event=_progress_printer(sys.stderr) if verbose else None,
            )
        finally:
            shutdown_session()

        if transcript_path is not None:
            transcript_path.parent.mkdir(parents=True, exist_ok=True)
            transcript_path.write_text(json.dumps(result.messages, indent=2, default=str), encoding="utf-8")

        if output_json:
            real_stdout.write(json.dumps(result.to_json()) + "\n")
        elif result.stop_reason == "error":
            print(result.result, file=sys.stderr)
        else:
            real_stdout.write(result.result.rstrip() + "\n")
        real_stdout.flush()

    if result.stop_reason == "max_turns":
        print("Stopped at the tool turn limit; the task may be incomplete.", file=sys.stderr)
    if result.denied_tools and permission_mode != "all":
        print(
            f"Denied without asking: {', '.join(sorted(set(result.denied_tools)))}. "
            "Pass --accept-edits or --yes to allow them.",
            file=sys.stderr,
        )
    return result.exit_code


__all__ = [
    "EXIT_ERROR",
    "EXIT_MAX_TURNS",
    "EXIT_OK",
    "HeadlessResult",
    "PERMISSION_MODES",
    "headless_main",
    "make_headless_confirm",
    "run_headless",
]
