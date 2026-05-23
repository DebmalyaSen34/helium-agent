from __future__ import annotations

from rag_service.config import RagServiceConfig
from rag_service.models import Chunk, ExtractedDocument, SourceLocation


def chunk_document(document: ExtractedDocument, config: RagServiceConfig) -> list[Chunk]:
    chunks: list[Chunk] = []
    target = 1400
    overlap = 160

    for block in document.blocks:
        text = block.text.strip()
        if not text:
            continue
        if len(text) <= target:
            chunks.append(_chunk(document, text, block.location, len(chunks), "structure"))
            continue

        start = 0
        while start < len(text):
            end = min(len(text), start + target)
            if end < len(text):
                newline = text.rfind("\n", start, end)
                if newline > start + target // 2:
                    end = newline
            snippet = text[start:end].strip()
            if snippet:
                chunks.append(_chunk(document, snippet, block.location, len(chunks), "window"))
            if end >= len(text):
                break
            start = max(start + 1, end - overlap)
        if len(chunks) >= config.max_chunks:
            break

    return chunks[: config.max_chunks]


def _chunk(document: ExtractedDocument, text: str, location: SourceLocation, index: int, strategy: str) -> Chunk:
    return Chunk(
        id=f"{document.file_hash[:12]}:{index}",
        file_name=document.file_name,
        file_hash=document.file_hash,
        text=text,
        location=location,
        strategy=strategy,
        index=index,
    )
