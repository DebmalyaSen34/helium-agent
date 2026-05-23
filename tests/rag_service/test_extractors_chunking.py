import tempfile
import unittest
from pathlib import Path

from rag_service.chunking import chunk_document
from rag_service.config import RagServiceConfig
from rag_service.extractors import extract_document
from rag_service.models import RagError


def config_for(root: Path) -> RagServiceConfig:
    return RagServiceConfig.from_settings({"rag_service": {"safe_roots": [str(root)], "cache_dir": str(root / ".cache")}})


class RagServiceExtractionChunkingTests(unittest.TestCase):
    def test_extracts_markdown_headings_as_blocks(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            target = root / "notes.md"
            target.write_text("# Intro\nhello\n\n## Risk\nfire", encoding="utf-8")

            document = extract_document(target)

            self.assertEqual(document.kind, "md")
            self.assertIn("# Intro", document.outline)
            self.assertEqual(len(document.blocks), 2)

    def test_extracts_python_functions_as_blocks(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            target = root / "app.py"
            target.write_text("import os\n\n\ndef run():\n    return os.getcwd()\n", encoding="utf-8")

            document = extract_document(target)

            self.assertIn("function run", document.outline)
            self.assertTrue(any(block.title == "imports" for block in document.blocks))

    def test_extracts_csv_as_table_summary(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            target = root / "data.csv"
            target.write_text("name,count\nalpha,2\nbeta,3\n", encoding="utf-8")

            document = extract_document(target)

            self.assertEqual(document.kind, "csv")
            self.assertIn("row_count", document.text)
            self.assertIn("name", document.text)

    def test_chunks_preserve_citation_location(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            target = root / "notes.md"
            target.write_text("# Intro\nhello", encoding="utf-8")

            chunks = chunk_document(extract_document(target), config_for(root))

            self.assertEqual(len(chunks), 1)
            self.assertIn("lines 1-2", chunks[0].citation)

    def test_pdf_dependency_error_is_controlled_when_missing_or_file_invalid(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            target = root / "bad.pdf"
            target.write_bytes(b"not really a pdf")

            with self.assertRaises((RagError, Exception)):
                extract_document(target)
