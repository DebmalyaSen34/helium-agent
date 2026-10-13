import json
import unittest
from unittest.mock import MagicMock, patch

from config.providers import normalize_chat_url, provider_for_url
from core.llm import AgenticLoop, assistant_message
from core.model_client import (
    LLMRequestError,
    ModelTurn,
    ToolCall,
    looks_like_tools_unsupported,
    parse_stream,
)


class UrlNormalizationTests(unittest.TestCase):
    def test_base_urls_get_chat_completions(self):
        self.assertEqual(normalize_chat_url("https://api.deepseek.com"), "https://api.deepseek.com/chat/completions")
        self.assertEqual(normalize_chat_url("https://api.deepseek.com/"), "https://api.deepseek.com/chat/completions")
        self.assertEqual(normalize_chat_url("https://openrouter.ai/api/v1"), "https://openrouter.ai/api/v1/chat/completions")

    def test_full_urls_unchanged(self):
        url = "https://api.deepseek.com/chat/completions"
        self.assertEqual(normalize_chat_url(url), url)

    def test_ollama_native_endpoint_mapped_to_openai_endpoint(self):
        self.assertEqual(
            normalize_chat_url("http://localhost:11434/api/chat"),
            "http://localhost:11434/v1/chat/completions",
        )

    def test_provider_lookup(self):
        self.assertEqual(provider_for_url("https://api.deepseek.com/chat/completions").name, "deepseek")
        self.assertIsNone(provider_for_url("https://example.com/v1/chat/completions"))


class DeepSeekKeyEnvTests(unittest.TestCase):
    def test_deepseek_api_key_env_is_used_for_deepseek_url(self):
        import tempfile
        from pathlib import Path
        from config.runtime_config import RuntimeConfigStore

        env = {"LLM_API_URL": "https://api.deepseek.com", "LLM_MODEL": "deepseek-flash", "DEEPSEEK_API_KEY": "sk-ds"}
        with tempfile.TemporaryDirectory() as tmp, patch.dict("os.environ", env, clear=False):
            import os
            os.environ.pop("LLM_API_KEY", None)
            config = RuntimeConfigStore(config_path=Path(tmp) / "config.toml").load()
        self.assertEqual(config.api_key, "sk-ds")
        self.assertEqual(config.sources["api_key"], "env:DEEPSEEK_API_KEY")


class ReasoningContentTests(unittest.TestCase):
    def test_stream_collects_reasoning_separately(self):
        turn = parse_stream(
            [
                {"choices": [{"delta": {"reasoning_content": "Let me "}}]},
                {"choices": [{"delta": {"reasoning_content": "think."}}]},
                {"choices": [{"delta": {"content": "Answer"}}], "usage": None},
                {"choices": [{"delta": {}, "finish_reason": "stop"}], "usage": {"prompt_tokens": 3, "completion_tokens": 4}},
            ]
        )
        self.assertEqual(turn.content, "Answer")
        self.assertEqual(turn.reasoning_content, "Let me think.")
        self.assertEqual(turn.usage["completion_tokens"], 4)

    def test_assistant_message_includes_reasoning_only_when_present(self):
        self.assertNotIn("reasoning_content", assistant_message("hi"))
        self.assertEqual(assistant_message("hi", "why")["reasoning_content"], "why")

    def test_reasoning_is_sent_back_with_tool_call_history(self):
        class Model:
            supports_tools = True
            cache_key = ("https://api.deepseek.com/chat/completions", "deepseek-flash")

            def __init__(self):
                self.requests = []
                self.turns = [
                    ModelTurn(content="", reasoning_content="need the time", tool_calls=[ToolCall("c1", "get_time", {})]),
                    ModelTurn(content="It is noon.", reasoning_content="got it"),
                ]

            def complete(self, messages, tools=None, on_text=None):
                self.requests.append([dict(m) for m in messages])
                return self.turns.pop(0)

        model = Model()
        result = AgenticLoop(model=model, execute_tool_call=lambda a, confirm_tool=None: "12:00", tool_mode="native").run("sys", "time?")

        tool_call_message = model.requests[1][-2]
        self.assertEqual(tool_call_message["reasoning_content"], "need the time")
        self.assertEqual(result.final_reasoning, "got it")

    def test_history_without_reasoning_is_dropped_after_deepseek_400(self):
        class Model:
            supports_tools = True
            cache_key = ("https://api.deepseek.com/chat/completions", "deepseek-flash")

            def __init__(self):
                self.requests = []

            def complete(self, messages, tools=None, on_text=None):
                self.requests.append([dict(m) for m in messages])
                if len(self.requests) == 1:
                    raise LLMRequestError('HTTP 400: {"error": "missing reasoning_content in assistant message"}', 400)
                return ModelTurn(content="ok")

        model = Model()
        history = [{"role": "user", "content": "earlier"}, {"role": "assistant", "content": "earlier answer"}]
        result = AgenticLoop(model=model, tool_mode="native").run("sys", "now", history=history)

        self.assertEqual(result.final_answer, "ok")
        self.assertEqual(len(model.requests[0]), 4)
        self.assertEqual([m["role"] for m in model.requests[1]], ["system", "user"])


