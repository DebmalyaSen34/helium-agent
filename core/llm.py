import requests
import logging
import time
import json
import os

from datetime import datetime
from collections.abc import Callable
from typing import Any

from dotenv import load_dotenv
from rich.console import Console

from config.settings import (
    ASSISTANT_PERSONA,
    API_MODEL,
)

from utils.check_llm_api import hit_api
from tools.registry import TOOL_PROMPT, execute_tool

load_dotenv()

logger = logging.getLogger(__name__)
console = Console()

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

conversation_history = []
MAX_HISTORY = 10


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


def stream_openrouter_response(payload: dict):

    response = hit_api(payload=payload, is_stream=True)

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


def build_messages(prompt: str) -> list[dict]:

    now = datetime.now().strftime("%B %d, %Y")

    messages = [
        {
            "role": "system",
            "content": (
                f"{ASSISTANT_PERSONA}\n\n"
                f"{TOOL_PROMPT}\n\n"
                f"Today's Date: {now}"
            ),
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


def generate_response(
    prompt: str,
    confirm_tool: Callable[[str, dict[str, Any], str], bool] | None = None,
    on_state: Callable[[str], None] | None = None,
    on_metrics: Callable[[dict[str, Any]], None] | None = None,
    on_tool_result: Callable[[str, str], None] | None = None,
    print_metrics: bool = True,
):

    global conversation_history

    start_time = time.time()

    think_end = None
    token_count = 0
    tools_used = []

    if on_state:
        on_state("Thinking")

    messages = build_messages(prompt)

    payload = {
        "model": os.getenv("API_MODEL", API_MODEL),
        "messages": messages,
        "temperature": 0.3,
        "stream": True,
        "stop": [
            "<end_of_turn>",
            "<start_of_turn>",
            "User:",
            "Current User:",
            "</start_of_turn>",
            "</end_of_turn>",
        ],
    }

    try:

        full_reply = ""
        current_sentence = ""
        is_tool_call = False

        for token in stream_openrouter_response(payload):

            if think_end is None:
                think_end = time.time()

            token_count += 1

            token = clean_token(token)

            full_reply += token
            # current_sentence += token

            # Detect tool call
            if full_reply.strip().startswith("{"):
                is_tool_call = True

            # Stream sentence-by-sentence
            # if (
            #     not is_tool_call
            #     and any(p in token for p in [".", "?", "!"])
            # ):
            #     yield clean_token(current_sentence.strip())
            #     current_sentence = ""

            if not is_tool_call:
                yield token

        if current_sentence.strip() and not is_tool_call:
            yield clean_token(current_sentence.strip())

        reply = full_reply.strip()

        # ---------------------------------------------------
        # TOOL EXECUTION
        # ---------------------------------------------------

        if is_tool_call:

            if on_state:
                on_state("Using tool")

            tool_name = "unknown"

            try:
                tool_data = json.loads(reply)

                tool_name = tool_data.get("tool", "unknown")

                tools_used.append(tool_name)

            except json.JSONDecodeError:
                pass

            tool_result = execute_tool(
                reply,
                confirm_tool=confirm_tool,
            )

            if tool_result:

                if on_tool_result:
                    on_tool_result(tool_name, tool_result)

                follow_up_messages = [
                    {
                        "role": "system",
                        "content": ASSISTANT_PERSONA,
                    },
                    {
                        "role": "user",
                        "content": (
                            f"The user asked: '{prompt}'.\n\n"
                            f"The previous tool returned:\n\n"
                            f"{tool_result}\n\n"
                            "Based on the tool result, answer directly.\n"
                            "Do NOT summarize articles.\n"
                            "Do NOT explain tools.\n"
                            "Be concise and factual."
                        ),
                    },
                ]

                follow_up_payload = {
                    "model": os.getenv("API_MODEL", API_MODEL),
                    "messages": follow_up_messages,
                    "temperature": 0.3,
                    "stream": True,
                }

                final_reply = ""
                follow_up_sentence = ""

                for token in stream_openrouter_response(
                    follow_up_payload
                ):

                    token_count += 1

                    token = clean_token(token)

                    final_reply += token
                    follow_up_sentence += token

                    if any(p in token for p in [".", "?", "!"]):
                        yield clean_token(
                            follow_up_sentence.strip()
                        )
                        follow_up_sentence = ""

                if follow_up_sentence.strip():
                    yield clean_token(
                        follow_up_sentence.strip()
                    )

                reply = clean_token(final_reply.strip())

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

        gen_time = (
            (end_time - start_time) - think_time
            if think_time
            else 1
        )

        total_time = end_time - start_time

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