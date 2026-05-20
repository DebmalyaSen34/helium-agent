import tempfile
import unittest
from pathlib import Path

from tools.rag.extractors import read_text_file
from tools.rag.models import RagConfig
from tools.rag.validation import validate_files


def config_for(root: Path) -> RagConfig:
    return RagConfig(
        enabled=True,
        max_files_per_request=2,
        max_bytes_per_file=20,
        max_total_attachment_bytes=30,
        max_indexed_chunks=400,
        max_retrieved_chunks=6,
        max_context_chars=6000,
        chunk_target_chars=800,
        chunk_overlap_chars=100,
        safe_roots=(str(root),),
        supported_extensions=(".md", ".txt"),
    )


class RagValidationTests(unittest.TestCase):
    def test_validate_accepts_supported_text_file(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            file_path = root / "notes.md"
            file_path.write_text("hello", encoding="utf-8")

            accepted, statuses = validate_files([file_path], config_for(root))

            self.assertEqual(accepted, [file_path])
            self.assertEqual(statuses, [])

    def test_validate_rejects_unsupported_extension(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            file_path = root / "notes.pdf"
            file_path.write_text("hello", encoding="utf-8")

            accepted, statuses = validate_files([file_path], config_for(root))

            self.assertEqual(accepted, [])
            self.assertEqual(statuses[0].status, "unsupported")

    def test_validate_rejects_too_many_files(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            files = []
            for index in range(3):
                file_path = root / f"{index}.md"
                file_path.write_text("hello", encoding="utf-8")
                files.append(file_path)

            accepted, statuses = validate_files(files, config_for(root))

            self.assertEqual(accepted, [])
            self.assertEqual(statuses[0].status, "rejected")
            self.assertIn("Too many files", statuses[0].reason)

    def test_validate_rejects_oversized_file(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            file_path = root / "large.md"
            file_path.write_text("x" * 25, encoding="utf-8")

            accepted, statuses = validate_files([file_path], config_for(root))

            self.assertEqual(accepted, [])
            self.assertEqual(statuses[0].status, "too_large")

    def test_read_text_file_rejects_invalid_utf8(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            file_path = root / "bad.md"
            file_path.write_bytes(b"\xff\xfe\x00\x00")

            with self.assertRaises(UnicodeDecodeError):
                read_text_file(file_path)