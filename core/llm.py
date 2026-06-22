import logging
import time
import json

from dataclasses import dataclass
from datetime import datetime
from collections.abc import Callable
from typing import Any

from rich.console import Console
from config.runtime_config import load_llm_runtime_config

from config.settings import (
    ASSISTANT_PERSONA,
    API_MODEL
)

from utils.check_llm_api import hit_api
from tools.registry import TOOL_PROMPT, execute_tool
from utils.parser import extract_json

logger = logging.getLogger(__name__)
console = Console()

conversation_history = []
MAX_HISTORY = 10
MAX_AGENTIC_TURNS = 6


@dataclass(frozen=True)
class AgenticLoopResult:
    final_answer: str
    stop_reason: str
    tools_used: list[str]
    observations: list[str]


class AgenticLoop:
    def __init__(
        self,
        ask_model: Callable[[list[dict[str, str]]], str],
        execute_tool_call: Callable[..., str | None],
        max_turns: int = MAX_AGENTIC_TURNS,
    ):
        self.ask_model = ask_model
        self.execute_tool_call = execute_tool_call
        self.max_turns = max_turns

    def run(
        self,
        system_prompt: str,
        user_prompt: str,
        history: list[dict[str, str]] | None = None,
        confirm_tool: Callable[[str, dict[str, Any], str], bool] | None = None,
    ) -> AgenticLoopResult:
        messages = [{"role": "system", "content": system_prompt}]
        if history:
            messages.extend(history)
        messages.append({"role": "user", "content": self._initial_user_prompt(user_prompt)})

        tools_used: list[str] = []
        observations: list[str] = []

        for _ in range(self.max_turns):
            reply = clean_token(self.ask_model(messages).strip())
            action_status, action = self._extract_action(reply)

            if action_status == "none":
                return AgenticLoopResult(
                    final_answer=reply,
                    stop_reason="final",
                    tools_used=tools_used,
                    observations=observations,
                )

            messages.append({"role": "assistant", "content": reply})

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
            tool_result = self.execute_tool_call(action, confirm_tool=confirm_tool)
            observation = str(tool_result) if tool_result is not None else "Tool returned no result."
            observations.append(observation)
            messages.append({"role": "user", "content": self._observation_prompt(tool_name, observation)})

        final_prompt = (
            "You have reached the tool turn limit. Give the best concise answer you can "
            "from the observations above. If the task is incomplete, say exactly what remains."
        )
        messages.append({"role": "user", "content": final_prompt})
        final_answer = clean_token(self.ask_model(messages).strip())
        return AgenticLoopResult(
            final_answer=final_answer,
            stop_reason="max_turns",
            tools_used=tools_used,
            observations=observations,
        )

    def _extract_action(self, reply: str) -> tuple[str, dict[str, Any] | None]:
        looks_like_action = "<action" in reply or '"tool"' in reply or reply.strip().startswith("{")
        if not looks_like_action:
            return "none", None

        action = extract_json(reply)
        if not isinstance(action, dict) or "tool" not in action:
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
            "Work in a simple loop: gather context, take one useful action, observe the result, "
            "verify when the task touches code, then answer when done.\n"
            "Use at most one tool per turn. If no tool is needed, answer directly.\n"
            "For coding tasks, prefer reading relevant files first, making focused edits, "
            "and running the smallest useful test or verification command after changes.\n"
            "</agentic_loop>"
        )

    @staticmethod
    def _observation_prompt(tool_name: str, observation: str) -> str:
        return (
            f"Observation from {tool_name}:\n{observation}\n\n"
            "Continue the task. Call one more tool if needed, or give the final answer if complete."
        )


def clean_token(token: str) -> str:
    tags = [
        "<end_of_turn>",
        "<start_of_turn>",
        "User:",
        "Current User:",
        "[Gemma]:",
        "model\n",
        "</start_of_turn>",
        "</end_of_turn>",
        "<think>",
        "</think>",
    ]

    for tag in tags:
        token = token.replace(tag, "")

    return token


def stream_openrouter_response(payload: dict, *, api_url: str | None = None, api_key: str | None = None):

    response = hit_api(payload=payload, is_stream=True, api_url=api_url, api_key=api_key)

    if response is None:
        raise Exception("Failed to get response from OpenRouter API.")

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
                data.get("choices", [{}])[0]
                .get("delta", {})
                .get("content", "")
            )

            if not token:
                continue

            yield token

        except json.JSONDecodeError:
            continue


def build_system_prompt(prompt: str, skills: list[Any] | None = None) -> str:
    from tools.memory_ops import get_relevant_memories

    now = datetime.now().strftime("%B %d, %Y")

    system_content = (
        f"{ASSISTANT_PERSONA}\n\n"
        f"{TOOL_PROMPT}\n\n"
        f"Today's Date: {now}"
    )

    # Inject model-invoked (contextual) skills into system prompt
    if skills:
        contextual = [s for s in skills if not s.is_slash_command]
        if contextual:
            lines = []
            for s in contextual:
                hint = f" (trigger: {s.trigger})" if s.trigger else ""
                lines.append(f"- {s.name}{hint}: {s.description}")
            skills_text = "\n".join(lines)
            system_content += f"\n\n=== AVAILABLE SKILLS ===\n{skills_text}\n========================"

    memories = get_relevant_memories(prompt)
    if memories:
        memories_text = "\n".join(f"- {m}" for m in memories)
        system_content += f"\n\n=== RELEVANT MEMORIES ===\n{memories_text}\n========================"

    return system_content


