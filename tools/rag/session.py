from __future__ import annotations

import hashlib
from pathlib import Path

from tools.rag.chunking import chunk_document
from tools.rag.extractors import read_text_file
from tools.rag.models import Document, FileStatus, IngestResult, RagConfig
from tools.rag.prompt import build_rag_prompt
from tools.rag.retrieval import LexicalRetriever
from tools.rag.validation import validate_files


class RagSession:
    def __init__(self, config: RagConfig, project_root: Path) -> None:
        self.config = config
        self.project_root = project_root.resolve()
        self.documents: list[Document] = []
        self.chunks = []
        self._hashes: set[str] = set()

    def ingest_paths(self, paths: list[Path]) -> IngestResult:
        accepted, statuses = validate_files(paths, self.config)
        result = IngestResult(statuses=list(statuses))

        for path in accepted:
            name = path.name
            try:
                text = read_text_file(path)
            except UnicodeDecodeError:
                result.statuses.append(FileStatus(name=name, status="decode_error", reason="File is not valid UTF-8 text."))
                continue

            content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
            if content_hash in self._hashes:
                result.statuses.append(FileStatus(name=name, status="duplicate", reason="File content already indexed."))
                continue

            document = Document(
                id=f"doc-{len(self.documents)}",
                name=name,
                path=str(path),
                content_hash=content_hash,
                byte_size=path.stat().st_size,
                text_length=len(text),
            )
            chunks = chunk_document(document, text, self.config)
            remaining = max(0, self.config.max_indexed_chunks - len(self.chunks))
            chunks = chunks[:remaining]

            if not chunks:
                result.statuses.append(FileStatus(name=name, status="empty", reason="No text chunks were extracted."))
                continue

            self._hashes.add(content_hash)
            self.documents.append(document)
            self.chunks.extend(chunks)
            result.documents.append(document)
            result.chunks.extend(chunks)
            result.statuses.append(FileStatus(name=name, status="indexed", chunks=len(chunks)))

        return result

    def build_prompt(self, user_question: str) -> str:
        if not self.chunks:
            return user_question
        retrieved = LexicalRetriever(self.chunks).search(user_question, self.config.max_retrieved_chunks)
        return build_rag_prompt(user_question, retrieved, self.config.max_context_chars)