import io
import unittest
from unittest.mock import patch

from rich.console import Console

from utils.stream_render import LiveReply, _TailView, stable_split
from utils.tui import assistant_block


def _lines(text: str) -> list[str]:
    return [line.rstrip() for line in text.splitlines() if line.strip()]


class StableSplitTests(unittest.TestCase):
    def test_splits_before_last_block(self):
        text = "# Title\n\nFirst paragraph.\n\nStill writ"
        self.assertEqual(text[stable_split(text):], "Still writ")

    def test_no_split_inside_open_fence(self):
        text = "Intro.\n\n```python\nx = 1\n\ny = 2\n"
        self.assertEqual(text[stable_split(text):], "```python\nx = 1\n\ny = 2\n")

    def test_splits_after_closed_fence(self):
        text = "```\na\n\nb\n```\n\nNext"
        self.assertEqual(text[stable_split(text):], "Next")

    def test_keeps_indented_continuations_together(self):
        text = "- item\n\n  more of the item"
        self.assertEqual(stable_split(text), 0)

    def test_single_block_has_no_split(self):
        self.assertEqual(stable_split("just one paragraph"), 0)


class TailViewTests(unittest.TestCase):
    def test_incremental_render_matches_full_render(self):
        block = "## Part {i}\n\nText with `code` and **bold**.\n\n- one\n- two\n\n```python\nprint({i})\n```\n\n"
        full = "".join(block.format(i=i) for i in range(6)) + "Half a sen"
        console = Console(file=io.StringIO(), width=80, height=10_000, force_terminal=True, color_system=None)
        reply = LiveReply(console, stream_text=False)
        view = _TailView(reply)

        # Grow the text in chunks, as streaming would, so the cache is exercised.
        for end in range(20, len(full), 37):
            reply._shown = full[:end]
            list(view.__rich_console__(console, console.options))
        reply._shown = full
        streamed = "".join(seg.text for seg in view.__rich_console__(console, console.options))

        reference = "\n".join(
            "".join(seg.text for seg in line)
            for line in console.render_lines(assistant_block(full), console.options, pad=False)
        )
        self.assertEqual(_lines(streamed), _lines(reference))

    def test_finished_blocks_are_not_rerendered(self):
        console = Console(file=io.StringIO(), width=80, height=10_000, force_terminal=True, color_system=None)
        reply = LiveReply(console, stream_text=False)
        view = _TailView(reply)
        reply._shown = "First paragraph.\n\nSecond"
        list(view.__rich_console__(console, console.options))

        reply._shown = "First paragraph.\n\nSecond paragraph grows"
        with patch.object(view, "_render", wraps=view._render) as render:
            list(view.__rich_console__(console, console.options))
        rendered = [call.args[2] for call in render.call_args_list]
        self.assertEqual(rendered, ["Second paragraph grows"])


class StartupConfigTests(unittest.TestCase):
    @patch("main.check_llm_api")
    @patch("main.load_llm_runtime_config")
    def test_complete_config_skips_api_request(self, mock_load, mock_check):
        from config.runtime_config import LlmRuntimeConfig
        from main import ensure_llm_runtime_config

        mock_load.return_value = LlmRuntimeConfig(
            api_key="key", api_url="https://api.example/v1/chat/completions", model="m", sources={}
        )

        self.assertTrue(ensure_llm_runtime_config())
        mock_check.assert_not_called()


if __name__ == "__main__":
    unittest.main()
