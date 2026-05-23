from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from rag_service.config import load_config
from rag_service.models import RagError
from rag_service.service import RagEvidenceService


app = FastAPI(title="Jarvis RAG Service", version="0.1.0")
_service: RagEvidenceService | None = None


def get_service() -> RagEvidenceService:
    global _service
    if _service is None:
        _service = RagEvidenceService(load_config())
    return _service


@app.get("/health")
def health() -> dict[str, Any]:
    config = load_config()
    return {
        "ok": True,
        "service": "rag_service",
        "embedding_model": config.embedding_model,
        "reranker_model": config.reranker_model,
    }


@app.post("/v1/evidence/path")
def evidence_for_path(payload: dict[str, Any]) -> JSONResponse:
    question = str(payload.get("question", "")).strip()
    file_path = str(payload.get("file_path", "")).strip()
    debug = bool(payload.get("debug", False))

    if not question:
        return JSONResponse(status_code=400, content={"ok": False, "error": {"code": "missing_question", "message": "Question is required."}})
    if not file_path:
        return JSONResponse(status_code=400, content={"ok": False, "error": {"code": "missing_file_path", "message": "file_path is required."}})

    try:
        pack = get_service().build_evidence_for_path(Path(file_path), question, debug=debug)
    except RagError as exc:
        return JSONResponse(status_code=400, content={"ok": False, "error": {"code": exc.code, "message": exc.message}})
    except Exception as exc:
        return JSONResponse(status_code=500, content={"ok": False, "error": {"code": "rag_service_error", "message": str(exc)}})

    return JSONResponse(content={"ok": True, "evidence": pack.to_dict()})
