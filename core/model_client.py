"""Chat model clients that understand native OpenAI-compatible tool calling."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol
from uuid import uuid4

logger = logging.getLogger(__name__)

TextCallback = Callable[[str], None]

# (api_url, model) -> False once an endpoint has rejected the `tools` field.
_TOOL_SUPPORT: dict[tuple[str, str], bool] = {}


class LLMRequestError(Exception):
    """The endpoint returned an error response."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class ToolsUnsupportedError(LLMRequestError):
    """The endpoint rejected a request because it included tool definitions."""


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]
    raw_arguments: str = ""
    parse_error: str | None = None


@dataclass
class ModelTurn:
    content: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    usage: dict[str, Any] = field(default_factory=dict)
    finish_reason: str | None = None


class ChatModel(Protocol):
    supports_tools: bool

    def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        on_text: TextCallback | None = None,
    ) -> ModelTurn: ...


def tools_supported(key: tuple[str, str]) -> bool:
    return _TOOL_SUPPORT.get(key, True)


def mark_tools_unsupported(key: tuple[str, str]) -> None:
    _TOOL_SUPPORT[key] = False


def reset_tool_support(key: tuple[str, str] | None = None) -> None:
    if key is None:
        _TOOL_SUPPORT.clear()
    else:
        _TOOL_SUPPORT.pop(key, None)


class LegacyTextModel:
    """Adapts a plain `ask_model(messages) -> str | (str, tokens)` callable."""

    supports_tools = False

    def __init__(self, ask_model: Callable[[list[dict[str, Any]]], Any]) -> None:
        self.ask_model = ask_model

    def complete(self, messages, tools=None, on_text=None) -> ModelTurn:
        reply = self.ask_model(messages)
        usage: dict[str, Any] = {}
        if isinstance(reply, tuple):
            reply, tokens = reply
            usage = {"completion_tokens": tokens}
        return ModelTurn(content=str(reply or ""), usage=usage)


class OpenAICompatibleModel:
    """Streams chat completions from an OpenAI-compatible endpoint."""

    supports_tools = True

    def __init__(
        self,
        model: str | None = None,
        api_url: str | None = None,
        api_key: str | None = None,
        temperature: float = 0.3,
    ) -> None:
        from config.runtime_config import load_llm_runtime_config
        from core.session import get_active_model

        runtime_config = load_llm_runtime_config()
        self.model = model or get_active_model()
        self.api_url = api_url or runtime_config.api_url
        self.api_key = api_key or runtime_config.api_key
        self.temperature = temperature

    @property
    def cache_key(self) -> tuple[str, str]:
        return (str(self.api_url or ""), str(self.model or ""))

    def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        on_text: TextCallback | None = None,
    ) -> ModelTurn:
        from config.settings import LLM_SETTINGS
        from utils.check_llm_api import hit_api

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        stop_sequences = LLM_SETTINGS.get("stop_sequences") or []
        if stop_sequences:
            payload["stop"] = list(stop_sequences)

        response = hit_api(payload, is_stream=True, api_url=self.api_url, api_key=self.api_key)
        if response is None:
            raise LLMRequestError("Could not reach the LLM endpoint (connection failed or timed out).")

        if response.status_code >= 400:
            body = _safe_body(response)
            auth_or_rate_limit = response.status_code in (401, 402, 403, 429)
            if tools and not auth_or_rate_limit and (
                response.status_code in (400, 404, 422) or "tool" in body.lower()
            ):
                raise ToolsUnsupportedError(
                    f"Endpoint rejected tool definitions (HTTP {response.status_code}): {body[:300]}",
                    response.status_code,
                )
            raise LLMRequestError(f"HTTP {response.status_code}: {body[:500]}", response.status_code)

        return parse_stream(_iter_sse_data(response.iter_lines()), on_text=on_text)


def _safe_body(response) -> str:
    try:
        return response.text or ""
    except Exception:
        return ""


def _iter_sse_data(lines) -> Any:
    for line in lines:
        if not line:
            continue
        if isinstance(line, bytes):
            line = line.decode("utf-8", errors="replace")
        if not line.startswith("data: "):
            continue
        data = line[6:].strip()
        if data == "[DONE]":
            return
        try:
            yield json.loads(data)
        except json.JSONDecodeError:
            continue


def parse_stream(events, on_text: TextCallback | None = None) -> ModelTurn:
    """Assemble a ModelTurn from decoded streaming chunks."""
    content_parts: list[str] = []
    partial_calls: dict[int, dict[str, str]] = {}
    usage: dict[str, Any] = {}
    finish_reason: str | None = None

    for event in events:
        if event.get("error"):
            message = event["error"].get("message") if isinstance(event["error"], dict) else event["error"]
            raise LLMRequestError(f"Stream error: {message}")
        if event.get("usage"):
            usage = event["usage"]
        for choice in event.get("choices") or []:
            delta = choice.get("delta") or {}
            text = delta.get("content")
            if text:
                content_parts.append(text)
                if on_text:
                    on_text(text)
            for fragment in delta.get("tool_calls") or []:
                index = fragment.get("index", len(partial_calls))
                call = partial_calls.setdefault(index, {"id": "", "name": "", "arguments": ""})
                if fragment.get("id"):
                    call["id"] = fragment["id"]
                function = fragment.get("function") or {}
                if function.get("name"):
                    call["name"] += function["name"]
                if function.get("arguments"):
                    call["arguments"] += function["arguments"]
            if choice.get("finish_reason"):
                finish_reason = choice["finish_reason"]

    tool_calls = [_finish_tool_call(partial_calls[index]) for index in sorted(partial_calls)]
    return ModelTurn(
        content="".join(content_parts),
        tool_calls=[call for call in tool_calls if call.name],
        usage=usage,
        finish_reason=finish_reason,
    )


def _finish_tool_call(partial: dict[str, str]) -> ToolCall:
    raw = partial["arguments"].strip()
    call_id = partial["id"] or f"call_{uuid4().hex[:12]}"
    if not raw:
        return ToolCall(id=call_id, name=partial["name"], arguments={}, raw_arguments=raw)
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        return ToolCall(id=call_id, name=partial["name"], arguments={}, raw_arguments=raw, parse_error=str(exc))
    if not isinstance(parsed, dict):
        return ToolCall(
            id=call_id,
            name=partial["name"],
            arguments={},
            raw_arguments=raw,
            parse_error="arguments must be a JSON object",
        )
    return ToolCall(id=call_id, name=partial["name"], arguments=parsed, raw_arguments=raw)


__all__ = [
    "ChatModel",
    "LLMRequestError",
    "LegacyTextModel",
    "ModelTurn",
    "OpenAICompatibleModel",
    "ToolCall",
    "ToolsUnsupportedError",
    "mark_tools_unsupported",
    "parse_stream",
    "reset_tool_support",
    "tools_supported",
]
