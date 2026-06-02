import concurrent.futures
import unittest
from unittest.mock import patch

from utils import start_animation
from utils.system_check import check_llm_api


class StartupCheckTests(unittest.TestCase):
    @patch("utils.system_check.hit_api")
    def test_llm_check_uses_runtime_config(self, mock_hit_api):
        from config.runtime_config import LlmRuntimeConfig

        mock_hit_api.return_value.status_code = 200
        config = LlmRuntimeConfig(
            api_key="key",
            api_url="http://127.0.0.1:9999/v1/chat/completions",
            model="local-model",
            use_playwright=True,
            sources={},
        )

        self.assertTrue(check_llm_api(config))

        payload = mock_hit_api.call_args.args[0]
        self.assertEqual(payload["model"], "local-model")
        self.assertEqual(payload["messages"][0]["content"], "Hi!")
        self.assertEqual(payload["max_tokens"], 1)
        self.assertFalse(payload["stream"])
        self.assertEqual(mock_hit_api.call_args.kwargs["api_url"], "http://127.0.0.1:9999/v1/chat/completions")
        self.assertEqual(mock_hit_api.call_args.kwargs["api_key"], "key")

    @patch("utils.check_llm_api.requests.post")
    def test_hit_api_uses_explicit_url_and_key(self, mock_post):
        from utils.check_llm_api import hit_api

        hit_api(
            {"model": "local-model", "stream": False},
            is_stream=False,
            api_url="https://api.example/v1/chat/completions",
            api_key="secret-key",
        )

        self.assertEqual(mock_post.call_args.args[0], "https://api.example/v1/chat/completions")
        self.assertEqual(mock_post.call_args.kwargs["headers"]["Authorization"], "Bearer secret-key")
        self.assertFalse(mock_post.call_args.kwargs["stream"])

    def test_health_check_future_timeout_returns_false(self):
        future = concurrent.futures.Future()

        self.assertFalse(start_animation._future_ok(future, "slow check", timeout=0.01))

    @patch("core.llm.stream_openrouter_response")
    @patch("core.llm.load_llm_runtime_config")
    def test_call_llm_once_uses_runtime_model(self, mock_load_runtime_config, mock_stream):
        from config.runtime_config import LlmRuntimeConfig
        from core.llm import call_llm_once

        mock_load_runtime_config.return_value = LlmRuntimeConfig(
            api_key="key",
            api_url="https://api.example/v1/chat/completions",
            model="runtime-model",
            use_playwright=True,
            sources={},
        )
        mock_stream.return_value = ["hello"]

        reply, tokens = call_llm_once([{"role": "user", "content": "Hi"}])

        self.assertEqual(reply, "hello")
        self.assertEqual(tokens, 0)
        payload = mock_stream.call_args.args[0]
        self.assertEqual(payload["model"], "runtime-model")
        self.assertEqual(mock_stream.call_args.kwargs["api_url"], "https://api.example/v1/chat/completions")
        self.assertEqual(mock_stream.call_args.kwargs["api_key"], "key")

    @patch("main.parse_legacy_env_file")
    @patch("main.save_llm_runtime_config")
    @patch("main.Prompt.ask")
    @patch("main.load_llm_runtime_config")
    @patch("main.check_llm_api")
    def test_setup_wizard_saves_secure_runtime_config(self, mock_check, mock_load, mock_prompt, mock_save, mock_parse_legacy):
        from config.runtime_config import LlmRuntimeConfig
        from main import ensure_llm_runtime_config

        mock_parse_legacy.return_value = {}
        mock_load.return_value = LlmRuntimeConfig(
            api_key=None,
            api_url=None,
            model=None,
            use_playwright=None,
            sources={},
        )
        mock_check.return_value = False
        mock_prompt.side_effect = [
            "secret-key",
            "https://api.example/v1/chat/completions",
            "runtime-model",
            "true",
        ]

        self.assertTrue(ensure_llm_runtime_config())

        mock_save.assert_called_once_with(
            api_key="secret-key",
            api_url="https://api.example/v1/chat/completions",
            model="runtime-model",
            use_playwright=True,
        )


if __name__ == "__main__":
    unittest.main()
