"""Live checks against the real DeepSeek API.

Skipped unless HELIUM_LIVE_DEEPSEEK=1 and DEEPSEEK_API_KEY are set (a project
`.env` works). They make a few small requests to deepseek-flash.

    HELIUM_LIVE_DEEPSEEK=1 uv run pytest tests/live -q
"""

import os

import pytest
from dotenv import dotenv_values

pytestmark = pytest.mark.live

KEY = os.getenv("DEEPSEEK_API_KEY") or dotenv_values(".env").get("DEEPSEEK_API_KEY")
if os.getenv("HELIUM_LIVE_DEEPSEEK") != "1" or not KEY:
    pytest.skip("live DeepSeek tests are opt-in (HELIUM_LIVE_DEEPSEEK=1 + DEEPSEEK_API_KEY)", allow_module_level=True)

URL = "https://api.deepseek.com"
MODEL = os.getenv("HELIUM_LIVE_DEEPSEEK_MODEL", "deepseek-flash")


@pytest.fixture
def model():
    from core.model_client import OpenAICompatibleModel, reset_tool_support

    reset_tool_support()
    return OpenAICompatibleModel(model=MODEL, api_url=URL, api_key=KEY)


def test_stream_returns_content_reasoning_and_usage(model):
    turn = model.complete([{"role": "user", "content": "Reply with the single word: pong"}])
    assert "pong" in turn.content.lower()
    assert turn.reasoning_content  # thinking mode is on by default
    assert turn.usage.get("completion_tokens", 0) > 0


def test_native_tool_call_round_trip(model):
    from core.llm import AgenticLoop

    calls = []
    result = AgenticLoop(
        model=model,
        execute_tool_call=lambda action, confirm_tool=None: calls.append(action) or "12:00",
        tool_names=["get_time"],
        tool_mode="native",
    ).run("Use tools when they help.", "What time is it? Use the get_time tool.")
    assert [c["tool"] for c in calls] == ["get_time"]
    assert "12" in result.final_answer


def test_history_without_reasoning_is_accepted_with_tools(model):
    """Turns stored without reasoning_content (e.g. /code reports) must not break tool requests."""
    from core.llm import AgenticLoop

    history = [
        {"role": "user", "content": "/code create hello.py"},
        {"role": "assistant", "content": "Changed files:\n- hello.py"},
    ]
    result = AgenticLoop(
        model=model,
        execute_tool_call=lambda action, confirm_tool=None: "12:00",
        tool_names=["get_time"],
        tool_mode="native",
    ).run("Use tools when they help.", "Which file did you create, and what time is it?", history=history)
    assert "hello.py" in result.final_answer
