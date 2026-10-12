import json
import unittest
from unittest.mock import MagicMock, patch

from core.model_client import (
    OpenAICompatibleModel,
    ToolsUnsupportedError,
    LLMRequestError,
    parse_stream,
    reset_tool_support,
)


def _sse(*events):
    return [f"data: {json.dumps(event)}".encode() for event in events] + [b"data: [DONE]"]


class ParseStreamTests(unittest.TestCase):
    def test_content_only_reply_streams_text(self):
        seen = []
        turn = parse_stream(
            [
                {"choices": [{"delta": {"content": "Hel"}}]},
                {"choices": [{"delta": {"content": "lo"}, "finish_reason": "stop"}]},
            ],
            on_text=seen.append,
        )
        self.assertEqual(turn.content, "Hello")
        self.assertEqual(seen, ["Hel", "lo"])
        self.assertEqual(turn.tool_calls, [])
        self.assertEqual(turn.finish_reason, "stop")

    def test_tool_call_arguments_split_across_chunks(self):
        turn = parse_stream(
            [
                {"choices": [{"delta": {"tool_calls": [{"index": 0, "id": "call_1", "function": {"name": "read_file", "arguments": '{"pa'}}]}}]},
                {"choices": [{"delta": {"tool_calls": [{"index": 0, "function": {"arguments": 'th": "README.md"}'}}]}}]},
                {"usage": {"prompt_tokens": 10, "completion_tokens": 4}, "choices": []},
            ]
        )
        self.assertEqual(len(turn.tool_calls), 1)
        call = turn.tool_calls[0]
        self.assertEqual((call.id, call.name, call.arguments), ("call_1", "read_file", {"path": "README.md"}))
        self.assertEqual(turn.usage["completion_tokens"], 4)

    def test_parallel_tool_calls_keep_order(self):
        turn = parse_stream(
            [
                {"choices": [{"delta": {"tool_calls": [
                    {"index": 0, "id": "a", "function": {"name": "get_time", "arguments": "{}"}},
                    {"index": 1, "id": "b", "function": {"name": "list_directory", "arguments": "{}"}},
                ]}}]},
            ]
        )
        self.assertEqual([c.name for c in turn.tool_calls], ["get_time", "list_directory"])

    def test_bad_json_arguments_are_flagged(self):
        turn = parse_stream(
            [{"choices": [{"delta": {"tool_calls": [{"index": 0, "id": "x", "function": {"name": "read_file", "arguments": "{oops"}}]}}]}]
        )
        self.assertIsNotNone(turn.tool_calls[0].parse_error)


class OpenAICompatibleModelTests(unittest.TestCase):
    def setUp(self):
        reset_tool_support()

    def _model(self):
        return OpenAICompatibleModel(model="m", api_url="https://api.example/v1/chat/completions", api_key="k")

    @patch("utils.check_llm_api.hit_api")
    def test_sends_tools_and_parses_stream(self, mock_hit_api):
        response = MagicMock(status_code=200)
        response.iter_lines.return_value = _sse({"choices": [{"delta": {"content": "hi"}}]})
        mock_hit_api.return_value = response

        turn = self._model().complete([{"role": "user", "content": "x"}], tools=[{"type": "function"}])

        payload = mock_hit_api.call_args.args[0]
        self.assertEqual(payload["tools"], [{"type": "function"}])
        self.assertEqual(payload["tool_choice"], "auto")
        self.assertNotIn("stop", payload)
        self.assertEqual(turn.content, "hi")

    @patch("utils.check_llm_api.hit_api")
    def test_400_with_tools_raises_tools_unsupported(self, mock_hit_api):
        mock_hit_api.return_value = MagicMock(status_code=400, text="tools are not supported")
        with self.assertRaises(ToolsUnsupportedError):
            self._model().complete([], tools=[{"type": "function"}])

    @patch("utils.check_llm_api.hit_api")
    def test_auth_errors_are_not_mistaken_for_tool_support(self, mock_hit_api):
        mock_hit_api.return_value = MagicMock(status_code=401, text="invalid key for tool use")
        with self.assertRaises(LLMRequestError) as ctx:
            self._model().complete([], tools=[{"type": "function"}])
        self.assertNotIsInstance(ctx.exception, ToolsUnsupportedError)


if __name__ == "__main__":
    unittest.main()
