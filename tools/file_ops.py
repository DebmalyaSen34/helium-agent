
from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable

from tools.file_models import FileOperationError, FileOperationResult
from tools.file_service import FileOperationService

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def set_project_root(path: str | Path) -> None:
    global PROJECT_ROOT
    PROJECT_ROOT = Path(path).resolve()


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
    return _run("write_file", path, lambda service: service.write_file(path, content, mode))


def append_file(path: str, content: str) -> str:
    return _run("append_file", path, lambda service: service.append_file(path, content))


def delete_file(path: str, recursive: bool = False) -> str:
    return _run("delete_file", path, lambda service: service.delete_file(path, recursive))


def copy_file(source: str, destination: str, overwrite: bool = False) -> str:
    return _run("copy_file", source, lambda service: service.copy_file(source, destination, overwrite))


def move_file(source: str, destination: str, overwrite: bool = False) -> str:
    return _run("move_file", source, lambda service: service.move_file(source, destination, overwrite))


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
    return _run("replace_text", path, lambda service: service.replace_text(path, old, new, expected_count))


def patch_file(path: str, patch: str, expected_original_hash: str | None = None) -> str:
    return _run("patch_file", path, lambda service: service.patch_file(path, patch, expected_original_hash))


def mkdir(path: str, parents: bool = True, exist_ok: bool = True) -> str:
    return _run("mkdir", path, lambda service: service.mkdir(path, parents, exist_ok))


def touch_file(path: str) -> str:
    return _run("touch_file", path, lambda service: service.touch_file(path))


def stat_file(path: str) -> str:
    return _run("stat_file", path, lambda service: service.stat_file(path))


def checksum_file(path: str, algorithm: str = "sha256") -> str:
    return _run("checksum_file", path, lambda service: service.checksum_file(path, algorithm))


def diff_text(path: str, proposed_content: str, context_lines: int = 3) -> str:
    return _run("diff_text", path, lambda service: service.diff_text(path, proposed_content, context_lines))

