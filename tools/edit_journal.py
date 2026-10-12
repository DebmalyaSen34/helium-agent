"""Snapshots of files before the agent changes them, so /undo can restore them."""

from __future__ import annotations

import os
import shutil
import tempfile
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_MAX_GROUPS = 50
DEFAULT_MAX_BYTES_PER_FILE = 5_000_000


@dataclass
class _Snapshot:
    path: Path
    existed: bool
    was_dir: bool = False
    content: bytes | None = None
    spill: Path | None = None
    too_large: bool = False


@dataclass
class EditGroup:
    label: str
    snapshots: list[_Snapshot] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    spill_dir: Path | None = None

    def discard(self) -> None:
        if self.spill_dir is not None:
            shutil.rmtree(self.spill_dir, ignore_errors=True)
            self.spill_dir = None


@dataclass
class UndoResult:
    label: str
    restored: list[Path]
    skipped: list[Path]


class EditJournal:
    def __init__(
        self,
        max_groups: int = DEFAULT_MAX_GROUPS,
        max_bytes_per_file: int = DEFAULT_MAX_BYTES_PER_FILE,
        spill_root: Path | None = None,
    ) -> None:
        self.max_groups = max_groups
        self.max_bytes_per_file = max_bytes_per_file
        self.spill_root = spill_root
        self._groups: list[EditGroup] = []
        self._lock = threading.Lock()

    def __len__(self) -> int:
        return len(self._groups)

    def snapshot(self, label: str, paths: list[Path]) -> EditGroup:
        group = EditGroup(label=label)
        for path in paths:
            group.snapshots.append(self._snapshot_path(group, path))
        return group

    def commit(self, group: EditGroup) -> None:
        with self._lock:
            self._groups.append(group)
            while len(self._groups) > self.max_groups:
                self._groups.pop(0).discard()

    def undo(self) -> UndoResult | None:
        with self._lock:
            if not self._groups:
                return None
            group = self._groups.pop()

        restored: list[Path] = []
        skipped: list[Path] = []
        for snap in reversed(group.snapshots):
            if snap.too_large:
                skipped.append(snap.path)
                continue
            self._restore(snap)
            restored.append(snap.path)
        group.discard()
        return UndoResult(label=group.label, restored=list(reversed(restored)), skipped=skipped)

    def peek_label(self) -> str | None:
        with self._lock:
            return self._groups[-1].label if self._groups else None

    def clear(self) -> None:
        with self._lock:
            for group in self._groups:
                group.discard()
            self._groups.clear()

    # -- internals ---------------------------------------------------------------

    def _snapshot_path(self, group: EditGroup, path: Path) -> _Snapshot:
        if not path.exists():
            return _Snapshot(path=path, existed=False)
        if path.is_dir():
            spill = self._spill_dir(group) / f"{len(group.snapshots)}"
            shutil.copytree(path, spill, symlinks=True)
            return _Snapshot(path=path, existed=True, was_dir=True, spill=spill)
        if path.stat().st_size > self.max_bytes_per_file:
            return _Snapshot(path=path, existed=True, too_large=True)
        return _Snapshot(path=path, existed=True, content=path.read_bytes())

    def _spill_dir(self, group: EditGroup) -> Path:
        if group.spill_dir is None:
            root = self.spill_root or Path(tempfile.gettempdir()) / "helium-agent-undo"
            root.mkdir(parents=True, exist_ok=True)
            group.spill_dir = Path(tempfile.mkdtemp(prefix="undo-", dir=root))
        return group.spill_dir

    @staticmethod
    def _remove(path: Path) -> None:
        if path.is_dir() and not path.is_symlink():
            shutil.rmtree(path)
        elif path.exists() or path.is_symlink():
            path.unlink()

    def _restore(self, snap: _Snapshot) -> None:
        if not snap.existed:
            self._remove(snap.path)
            return
        if snap.was_dir and snap.spill is not None:
            self._remove(snap.path)
            shutil.copytree(snap.spill, snap.path, symlinks=True)
            return
        if snap.content is None:
            return
        if snap.path.is_dir():
            shutil.rmtree(snap.path)
        snap.path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(prefix=f".{snap.path.name}.", suffix=".undo", dir=str(snap.path.parent))
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(snap.content)
            os.replace(temp_name, snap.path)
        except Exception:
            Path(temp_name).unlink(missing_ok=True)
            raise


JOURNAL = EditJournal()

__all__ = ["EditGroup", "EditJournal", "JOURNAL", "UndoResult"]
