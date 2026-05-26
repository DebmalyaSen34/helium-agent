from __future__ import annotations

from dataclasses import dataclass

@dataclass(frozen=True)
class FileOperationResult:
    status: str
    operation: str
    path: str | None = None
    source: str | None = None
    destination: str | None = None
    code: str | None = None
    details: str | None = None
    reason: str | None = None

    @classmethod
    def success(
        cls,
        operation: str,
        path: str | None = None,
        source: str | None = None,
        destination: str | None = None,
        details: str | None = None,
    ) -> "FileOperationResult":
        return cls(
            status="success",
            operation=operation,
            path=path,
            source=source,
            destination=destination,
            details=details,
        )
    
    @classmethod
    def error(
        cls,
        operation: str,
        path: str | None = None,
        source: str | None = None,
        destination: str | None = None,
        code: str | None = "file_operation_error",
        reason: str | None = "file operation failed",
    ) -> "FileOperationResult":
        return cls(
            status="error",
            operation=operation,
            path=path,
            source=source,
            destination=destination,
            code=code,
            reason=reason,
        )
    
    @classmethod
    def from_exception(
        cls,
        operation: str,
        error: Exception,
        path: str | None = None,
        source: str | None = None,
        destination: str | None = None,
    ) -> "FileOperationResult":
        code = "unexpected_error"
        if isinstance(error, FileOperationError):
            code = error.code
        return cls.error(
            operation=operation,
            path=path,
            source=source,
            destination=destination,
            code=code,
            reason=str(error),
        )
    
    def __str__(self) -> str:
        lines = [
            f"status: {self.status}",
            f"operation: {self.operation}",
        ]

        if self.path is not None:
            lines.append(f"path: {self.path}")
        if self.source is not None:
            lines.append(f"source: {self.source}")
        if self.destination is not None:
            lines.append(f"destination: {self.destination}")
        if self.code is not None:   
            lines.append(f"code: {self.code}")
        if self.reason is not None:
            lines.append(f"reason: {self.reason}")
        if self.details is not None:
            lines.append(f"details: {self.details}")
        return "\n".join(lines)
    
class FileOperationError(Exception):
    code = "file_operation_error"

class PathOutsideProjectError(FileOperationError):
    code = "path_outside_project"

class ProtectedPathError(FileOperationError):
    code = "protected_path"

class FileConflictError(FileOperationError):
    code = "file_conflict"

class FileNotFoundForOperationError(FileOperationError):
    code = "file_not_found"

class NoTextFileError(FileOperationError):
    code = "no_text_file"

class UnsafeOperationError(FileOperationError):
    code = "unsafe_operation"
