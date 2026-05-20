from __future__ import annotations
from pathlib import Path

def read_text_file(path: Path) -> str:
    return path.read_text(encoding="utf-8")