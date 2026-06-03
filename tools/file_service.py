from __future__ import annotations

import hashlib
import os
import tempfile
import difflib
import fnmatch
import shutil
from datetime import datetime, timezone

from dataclasses import dataclass
from pathlib import Path

from tools.file_models import (
    PathOutsideProjectError, 
    ProtectedPathError,
    FileNotFoundForOperationError,
    FileConflictError,
    FileOperationResult,
    NoTextFileError,
    UnsafeOperationError
)
@dataclass(frozen=True)
class ResolvedProjectPath:
    absolute_path: Path
    display_path: str

class FileOperationService:
    def __init__(self, project_root: str | Path):
        self.project_root = Path(project_root).resolve()

    def resolve_project_path(self, path: str) -> ResolvedProjectPath:
        if path is None or str(path).strip() == "":
            raise PathOutsideProjectError("path is impty")

        candidate = Path(path)
        if not candidate.is_absolute():
            candidate = self.project_root / candidate

        resolved = self._resolve_existing_prefix(candidate)

        try:
            display_path = resolved.relative_to(self.project_root).as_posix()
        except ValueError as exc:
            raise PathOutsideProjectError("path is outside the project root") from exc

        if display_path == ".git" or display_path.startswith(".git/"):
            raise ProtectedPathError(".git paths are protected")

        return ResolvedProjectPath(absolute_path=resolved, display_path=display_path)

    def _resolve_existing_prefix(self, candidate: Path) -> Path:
        existing = candidate
        missing_parts: list[str] =[]

        while not existing.exists() and existing != existing.parent:
            missing_parts.append(existing.name)
            existing = existing.parent

        resolved_existing = existing.resolve()
        resolved = resolved_existing
        for part in reversed(missing_parts):
            resolved = resolved / part
        return resolved

    def read_file(
        self,
        path: str,
        start_line: int | None = None,
        end_line: int | None = None,
        max_chars: int = 20000,
    ) -> FileOperationResult:
        resolved = self.resolve_project_path(path)
        if not resolved.absolute_path.is_file():
            raise FileNotFoundForOperationError("file does not exist")
        try:
            content = resolved.absolute_path.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            raise NoTextFileError("file is not valid UTF-8 text") from exc

        if start_line is not None or end_line is not None:
            lines = content.splitlines(keepends=True)
            start = 0 if start_line is None else max(start_line - 1, 0)
            end = None if end_line is None else max(end_line, start)
            content = "".join(lines[start:end])

        truncated = content[:max_chars]
        suffix = "" if len(content) <= max_chars else f"\n[truncated at {max_chars} chars]"
        return FileOperationResult(
            status="success",
            operation="read_file",
            path=resolved.display_path,
            details=truncated + suffix,
        )

    def _apply_unified_patch(self, content: str, patch: str) -> str:
        original_lines = content.splitlines(keepends=True)
        patch_lines = patch.splitlines(keepends=True)
        output: list[str] = []
        original_index = 0
        patch_index = 0

        while patch_index < len(patch_lines):
            line = patch_lines[patch_index]
            if line.startswith("--- ") or line.startswith("+++ "):
                patch_index += 1
                continue
            if not line.startswith("@@ "):
                raise UnsafeOperationError("invalid unified diff hunk header")

            old_start = self._parse_hunk_old_start(line)
            target_index = old_start - 1
            output.extend(original_lines[original_index:target_index])
            original_index = target_index
            patch_index += 1

            while patch_index < len(patch_lines) and not patch_lines[patch_index].startswith("@@ "):
                patch_line = patch_lines[patch_index]
                marker = patch_line[:1]
                text = patch_line[1:]
                if marker == " ":
                    if original_index >= len(original_lines) or original_lines[original_index] != text:
                        raise UnsafeOperationError("patch context does not match file")
                    output.append(original_lines[original_index])
                    original_index += 1
                elif marker == "-":
                    if original_index >= len(original_lines) or original_lines[original_index] != text:
                        raise UnsafeOperationError("patch deletion does not match file")
                    original_index += 1
                elif marker == "+":
                    output.append(text)
                elif patch_line.startswith("\\ No newline at end of file"):
                    pass
                else:
                    raise UnsafeOperationError("invalid unified diff line")
                patch_index += 1

        output.extend(original_lines[original_index:])
        return "".join(output)

    def _parse_hunk_old_start(self, hunk_header: str) -> int:
        try:
            old_range = hunk_header.split(" ", 2)[1]
            start = old_range.split(",", 1)[0].lstrip("-")
            return int(start)
        except (IndexError, ValueError) as exc:
            raise UnsafeOperationError("invalid unified diff hunk header") from exc
    

    def write_file(self, path: str, content: str, mode: str = "overwrite") -> FileOperationResult:
        resolved = self.resolve_project_path(path)
        if mode not in {"overwrite", "create_only"}:
            raise UnsafeOperationError("mode must be 'overwrite' or 'create_only'")
        if mode == "create_only" and resolved.absolute_path.exists():
            raise FileConflictError("file already exists")
        if not resolved.absolute_path.parent.exists():
            raise FileNotFoundForOperationError("parent directory does not exist")

        fd, temp_name = tempfile.mkstemp(
            prefix=f".{resolved.absolute_path.name}.",
            suffix=".tmp",
            dir=str(resolved.absolute_path.parent),
            text=True,
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(content)
            os.replace(temp_name, resolved.absolute_path)
        except Exception:
            Path(temp_name).unlink(missing_ok=True)
            raise

        return FileOperationResult(
            status="success",
            operation="write_file",
            path=resolved.display_path,
            details=f"wrote {len(content.encode('utf-8'))} bytes",
        )

    def append_file(self, path: str, content: str) -> FileOperationResult:
        resolved = self.resolve_project_path(path)
        if not resolved.absolute_path.parent.exists():
            raise FileNotFoundForOperationError("parent directory does not exist")
        with resolved.absolute_path.open("a", encoding="utf-8") as handle:
            handle.write(content)
        return FileOperationResult(
            status="success",
            operation="append_file",
            path=resolved.display_path,
            details=f"appended {len(content.encode('utf-8'))} bytes",
        )

    def mkdir(self, path: str, parents: bool = True, exist_ok: bool = True) -> FileOperationResult:
        resolved = self.resolve_project_path(path)
        resolved.absolute_path.mkdir(parents=parents, exist_ok=exist_ok)
        return FileOperationResult(
            status="success",
            operation="mkdir",
            path=resolved.display_path,
            details="directory created",
        )

    def touch_file(self, path: str) -> FileOperationResult:
        resolved = self.resolve_project_path(path)
        if not resolved.absolute_path.parent.exists():
            raise FileNotFoundForOperationError("parent directory does not exist")
        resolved.absolute_path.touch()
        return FileOperationResult(
            status="success",
            operation="touch_file",
            path=resolved.display_path,
            details="file touched",
        )

    def stat_file(self, path: str) -> FileOperationResult:
        resolved = self.resolve_project_path(path)
        if not resolved.absolute_path.exists():
            raise FileNotFoundForOperationError("path does not exist")
        stat = resolved.absolute_path.stat()
        kind = "directory" if resolved.absolute_path.is_dir() else "file"
        modified = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat()
        return FileOperationResult(
            status="success",
            operation="stat_file",
            path=resolved.display_path,
            details=f"type={kind} size={stat.st_size} modified={modified}",
        )

    def checksum_file(self, path: str, algorithm: str = "sha256") -> FileOperationResult:
        if algorithm not in {"sha256", "sha1", "md5"}:
            raise UnsafeOperationError("algorithm must be sha256, sha1, or md5")
        resolved = self.resolve_project_path(path)
        if not resolved.absolute_path.is_file():
            raise FileNotFoundForOperationError("file does not exist")

        digest = hashlib.new(algorithm)
        with resolved.absolute_path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return FileOperationResult(
            status="success",
            operation="checksum_file",
            path=resolved.display_path,
            details=f"{algorithm}={digest.hexdigest()}",
        )

    def delete_file(self, path: str, recursive: bool = False) -> FileOperationResult:
        resolved = self.resolve_project_path(path)
        if not resolved.absolute_path.exists():
            raise FileNotFoundForOperationError("path does not exist")
        if resolved.absolute_path.is_dir():
            if not recursive:
                raise UnsafeOperationError("recursive=True is required to delete a directory")
            shutil.rmtree(resolved.absolute_path)
            details = "directory permanently deleted"
        else:
            resolved.absolute_path.unlink()
            details = "file permanently deleted"
        return FileOperationResult(
            status="success",
            operation="delete_file",
            path=resolved.display_path,
            details=details,
        )

    def copy_file(self, source: str, destination: str, overwrite: bool = False) -> FileOperationResult:
        src = self.resolve_project_path(source)
        dst = self.resolve_project_path(destination)
        if not src.absolute_path.exists():
            raise FileNotFoundForOperationError("source does not exist")
        if dst.absolute_path.exists():
            if not overwrite:
                raise FileConflictError("destination already exists")
            if dst.absolute_path.is_dir():
                shutil.rmtree(dst.absolute_path)
            else:
                dst.absolute_path.unlink()
        if not dst.absolute_path.parent.exists():
            raise FileNotFoundForOperationError("destination parent directory does not exist")

        if src.absolute_path.is_dir():
            shutil.copytree(src.absolute_path, dst.absolute_path)
            details = "directory copied"
        else:
            shutil.copy2(src.absolute_path, dst.absolute_path)
            details = "file copied"
        return FileOperationResult(
            status="success",
            operation="copy_file",
            source=src.display_path,
            destination=dst.display_path,
            details=details,
        )

    def move_file(self, source: str, destination: str, overwrite: bool = False) -> FileOperationResult:
        src = self.resolve_project_path(source)
        dst = self.resolve_project_path(destination)
        if not src.absolute_path.exists():
            raise FileNotFoundForOperationError("source does not exist")
        if dst.absolute_path.exists():
            if not overwrite:
                raise FileConflictError("destination already exists")
            if dst.absolute_path.is_dir():
                shutil.rmtree(dst.absolute_path)
            else:
                dst.absolute_path.unlink()
        if not dst.absolute_path.parent.exists():
            raise FileNotFoundForOperationError("destination parent directory does not exist")

        shutil.move(str(src.absolute_path), str(dst.absolute_path))
        return FileOperationResult(
            status="success",
            operation="move_file",
            source=src.display_path,
            destination=dst.display_path,
            details="path moved",
        )

    def list_directory(
        self,
        path: str = ".",
        recursive: bool = False,
        max_entries: int = 200,
    ) -> FileOperationResult:
        resolved = self.resolve_project_path(path)
        if not resolved.absolute_path.is_dir():
            raise FileNotFoundForOperationError("directory does not exist")

        entries: list[str] = []
        iterator = resolved.absolute_path.rglob("*") if recursive else resolved.absolute_path.iterdir()
        for entry in sorted(iterator):
            if len(entries) >= max_entries:
                break
            try:
                relative = entry.resolve().relative_to(self.project_root).as_posix()
            except ValueError:
                relative = entry.relative_to(self.project_root).as_posix()
            suffix = "/" if entry.is_dir() else ""
            entries.append(relative + suffix)

        truncated = "" if len(entries) < max_entries else f"\n[truncated at {max_entries} entries]"
        return FileOperationResult(
            status="success",
            operation="list_directory",
            path=resolved.display_path,
            details="\n".join(entries) + truncated,
        )

    def search_text(
        self,
        query: str,
        path: str = ".",
        glob: str | None = None,
        case_sensitive: bool = False,
        max_matches: int = 100,
    ) -> FileOperationResult:
        resolved = self.resolve_project_path(path)
        if not resolved.absolute_path.exists():
            raise FileNotFoundForOperationError("path does not exist")
        files = [resolved.absolute_path] if resolved.absolute_path.is_file() else sorted(resolved.absolute_path.rglob("*"))

        needle = query if case_sensitive else query.casefold()
        matches: list[str] = []
        skipped = 0
        for file_path in files:
            if len(matches) >= max_matches:
                break
            if not file_path.is_file():
                continue
            try:
                relative = file_path.resolve().relative_to(self.project_root).as_posix()
            except ValueError:
                continue
            if glob is not None and not fnmatch.fnmatch(relative, glob):
                continue
            try:
                lines = file_path.read_text(encoding="utf-8").splitlines()
            except UnicodeDecodeError:
                skipped += 1
                continue
            for line_number, line in enumerate(lines, start=1):
                haystack = line if case_sensitive else line.casefold()
                if needle in haystack:
                    matches.append(f"{relative}:{line_number}:{line}")
                    if len(matches) >= max_matches:
                        break

        details = "\n".join(matches)
        if skipped:
            details += f"\n[skipped {skipped} non-text files]"
        if len(matches) >= max_matches:
            details += f"\n[truncated at {max_matches} matches]"
        return FileOperationResult(
            status="success",
            operation="search_text",
            path=resolved.display_path,
            details=details,
        )

    def replace_text(
        self,
        path: str,
        old: str,
        new: str,
        expected_count: int | None = None,
    ) -> FileOperationResult:
        if old == "":
            raise UnsafeOperationError("old text must not be empty")
        resolved = self.resolve_project_path(path)
        if not resolved.absolute_path.is_file():
            raise FileNotFoundForOperationError("file does not exist")
        try:
            content = resolved.absolute_path.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            raise NoTextFileError("file is not valid UTF-8 text") from exc
        count = content.count(old)
        if expected_count is not None and count != expected_count:
            raise UnsafeOperationError(f"expected {expected_count} matches, found {count}")
        self.write_file(path, content.replace(old, new))
        return FileOperationResult(
            status="success",
            operation="replace_text",
            path=resolved.display_path,
            details=f"replaced {count} occurrences",
        )

    def diff_text(self, path: str, proposed_content: str, context_lines: int = 3) -> FileOperationResult:
        resolved = self.resolve_project_path(path)
        if not resolved.absolute_path.is_file():
            raise FileNotFoundForOperationError("file does not exist")
        try:
            current = resolved.absolute_path.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            raise NoTextFileError("file is not valid UTF-8 text") from exc
        diff = difflib.unified_diff(
            current.splitlines(keepends=True),
            proposed_content.splitlines(keepends=True),
            fromfile=resolved.display_path,
            tofile=f"proposed/{resolved.display_path}",
            n=context_lines,
        )
        return FileOperationResult(
            status="success",
            operation="diff_text",
            path=resolved.display_path,
            details="".join(diff),
        )

    def patch_file(
        self,
        path: str,
        patch: str,
        expected_original_hash: str | None = None,
    ) -> FileOperationResult:
        resolved = self.resolve_project_path(path)
        if not resolved.absolute_path.is_file():
            raise FileNotFoundForOperationError("file does not exist")
        current_bytes = resolved.absolute_path.read_bytes()
        current_hash = hashlib.sha256(current_bytes).hexdigest()
        if expected_original_hash is not None and current_hash != expected_original_hash:
            raise UnsafeOperationError("current file hash does not match expected_original_hash")
        try:
            current = current_bytes.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise NoTextFileError("file is not valid UTF-8 text") from exc

        patched = self._apply_unified_patch(current, patch)
        self.write_file(path, patched)
        return FileOperationResult(
            status="success",
            operation="patch_file",
            path=resolved.display_path,
            details="patch applied",
        )
      
