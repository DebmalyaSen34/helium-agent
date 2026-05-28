import unittest
from unittest.mock import patch

from core import llm
from core.llm import AgenticLoop


class AgenticLoopTests(unittest.TestCase):
    def setUp(self):
        llm.conversation_history.clear()

    def test_runs_multiple_tool_turns_before_final_answer(self):
        replies = iter(
            [
                '<action>{"tool": "read_file", "args": {"path": "README.md"}}</action>',
                '<action>{"tool": "execute_bash", "args": {"command": "pytest tests/test_agentic_loop.py -q"}}</action>',
                "I read the code, ran the focused test, and it passes.",
            ]
        )
        prompts = []
        executed = []

        def ask_model(messages):
            prompts.append(messages[-1]["content"])
            return next(replies)

        def execute_tool_call(tool_call, confirm_tool=None):
            executed.append(tool_call["tool"])
            return f"{tool_call['tool']} result"

        loop = AgenticLoop(
            ask_model=ask_model,
            execute_tool_call=execute_tool_call,
            max_turns=4,
        )

        result = loop.run(
            system_prompt="You are Helium.",
            user_prompt="Improve the project and verify it.",
        )

        self.assertEqual(
            executed,
            ["read_file", "execute_bash"],
        )
        self.assertEqual(
            result.final_answer,
            "I read the code, ran the focused test, and it passes.",
        )
        self.assertEqual(result.stop_reason, "final")
        self.assertEqual(result.tools_used, ["read_file", "execute_bash"])
        self.assertIn("Observation from read_file", prompts[1])
        self.assertIn("Observation from execute_bash", prompts[2])

    def test_malformed_action_is_returned_as_observation_for_recovery(self):
        replies = iter(
            [
                '<action>{"tool": "read_file", "args": {"path": "README.md"}</action>',
                '<action>{"tool": "list_directory", "args": {"path": "."}}</action>',
                "I recovered and listed the project.",
            ]
        )
        executed = []

        def ask_model(messages):
            return next(replies)

        def execute_tool_call(tool_call, confirm_tool=None):
            executed.append(tool_call["tool"])
            return "directory listing"

        loop = AgenticLoop(
            ask_model=ask_model,
            execute_tool_call=execute_tool_call,
            max_turns=4,
        )

        result = loop.run(
            system_prompt="You are Helium.",
            user_prompt="List the project.",
        )

        self.assertEqual(executed, ["list_directory"])
        self.assertEqual(result.stop_reason, "final")
        self.assertIn("recovered", result.final_answer)
        self.assertEqual(len(result.observations), 2)
        self.assertIn("Invalid tool action", result.observations[0])

    @patch("tools.memory_ops.get_relevant_memories", return_value=[])
    @patch("core.llm.execute_agent_tool")
    @patch("core.llm.call_llm_once")
    def test_generate_response_uses_agentic_loop_until_final_answer(
        self,
        mock_call_llm_once,
        mock_execute_agent_tool,
        _mock_memories,
    ):
        mock_call_llm_once.side_effect = [
            ('<action>{"tool": "read_file", "args": {"path": "README.md"}}</action>', 8),
            ('<action>{"tool": "list_directory", "args": {"path": "."}}</action>', 8),
            ("Done after reading and listing.", 6),
        ]
        mock_execute_agent_tool.side_effect = [
            "README contents",
            "project listing",
        ]
        tool_results = []

        chunks = list(
            llm.generate_response(
                "Understand the project.",
                on_tool_result=lambda name, result: tool_results.append((name, result)),
                print_metrics=False,
            )
        )

        self.assertEqual("".join(chunks), "Done after reading and listing.")
        self.assertEqual(
            [call.args[0]["tool"] for call in mock_execute_agent_tool.call_args_list],
            ["read_file", "list_directory"],
        )
        self.assertEqual(
            tool_results,
            [
                ("read_file", "README contents"),
                ("list_directory", "project listing"),
            ],
        )
        self.assertEqual(llm.conversation_history[-1]["content"], "Done after reading and listing.")


if __name__ == "__main__":
    unittest.main()
