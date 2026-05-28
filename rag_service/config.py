from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from config.settings import BASE_DIR, SETTINGS


DEFAULT_SUPPORTED_EXTENSIONS = (
    ".txt",
    ".md",
    ".py",
    ".js",
    ".ts",
    ".tsx",
    ".jsx",
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".csv",
    ".log",
    ".pdf",
    ".docx",
    ".xlsx",
)


@dataclass(frozen=True)
class RagServiceConfig:
    enabled: bool
    service_url: str
    host: str
    port: int
    auto_start: bool
    fail_closed: bool
    safe_roots: tuple[Path, ...]
    cache_dir: Path
    max_bytes_per_file: int
    evidence_budget_chars: int
    full_text_budget_chars: int
    max_chunks: int
    max_candidates: int
    max_evidence_chunks: int
    embedding_model: str
    fallback_embedding_model: str
    reranker_model: str
    device: str
    batch_size: int
    timeout_seconds: float
    rag_debug: bool
    persist_debug_traces: bool
    supported_extensions: tuple[str, ...]

    @classmethod
    def from_settings(cls, settings: dict[str, Any] | None = None) -> "RagServiceConfig":
        raw = (settings or SETTINGS).get("rag_service", {})
        root = Path.cwd().resolve()
        safe_roots = raw.get("safe_roots", ["."])
        resolved_roots: list[Path] = []
        for safe_root in safe_roots:
            path = Path(str(safe_root)).expanduser()
            if not path.is_absolute():
                path = root / path
            resolved_roots.append(path.resolve())

        cache_dir = Path(str(raw.get("cache_dir", ".cache/rag_service"))).expanduser()
        if not cache_dir.is_absolute():
            cache_dir = root / cache_dir

        host = str(raw.get("host", "127.0.0.1"))
        port = int(raw.get("port", 8765))
        service_url = str(raw.get("service_url", f"http://{host}:{port}")).rstrip("/")

        return cls(
            enabled=bool(raw.get("enabled", True)),
            service_url=service_url,
            host=host,
            port=port,
            auto_start=bool(raw.get("auto_start", False)),
            fail_closed=bool(raw.get("fail_closed", True)),
            safe_roots=tuple(resolved_roots),
            cache_dir=cache_dir.resolve(),
            max_bytes_per_file=int(raw.get("max_bytes_per_file", 25_000_000)),
            evidence_budget_chars=int(raw.get("evidence_budget_chars", 16_000)),
            full_text_budget_chars=int(raw.get("full_text_budget_chars", 12_000)),
            max_chunks=int(raw.get("max_chunks", 600)),
            max_candidates=int(raw.get("max_candidates", 24)),
            max_evidence_chunks=int(raw.get("max_evidence_chunks", 8)),
            embedding_model=str(raw.get("embedding_model", "BAAI/bge-m3")),
            fallback_embedding_model=str(raw.get("fallback_embedding_model", "BAAI/bge-base-en-v1.5")),
            reranker_model=str(raw.get("reranker_model", "BAAI/bge-reranker-base")),
            device=str(raw.get("device", "auto")),
            batch_size=int(raw.get("batch_size", 8)),
            timeout_seconds=float(raw.get("timeout_seconds", 120.0)),
            rag_debug=bool(raw.get("rag_debug", False)),
            persist_debug_traces=bool(raw.get("persist_debug_traces", False)),
            supported_extensions=tuple(
                str(ext).lower() for ext in raw.get("supported_extensions", DEFAULT_SUPPORTED_EXTENSIONS)
            ),
        )


def load_config() -> RagServiceConfig:
    return RagServiceConfig.from_settings()
