from __future__ import annotations

import importlib.util
from dataclasses import dataclass

from rag_service.config import RagServiceConfig, load_config


@dataclass(frozen=True)
class DoctorCheck:
    name: str
    ok: bool
    detail: str


def run_doctor(config: RagServiceConfig | None = None) -> list[DoctorCheck]:
    config = config or load_config()
    checks = [
        DoctorCheck("cache_dir", _cache_dir_ok(config), str(config.cache_dir)),
        DoctorCheck("fastapi", _module_exists("fastapi"), "required for service API"),
        DoctorCheck("uvicorn", _module_exists("uvicorn"), "required for manual service startup"),
        DoctorCheck("faiss", _module_exists("faiss"), "optional dense vector index; install requirements-rag.txt"),
        DoctorCheck("FlagEmbedding", _module_exists("FlagEmbedding"), "optional BGE embeddings/reranker; install requirements-rag.txt"),
        DoctorCheck("sentence_transformers", _module_exists("sentence_transformers"), "optional embedding fallback"),
        DoctorCheck("pypdf", _module_exists("pypdf"), "required for PDF extraction"),
        DoctorCheck("docx", _module_exists("docx"), "required for DOCX extraction"),
        DoctorCheck("openpyxl", _module_exists("openpyxl"), "required for XLSX extraction"),
    ]
    return checks


def _module_exists(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def _cache_dir_ok(config: RagServiceConfig) -> bool:
    try:
        config.cache_dir.mkdir(parents=True, exist_ok=True)
        probe = config.cache_dir / ".doctor-write-test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        return True
    except OSError:
        return False
