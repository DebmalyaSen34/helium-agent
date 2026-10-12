import unittest

from utils.parser import extract_json


class ParserTests(unittest.TestCase):
    def test_plain_text_is_not_tool_call(self):
        self.assertIsNone(extract_json("Hello, I can help with that."))

    def test_valid_tool_json(self):
        text = '{"tool": "search_web", "args": {"query": "latest AI news", "num_results": 2}}'
        self.assertEqual(
            extract_json(text),
            {"tool": "search_web", "args": {"query": "latest AI news", "num_results": 2}},
        )

    def test_markdown_wrapped_json(self):
        text = '```json\n{"tool": "get_time", "args": {}}\n```'
        self.assertEqual(extract_json(text), {"tool": "get_time", "args": {}})

    def test_malformed_search_tool_fallback(self):
        text = '{"tool": "search_web", "args": {"query": "weather in London", "num_results": 3}</start_of_turn>'
        self.assertEqual(
            extract_json(text),
            {"tool": "search_web", "args": {"query": "weather in London", "num_results": 3}},
        )


if __name__ == "__main__":
    unittest.main()
