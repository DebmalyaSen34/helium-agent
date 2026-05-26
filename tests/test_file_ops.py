import pytest
import hashlib

from unittest.mock import patch

from tools import file_ops

from tools.file_models import (
    FileOperationError,
    FileOperationResult,
    PathOutsideProjectError,
    ProtectedPathError,
    FileConflictError,
    FileNotFoundForOperationError,
    NoTextFileError,
    UnsafeOperationError
)

from tools.file_service import FileOperationService

def test_file_operation_result_success_format():
    result = FileOperationResult.success(
        operation="write_file",
        path="notes.txt",
        details="wrote 5 bytes",
    )

    assert str(result) == (
        "status: success\n"
        "operation: write_file\n"
        "path: notes.txt\n"
        "details: wrote 5 bytes"
    )


def test_file_operation_result_error_format():
    result = FileOperationResult.error(
        operation="write_file",
        path="../outside.txt",
        code="path_outside_project",
        reason="path is outside the project root",
    )

    assert str(result) == (
        "status: error\n"
        "operation: write_file\n"
        "path: ../outside.txt\n"
        "code: path_outside_project\n"
        "reason: path is outside the project root"
    )


def test_file_operation_errors_have_codes_and_messages():
    assert issubclass(PathOutsideProjectError, Exception)
    assert issubclass(ProtectedPathError, Exception)
    error = PathOutsideProjectError("path is outside the project root")

    assert isinstance(error, FileOperationError)
    assert error.code == "path_outside_project"
    assert str(error) == "path is outside the project root"


def test_file_operation_result_from_exception():
    error = ProtectedPathError(".git paths are protected")

    result = FileOperationResult.from_exception(
        operation="read_file",
        path=".git/config",
        error=error,
    )

    assert str(result) == (
        "status: error\n"
        "operation: read_file\n"
        "path: .git/config\n"
        "code: protected_path\n"
        "reason: .git paths are protected"
    )

def test_resolve_project_path_accepts_relative_path(tmp_path):
    service = FileOperationService(tmp_path)

    resolved = service.resolve_project_path("src/app.py")

    assert resolved.absolute_path == tmp_path / "src" / "app.py"
    assert resolved.display_path == "src/app.py"


def test_resolve_project_path_accepts_absolute_inside_root(tmp_path):
    service = FileOperationService(tmp_path)
    target = tmp_path / "src" / "app.py"

    resolved = service.resolve_project_path(str(target))

    assert resolved.absolute_path == target
    assert resolved.display_path == "src/app.py"


def test_resolve_project_path_rejects_parent_escape(tmp_path):
    service = FileOperationService(tmp_path)

    with pytest.raises(PathOutsideProjectError):
        service.resolve_project_path("../outside.txt")


def test_resolve_project_path_rejects_absolute_outside_root(tmp_path):
    service = FileOperationService(tmp_path)

    with pytest.raises(PathOutsideProjectError):
        service.resolve_project_path("/tmp/outside.txt")


def test_resolve_project_path_rejects_empty_path(tmp_path):
    service = FileOperationService(tmp_path)

    with pytest.raises(PathOutsideProjectError):
        service.resolve_project_path("")


def test_resolve_project_path_rejects_git_directory(tmp_path):
    service = FileOperationService(tmp_path)

    with pytest.raises(ProtectedPathError):
        service.resolve_project_path(".git/config")


def test_resolve_project_path_rejects_symlink_escape(tmp_path):
    outside = tmp_path.parent / f"{tmp_path.name}-outside"
    outside.mkdir()
    link = tmp_path / "link"
    link.symlink_to(outside, target_is_directory=True)
    service = FileOperationService(tmp_path)

    with pytest.raises(PathOutsideProjectError):
        service.resolve_project_path("link/secret.txt")

def test_write_file_creates_file(tmp_path):
    service = FileOperationService(tmp_path)

    result = service.write_file("notes.txt", "hello")

    assert (tmp_path / "notes.txt").read_text(encoding="utf-8") == "hello"
    assert result.status == "success"
    assert result.path == "notes.txt"


def test_write_file_create_only_rejects_existing_file(tmp_path):
    (tmp_path / "notes.txt").write_text("old", encoding="utf-8")
    service = FileOperationService(tmp_path)

    with pytest.raises(FileConflictError):
        service.write_file("notes.txt", "new", mode="create_only")


