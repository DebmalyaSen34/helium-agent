import contextvars
import json
import logging
import re
import time

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from collections.abc import Callable
from typing import Any

from utils.theme import make_console
from config.runtime_config import load_llm_runtime_config

from config.settings import (
    AGENT_SETTINGS,
    API_MODEL,
    LLM_SETTINGS,
)

from core.model_client import (
    ChatModel,
    LLMRequestError,
    LegacyTextModel,
    ModelTurn,
    OpenAICompatibleModel,
    ToolsUnsupportedError,
    mark_tools_unsupported,
    tools_supported,
)
from utils.check_llm_api import hit_api
from tools.registry import (
    build_openai_tools,
    execute_tool_call as registry_execute_tool_call,
    render_text_protocol_prompt,
    tool_permission,
    tools_for,
)
from utils.parser import extract_json, strip_reasoning

logger = logging.getLogger(__name__)
console = make_console()

conversation_history = []
MAX_HISTORY = 10
MAX_AGENTIC_TURNS = int(AGENT_SETTINGS.get("chat_max_turns", 12))
PARALLEL_TOOL_WORKERS = 4
# Marked safe, but they run whole subagent loops that may ask the user for
# confirmation, so they must never run concurrently with other calls.
SEQUENTIAL_TOOLS = frozenset({"create_subagent", "delegate_task", "delete_subagent", "list_subagents"})

ConfirmTool = Callable[[str, dict[str, Any], str], bool]
EventCallback = Callable[[str, Any], None]


@dataclass(frozen=True)
class AgenticLoopResult:
    final_answer: str
    stop_reason: str
    tools_used: list[str]
    observations: list[str]
    usage: dict[str, int] = field(default_factory=dict)
    messages: list[dict[str, Any]] = field(default_factory=list)
    final_reasoning: str = ""


@dataclass
class _PendingCall:
    call_id: str
    name: str
    args: dict[str, Any]
    parse_error: str | None = None


