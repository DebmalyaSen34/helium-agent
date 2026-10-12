"""Per-call agent context shared between the loop, the tool registry, and subagents."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any

ConfirmTool = Callable[[str, dict[str, Any], str], bool]

current_confirm_tool: ContextVar[ConfirmTool | None] = ContextVar("current_confirm_tool", default=None)
subagent_depth: ContextVar[int] = ContextVar("subagent_depth", default=0)


@contextmanager
def confirm_tool_scope(confirm_tool: ConfirmTool | None) -> Iterator[None]:
    token = current_confirm_tool.set(confirm_tool)
    try:
        yield
    finally:
        current_confirm_tool.reset(token)


@contextmanager
def subagent_scope() -> Iterator[None]:
    token = subagent_depth.set(subagent_depth.get() + 1)
    try:
        yield
    finally:
        subagent_depth.reset(token)


def in_subagent() -> bool:
    return subagent_depth.get() > 0