def test_append_file_appends_text(tmp_path):
    (tmp_path / "notes.txt").write_text("hello", encoding="utf-8")
    service = FileOperationService(tmp_path)

    service.append_file("notes.txt", " world")

    assert (tmp_path / "notes.txt").read_text(encoding="utf-8") == "hello world"


def test_read_file_supports_line_ranges(tmp_path):
    (tmp_path / "notes.txt").write_text("one\ntwo\nthree\n", encoding="utf-8")
    service = FileOperationService(tmp_path)

    result = service.read_file("notes.txt", start_line=2, end_line=3)

    assert "two\nthree" in result.details


def test_read_file_respects_max_chars(tmp_path):
    (tmp_path / "notes.txt").write_text("abcdef", encoding="utf-8")
    service = FileOperationService(tmp_path)

    result = service.read_file("notes.txt", max_chars=3)

    assert result.details == "abc\n[truncated at 3 chars]"


def test_read_file_rejects_invalid_utf8(tmp_path):
    (tmp_path / "bad.txt").write_bytes(b"\xff\xfe")
    service = FileOperationService(tmp_path)

    with pytest.raises(NoTextFileError):
        service.read_file("bad.txt")


def test_mkdir_creates_directory(tmp_path):
    service = FileOperationService(tmp_path)

    service.mkdir("src/pkg", parents=True, exist_ok=True)

    assert (tmp_path / "src" / "pkg").is_dir()


def test_touch_file_creates_file(tmp_path):
    service = FileOperationService(tmp_path)

    service.touch_file("empty.txt")

    assert (tmp_path / "empty.txt").is_file()


def test_stat_file_reports_metadata(tmp_path):
    (tmp_path / "notes.txt").write_text("hello", encoding="utf-8")
    service = FileOperationService(tmp_path)

    result = service.stat_file("notes.txt")

    assert "type=file" in result.details
    assert "size=5" in result.details


def test_checksum_file_returns_sha256(tmp_path):
    (tmp_path / "notes.txt").write_text("hello", encoding="utf-8")
    service = FileOperationService(tmp_path)

    result = service.checksum_file("notes.txt")

    assert hashlib.sha256(b"hello").hexdigest() in result.details


def test_read_missing_file_raises_controlled_error(tmp_path):
    service = FileOperationService(tmp_path)

    with pytest.raises(FileNotFoundForOperationError):
        service.read_file("missing.txt")

def test_delete_file_permanently_deletes_file(tmp_path):
    (tmp_path / "notes.txt").write_text("hello", encoding="utf-8")
    service = FileOperationService(tmp_path)

    service.delete_file("notes.txt")

    assert not (tmp_path / "notes.txt").exists()


def test_delete_file_rejects_directory_without_recursive(tmp_path):
    (tmp_path / "src").mkdir()
    service = FileOperationService(tmp_path)

    with pytest.raises(UnsafeOperationError):
        service.delete_file("src")


