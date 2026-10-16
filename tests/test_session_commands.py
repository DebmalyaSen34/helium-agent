import unittest
from pathlib import Path
from unittest.mock import patch

import main
from core import llm
from core.session import SESSION
from utils.stream_render import summarize_args, visible_text


class SessionCommandTests(unittest.TestCase):
    def setUp(self):
        SESSION.reset()
        llm.conversation_history.clear()

    def tearDown(self):
        SESSION.reset()
        llm.conversation_history.clear()

    @patch("main.print_chat_message")
    def test_clear_resets_conversation_history(self, mock_print):
        llm.conversation_history.extend([{"role": "user", "content": "hi"}, {"role": "assistant", "content": "yo"}])
        self.assertTrue(main.handle_clear_command("/clear"))
        self.assertEqual(llm.conversation_history, [])
        self.assertFalse(main.handle_clear_command("/clearly not"))

    @patch("main.print_chat_message")
    def test_model_switches_for_session(self, mock_print):
        self.assertTrue(main.handle_model_command("/model my-model"))
        self.assertEqual(SESSION.model_override, "my-model")
        from core.session import get_active_model

        self.assertEqual(get_active_model(), "my-model")

    @patch("config.runtime_config.update_llm_runtime_config")
    @patch("main.print_chat_message")
    def test_model_save_persists_only_the_model(self, mock_print, mock_update):
        main.handle_model_command("/model other --save")
        mock_update.assert_called_once_with(model="other")
        self.assertEqual(SESSION.model_override, "other")

    @patch("main.print_chat_message")
    def test_model_without_args_shows_status(self, mock_print):
        main.handle_model_command("/model")
        self.assertIn("Model:", mock_print.call_args.args[1])

    @patch("main.console.print")
    def test_usage_prints_table(self, mock_print):
        SESSION.usage.add({"prompt_tokens": 10, "completion_tokens": 5}, requests=1, tool_calls=2)
        self.assertTrue(main.handle_usage_command("/usage"))
        mock_print.assert_called_once()

    @patch("main.print_chat_message")
    def test_undo_with_empty_journal(self, mock_print):
        from tools.edit_journal import JOURNAL

        JOURNAL.clear()
        self.assertTrue(main.handle_undo_command("/undo"))
        self.assertIn("Nothing to undo", mock_print.call_args.args[1])

    def test_help_lists_new_commands(self):
        help_text = main.build_help_text()
        for command in ("/clear", "/model", "/undo", "/usage", "/init", "/notes", "/exit"):
            self.assertIn(command, help_text)

    def test_exit_command_is_recognised(self):
        from utils.commands import EXIT_COMMANDS

        self.assertIn("/exit", EXIT_COMMANDS)
        self.assertIn("exit", EXIT_COMMANDS)


class NotesCommandTests(unittest.TestCase):
    def setUp(self):
        import tempfile

        self._tmp = tempfile.TemporaryDirectory()
        self.workspace = Path(self._tmp.name) / "project"
        self.workspace.mkdir()
        self._env = patch.dict("os.environ", {"HELIUM_DATA_DIR": str(Path(self._tmp.name) / "data")})
        self._env.start()

    def tearDown(self):
        self._env.stop()
        self._tmp.cleanup()

    @patch("main.print_chat_message")
    def test_notes_with_text_appends_timestamped_lines(self, mock_print):
        from utils.notes import read_notes

        self.assertTrue(main.handle_notes_command("/notes first thought", self.workspace))
        self.assertTrue(main.handle_notes_command("/notes second", self.workspace))
        lines = read_notes(self.workspace).splitlines()
        self.assertEqual(len(lines), 2)
        self.assertTrue(lines[0].startswith("- ") and lines[0].endswith("first thought"))
        self.assertTrue(lines[1].endswith("second"))

    def test_notes_without_text_opens_editor(self):
        with patch("utils.notes.edit_notes", return_value=True) as mock_edit, patch("main.console"):
            self.assertTrue(main.handle_notes_command("/notes", self.workspace))
        mock_edit.assert_called_once_with(self.workspace)

    def test_other_text_is_not_a_notes_command(self):
        self.assertFalse(main.handle_notes_command("/notesy", self.workspace))
        self.assertFalse(main.handle_notes_command("notes", self.workspace))

    def test_notes_are_per_workspace(self):
        from utils.notes import append_note, read_notes

        other = Path(self._tmp.name) / "other"
        other.mkdir()
        append_note(self.workspace, "only here")
        self.assertEqual(read_notes(other), "")


