"""Regression tests for bugs found in the full-agent diagnosis."""

import threading
import unittest
from unittest.mock import MagicMock, patch

import main
from core import llm
from core.llm import AgenticLoop
from core.model_client import ModelTurn, ToolCall


class BashStdinTests(unittest.TestCase):
    def test_commands_reading_stdin_do_not_wait_on_the_terminal(self):
        from tools.bash_ops import execute_bash

        with patch("subprocess.run", wraps=__import__("subprocess").run) as run:
            execute_bash("cat")
        import subprocess

        self.assertIs(run.call_args.kwargs["stdin"], subprocess.DEVNULL)

    def test_tail_follow_needs_confirmation(self):
        from tools.bash_ops import is_command_safe

        self.assertFalse(is_command_safe("tail -f app.log"))
        self.assertTrue(is_command_safe("tail -n 20 README.md"))


class WebSourcesTests(unittest.TestCase):
    def test_sources_are_read_from_search_web_output(self):
        observation = (
            "Tool 'search_web' executed successfully. Result: Question type: general\n"
            "Confidence: high\nEvidence:\n- Something happened source: https://a.example/x\n"
            "Sources:\n- Example A: https://a.example/x\n- B: Title with colon: https://b.example/y\n"
            "Diagnostics:\n- ddgs failed"
        )
        sources = main.extract_web_sources(observation)
        self.assertEqual(
            sources,
            [
                {"title": "Example A", "url": "https://a.example/x"},
                {"title": "B: Title with colon", "url": "https://b.example/y"},
            ],
        )
        self.assertEqual(main.extract_web_sources("no sources here"), [])


class LoopBehaviourTests(unittest.TestCase):
    def test_subagent_tools_never_run_in_parallel(self):
        active = []
        overlap = []
        lock = threading.Lock()

        def execute(action, confirm_tool=None):
            with lock:
                active.append(1)
                if len(active) > 1:
                    overlap.append(action["tool"])
            import time

            time.sleep(0.05)
            with lock:
                active.pop()
            return "ok"

        class Model:
            supports_tools = True
            cache_key = ("x", "y")

            def __init__(self):
                self.turns = [
                    ModelTurn(content="", tool_calls=[ToolCall("a", "delegate_task", {"agent_id": "1", "task": "t"}), ToolCall("b", "delegate_task", {"agent_id": "2", "task": "t"})]),
                    ModelTurn(content="done"),
                ]

            def complete(self, messages, tools=None, on_text=None):
                return self.turns.pop(0)

        AgenticLoop(model=Model(), execute_tool_call=execute, tool_mode="native").run("sys", "go")
        self.assertEqual(overlap, [])

    def test_text_mode_json_answer_is_not_a_tool_call(self):
        replies = iter(['{"name": "Ada", "age": 36}'])
        result = AgenticLoop(ask_model=lambda m: next(replies)).run("sys", "give me JSON")
        self.assertEqual(result.stop_reason, "final")
        self.assertEqual(result.final_answer, '{"name": "Ada", "age": 36}')

    @patch.dict("core.llm.LLM_SETTINGS", {"tool_mode": "text"})
    @patch("tools.memory_ops.get_relevant_memories", return_value=[])
    @patch("core.llm.call_llm_once", return_value=("Answer.", 3))
    def test_history_keeps_user_words_not_attachment_evidence(self, _llm, _memories):
        llm.conversation_history.clear()
        list(llm.generate_response("EVIDENCE " * 2000, history_prompt="@README.md what is this", print_metrics=False))
        self.assertEqual(llm.conversation_history[-2]["content"], "@README.md what is this")
        llm.conversation_history.clear()


class UrlTests(unittest.TestCase):
    def test_bare_local_server_urls_use_v1(self):
        from config.providers import normalize_chat_url

        self.assertEqual(normalize_chat_url("http://localhost:11434"), "http://localhost:11434/v1/chat/completions")
        self.assertEqual(normalize_chat_url("http://127.0.0.1:1234/"), "http://127.0.0.1:1234/v1/chat/completions")
        self.assertEqual(normalize_chat_url("https://api.deepseek.com"), "https://api.deepseek.com/chat/completions")


class SessionSummaryPruningTests(unittest.TestCase):
    def test_only_recent_session_summaries_are_kept(self):
        import sqlite3

        from memory.conversation import ConversationStore
        from memory.flat_store import FlatMemoryStore

        conn = sqlite3.connect(":memory:")
        flat, conversation = FlatMemoryStore(conn), ConversationStore(conn)
        for index in range(15):
            conversation.append(f"s{index}", "user", f"turn {index}")
            conversation.store_session_context(flat, f"s{index}")
        count = conn.execute("SELECT COUNT(*) FROM memories WHERE tags = 'session-summary'").fetchone()[0]
        self.assertEqual(count, ConversationStore.KEEP_SESSION_SUMMARIES)
        latest = conn.execute("SELECT content FROM memories WHERE tags = 'session-summary' ORDER BY id DESC LIMIT 1").fetchone()[0]
        self.assertIn("turn 14", latest)


class InterruptTests(unittest.TestCase):
    def _run_repl(self, prompt_side_effect, **patches):
        with patch("main.ensure_llm_runtime_config", return_value=True), \
             patch("main.animated_header_supported", return_value=False), \
             patch("main.print_header"), \
             patch("main.print_goodbye") as goodbye, \
             patch("main.console.print"), \
             patch("main.PromptSession") as session:
            session.return_value.prompt.side_effect = prompt_side_effect
            for target, value in patches.items():
                patch(target, value).start()
            try:
                main.main(target_path=".")
            finally:
                patch.stopall()
        return session.return_value.prompt.call_count, goodbye

    def test_ctrl_c_during_a_turn_cancels_only_that_turn(self):
        def interrupted(*args, **kwargs):
            raise KeyboardInterrupt
            yield  # pragma: no cover

        calls, goodbye = self._run_repl(
            ["hello", "exit"],
            **{"main.generate_response": interrupted, "main.prepare_rag_prompt": lambda text: text},
        )
        self.assertEqual(calls, 2)  # the session kept going after the interrupt
        goodbye.assert_called_once()

    def test_ctrl_c_at_the_prompt_needs_a_second_press_to_exit(self):
        calls, goodbye = self._run_repl([KeyboardInterrupt(), "/clear", KeyboardInterrupt(), KeyboardInterrupt()])
        self.assertEqual(calls, 4)
        goodbye.assert_called_once()


if __name__ == "__main__":
    unittest.main()
