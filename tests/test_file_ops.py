from tools.file_models import (
    FileOperationError,
    FileOperationResult,
    PathOutsideProjectError,
    ProtectedPathError,
)


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