from __future__ import annotations

import json
import time
from pathlib import Path

from rag_service.cache import RagCache
from rag_service.chunking import chunk_document
from rag_service.config import RagServiceConfig, load_config
from rag_service.evidence import build_evidence_pack
from rag_service.extractors import extract_document, file_hash
from rag_service.models import EvidencePack, RagError
from rag_service.validation import validate_one_file_path


class RagEvidenceService:
    def __init__(self, config: RagServiceConfig | None = None) -> None:
        self.config = config or load_config()
        self.cache = RagCache(self.config.cache_dir)

    def build_evidence_for_path(self, file_path: Path, question: str, *, debug: bool = False) -> EvidencePack:
        start = time.time()
        validation = validate_one_file_path(file_path, self.config)
        current_hash = file_hash(validation.file_path)

        document = extract_document(validation.file_path)
        cached_chunks = self.cache.load_chunks(current_hash)
        cache_hit = bool(cached_chunks)
        if cached_chunks:
            chunks = cached_chunks
        else:
            chunks = chunk_document(document, self.config)
            if not chunks:
                raise RagError("no_chunks", "Attachment did not produce any usable text chunks.")
            self.cache.store(document, chunks)

        pack = build_evidence_pack(document, chunks, question, self.config)
        debug_data = dict(pack.debug)
        debug_data.update(
            {
                "cache_hit": cache_hit,
                "elapsed_seconds": round(time.time() - start, 3),
                "service_mode": "local",
            }
        )
        pack = EvidencePack(
            prompt=pack.prompt,
            sources=pack.sources,
            citations=pack.citations,
            warnings=pack.warnings,
            debug=debug_data,
        )
        if debug or self.config.persist_debug_traces:
            self._write_trace(pack)
        return pack

    def _write_trace(self, pack: EvidencePack) -> None:
        trace_dir = self.config.cache_dir / "traces"
        trace_dir.mkdir(parents=True, exist_ok=True)
        name = f"trace-{int(time.time() * 1000)}.json"
        (trace_dir / name).write_text(json.dumps(pack.to_dict(), indent=2, default=str), encoding="utf-8")
