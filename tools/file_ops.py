
from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable

from tools.file_models import FileOperationError, FileOperationResult
from tools.file_service import FileOperationService
from utils.file_change_display import (
    display_file_change,
    display_file_status,
    display_patch,
)

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def set_project_root(path: str | Path) -> None:
    global PROJECT_ROOT
    PROJECT_ROOT = Path(path).resolve()


def _read_before(path: str) -> str | None:
    """Read file content before an operation. Returns None if file doesn't exist or isn't readable."""
    try:
        candidate = Path(path)
        if not candidate.is_absolute():
            candidate = PROJECT_ROOT / candidate
        resolved = candidate.resolve()
        if resolved.is_file() and resolved.exists():
            return resolved.read_text(encoding="utf-8")
    except Exception:
        pass
    return None


def _run(operation: str, path: str | None, call: Callable[[FileOperationService], FileOperationResult]) -> str:
    service = FileOperationService(PROJECT_ROOT)
    try:
        return str(call(service))
    except FileOperationError as exc:
        return str(FileOperationResult.from_exception(operation=operation, path=path, error=exc))
    except Exception as exc:
        logger.error("Unexpected file operation error", exc_info=True)
        return str(FileOperationResult.from_exception(operation=operation, path=path, error=exc))


def create_file(filename: str, content: str) -> str:
    return write_file(filename, content, mode="overwrite")


def read_file(path: str, start_line: int | None = None, end_line: int | None = None, max_chars: int = 20000) -> str:
    return _run("read_file", path, lambda service: service.read_file(path, start_line, end_line, max_chars))


def write_file(path: str, content: str, mode: str = "overwrite") -> str:
    old = _read_before(path)
    result = _run("write_file", path, lambda service: service.write_file(path, content, mode))
    if "success" in result:
        display_file_change("write_file", path, old, content)
    return result


def append_file(path: str, content: str) -> str:
    old = _read_before(path)
    result = _run("append_file", path, lambda service: service.append_file(path, content))
    if "success" in result:
        display_file_change("append_file", path, old, (old or "") + content)
    return result


def delete_file(path: str, recursive: bool = False) -> str:
    old = _read_before(path)
    result = _run("delete_file", path, lambda service: service.delete_file(path, recursive))
    if "success" in result:
        display_file_change("delete_file", path, old, None)
    return result


def copy_file(source: str, destination: str, overwrite: bool = False) -> str:
    result = _run("copy_file", source, lambda service: service.copy_file(source, destination, overwrite))
    if "success" in result:
        display_file_status("copy_file", source, f"→ {destination}")
    return result


def move_file(source: str, destination: str, overwrite: bool = False) -> str:
    result = _run("move_file", source, lambda service: service.move_file(source, destination, overwrite))
    if "success" in result:
        display_file_status("move_file", source, f"→ {destination}")
    return result


def list_directory(path: str = ".", recursive: bool = False, max_entries: int = 200) -> str:
    return _run("list_directory", path, lambda service: service.list_directory(path, recursive, max_entries))


def search_text(
    query: str,
    path: str = ".",
    glob: str | None = None,
    case_sensitive: bool = False,
    max_matches: int = 100,
) -> str:
    return _run(
        "search_text",
        path,
        lambda service: service.search_text(query, path, glob, case_sensitive, max_matches),
    )


def replace_text(path: str, old: str, new: str, expected_count: int | None = None) -> str:
    old_content = _read_before(path)
    result = _run("replace_text", path, lambda service: service.replace_text(path, old, new, expected_count))
    if "success" in result and old_content is not None:
        new_content = old_content.replace(old, new) if expected_count is None else old_content.replace(old, new, expected_count)
        display_file_change("replace_text", path, old_content, new_content)
    return result


def patch_file(path: str, patch: str, expected_original_hash: str | None = None) -> str:
    result = _run("patch_file", path, lambda service: service.patch_file(path, patch, expected_original_hash))
    if "success" in result:
        display_patch(path, patch)
    return result


def mkdir(path: str, parents: bool = True, exist_ok: bool = True) -> str:
    result = _run("mkdir", path, lambda service: service.mkdir(path, parents, exist_ok))
    if "success" in result:
        display_file_status("mkdir", path)
    return result


def touch_file(path: str) -> str:
    result = _run("touch_file", path, lambda service: service.touch_file(path))
    if "success" in result:
        display_file_status("touch_file", path)
    return result


def stat_file(path: str) -> str:
    return _run("stat_file", path, lambda service: service.stat_file(path))


def checksum_file(path: str, algorithm: str = "sha256") -> str:
    return _run("checksum_file", path, lambda service: service.checksum_file(path, algorithm))


def diff_text(path: str, proposed_content: str, context_lines: int = 3) -> str:
    return _run("diff_text", path, lambda service: service.diff_text(path, proposed_content, context_lines))

