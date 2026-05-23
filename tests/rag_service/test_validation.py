import tempfile
import unittest
from pathlib import Path

from rag_service.config import RagServiceConfig
from rag_service.models import RagError
from rag_service.validation import validate_one_file_path


def config_for(root: Path) -> RagServiceConfig:
    return RagServiceConfig.from_settings(
        {
            "rag_service": {
                "safe_roots": [str(root)],
                "cache_dir": str(root / ".cache"),
                "supported_extensions": [".md", ".txt"],
                "max_bytes_per_file": 10,
            }
        }
    )


class RagServiceValidationTests(unittest.TestCase):
    def test_accepts_supported_file_under_safe_root(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            target = root / "notes.md"
            target.write_text("hello", encoding="utf-8")

            result = validate_one_file_path(target, config_for(root))

            self.assertEqual(result.file_path, target.resolve())
            self.assertEqual(result.byte_size, 5)

    def test_rejects_file_outside_safe_root(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "root"
            outside = Path(temp) / "outside.md"
            root.mkdir()
            outside.write_text("hello", encoding="utf-8")

            with self.assertRaises(RagError) as caught:
                validate_one_file_path(outside, config_for(root))

            self.assertEqual(caught.exception.code, "outside_safe_roots")

    def test_rejects_unsupported_extension(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            target = root / "paper.pdf"
            target.write_text("hello", encoding="utf-8")

            with self.assertRaises(RagError) as caught:
                validate_one_file_path(target, config_for(root))

            self.assertEqual(caught.exception.code, "unsupported_file")

    def test_rejects_oversized_file(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            target = root / "notes.md"
            target.write_text("hello world", encoding="utf-8")

            with self.assertRaises(RagError) as caught:
                validate_one_file_path(target, config_for(root))

            self.assertEqual(caught.exception.code, "file_too_large")
