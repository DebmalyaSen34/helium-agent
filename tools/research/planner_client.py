from __future__ import annotations

import json
from typing import Any

import requests

PLANNER_SYSTEM_PROMPT = "You are a research planning module. Output JSON only."


class ResearchPlannerLLM:
    """Asks the configured chat model for a research plan.

    `url` is a legacy override for a raw llama.cpp-style `/completion` endpoint;
    when omitted the planner uses the same OpenAI-compatible endpoint as chat.
    """

    def __init__(self, url: str | None = None, timeout: float = 30.0) -> None:
        self.url = url
        self.timeout = timeout

    def complete_plan(self, prompt: str) -> str:
        if self.url is None:
            from core.llm import call_llm_once

            reply, _tokens = call_llm_once(
                [
                    {"role": "system", "content": PLANNER_SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ]
            )
            return reply

        payload = {
            "prompt": prompt,
            "stream": False,
            "temperature": 0.1,
        }
        response = requests.post(self.url, json=payload, timeout=self.timeout)
        response.raise_for_status()
        return extract_completion_text(response.json())


def extract_completion_text(data: dict[str, Any]) -> str:
    if isinstance(data.get("content"), str):
        return data["content"]

    if isinstance(data.get("response"), str):
        return data["response"]

    if isinstance(data.get("choices"), list) and data["choices"]:
        choice = data["choices"][0]
        if isinstance(choice.get("text"), str):
            return choice["text"]
        message = choice.get("message") or {}
        if isinstance(message.get("content"), str):
            return message["content"]

    return json.dumps(data)