def test_delete_file_recursive_deletes_directory(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("print('hi')", encoding="utf-8")
    service = FileOperationService(tmp_path)

    service.delete_file("src", recursive=True)

    assert not (tmp_path / "src").exists()


def test_copy_file_rejects_existing_destination_without_overwrite(tmp_path):
    (tmp_path / "a.txt").write_text("a", encoding="utf-8")
    (tmp_path / "b.txt").write_text("b", encoding="utf-8")
    service = FileOperationService(tmp_path)

    with pytest.raises(FileConflictError):
        service.copy_file("a.txt", "b.txt")


def test_copy_file_overwrites_destination(tmp_path):
    (tmp_path / "a.txt").write_text("a", encoding="utf-8")
    (tmp_path / "b.txt").write_text("b", encoding="utf-8")
    service = FileOperationService(tmp_path)

    service.copy_file("a.txt", "b.txt", overwrite=True)

    assert (tmp_path / "b.txt").read_text(encoding="utf-8") == "a"


def test_move_file_moves_source_to_destination(tmp_path):
    (tmp_path / "a.txt").write_text("a", encoding="utf-8")
    service = FileOperationService(tmp_path)

    service.move_file("a.txt", "b.txt")

    assert not (tmp_path / "a.txt").exists()
    assert (tmp_path / "b.txt").read_text(encoding="utf-8") == "a"


def test_list_directory_non_recursive(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("", encoding="utf-8")
    (tmp_path / "top.txt").write_text("", encoding="utf-8")
    service = FileOperationService(tmp_path)

    result = service.list_directory(".")

    assert "src/" in result.details
    assert "top.txt" in result.details
    assert "src/app.py" not in result.details


def test_list_directory_recursive(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("", encoding="utf-8")
    service = FileOperationService(tmp_path)

    result = service.list_directory(".", recursive=True)

    assert "src/app.py" in result.details

def test_search_text_finds_matches(tmp_path):
    (tmp_path / "a.txt").write_text("hello\nworld\n", encoding="utf-8")
    service = FileOperationService(tmp_path)

    result = service.search_text("world")

    assert "a.txt:2:world" in result.details


def test_search_text_respects_glob(tmp_path):
    (tmp_path / "a.txt").write_text("needle", encoding="utf-8")
    (tmp_path / "a.py").write_text("needle", encoding="utf-8")
    service = FileOperationService(tmp_path)

    result = service.search_text("needle", glob="*.py")

    assert "a.py" in result.details
    assert "a.txt" not in result.details


def test_search_text_case_insensitive_by_default(tmp_path):
    (tmp_path / "a.txt").write_text("Needle", encoding="utf-8")
    service = FileOperationService(tmp_path)

    result = service.search_text("needle")

    assert "a.txt:1:Needle" in result.details


def test_replace_text_respects_expected_count(tmp_path):
    (tmp_path / "a.txt").write_text("one two one", encoding="utf-8")
    service = FileOperationService(tmp_path)

    with pytest.raises(UnsafeOperationError):
        service.replace_text("a.txt", "one", "three", expected_count=1)


def test_replace_text_updates_file(tmp_path):
    (tmp_path / "a.txt").write_text("one two one", encoding="utf-8")
    service = FileOperationService(tmp_path)

    service.replace_text("a.txt", "one", "three", expected_count=2)

    assert (tmp_path / "a.txt").read_text(encoding="utf-8") == "three two three"


def test_diff_text_does_not_modify_file(tmp_path):
    (tmp_path / "a.txt").write_text("old\n", encoding="utf-8")
    service = FileOperationService(tmp_path)

    result = service.diff_text("a.txt", "new\n")

    assert "--- a.txt" in result.details
    assert "+++ proposed/a.txt" in result.details
    assert (tmp_path / "a.txt").read_text(encoding="utf-8") == "old\n"


def test_patch_file_rejects_stale_hash(tmp_path):
    (tmp_path / "a.txt").write_text("old\n", encoding="utf-8")
    service = FileOperationService(tmp_path)

    with pytest.raises(UnsafeOperationError):
        service.patch_file("a.txt", "--- a.txt\n+++ a.txt\n", expected_original_hash="bad")

def test_patch_file_applies_single_file_unified_patch(tmp_path):
    (tmp_path / "a.txt").write_text("one\ntwo\nthree\n", encoding="utf-8")
    service = FileOperationService(tmp_path)
    original_hash = hashlib.sha256(b"one\ntwo\nthree\n").hexdigest()
    patch = (
        "--- a.txt\n"
        "+++ a.txt\n"
        "@@ -1,3 +1,3 @@\n"
        " one\n"
        "-two\n"
        "+TWO\n"
        " three\n"
    )

    result = service.patch_file("a.txt", patch, expected_original_hash=original_hash)

    assert result.status == "success"
    assert (tmp_path / "a.txt").read_text(encoding="utf-8") == "one\nTWO\nthree\n"

def test_write_file_wrapper_returns_success_string(tmp_path):
    with patch.object(file_ops, "PROJECT_ROOT", tmp_path):
        result = file_ops.write_file("notes.txt", "hello")

    assert "status: success" in result
    assert (tmp_path / "notes.txt").read_text(encoding="utf-8") == "hello"


def test_create_file_wrapper_uses_write_file(tmp_path):
    with patch.object(file_ops, "PROJECT_ROOT", tmp_path):
        result = file_ops.create_file("notes.txt", "hello")

    assert "operation: write_file" in result
    assert (tmp_path / "notes.txt").read_text(encoding="utf-8") == "hello"


def test_wrapper_returns_controlled_error_string(tmp_path):
    with patch.object(file_ops, "PROJECT_ROOT", tmp_path):
        result = file_ops.read_file("../outside.txt")

    assert "status: error" in result
    assert "reason:" in result
