import tempfile
import unittest
from pathlib import Path

from rag_service.config import RagServiceConfig
from rag_service.models import RagError
from rag_service.terminal import resolve_single_mention


def config_for(root: Path) -> RagServiceConfig:
    return RagServiceConfig.from_settings(
        {
            "rag_service": {
                "safe_roots": [str(root)],
                "cache_dir": str(root / ".cache"),
                "supported_extensions": [".md", ".py"],
            }
        }
    )


class RagServiceTerminalTests(unittest.TestCase):
    def test_returns_none_without_mention(self):
        with tempfile.TemporaryDirectory() as temp:
            self.assertIsNone(resolve_single_mention("hello there", config_for(Path(temp))))

    def test_resolves_exact_path_and_cleans_question(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            target = root / "notes.md"
            target.write_text("hello", encoding="utf-8")

            result = resolve_single_mention(f"summarize @{target}", config_for(root))

            self.assertEqual(result.file_path, target.resolve())
            self.assertEqual(result.question, "summarize")

    def test_resolves_fuzzy_filename(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            target = root / "architecture-notes.md"
            target.write_text("hello", encoding="utf-8")

            result = resolve_single_mention("summarize @architecture", config_for(root))

            self.assertEqual(result.file_path, target.resolve())

    def test_rejects_multiple_mentions(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "a.md").write_text("a", encoding="utf-8")
            (root / "b.md").write_text("b", encoding="utf-8")

            with self.assertRaises(RagError) as caught:
                resolve_single_mention("@a.md and @b.md", config_for(root))

            self.assertEqual(caught.exception.code, "too_many_attachments")


class MentionPassThroughTests(unittest.TestCase):
    def test_plain_at_words_are_ordinary_text(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "notes.md").write_text("hello", encoding="utf-8")
            self.assertIsNone(resolve_single_mention("use the @decorator syntax", config_for(root)))
            self.assertIsNone(resolve_single_mention("ping @alice and @bob", config_for(root)))

    def test_path_like_mentions_still_report_errors(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(RagError):
                resolve_single_mention("read @missing.md", config_for(Path(temp)))

    def test_trailing_punctuation_and_other_at_words(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            target = root / "notes.md"
            target.write_text("hello", encoding="utf-8")
            result = resolve_single_mention("what is in @notes.md? also see @decorator", config_for(root))
            self.assertEqual(result.file_path, target.resolve())

    def test_fuzzy_search_skips_virtualenvs(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            hidden = root / ".venv" / "lib" / "decorator.py"
            hidden.parent.mkdir(parents=True)
            hidden.write_text("x", encoding="utf-8")
            self.assertIsNone(resolve_single_mention("explain @decorator", config_for(root)))
