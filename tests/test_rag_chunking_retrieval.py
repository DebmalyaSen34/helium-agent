import unittest

from tools.rag.chunking import chunk_document
from tools.rag.models import Document, RagConfig
from tools.rag.prompt import build_rag_prompt
from tools.rag.retrieval import LexicalRetriever


def config() -> RagConfig:
    return RagConfig(
        enabled=True,
        max_files_per_request=5,
        max_bytes_per_file=1_000_000,
        max_total_attachment_bytes=3_000_000,
        max_indexed_chunks=400,
        max_retrieved_chunks=3,
        max_context_chars=400,
        chunk_target_chars=40,
        chunk_overlap_chars=10,
        safe_roots=(".",),
        supported_extensions=(".md", ".txt"),
    )


def document(name: str = "notes.md") -> Document:
    return Document(
        id="doc-1",
        name=name,
        path=f"/repo/{name}",
        content_hash="hash",
        byte_size=100,
        text_length=100,
    )


class RagChunkRetrievalTests(unittest.TestCase):
    def test_chunk_document_creates_overlapping_chunks(self):
        chunks = chunk_document(document(), "alpha beta gamma delta epsilon zeta eta theta", config())

        self.assertGreater(len(chunks), 1)
        self.assertEqual(chunks[0].document_name, "notes.md")
        self.assertTrue(chunks[0].text)
        self.assertEqual(chunks[0].citation, "[file:notes.md#chunk-0]")

    def test_retriever_finds_exact_terms(self):
        chunks = chunk_document(document(), "deploy risk is high\ncooking recipe is unrelated", config())
        retriever = LexicalRetriever(chunks)

        results = retriever.search("deploy risk", max_results=2)

        self.assertGreater(results[0].score, 0)
        self.assertIn("deploy", results[0].chunk.text)

    def test_retriever_applies_filename_boost(self):
        risk_doc = document("risk.md")
        notes_doc = Document("doc-2", "notes.md", "/repo/notes.md", "hash2", 100, 100)
        chunks = [
            chunk_document(risk_doc, "ordinary planning text", config())[0],
            chunk_document(notes_doc, "ordinary planning text", config())[0],
        ]
        retriever = LexicalRetriever(chunks)

        results = retriever.search("risk", max_results=2)

        self.assertEqual(results[0].chunk.document_name, "risk.md")

    def test_retriever_returns_empty_for_no_match(self):
        chunks = chunk_document(document(), "alpha beta gamma", config())
        retriever = LexicalRetriever(chunks)

        self.assertEqual(retriever.search("zebra", max_results=2), [])

    def test_prompt_builder_emits_citations_and_budget(self):
        chunks = chunk_document(document(), "deploy risk is high because rollback is manual", config())
        result = LexicalRetriever(chunks).search("deploy risk", max_results=2)

        prompt = build_rag_prompt("what is the risk?", result, max_context_chars=120)

        self.assertIn("[file:notes.md#chunk-0]", prompt)
        self.assertIn("User question:", prompt)
        self.assertLessEqual(len(prompt), 600)