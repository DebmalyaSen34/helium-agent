import tempfile
from pathlib import Path

import unittest
from tools.rag.session import RagSession
from tools.rag.models import RagConfig
from config.settings import RAG_SETTINGS

class RagSessionFacadeTests(unittest.TestCase):
    def test_ingest_files_indexes_chunks_and_reports_status(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            file_path = root / "notes.md"
            file_path.write_text("deploy risk is high", encoding="utf-8")
            config = RagConfig.from_settings(
                {
                    **RAG_SETTINGS,
                    "safe_roots": [str(root)],
                    "supported_extensions": [".md"],
                    "chunk_target_chars": 800,
                    "chunk_overlap_chars": 100,
                }
            )
            session = RagSession(config=config, project_root=root)

            result = session.ingest_paths([file_path])

            self.assertEqual(result.statuses[0].status, "indexed")
            self.assertEqual(len(session.chunks), 1)

    def test_build_prompt_adds_retrieved_context(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            file_path = root / "notes.md"
            file_path.write_text("deploy risk is high", encoding="utf-8")
            config = RagConfig.from_settings({**RAG_SETTINGS, "safe_roots": [str(root)], "supported_extensions": [".md"]})
            session = RagSession(config=config, project_root=root)
            session.ingest_paths([file_path])

            prompt = session.build_prompt("what is deploy risk?")

            self.assertIn("Attached file context:", prompt)
            self.assertIn("[file:notes.md#chunk-0]", prompt)

    def test_build_prompt_without_matches_returns_original_question(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            config = RagConfig.from_settings({**RAG_SETTINGS, "safe_roots": [str(root)]})
            session = RagSession(config=config, project_root=root)

            self.assertEqual(session.build_prompt("hello"), "hello")