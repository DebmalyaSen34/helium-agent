from __future__ import annotations
import re
from pathlib import Path
from tools.rag.models import FileMention, FileStatus, RagConfig

MENTION_RE = re.compile(r"(?<![\w.])@(?P<path>[A-Za-z0-9_./~ -]+\.[A-Za-z0-9]+)")

def extract_file_mentions(text: str) -> tuple[str, list[FileMention]]:
    mentions: list[FileMention] = []

    for match in MENTION_RE.finditer(text):
        path_text = match.group("path").strip()
        if not path_text:
            continue
        mentions.append(
            FileMention(
                raw=match.group(0),
                path_text=path_text,
                start=match.start(),
                end=match.end()
            )
        )

    cleaned = text
    
    for mention in reversed(mentions):
        cleaned = f"{cleaned[:mention.start]}{cleaned[mention.end:]}"

    cleaned = " ".join(cleaned.split())
    
    return cleaned, mentions

def _safe_roots(project_root: Path, config: RagConfig) -> list[Path]:
    roots: list[Path] = []
    for raw_root in config.safe_roots:
        root = Path(raw_root).expanduser()
        if not root.is_absolute():
            root = project_root / root
        roots.append(root.resolve())
    return roots

def _is_under(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False
    
def resolve_mentions(mentions: list[FileMention], project_root: Path, config: RagConfig) -> tuple[list[Path], list[FileStatus]]:
    safe_roots = _safe_roots(project_root.resolve(), config)
    resolved: list[Path] = []
    statuses: list[FileStatus] = []

    for mention in mentions:
        raw_path = Path(mention.path_text).expanduser()
        candidate = raw_path if raw_path.is_absolute() else project_root / raw_path
        candidate = candidate.resolve()

        if not any(_is_under(candidate, root) for root in safe_roots):
            statuses.append(
                FileStatus(
                    name=mention.path_text,
                    status="rejected",
                    reason="Path is outside allowed roots"
                )
            )
            continue

        if not candidate.exists() or not candidate.is_file():
            statuses.append(
                FileStatus(
                    name=mention.path_text,
                    status="rejected",
                    reason="File does not exist"
                )
            )
            continue

        resolved.append(candidate)

    return resolved, statuses