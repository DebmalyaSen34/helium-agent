import tempfile
import unittest
from pathlib import Path

from tools.rag.models import RagConfig
from tools.rag.terminal import extract_file_mentions, resolve_mentions


def config_for(root: Path) -> RagConfig:
    return RagConfig(
        enabled=True,
        max_files_per_request=5,
        max_bytes_per_file=1_000_000,
        max_total_attachment_bytes=3_000_000,
        max_indexed_chunks=400,
        max_retrieved_chunks=6,
        max_context_chars=6000,
        chunk_target_chars=800,
        chunk_overlap_chars=100,
        safe_roots=(str(root),),
        supported_extensions=(".md", ".py", ".txt"),
    )


class RagTerminalTests(unittest.TestCase):
    def test_extract_single_file_mention(self):
        cleaned, mentions = extract_file_mentions("summarize @README.md please")

        self.assertEqual(cleaned, "summarize please")
        self.assertEqual([mention.path_text for mention in mentions], ["README.md"])

    def test_extract_multiple_file_mentions(self):
        cleaned, mentions = extract_file_mentions("compare @core/llm.py with @api/main.py")

        self.assertEqual(cleaned, "compare with")
        self.assertEqual([mention.path_text for mention in mentions], ["core/llm.py", "api/main.py"])

    def test_does_not_treat_email_as_file(self):
        cleaned, mentions = extract_file_mentions("email me at test@example.com")

        self.assertEqual(cleaned, "email me at test@example.com")
        self.assertEqual(mentions, [])

    def test_resolve_mentions_accepts_safe_relative_path(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            target = root / "README.md"
            target.write_text("hello", encoding="utf-8")
            _, mentions = extract_file_mentions("read @README.md")

            resolved, statuses = resolve_mentions(mentions, root, config_for(root))

            self.assertEqual(resolved, [target.resolve()])
            self.assertEqual(statuses, [])

    def test_resolve_mentions_rejects_outside_safe_root(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "root"
            outside = Path(temp) / "outside.md"
            root.mkdir()
            outside.write_text("secret", encoding="utf-8")
            _, mentions = extract_file_mentions(f"read @{outside}")

            resolved, statuses = resolve_mentions(mentions, root, config_for(root))

            self.assertEqual(resolved, [])
            self.assertEqual(statuses[0].status, "rejected")
            self.assertIn("outside allowed roots", statuses[0].reason)