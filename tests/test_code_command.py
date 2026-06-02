import unittest

from unittest.mock import patch

import main


class CodeCommandTests(unittest.TestCase):
    def test_parse_code_command_extracts_task(self):
        parsed = main.parse_code_command("/code fix the failing todo test")

        self.assertEqual(parsed, "fix the failing todo test")

    def test_parse_code_command_trims_whitespace(self):
        parsed = main.parse_code_command("  /code   add tests for parser   ")

        self.assertEqual(parsed, "add tests for parser")

    def test_parse_code_command_returns_empty_string_for_empty_task(self):
        parsed = main.parse_code_command("/code   ")

        self.assertEqual(parsed, "")

    def test_parse_code_command_ignores_normal_chat(self):
        parsed = main.parse_code_command("summarize this README")

        self.assertIsNone(parsed)

    def test_parse_code_command_does_not_match_prefix_words(self):
        parsed = main.parse_code_command("/codegen create a file")

        self.assertIsNone(parsed)

class CodeCommandHandlerTests(unittest.TestCase):
    @patch("main.print_chat_message")
    def test_handle_code_command_shows_usage_for_empty_task(self, mock_print):
        handled = main.handle_code_command("/code", confirm_tool=lambda *_args: True)

        self.assertTrue(handled)
        mock_print.assert_called_once()
        self.assertIn("Usage: /code <coding task>", mock_print.call_args.args[1])

    @patch("main.run_coding_workflow")
    @patch("main.print_chat_message")
    @patch("main.set_state")
    def test_handle_code_command_runs_workflow_for_code_task(
        self,
        mock_set_state,
        mock_print,
        mock_run_workflow,
    ):
        class Result:
            final_answer = "Changed files:\n- main.py\n\nVerification:\n- Not run\n\nRemaining risks:\n- None"

        mock_run_workflow.return_value = Result()

        handled = main.handle_code_command("/code add parser tests", confirm_tool=lambda *_args: True)

        self.assertTrue(handled)
        mock_set_state.assert_called_with("Coding Workflow")
        mock_run_workflow.assert_called_once()
        self.assertEqual(mock_run_workflow.call_args.args[0], "add parser tests")
        mock_print.assert_called_with("Helium", Result.final_answer, style="cyan", markdown=True)

    @patch("main.run_coding_workflow")
    def test_handle_code_command_ignores_normal_chat(self, mock_run_workflow):
        handled = main.handle_code_command("hello", confirm_tool=lambda *_args: True)

        self.assertFalse(handled)
        mock_run_workflow.assert_not_called()

    @patch("main.run_coding_workflow")
    @patch("main.print_chat_message")
    @patch("main.set_state")
    def test_handle_code_command_appends_metadata_when_missing_from_answer(
        self,
        _mock_set_state,
        mock_print,
        mock_run_workflow,
    ):
        class Result:
            final_answer = "Implemented the requested change."
            changed_files = ["core/example.py"]
            verification_commands = ["python -m unittest tests.test_example -v"]

        mock_run_workflow.return_value = Result()

        handled = main.handle_code_command("/code change example", confirm_tool=lambda *_args: True)

        self.assertTrue(handled)
        rendered = mock_print.call_args.args[1]
        self.assertIn("Implemented the requested change.", rendered)
        self.assertIn("Changed files:", rendered)
        self.assertIn("core/example.py", rendered)
        self.assertIn("Verification:", rendered)
        self.assertIn("python -m unittest tests.test_example -v", rendered)
        self.assertIn("Remaining risks:", rendered)

if __name__ == "__main__":
    unittest.main()