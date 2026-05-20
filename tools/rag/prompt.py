from __future__ import annotations

from tools.rag.models import RetrievedChunk


def build_rag_prompt(user_question: str, retrieved: list[RetrievedChunk], max_context_chars: int) -> str:
    if not retrieved:
        return user_question

    snippets: list[str] = []
    used = 0
    for item in retrieved:
        block = f"{item.chunk.citation}\n{item.chunk.text.strip()}\n"
        if used + len(block) > max_context_chars:
            break
        snippets.append(block)
        used += len(block)

    if not snippets:
        return user_question

    context = "\n".join(snippets).strip()
    return (
        "Attached file context:\n\n"
        f"{context}\n\n"
        "Instructions:\n"
        "- Answer using the attached file context when it is relevant.\n"
        "- Cite file snippets using their markers.\n"
        "- If the attached file context does not contain enough evidence, say that clearly.\n"
        "- Do not invent file contents.\n\n"
        f"User question:\n{user_question}"
    )