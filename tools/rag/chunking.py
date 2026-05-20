from __future__ import annotations
from tools.rag.models import Chunk, Document, RagConfig

def chunk_document(document: Document, text: str, config: RagConfig) -> list[Chunk]:
    clean_text = text.strip()
    
    if not clean_text:
        return []
    
    target = max(20, config.chunk_target_chars)
    overlap = min(max(0, config.chunk_overlap_chars), target//2)
    chunks: list[Chunk] = []
    start = 0

    while start<len(clean_text):
        end = min(len(clean_text), start+target)
        if end<len(clean_text):
            newline = clean_text.rfind('\n', start, end)
            if newline>start+target//2:
                end = newline

        chunk_text = clean_text[start:end].strip()
        if chunk_text:
            chunks.append(
                Chunk(
                    id=f"{document.id}:{len(chunks)}",
                    document_id=document.id,
                    document_name=document.name,
                    index=len(chunks),
                    text=chunk_text,
                )
            )

        if end>=len(clean_text):
            break
        start = max(end-overlap, start+1)

    return chunks