def assistant_message(content: str, reasoning: str = "", tool_calls: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """An assistant transcript entry. `reasoning_content` is kept when the provider sent one,
    because DeepSeek-style APIs reject tool requests whose history drops it."""
    message: dict[str, Any] = {"role": "assistant", "content": content}
    if reasoning:
        message["reasoning_content"] = reasoning
    if tool_calls:
        message["tool_calls"] = tool_calls
    return message


def truncate_observation(text: str, limit: int) -> str:
    """Keep the head and tail of long tool output so errors at the end survive."""
    if limit <= 0 or len(text) <= limit:
        return text
    head = (limit * 2) // 3
    tail = limit - head
    omitted = len(text) - head - tail
    return f"{text[:head]}\n... [{omitted} characters of tool output omitted] ...\n{text[-tail:]}"


class AgenticLoop:
    """Runs model turns and tool calls until the model gives a final answer.

    Two protocols are supported:
    - native: tool schemas go in the request and the model returns `tool_calls`;
      results go back as `role: tool` messages. Several calls per turn are allowed.
    - text: the model writes `<action>{"tool": ..., "args": ...}</action>` and the
      observation comes back as a user message. Used when the endpoint has no tool
      support, when `llm.tool_mode = "text"`, or with a plain `ask_model` callable.
    """

    def __init__(
        self,
        ask_model: Callable[[list[dict[str, Any]]], Any] | None = None,
        execute_tool_call: Callable[..., str | None] | None = None,
        max_turns: int = MAX_AGENTIC_TURNS,
        *,
        model: ChatModel | None = None,
        tool_names: list[str] | None = None,
        on_event: EventCallback | None = None,
        tool_mode: str | None = None,
        max_tool_output_chars: int | None = None,
        context_budget_chars: int | None = None,
        parallel_safe_tools: bool | None = None,
    ):
        if model is None:
            if ask_model is None:
                raise ValueError("AgenticLoop needs either ask_model or model.")
            model = LegacyTextModel(ask_model)
        self.model = model
        self.execute_tool_call = execute_tool_call or _default_execute_tool_call
        self.max_turns = max_turns
        self.tool_names = list(tool_names) if tool_names else None
        self.on_event = on_event
        self.tool_mode = tool_mode or str(LLM_SETTINGS.get("tool_mode", "auto"))
        self.max_tool_output_chars = int(
            max_tool_output_chars if max_tool_output_chars is not None else LLM_SETTINGS.get("max_tool_output_chars", 12_000)
        )
        self.context_budget_chars = int(
            context_budget_chars if context_budget_chars is not None else LLM_SETTINGS.get("context_budget_chars", 300_000)
        )
        self.parallel_safe_tools = bool(
            parallel_safe_tools if parallel_safe_tools is not None else AGENT_SETTINGS.get("parallel_safe_tools", True)
        )

    # -- public ------------------------------------------------------------

    def run(
        self,
        system_prompt: str,
        user_prompt: str,
        history: list[dict[str, str]] | None = None,
        confirm_tool: ConfirmTool | None = None,
    ) -> AgenticLoopResult:
        native = self._use_native()
        messages: list[dict[str, Any]] = [{"role": "system", "content": self._system_content(system_prompt, native)}]
        if history:
            messages.extend(dict(message) for message in history)
        self._history_len = len(history or [])
        messages.append({"role": "user", "content": self._initial_user_prompt(user_prompt)})

        tools_used: list[str] = []
        observations: list[str] = []
        usage = {"prompt_tokens": 0, "completion_tokens": 0, "requests": 0}

        for _ in range(self.max_turns):
            self._compact(messages)
            turn, native = self._complete(messages, native, system_prompt, usage)
            content = strip_reasoning(clean_token(turn.content or ""))

            if native and turn.tool_calls:
                pending = [
                    _PendingCall(call.id, call.name, call.arguments, call.parse_error)
                    for call in turn.tool_calls
                ]
                messages.append(
                    assistant_message(
                        content,
                        turn.reasoning_content,
                        [
                            {
                                "id": call.id,
                                "type": "function",
                                "function": {"name": call.name, "arguments": call.raw_arguments or json.dumps(call.arguments)},
                            }
                            for call in turn.tool_calls
                        ],
                    )
                )
                results = self._run_calls(pending, confirm_tool)
                for call, result in zip(pending, results):
                    tools_used.append(call.name)
                    observations.append(result)
                    messages.append({"role": "tool", "tool_call_id": call.call_id, "content": result})
                continue

            if native and not BARE_TEXT_ACTION_RE.match(content):
                # In native mode a text action is only a fallback for models that ignore
                # `tools`, so it must be the whole reply. Prose that mentions or quotes
                # `<action>` blocks is a final answer, not a tool call.
                action_status, action = "none", None
            else:
                action_status, action = self._extract_action(content)

            if action_status == "none":
                return self._result(content, "final", tools_used, observations, usage, messages, turn.reasoning_content)

            messages.append(assistant_message(content, turn.reasoning_content))

            if action_status == "invalid" or action is None:
                observation = (
                    "Invalid tool action. Return exactly one valid JSON object inside "
                    "<action> and </action> with 'tool' and 'args' keys."
                )
                observations.append(observation)
                messages.append({"role": "user", "content": self._observation_prompt("tool action", observation)})
                continue

            tool_name = str(action.get("tool", "unknown"))
            tools_used.append(tool_name)
            result = self._run_calls([_PendingCall("", tool_name, action.get("args") or {})], confirm_tool)[0]
            observations.append(result)
            messages.append({"role": "user", "content": self._observation_prompt(tool_name, result)})

        final_prompt = (
            "You have reached the tool turn limit. Give the best concise answer you can "
            "from the observations above. If the task is incomplete, say exactly what remains."
        )
        messages.append({"role": "user", "content": final_prompt})
        turn, native = self._complete(messages, native, system_prompt, usage)
        final_answer = strip_reasoning(clean_token(turn.content or ""))
        if not final_answer:
            final_answer = "I reached the tool turn limit before finishing. The task is incomplete."
        return self._result(final_answer, "max_turns", tools_used, observations, usage, messages, turn.reasoning_content)

    # -- model calls ---------------------------------------------------------

    def _use_native(self) -> bool:
        if not getattr(self.model, "supports_tools", False):
            return False
        if self.tool_mode == "text":
            return False
        if self.tool_mode == "auto":
            return tools_supported(getattr(self.model, "cache_key", ("", "")))
        return True

    def _system_content(self, system_prompt: str, native: bool) -> str:
        if native:
            return system_prompt
        return f"{system_prompt}\n\n{render_text_protocol_prompt(self.tool_names)}"

    def _complete(
        self,
        messages: list[dict[str, Any]],
        native: bool,
        system_prompt: str,
        usage: dict[str, int],
    ) -> tuple[ModelTurn, bool]:
        on_text = self._emit_text if native else None
        try:
            tools = build_openai_tools(self.tool_names) if native else None
            try:
                turn = self.model.complete(messages, tools=tools, on_text=on_text)
            except LLMRequestError as exc:
                if not self._drop_history_missing_reasoning(messages, exc):
                    raise
                turn = self.model.complete(messages, tools=tools, on_text=on_text)
        except ToolsUnsupportedError as exc:
            if self.tool_mode == "native":
                raise
            logger.info("Falling back to the text tool protocol: %s", exc)
            native = False
            messages[0]["content"] = self._system_content(system_prompt, native)
            turn = self.model.complete(_flatten_native_messages(messages), tools=None, on_text=None)
            # Only remember the downgrade once the text request actually worked.
            mark_tools_unsupported(getattr(self.model, "cache_key", ("", "")))

        usage["requests"] += 1
        for key in ("prompt_tokens", "completion_tokens"):
            usage[key] += int((turn.usage or {}).get(key) or 0)
        self._emit("usage", dict(turn.usage or {}))
        return turn, native

    def _drop_history_missing_reasoning(self, messages: list[dict[str, Any]], exc: LLMRequestError) -> bool:
        """DeepSeek rejects tool requests when earlier assistant turns lack reasoning_content
        (e.g. they came from another model). Drop that prior-session history once and retry."""
        if isinstance(exc, ToolsUnsupportedError) or "reasoning_content" not in str(exc):
            return False
        history_len = getattr(self, "_history_len", 0)
        if not history_len:
            return False
        logger.info("Dropping %d earlier history messages that lack reasoning_content.", history_len)
        del messages[1 : 1 + history_len]
        self._history_len = 0
        return True

    # -- tool execution ------------------------------------------------------

    def _run_calls(self, calls: list[_PendingCall], confirm_tool: ConfirmTool | None) -> list[str]:
        def run_one(call: _PendingCall) -> str:
            self._emit("tool_start", {"name": call.name, "args": call.args})
            if call.parse_error:
                result = (
                    f"Error: could not parse the arguments for '{call.name}' as JSON ({call.parse_error}). "
                    "Call the tool again with a valid JSON object."
                )
            else:
                raw = self.execute_tool_call({"tool": call.name, "args": call.args}, confirm_tool=confirm_tool)
                result = str(raw) if raw is not None else "Tool returned no result."
            result = truncate_observation(result, self.max_tool_output_chars)
            self._emit("tool_end", {"name": call.name, "result": result})
            return result

        parallel = (
            self.parallel_safe_tools
            and len(calls) > 1
            and all(
                not call.parse_error
                and call.name not in SEQUENTIAL_TOOLS
                and tool_permission(call.name, call.args) == "safe"
                for call in calls
            )
        )
        if not parallel:
            return [run_one(call) for call in calls]

        with ThreadPoolExecutor(max_workers=min(PARALLEL_TOOL_WORKERS, len(calls))) as pool:
            futures = [pool.submit(contextvars.copy_context().run, run_one, call) for call in calls]
            return [future.result() for future in futures]

    # -- context management --------------------------------------------------

    def _compact(self, messages: list[dict[str, Any]]) -> None:
        """Elide the oldest tool outputs once the transcript exceeds the budget."""
        total = sum(
            len(str(message.get("content") or "")) + len(str(message.get("reasoning_content") or ""))
            for message in messages
        )
        if total <= self.context_budget_chars:
            return
        protected_tail = 4
        for message in messages[1:-protected_tail]:
            if total <= self.context_budget_chars:
                break
            content = str(message.get("content") or "")
            is_tool_output = message.get("role") == "tool" or (
                message.get("role") == "user" and content.startswith("Observation from")
            )
            if not is_tool_output or content.startswith("[earlier tool output elided"):
                continue
            placeholder = f"[earlier tool output elided: {len(content)} characters]"
            message["content"] = placeholder
            total -= len(content) - len(placeholder)

    # -- helpers -------------------------------------------------------------

    def _emit(self, kind: str, payload: Any) -> None:
        if self.on_event:
            try:
                self.on_event(kind, payload)
            except Exception:
                logger.debug("on_event handler failed", exc_info=True)

    def _emit_text(self, text: str) -> None:
        self._emit("text_delta", text)

    def _result(self, answer, stop_reason, tools_used, observations, usage, messages, reasoning="") -> AgenticLoopResult:
        return AgenticLoopResult(
            final_answer=answer,
            stop_reason=stop_reason,
            tools_used=tools_used,
            observations=observations,
            usage=dict(usage),
            messages=messages,
            final_reasoning=reasoning or "",
        )

    def _extract_action(self, reply: str) -> tuple[str, dict[str, Any] | None]:
        looks_like_action = "<action>" in reply or reply.strip().startswith("{")
        if not looks_like_action:
            return "none", None

        action = extract_json(reply)
        if not isinstance(action, dict) or "tool" not in action:
            if "<action>" not in reply:
                # A reply that is (or starts with) ordinary JSON, e.g. the user asked
                # for JSON output, is an answer rather than a malformed tool call.
                return "none", None
            return "invalid", None

        args = action.get("args", {})
        if args is None:
            action["args"] = {}
        elif not isinstance(args, dict):
            return "invalid", None

        return "action", action

    @staticmethod
    def _initial_user_prompt(user_prompt: str) -> str:
        return (
            f"{user_prompt}\n\n"
            "<agentic_loop>\n"
            "Work in a loop: gather context, take useful actions, observe the results, "
            "verify when the task touches code, then answer when done. "
            "If no tool is needed, answer directly.\n"
            "For coding tasks, read relevant files first, make focused edits, "
            "and run the smallest useful test or verification command after changes.\n"
            "</agentic_loop>"
        )

    @staticmethod
    def _observation_prompt(tool_name: str, observation: str) -> str:
        return (
            f"Observation from {tool_name}:\n{observation}\n\n"
            "Continue the task. Call one more tool if needed, or give the final answer if complete."
        )


def _flatten_native_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Rewrite native tool-call history into plain messages for text-protocol retries."""
    if not any(message.get("role") == "tool" or message.get("tool_calls") for message in messages):
        return messages
    flattened: list[dict[str, Any]] = []
    for message in messages:
        if message.get("tool_calls"):
            calls = "\n".join(
                f"<action>{json.dumps({'tool': c['function']['name'], 'args': _loads_object(c['function']['arguments'])})}</action>"
                for c in message["tool_calls"]
            )
            flattened.append({"role": "assistant", "content": f"{message.get('content') or ''}\n{calls}".strip()})
        elif message.get("role") == "tool":
            flattened.append({"role": "user", "content": f"Observation:\n{message.get('content')}"})
        else:
            flattened.append(message)
    messages[:] = flattened
    return messages


def _loads_object(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    try:
        value = json.loads(raw or "{}")
    except (TypeError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


CHAT_TEMPLATE_TOKENS = (
    "<end_of_turn>",
    "<start_of_turn>",
    "</start_of_turn>",
    "</end_of_turn>",
)

# A reply that consists only of an (optional) <thought> and one <action> block.
BARE_TEXT_ACTION_RE = re.compile(
    r"^\s*(?:<thought>.*?</thought>\s*)?<action>\s*\{.*\}\s*</action>\s*$",
    re.DOTALL,
)

def clean_token(token: str) -> str:
    """Strip chat-template control tokens that some local models leak into text."""
    for tag in CHAT_TEMPLATE_TOKENS:
        token = token.replace(tag, "")
    return token


def stream_openrouter_response(payload: dict, *, api_url: str | None = None, api_key: str | None = None):

    response = hit_api(payload=payload, is_stream=True, api_url=api_url, api_key=api_key)

    if response is None:
        raise Exception("Failed to get response from the LLM API.")

    response.raise_for_status()

    for line in response.iter_lines():
        if not line:
            continue

        line = line.decode("utf-8")

        if not line.startswith("data: "):
            continue

        data_str = line[6:]

        if data_str == "[DONE]":
            break

        try:
            data = json.loads(data_str)

            if "usage" in data and data["usage"]:
                yield {
                    "usage": data["usage"],
                }
                continue

            token = (
                (data.get("choices") or [{}])[0]
                .get("delta", {})
                .get("content", "")
            )

            if not token:
                continue

            yield token

        except json.JSONDecodeError:
            continue


def build_system_prompt(prompt: str, skills: list[Any] | None = None) -> str:
    from core.prompts import build_system_prompt as build_prompt

    return build_prompt("chat", user_prompt=prompt, skills=skills)


def build_messages(prompt: str) -> list[dict]:
    messages = [{"role": "system", "content": build_system_prompt(prompt)}]
    messages.extend(conversation_history)
    messages.append({"role": "user", "content": prompt})
    return messages


def call_llm_once(messages: list[dict[str, str]]) -> tuple[str, int]:
    """Plain completion without tools. Returns (reply, completion_tokens)."""
    from core.session import SESSION

    runtime_config = load_llm_runtime_config()
    payload = {
        "model": SESSION.model_override or runtime_config.model or API_MODEL,
        "messages": messages,
        "temperature": 0.3,
        "stream": True,
        "stream_options": {
            "include_usage": True,
        },
    }
    stop_sequences = LLM_SETTINGS.get("stop_sequences") or []
    if stop_sequences:
        payload["stop"] = list(stop_sequences)

    full_reply = ""
    token_count = 0

    for item in stream_openrouter_response(
        payload,
        api_url=runtime_config.api_url,
        api_key=runtime_config.api_key,
    ):
        if isinstance(item, dict) and "usage" in item:
            token_count += item["usage"].get("completion_tokens", 0)
            continue

        full_reply += clean_token(item)

    return strip_reasoning(clean_token(full_reply)), token_count


def execute_agent_tool(
    action: dict[str, Any],
    confirm_tool: ConfirmTool | None = None,
) -> str | None:
    return registry_execute_tool_call(
        str(action.get("tool", "")),
        action.get("args") or {},
        confirm_tool,
    )


def _default_execute_tool_call(action: dict[str, Any], confirm_tool: ConfirmTool | None = None) -> str | None:
    # Looked up at call time so tests and wrappers can patch execute_agent_tool.
    return execute_agent_tool(action, confirm_tool=confirm_tool)


def default_model() -> ChatModel:
    """Model for the configured protocol; text mode keeps the simple call_llm_once path."""
    if str(LLM_SETTINGS.get("tool_mode", "auto")) == "text":
        return LegacyTextModel(lambda messages: call_llm_once(messages))
    return OpenAICompatibleModel()


def run_agent(
    system_prompt: str,
    user_prompt: str,
    *,
    history: list[dict[str, str]] | None = None,
    confirm_tool: ConfirmTool | None = None,
    tool_names: list[str] | None = None,
    max_turns: int = MAX_AGENTIC_TURNS,
    on_event: EventCallback | None = None,
    execute_tool_call: Callable[..., str | None] | None = None,
    model: ChatModel | None = None,
    ask_model: Callable[[list[dict[str, Any]]], Any] | None = None,
) -> AgenticLoopResult:
    """Shared entry point for chat, /code, skills, and subagents."""
    from core.session import SESSION

    if model is None and ask_model is None:
        model = default_model()

    loop = AgenticLoop(
        ask_model=ask_model,
        execute_tool_call=execute_tool_call,
        max_turns=max_turns,
        model=model,
        tool_names=tool_names,
        on_event=on_event,
    )
    result = loop.run(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        history=history,
        confirm_tool=confirm_tool,
    )
    SESSION.usage.add(result.usage, requests=result.usage.get("requests", 0), tool_calls=len(result.tools_used))
    return result


def remember_turn(user_prompt: str, reply: str, *, persist: bool = True, reasoning: str = "") -> None:
    """Append a finished exchange to the conversation history (and the workspace memory)."""
    global conversation_history

    if persist:
        from tools.memory_ops import record_turn

        record_turn("user", user_prompt)
        record_turn("assistant", reply)

    conversation_history.append({"role": "user", "content": user_prompt})
    conversation_history.append(assistant_message(reply, reasoning))
    if len(conversation_history) > MAX_HISTORY:
        conversation_history[:] = conversation_history[-MAX_HISTORY:]


def generate_response(
    prompt: str,
    confirm_tool: ConfirmTool | None = None,
    on_state: Callable[[str], None] | None = None,
    on_metrics: Callable[[dict[str, Any]], None] | None = None,
    on_tool_result: Callable[[str, str], None] | None = None,
    print_metrics: bool = True,
    skills: list[Any] | None = None,
    on_token: Callable[[str], None] | None = None,
    on_event: EventCallback | None = None,
    history_prompt: str | None = None,
):
    """Run one chat turn and yield the reply.

    `history_prompt` is what gets remembered for later turns; pass the user's own
    words when `prompt` was expanded (e.g. with pasted reference text) so the
    expansion isn't resent with every future request.
    """
    start_time = time.time()
    tool_execution_time = 0.0
    tool_started_at: list[float] = []

    if on_state:
        on_state("Thinking")

    def handle_event(kind: str, payload: Any) -> None:
        nonlocal tool_execution_time
        if kind == "tool_start":
            tool_started_at.append(time.time())
            if on_state:
                on_state(f"Using {payload['name']}")
        elif kind == "tool_end":
            if tool_started_at:
                tool_execution_time += time.time() - tool_started_at.pop()
            if on_tool_result and payload["result"]:
                on_tool_result(payload["name"], payload["result"])
            if on_state:
                on_state("Thinking")
        elif kind == "text_delta" and on_token:
            on_token(payload)
        if on_event:
            on_event(kind, payload)

    try:
        system_prompt = build_system_prompt(prompt, skills=skills)
        think_end = time.time()

        loop_result = run_agent(
            system_prompt,
            prompt,
            history=conversation_history,
            confirm_tool=confirm_tool,
            tool_names=tools_for("chat"),
            on_event=handle_event,
        )
        reply = loop_result.final_answer

        if on_state:
            on_state("Responding")

        if reply:
            yield reply

        remember_turn(history_prompt or prompt, reply, reasoning=loop_result.final_reasoning)

        end_time = time.time()
        total_time = end_time - start_time
        think_time = think_end - start_time
        gen_time = total_time - think_time - tool_execution_time
        token_count = int(loop_result.usage.get("completion_tokens", 0))
        tps = token_count / gen_time if gen_time > 0 else 0
        tools_str = ", ".join(loop_result.tools_used) if loop_result.tools_used else "None"

        metrics_data = {
            "total_time": total_time,
            "think_time": think_time,
            "gen_time": gen_time,
            "tokens": token_count,
            "prompt_tokens": int(loop_result.usage.get("prompt_tokens", 0)),
            "tps": tps,
            "tools_used": tools_str,
        }

        if on_metrics:
            on_metrics(metrics_data)

        if print_metrics:
            console.print(
                f"\n\n[bold dim]Run Metrics:[/bold dim] "
                f"Total Time: {total_time:.2f}s | "
                f"Think Time: {think_time:.2f}s | "
                f"Gen Time: {gen_time:.2f}s | "
                f"Tokens: {token_count} | "
                f"TPS: {tps:.2f} | "
                f"Tools Used: {tools_str}"
            )

    except Exception as e:
        logger.error("LLM request failed: %s", e)
        yield f"I am having trouble connecting to my brain. LLM request failed: {e}"
