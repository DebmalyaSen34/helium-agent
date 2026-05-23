from __future__ import annotations

from rag_service.config import RagServiceConfig
from rag_service.models import Chunk, EvidencePack, ExtractedDocument, RetrievedChunk
from rag_service.retrieval import HybridRetriever


def build_evidence_pack(document: ExtractedDocument, chunks: list[Chunk], question: str, config: RagServiceConfig) -> EvidencePack:
    warnings = list(document.warnings)
    debug: dict[str, object] = {
        "file_name": document.file_name,
        "file_hash": document.file_hash,
        "chunk_count": len(chunks),
        "retrieval_mode": "full_text" if len(document.text) <= config.full_text_budget_chars else "lexical_hybrid_fallback",
    }

    if len(document.text) <= config.full_text_budget_chars:
        citation = chunks[0].citation if chunks else f"[file:{document.file_name}#chunk-0]"
        prompt = _render_prompt(
            question=question,
            file_name=document.file_name,
            summary=_summary(document),
            evidence_blocks=[f"{citation}\n{document.text.strip()}"],
            warnings=warnings,
        )
        return EvidencePack(prompt=prompt, sources=(citation,), citations=(citation,), warnings=tuple(warnings), debug=debug)

    retrieved = HybridRetriever(chunks).search(question, config.max_evidence_chunks)
    if not retrieved:
        warnings.append("No strong evidence matched the question.")
        evidence_blocks = []
        citations: tuple[str, ...] = ()
    else:
        evidence_blocks = [f"{item.chunk.citation}\n{item.chunk.text.strip()}" for item in retrieved]
        citations = tuple(item.chunk.citation for item in retrieved)

    prompt = _render_prompt(
        question=question,
        file_name=document.file_name,
        summary=_summary(document),
        evidence_blocks=_fit_budget(evidence_blocks, config.evidence_budget_chars),
        warnings=warnings,
    )
    debug["retrieved"] = [
        {"citation": item.chunk.citation, "score": item.score, "reason": item.reason}
        for item in retrieved
    ]
    return EvidencePack(prompt=prompt, sources=citations, citations=citations, warnings=tuple(warnings), debug=debug)


def _summary(document: ExtractedDocument) -> str:
    outline = "\n".join(f"- {item}" for item in document.outline[:20])
    if outline:
        return f"Document type: {document.kind}\nOutline:\n{outline}"
    preview = document.text.strip().replace("\n", " ")[:600]
    return f"Document type: {document.kind}\nPreview: {preview}"


def _fit_budget(blocks: list[str], budget: int) -> list[str]:
    selected: list[str] = []
    used = 0
    for block in blocks:
        if used + len(block) > budget:
            break
        selected.append(block)
        used += len(block)
    return selected


def _render_prompt(
    *,
    question: str,
    file_name: str,
    summary: str,
    evidence_blocks: list[str],
    warnings: list[str],
) -> str:
    evidence = "\n\n".join(evidence_blocks).strip()
    if not evidence:
        evidence = "No sufficiently relevant snippets were retrieved from the attached file."

    warning_text = "\n".join(f"- {warning}" for warning in warnings) if warnings else "- None"
    return (
        "Attached file evidence pack:\n\n"
        f"File: {file_name}\n\n"
        f"Document summary:\n{summary}\n\n"
        f"Evidence:\n{evidence}\n\n"
        f"Warnings:\n{warning_text}\n\n"
        "Instructions:\n"
        "- Answer the user using the attached file evidence when relevant.\n"
        "- Cite factual claims with the provided file citations.\n"
        "- If the evidence is insufficient, say that clearly instead of inventing file contents.\n"
        "- After the answer, include a compact Sources section listing the citations used.\n\n"
        f"User question:\n{question}"
    )
