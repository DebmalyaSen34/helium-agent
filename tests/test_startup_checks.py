import concurrent.futures
import unittest
from unittest.mock import patch

from utils import start_animation
from utils.system_check import check_llm_api


class StartupCheckTests(unittest.TestCase):
    @patch("utils.system_check.hit_api")
    @patch.dict(
        "os.environ",
        {
            "LLM_API_KEY": "key",
            "LLM_API_URL": "http://127.0.0.1:9999/v1/chat/completions",
            "LLM_MODEL": "local-model",
        },
        clear=False,
    )
    def test_llm_check_uses_normal_api_helper(self, mock_hit_api):
        mock_hit_api.return_value.status_code = 200

        self.assertTrue(check_llm_api())

        payload = mock_hit_api.call_args.args[0]
        self.assertEqual(payload["model"], "local-model")
        self.assertEqual(payload["messages"][0]["content"], "Hi!")
        self.assertEqual(payload["max_tokens"], 1)
        self.assertFalse(payload["stream"])
        self.assertEqual(mock_hit_api.call_args.kwargs, {})

    def test_health_check_future_timeout_returns_false(self):
        future = concurrent.futures.Future()

        self.assertFalse(start_animation._future_ok(future, "slow check", timeout=0.01))


if __name__ == "__main__":
    unittest.main()
