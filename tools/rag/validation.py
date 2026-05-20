from __future__ import annotations
from pathlib import Path
from tools.rag.models import FileStatus, RagConfig

def validate_files(paths: list[Path], config: RagConfig) -> tuple[list[Path], list[FileStatus]]:
    if len(paths) > config.max_files_per_request:
        return [], [
            FileStatus(
                name="attachments",
                status="rejected",
                reason=f"Too many files. Maximum allowed is {config.max_files_per_request}."
            )
        ]
    
    accepted: list[Path] = []
    statuses: list[FileStatus] = []
    total_bytes = 0
    seen: set[Path] = set()

    for path in paths:
        resolved = path.resolve()
        name = resolved.name

        if resolved in seen:
            statuses.append(
                FileStatus(
                    name=name,
                    status="duplicated",
                    reason="File already attached."
                )
            )
            continue

        seen.add(resolved)

        if resolved.suffix.lower() not in config.supported_extensions:
            statuses.append(
                FileStatus(
                    name=name,
                    status="unsupported",
                    reason=f"File type is not supported."
                )
            )
            continue

        byte_size = resolved.stat().st_size
        if byte_size == 0:
            statuses.append(
                FileStatus(
                    name=name,
                    status="empty",
                    reason="File is empty."
                )
            )
            continue

        if byte_size > config.max_bytes_per_file:
            statuses.append(
                FileStatus(
                    name=name,
                    status="too_large",
                    reason=f"File exceeds per-file limit."
                )
            )
            continue

        total_bytes += byte_size
        if total_bytes > config.max_total_attachment_bytes:
            statuses.append(
                FileStatus(
                    name=name,
                    status="too_large",
                    reason=f"Files exceed total attachment byte limit."
                )
            )
            continue

        accepted.append(resolved)

    return accepted, statuses