class StreamRenderTests(unittest.TestCase):
    def test_visible_text_hides_reasoning_and_actions(self):
        self.assertEqual(visible_text("<think>hmm"), "")
        self.assertEqual(visible_text("<think>a</think>Answer"), "Answer")
        self.assertEqual(visible_text('<action>{"tool"'), "")
        # Mid-reply tags are prose, not tool calls (native mode won't execute them either).
        self.assertEqual(visible_text('Use `<action>{"tool": ...}</action>` blocks.'), 'Use `<action>{"tool": ...}</action>` blocks.')

    def test_summarize_args_hides_large_content(self):
        summary = summarize_args({"path": "a.py", "content": "x" * 500})
        self.assertIn("path=a.py", summary)
        self.assertIn("<500 chars>", summary)


if __name__ == "__main__":
    unittest.main()


class InitCommandTests(unittest.TestCase):
    @patch("main.print_chat_message")
    @patch("main.run_main_turn")
    def test_init_runs_main_turn_with_init_task(self, mock_run, mock_print):
        import tempfile
        from pathlib import Path
        from core.project_context import INIT_TASK
        from tools import file_ops

        original = file_ops.PROJECT_ROOT
        with tempfile.TemporaryDirectory() as tmp:
            file_ops.set_project_root(Path(tmp))
            try:
                self.assertTrue(main.handle_init_command("/init", confirm_tool=lambda *a: True))
            finally:
                file_ops.set_project_root(original)
        self.assertEqual(mock_run.call_args.args[0], INIT_TASK)
        self.assertEqual(mock_run.call_args.kwargs["history_prompt"], "/init")

    @patch("main.print_chat_message")
    @patch("main.run_main_turn")
    @patch("main.Prompt.ask", return_value="cancel")
    def test_init_cancel_when_file_exists(self, mock_ask, mock_run, mock_print):
        import tempfile
        from pathlib import Path
        from tools import file_ops

        original = file_ops.PROJECT_ROOT
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "HELIUM.md").write_text("x")
            file_ops.set_project_root(Path(tmp))
            try:
                main.handle_init_command("/init", confirm_tool=lambda *a: True)
            finally:
                file_ops.set_project_root(original)
        mock_run.assert_not_called()


class LongStreamRenderingTests(unittest.TestCase):
    def test_long_streamed_answer_is_printed_once_in_full(self):
        import io
        import re
        from rich.console import Console
        from utils.stream_render import LiveReply

        buf = io.StringIO()
        console = Console(file=buf, force_terminal=True, width=60, height=15, color_system=None)
        reply = LiveReply(console, stream_text=True)
        reply.start()
        for i in range(80):
            reply.on_text(f"Line {i} of a long answer that mentions `<action>` in prose.\n\n")
        self.assertTrue(reply.finish())
        out = re.sub(r"\x1b\[[0-9;?]*[A-Za-z]", "", buf.getvalue())
        self.assertIn("Line 79 of a long answer", out)
        # The final full panel shows each line once; the transient tail may repeat
        # only the last screenful, never the whole answer.
        self.assertLessEqual(out.count("Line 0 of a long answer"), 2)


class TagsMentionedInProseTests(unittest.TestCase):
    ANSWER = (
        "Two protocols: native tool-calling (results returned as role: tool messages) "
        'and a text `<action>{"tool": ..., "args": ...}</action>` protocol. '
        "Reasoning in `<think>` blocks is stripped. The end."
    )

    def test_stream_display_keeps_whole_answer(self):
        self.assertTrue(visible_text(self.ANSWER).endswith("The end."))

    def test_final_answer_keeps_whole_answer(self):
        from core.llm import strip_reasoning

        self.assertTrue(strip_reasoning(self.ANSWER).endswith("The end."))

    def test_leading_reasoning_and_bare_actions_are_still_hidden(self):
        from core.llm import strip_reasoning

        self.assertEqual(visible_text("<think>planning"), "")
        self.assertEqual(visible_text("<think>plan</think>Answer"), "Answer")
        self.assertEqual(visible_text('<action>{"tool": "get_time"'), "")
        self.assertEqual(strip_reasoning("still reasoning</think>Answer"), "Answer")
        self.assertEqual(strip_reasoning("Literal `</think>` tag."), "Literal `</think>` tag.")

    def test_native_loop_returns_whole_answer(self):
        from core.llm import AgenticLoop
        from core.model_client import ModelTurn

        class Model:
            supports_tools = True
            cache_key = ("https://x", "m")

            def complete(self, messages, tools=None, on_text=None):
                return ModelTurn(content=TagsMentionedInProseTests.ANSWER)

        result = AgenticLoop(model=Model(), tool_mode="native").run("sys", "explain")
        self.assertEqual(result.final_answer, self.ANSWER)
