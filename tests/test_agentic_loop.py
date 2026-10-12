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

    @patch.dict("core.llm.LLM_SETTINGS", {"tool_mode": "text"})
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


class ReasoningCleanupTests(unittest.TestCase):
    def test_strip_reasoning_removes_think_blocks(self):
        from core.llm import strip_reasoning

        self.assertEqual(strip_reasoning("<think>plan</think>Answer"), "Answer")
        self.assertEqual(strip_reasoning("still thinking</think>Answer"), "Answer")
        self.assertEqual(strip_reasoning("<think>never closed"), "")

    def test_clean_token_keeps_user_prefix_in_content(self):
        from core.llm import clean_token

        self.assertEqual(clean_token("User: alice<end_of_turn>"), "User: alice")


from core.model_client import ModelTurn, ToolCall, ToolsUnsupportedError, reset_tool_support, tools_supported


class FakeNativeModel:
    supports_tools = True
    cache_key = ("https://fake", "fake-model")

    def __init__(self, turns):
        self.turns = list(turns)
        self.calls = []

    def complete(self, messages, tools=None, on_text=None):
        self.calls.append({"messages": [dict(m) for m in messages], "tools": tools})
        turn = self.turns.pop(0)
        if isinstance(turn, Exception):
            raise turn
        if on_text and turn.content:
            on_text(turn.content)
        return turn


class NativeToolLoopTests(unittest.TestCase):
    def setUp(self):
        reset_tool_support()

    def test_native_tool_calls_are_paired_with_tool_messages(self):
        model = FakeNativeModel(
            [
                ModelTurn(content="", tool_calls=[ToolCall("c1", "read_file", {"path": "README.md"})], usage={"prompt_tokens": 5, "completion_tokens": 2}),
                ModelTurn(content="All done.", usage={"prompt_tokens": 9, "completion_tokens": 3}),
            ]
        )
        loop = AgenticLoop(
            model=model,
            execute_tool_call=lambda action, confirm_tool=None: f"{action['tool']} ok",
            tool_mode="auto",
        )
        result = loop.run("sys", "go")

        self.assertEqual(result.final_answer, "All done.")
        self.assertEqual(result.tools_used, ["read_file"])
        self.assertEqual(result.usage["completion_tokens"], 5)
        second_request = model.calls[1]["messages"]
        self.assertEqual(second_request[-2]["tool_calls"][0]["id"], "c1")
        self.assertEqual(second_request[-1], {"role": "tool", "tool_call_id": "c1", "content": "read_file ok"})
        self.assertIsNotNone(model.calls[0]["tools"])
        self.assertNotIn("<json_contract>", second_request[0]["content"])

    def test_safe_calls_in_one_turn_run_in_parallel_and_keep_order(self):
        import threading

        barrier = threading.Barrier(2, timeout=2)

        def execute(action, confirm_tool=None):
            barrier.wait()  # deadlocks unless both calls run concurrently
            return action["tool"]

        model = FakeNativeModel(
            [
                ModelTurn(content="", tool_calls=[ToolCall("a", "get_time", {}), ToolCall("b", "list_directory", {})]),
                ModelTurn(content="ok"),
            ]
        )
        result = AgenticLoop(model=model, execute_tool_call=execute, tool_mode="native").run("sys", "go")
        self.assertEqual(result.observations, ["get_time", "list_directory"])

    def test_bad_arguments_are_fed_back_without_running_the_tool(self):
        executed = []
        model = FakeNativeModel(
            [
                ModelTurn(content="", tool_calls=[ToolCall("a", "read_file", {}, raw_arguments="{bad", parse_error="Expecting value")]),
                ModelTurn(content="recovered"),
            ]
        )
        result = AgenticLoop(
            model=model,
            execute_tool_call=lambda action, confirm_tool=None: executed.append(action) or "ran",
            tool_mode="native",
        ).run("sys", "go")
        self.assertEqual(executed, [])
        self.assertIn("could not parse", result.observations[0])

    def test_falls_back_to_text_protocol_when_tools_rejected(self):
        model = FakeNativeModel(
            [
                ToolsUnsupportedError("no tools", 400),
                ModelTurn(content='<action>{"tool": "get_time", "args": {}}</action>'),
                ModelTurn(content="It is noon."),
            ]
        )
        result = AgenticLoop(
            model=model,
            execute_tool_call=lambda action, confirm_tool=None: "12:00",
            tool_mode="auto",
        ).run("sys", "time?")

        self.assertEqual(result.final_answer, "It is noon.")
        self.assertFalse(tools_supported(model.cache_key))
        self.assertIsNone(model.calls[1]["tools"])
        self.assertIn("<json_contract>", model.calls[1]["messages"][0]["content"])

    def test_long_tool_output_is_truncated(self):
        model = FakeNativeModel(
            [ModelTurn(content="", tool_calls=[ToolCall("a", "get_time", {})]), ModelTurn(content="done")]
        )
        result = AgenticLoop(
            model=model,
            execute_tool_call=lambda action, confirm_tool=None: "x" * 5000 + "TAIL",
            tool_mode="native",
            max_tool_output_chars=300,
        ).run("sys", "go")
        self.assertIn("omitted", result.observations[0])
        self.assertTrue(result.observations[0].endswith("TAIL"))

    def test_compaction_elides_oldest_tool_output(self):
        model = FakeNativeModel(
            [
                ModelTurn(content="", tool_calls=[ToolCall("a", "get_time", {})]),
                ModelTurn(content="", tool_calls=[ToolCall("b", "get_time", {})]),
                ModelTurn(content="", tool_calls=[ToolCall("c", "get_time", {})]),
                ModelTurn(content="done"),
            ]
        )
        AgenticLoop(
            model=model,
            execute_tool_call=lambda action, confirm_tool=None: "y" * 1000,
            tool_mode="native",
            context_budget_chars=1500,
        ).run("sys", "go")
        last_request = model.calls[-1]["messages"]
        self.assertTrue(any(str(m.get("content", "")).startswith("[earlier tool output elided") for m in last_request))

    def test_tool_names_limit_schemas_sent(self):
        model = FakeNativeModel([ModelTurn(content="hi")])
        AgenticLoop(model=model, tool_names=["read_file"], tool_mode="native").run("sys", "go")
        self.assertEqual([t["function"]["name"] for t in model.calls[0]["tools"]], ["read_file"])

    def test_text_deltas_are_emitted_in_native_mode(self):
        events = []
        model = FakeNativeModel([ModelTurn(content="streamed")])
        AgenticLoop(model=model, tool_mode="native", on_event=lambda kind, payload: events.append((kind, payload))).run("sys", "go")
        self.assertIn(("text_delta", "streamed"), events)
