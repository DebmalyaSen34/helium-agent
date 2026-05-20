import unittest

from config.settings import RAG_SETTINGS
from tools.rag.models import Chunk, Document, RagConfig


class RagSessionTests(unittest.TestCase):
    def test_default_rag_settings_are_available(self):
        self.assertTrue(RAG_SETTINGS["enabled"])
        self.assertEqual(RAG_SETTINGS["max_files_per_request"], 5)
        self.assertEqual(RAG_SETTINGS["max_retrieved_chunks"], 6)

    def test_rag_config_from_settings(self):
        config = RagConfig.from_settings(RAG_SETTINGS)

        self.assertEqual(config.max_files_per_request, 5)
        self.assertIn(".md", config.supported_extensions)

    def test_document_and_chunk_models_hold_metadata(self):
        document = Document(
            id="doc-1",
            name="README.md",
            path="/repo/README.md",
            content_hash="abc",
            byte_size=10,
            text_length=20,
        )
        chunk = Chunk(
            id="doc-1:0",
            document_id=document.id,
            document_name=document.name,
            index=0,
            text="hello world",
        )

        self.assertEqual(chunk.citation, "[file:README.md#chunk-0]")
        self.assertEqual(chunk.document_id, "doc-1")