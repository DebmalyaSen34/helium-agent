from __future__ import annotations

import math
import re
from collections import Counter

from tools.rag.models import Chunk, RetrievedChunk

TOKEN_RE = re.compile(r"[A-Za-z0-9_]+")
STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "how",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "that",
    "the",
    "this",
    "to",
    "what",
    "with",
}


def tokenize(text: str) -> list[str]:
    return [token.lower() for token in TOKEN_RE.findall(text) if len(token) > 1 and token.lower() not in STOPWORDS]


class LexicalRetriever:
    def __init__(self, chunks: list[Chunk]) -> None:
        self.chunks = chunks
        self.chunk_terms = [Counter(tokenize(chunk.text)) for chunk in chunks]
        self.filename_terms = [set(tokenize(chunk.document_name)) for chunk in chunks]
        self.doc_freq: Counter[str] = Counter()
        for terms in self.chunk_terms:
            self.doc_freq.update(terms.keys())
        total_len = sum(sum(terms.values()) for terms in self.chunk_terms)
        self.avg_len = total_len / len(self.chunk_terms) if self.chunk_terms else 1.0

    def search(self, query: str, max_results: int) -> list[RetrievedChunk]:
        query_terms = tokenize(query)
        if not query_terms:
            return []

        scored: list[RetrievedChunk] = []
        for index, chunk in enumerate(self.chunks):
            score = self._score(query_terms, index)
            if score > 0:
                scored.append(RetrievedChunk(chunk=chunk, score=score))

        scored.sort(key=lambda item: (-item.score, item.chunk.document_name, item.chunk.index))
        return scored[:max_results]

    def _score(self, query_terms: list[str], index: int) -> float:
        terms = self.chunk_terms[index]
        if not terms:
            return 0.0

        score = 0.0
        chunk_len = sum(terms.values())
        k1 = 1.2
        b = 0.75
        total_chunks = max(1, len(self.chunks))

        for term in query_terms:
            freq = terms.get(term, 0)
            filename_match = term in self.filename_terms[index]
            if freq == 0 and not filename_match:
                continue

            df = self.doc_freq.get(term, 0)
            idf = math.log(1 + (total_chunks - df + 0.5) / (df + 0.5))
            if freq:
                denom = freq + k1 * (1 - b + b * (chunk_len / self.avg_len))
                score += idf * ((freq * (k1 + 1)) / denom)
            if filename_match:
                score += 0.4

        phrase = " ".join(query_terms)
        if phrase and phrase in " ".join(tokenize(self.chunks[index].text)):
            score += 0.5

        return score