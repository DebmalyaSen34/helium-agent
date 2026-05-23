import tempfile
import unittest
from pathlib import Path

from rag_service.cache import RagCache
from rag_service.chunking import chunk_document
from rag_service.config import RagServiceConfig
from rag_service.evidence import build_evidence_pack
from rag_service.extractors import extract_document


def config_for(root: Path, *, full_text_budget_chars: int = 12000) -> RagServiceConfig:
    return RagServiceConfig.from_settings(
        {
            "rag_service": {
                "safe_roots": [str(root)],
                "cache_dir": str(root / ".cache"),
                "full_text_budget_chars": full_text_budget_chars,
                "evidence_budget_chars": 2000,
                "max_evidence_chunks": 3,
            }
        }
    )


class RagServiceEvidenceTests(unittest.TestCase):
    def test_small_file_evidence_includes_full_text(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            target = root / "notes.md"
            target.write_text("# Risk\nThe launch risk is database migration failure.", encoding="utf-8")
            config = config_for(root)
            document = extract_document(target)
            chunks = chunk_document(document, config)

            pack = build_evidence_pack(document, chunks, "what is the risk?", config)

            self.assertIn("database migration failure", pack.prompt)
            self.assertIn("[file:notes.md#chunk-0", pack.prompt)

    def test_large_file_evidence_retrieves_relevant_chunk(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            target = root / "notes.md"
            target.write_text("# Intro\n" + "alpha\n" * 400 + "\n# Risk\npayment outage risk", encoding="utf-8")
            config = config_for(root, full_text_budget_chars=50)
            document = extract_document(target)
            chunks = chunk_document(document, config)

            pack = build_evidence_pack(document, chunks, "payment risk", config)

            self.assertIn("payment outage risk", pack.prompt)
            self.assertTrue(pack.citations)

    def test_cache_stores_and_loads_chunks(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            target = root / "notes.md"
            target.write_text("# Intro\nhello", encoding="utf-8")
            config = config_for(root)
            document = extract_document(target)
            chunks = chunk_document(document, config)
            cache = RagCache(config.cache_dir)

            cache.store(document, chunks)
            loaded = cache.load_chunks(document.file_hash)

            self.assertTrue(cache.has_document(document.file_hash))
            self.assertEqual(loaded[0].citation, chunks[0].citation)