class ToolSupportClassificationTests(unittest.TestCase):
    def test_reasoning_content_400_is_not_tool_support(self):
        self.assertFalse(looks_like_tools_unsupported(400, "Missing reasoning_content for tool call message"))

    def test_tool_errors_are_tool_support(self):
        self.assertTrue(looks_like_tools_unsupported(400, "model does not support tools"))
        self.assertTrue(looks_like_tools_unsupported(404, "not found"))

    def test_unrelated_400_and_server_errors_are_not_tool_support(self):
        self.assertFalse(looks_like_tools_unsupported(400, "context length exceeded"))
        self.assertFalse(looks_like_tools_unsupported(500, "tool crashed"))
        self.assertFalse(looks_like_tools_unsupported(401, "invalid key"))


class ExtraParamsTests(unittest.TestCase):
    @patch("utils.check_llm_api.hit_api")
    def test_extra_params_are_sent(self, mock_hit_api):
        from core.model_client import OpenAICompatibleModel

        response = MagicMock(status_code=200)
        response.iter_lines.return_value = [b'data: {"choices": [{"delta": {"content": "x"}}]}', b"data: [DONE]"]
        mock_hit_api.return_value = response
        with patch.dict("core.llm.LLM_SETTINGS", {"extra_params": {"reasoning_effort": "high"}}):
            OpenAICompatibleModel(model="deepseek-flash", api_url="https://api.deepseek.com", api_key="k").complete([])
        self.assertEqual(mock_hit_api.call_args.args[0]["reasoning_effort"], "high")


if __name__ == "__main__":
    unittest.main()


class NativeProseMentioningActionsTests(unittest.TestCase):
    def _run(self, content):
        class Model:
            supports_tools = True
            cache_key = ("https://x", "m")

            def __init__(self):
                self.turns = [ModelTurn(content=content), ModelTurn(content="second")]

            def complete(self, messages, tools=None, on_text=None):
                return self.turns.pop(0)

        executed = []
        result = AgenticLoop(
            model=Model(),
            execute_tool_call=lambda a, confirm_tool=None: executed.append(a) or "ran",
            tool_mode="native",
        ).run("sys", "explain")
        return result, executed

    def test_prose_mentioning_action_tag_is_final_answer(self):
        text = "Text mode falls back to a `<action>` protocol when tools are unsupported."
        result, executed = self._run(text)
        self.assertEqual(result.final_answer, text)
        self.assertEqual(executed, [])

    def test_quoted_example_action_is_not_executed(self):
        text = 'Example:\n```\n<action>{"tool": "delete_file", "args": {"path": "x"}}</action>\n```\nThat is the format.'
        result, executed = self._run(text)
        self.assertEqual(executed, [])
        self.assertIn("That is the format.", result.final_answer)

    def test_bare_text_action_still_runs_in_native_mode(self):
        result, executed = self._run('<action>{"tool": "get_time", "args": {}}</action>')
        self.assertEqual(executed, [{"tool": "get_time", "args": {}}])
        self.assertEqual(result.final_answer, "second")


class ProviderKeyPrecedenceTests(unittest.TestCase):
    def _load(self, env, saved_key):
        import os
        import tempfile
        from pathlib import Path
        from config.runtime_config import RuntimeConfigStore

        with tempfile.TemporaryDirectory() as tmp, patch.dict("os.environ", env, clear=False):
            for name in ("LLM_API_KEY", "LLM_API_URL", "LLM_MODEL", "DEEPSEEK_API_KEY"):
                if name not in env:
                    os.environ.pop(name, None)
            store = RuntimeConfigStore(config_path=Path(tmp) / "config.toml")
            store.save(api_key=saved_key, api_url="http://localhost:11434/v1/chat/completions", model="llama3", use_playwright=False)
            return store.load()

    def test_provider_key_env_beats_a_key_saved_for_another_provider(self):
        config = self._load({"LLM_API_URL": "https://api.deepseek.com", "DEEPSEEK_API_KEY": "sk-ds"}, saved_key="ollama")
        self.assertEqual(config.api_key, "sk-ds")

    def test_explicit_llm_api_key_still_wins(self):
        config = self._load(
            {"LLM_API_URL": "https://api.deepseek.com", "DEEPSEEK_API_KEY": "sk-ds", "LLM_API_KEY": "sk-explicit"},
            saved_key="ollama",
        )
        self.assertEqual(config.api_key, "sk-explicit")
