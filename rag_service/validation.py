from __future__ import annotations

from pathlib import Path

from rag_service.config import RagServiceConfig
from rag_service.models import RagError, ValidationResult


def is_under(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def validate_one_file_path(file_path: Path, config: RagServiceConfig) -> ValidationResult:
    user_path = file_path.expanduser()
    if user_path.is_absolute():
        raise RagError("outside_safe_roots", "Attachment path must be relative to a configured safe root.")

    candidate: Path | None = None
    for safe_root in config.safe_roots:
        resolved_root = safe_root.resolve()
        resolved_candidate = (resolved_root / user_path).resolve()
        if is_under(resolved_candidate, resolved_root):
            candidate = resolved_candidate
            break

    if candidate is None:
        raise RagError("outside_safe_roots", "Attachment path is outside configured safe roots.")

    if not candidate.exists() or not candidate.is_file():
        raise RagError("missing_file", "Attachment file does not exist.")

    if candidate.suffix.lower() not in config.supported_extensions:
        raise RagError("unsupported_file", f"Unsupported attachment type: {candidate.suffix or '(none)'}.")

    byte_size = candidate.stat().st_size
    if byte_size == 0:
        raise RagError("empty_file", "Attachment file is empty.")

    if byte_size > config.max_bytes_per_file:
        raise RagError("file_too_large", "Attachment exceeds the configured per-file size limit.")

    return ValidationResult(file_path=candidate, byte_size=byte_size)
