"""Per-user and per-workspace data locations."""

from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path

try:
    from platformdirs import user_data_dir
except ModuleNotFoundError:  # pragma: no cover - optional dependency fallback
    user_data_dir = None

APP_NAME = "helium-agent"


def user_data_root() -> Path:
    override = os.getenv("HELIUM_DATA_DIR")
    if override:
        return Path(override).expanduser()
    if user_data_dir is None:
        return Path.home() / ".local" / "share" / APP_NAME
    return Path(user_data_dir(APP_NAME))


def workspace_id(workspace: Path) -> str:
    return hashlib.sha256(str(Path(workspace).resolve()).encode("utf-8")).hexdigest()[:16]


def workspace_data_dir(workspace: Path) -> Path:
    """Private directory for one workspace's memory and history (created on demand)."""
    workspace = Path(workspace).resolve()
    directory = user_data_root() / "workspaces" / workspace_id(workspace)
    directory.mkdir(parents=True, exist_ok=True)
    try:
        directory.chmod(0o700)
    except OSError:  # pragma: no cover
        pass
    marker = directory / "workspace.json"
    if not marker.exists():
        marker.write_text(json.dumps({"path": str(workspace), "created": int(time.time())}, indent=2))
    return directory


__all__ = ["user_data_root", "workspace_data_dir", "workspace_id"]