def build_messages(prompt: str) -> list[dict]:
    system_content = build_system_prompt(prompt)

    messages = [
        {
            "role": "system",
            "content": system_content,
        }
    ]

    # Add conversation history
    messages.extend(conversation_history)

    # Add current user message
    messages.append(
        {
            "role": "user",
            "content": prompt,
        }
    )

    return messages


def call_llm_once(messages: list[dict[str, str]]) -> tuple[str, int]:
    runtime_config = load_llm_runtime_config()
    payload = {
        "model": runtime_config.model or API_MODEL,
        "messages": messages,
        "temperature": 0.3,
        "stream": True,
        "stream_options": {
            "include_usage": True,
        },
        "stop": [
            "<end_of_turn>",
            "<start_of_turn>",
            "User:",
            "Current User:",
        ],
    }

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

    return clean_token(full_reply.strip()), token_count


def execute_agent_tool(
    action: dict[str, Any],
    confirm_tool: Callable[[str, dict[str, Any], str], bool] | None = None,
) -> str | None:
    return execute_tool(
        json.dumps(action),
        confirm_tool=confirm_tool,
    )


def generate_response(
    prompt: str,
    confirm_tool: Callable[[str, dict[str, Any], str], bool] | None = None,
    on_state: Callable[[str], None] | None = None,
    on_metrics: Callable[[dict[str, Any]], None] | None = None,
    on_tool_result: Callable[[str, str], None] | None = None,
    print_metrics: bool = True,
    skills: list[Any] | None = None,
):

    global conversation_history

    start_time = time.time()

    think_end = None
    token_count = 0
    tools_used = []
    tool_execution_time=0.0

    if on_state:
        on_state("Thinking")

    try:
        system_prompt = build_system_prompt(prompt, skills=skills)
        think_end = time.time()

        def ask_model(loop_messages: list[dict[str, str]]) -> str:
            nonlocal token_count
            reply_text, tokens = call_llm_once(loop_messages)
            token_count += tokens
            return reply_text

        def run_tool(
            action: dict[str, Any],
            confirm_tool: Callable[[str, dict[str, Any], str], bool] | None = None,
        ) -> str | None:
            nonlocal tool_execution_time
            tool_name = str(action.get("tool", "unknown"))
            if on_state:
                on_state(f"Using {tool_name}")

            tool_start_time = time.time()
            tool_result = execute_agent_tool(action, confirm_tool=confirm_tool)
            tool_execution_time += time.time() - tool_start_time

            if on_tool_result and tool_result:
                on_tool_result(tool_name, tool_result)

            return tool_result

        loop = AgenticLoop(
            ask_model=ask_model,
            execute_tool_call=run_tool,
            max_turns=MAX_AGENTIC_TURNS,
        )
        loop_result = loop.run(
            system_prompt=system_prompt,
            user_prompt=prompt,
            history=conversation_history,
            confirm_tool=confirm_tool,
        )
        reply = loop_result.final_answer
        tools_used.extend(loop_result.tools_used)

        if on_state:
            on_state("Responding")

        if reply:
            yield reply

        # ---------------------------------------------------
        # SAVE CONVERSATION HISTORY
        # ---------------------------------------------------

        conversation_history.append(
            {
                "role": "user",
                "content": prompt,
            }
        )

        conversation_history.append(
            {
                "role": "assistant",
                "content": reply,
            }
        )

        # Trim history
        if len(conversation_history) > MAX_HISTORY:
            conversation_history = conversation_history[-MAX_HISTORY:]

        # ---------------------------------------------------
        # METRICS
        # ---------------------------------------------------

        end_time = time.time()

        think_time = (
            (think_end - start_time)
            if think_end
            else 0
        )

        # gen_time = (
        #    (end_time - start_time) - think_time
        #    if think_time
        #    else 1
        # )

        total_time = end_time - start_time

        gen_time = total_time - think_time - tool_execution_time

        tps = (
            token_count / gen_time
            if gen_time > 0
            else 0
        )

        tools_str = (
            ", ".join(tools_used)
            if tools_used
            else "None"
        )

        metrics_data = {
            "total_time": total_time,
            "think_time": think_time,
            "gen_time": gen_time,
            "tokens": token_count,
            "tps": tps,
            "tools_used": tools_str,
        }

        if on_metrics:
            on_metrics(metrics_data)

        if print_metrics:

            metrics = (
                f"\n\n[bold dim]Run Metrics:[/bold dim] "
                f"Total Time: {total_time:.2f}s | "
                f"Think Time: {think_time:.2f}s | "
                f"Gen Time: {gen_time:.2f}s | "
                f"Tokens: {token_count} | "
                f"TPS: {tps:.2f} | "
                f"Tools Used: {tools_str}"
            )

            console.print(metrics)

    except Exception as e:

        logger.error(f"LLM request failed: {e}")

        yield "I am having trouble connecting to my brain."
