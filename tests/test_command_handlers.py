import unittest

from unittest.mock import patch

import main


class DeepResearchCommandTests(unittest.TestCase):
    def test_parse_deep_research_command_extracts_task(self):
        parsed = main.parse_deep_research_command(
            "/deep-research compare local-first agents and cloud agents"
        )

        self.assertEqual(parsed, "compare local-first agents and cloud agents")

    def test_parse_deep_research_command_trims_whitespace(self):
        parsed = main.parse_deep_research_command("  /deep-research   explain AI regulations   ")

        self.assertEqual(parsed, "explain AI regulations")

    def test_parse_deep_research_command_returns_empty_string_for_empty_task(self):
        parsed = main.parse_deep_research_command("/deep-research   ")

        self.assertEqual(parsed, "")

    def test_parse_deep_research_command_ignores_normal_chat(self):
        parsed = main.parse_deep_research_command("research this normally")

        self.assertIsNone(parsed)

    def test_parse_deep_research_command_does_not_match_prefix_words(self):
        parsed = main.parse_deep_research_command("/deep-researcher explain tools")

        self.assertIsNone(parsed)


class HelpCommandTests(unittest.TestCase):
    def test_parse_help_command_matches_help_only(self):
        self.assertTrue(main.parse_help_command("/help"))
        self.assertTrue(main.parse_help_command("  /help  "))

    def test_parse_help_command_ignores_prefix_words(self):
        self.assertFalse(main.parse_help_command("/helpme"))
        self.assertFalse(main.parse_help_command("hello"))

    def test_build_help_text_includes_core_capabilities(self):
        help_text = main.build_help_text()

        self.assertIn("/help", help_text)
        self.assertNotIn("/code", help_text)
        self.assertIn("/deep-research", help_text)
        self.assertIn("@path", help_text)
        self.assertIn("## Coding", help_text)
        self.assertIn("Deep research", help_text)
        self.assertIn("Tool safety", help_text)
        self.assertIn("quit", help_text)


class DeepResearchCommandHandlerTests(unittest.TestCase):
    @patch("main.print_chat_message")
    def test_handle_deep_research_command_shows_usage_for_empty_task(self, mock_print):
        handled = main.handle_deep_research_command("/deep-research")

        self.assertTrue(handled)
        mock_print.assert_called_once()
        self.assertIn("Usage: /deep-research <research task>", mock_print.call_args.args[1])

    @patch("main.research_query", return_value="Deep cited answer")
    @patch("main.print_chat_message")
    @patch("main.set_state")
    def test_handle_deep_research_command_runs_research_pipeline(
        self,
        mock_set_state,
        mock_print,
        mock_research_query,
    ):
        handled = main.handle_deep_research_command(
            "/deep-research compare local agents with cloud agents"
        )

        self.assertTrue(handled)
        mock_set_state.assert_called_with("Deep Research")
        mock_research_query.assert_called_once_with(
            "compare local agents with cloud agents",
            max_sources=8,
        )
        mock_print.assert_called_with("Helium", "Deep cited answer", style="cyan", markdown=True)

    @patch("main.research_query")
    def test_handle_deep_research_command_ignores_normal_chat(self, mock_research_query):
        handled = main.handle_deep_research_command("hello")

        self.assertFalse(handled)
        mock_research_query.assert_not_called()


class HelpCommandHandlerTests(unittest.TestCase):
    @patch("main.print_chat_message")
    def test_handle_help_command_prints_help(self, mock_print):
        handled = main.handle_help_command("/help")

        self.assertTrue(handled)
        mock_print.assert_called_once()
        self.assertIn("/deep-research", mock_print.call_args.args[1])
        self.assertIn("## Coding", mock_print.call_args.args[1])

    @patch("main.print_chat_message")
    def test_handle_help_command_ignores_normal_chat(self, mock_print):
        handled = main.handle_help_command("hello")

        self.assertFalse(handled)
        mock_print.assert_not_called()

if __name__ == "__main__":
    unittest.main()


class InvokeSkillTests(unittest.TestCase):
    @patch.dict("core.llm.LLM_SETTINGS", {"tool_mode": "text"})
    @patch("main.print_metrics")
    @patch("main.print_chat_message")
    @patch("core.llm.call_llm_once", return_value=("Skill done.", 3))
    def test_invoke_skill_reports_metrics_without_error(self, mock_llm, mock_print, mock_metrics):
        from pathlib import Path
        from skills.loader import Skill

        skill = Skill(name="demo", description="demo skill", trigger="/demo", body="Say done.")
        main.invoke_skill(skill, "", confirm_tool=None, workspace=Path("."))

        metrics = mock_metrics.call_args.args[0]
        for key in ("total_time", "tokens", "tps", "tools_used"):
            self.assertIn(key, metrics)
