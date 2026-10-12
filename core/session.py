"""Process-wide state for the interactive session (model override, usage, approvals)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class UsageTotals:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    requests: int = 0
    tool_calls: int = 0

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens

    def add(self, usage: dict[str, Any] | None, *, requests: int = 0, tool_calls: int = 0) -> None:
        usage = usage or {}
        self.prompt_tokens += int(usage.get("prompt_tokens") or 0)
        self.completion_tokens += int(usage.get("completion_tokens") or 0)
        self.requests += requests
        self.tool_calls += tool_calls


@dataclass
class SessionState:
    model_override: str | None = None
    usage: UsageTotals = field(default_factory=UsageTotals)
    # Tool approvals granted with "always allow" for the rest of the session.
    allow_list: set[str] = field(default_factory=set)

    def reset(self) -> None:
        self.model_override = None
        self.usage = UsageTotals()
        self.allow_list.clear()


SESSION = SessionState()


def get_active_model() -> str:
    """The model to use for requests: /model override, then runtime config, then settings."""
    if SESSION.model_override:
        return SESSION.model_override

    from config.runtime_config import load_llm_runtime_config
    from config.settings import API_MODEL

    runtime_config = load_llm_runtime_config()
    return runtime_config.model or API_MODEL


__all__ = ["SESSION", "SessionState", "UsageTotals", "get_active_model"]
