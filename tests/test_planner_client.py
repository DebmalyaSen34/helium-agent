import unittest
from unittest.mock import patch

from tools.research.planner_client import ResearchPlannerLLM, extract_completion_text


class PlannerClientTests(unittest.TestCase):
    @patch("core.llm.call_llm_once", return_value=('{"subqueries": []}', 5))
    def test_uses_configured_chat_endpoint_by_default(self, mock_call):
        reply = ResearchPlannerLLM().complete_plan("plan this")
        self.assertEqual(reply, '{"subqueries": []}')
        messages = mock_call.call_args.args[0]
        self.assertEqual(messages[-1], {"role": "user", "content": "plan this"})

    def test_extracts_text_from_completion_choices(self):
        self.assertEqual(extract_completion_text({"choices": [{"text": "hello"}]}), "hello")

    def test_extracts_text_from_chat_choices(self):
        data = {"choices": [{"message": {"content": "hi"}}]}
        self.assertEqual(extract_completion_text(data), "hi")


if __name__ == "__main__":
    unittest.main()
