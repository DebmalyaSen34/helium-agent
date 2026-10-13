from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path

from rag_service.config import RagServiceConfig
from rag_service.models import RagError
from rag_service.validation import is_under


MENTION_RE = re.compile(r"(?<![\w.])@(?P<target>[^\s]+)")


@dataclass(frozen=True)
class ResolvedMention:
    file_path: Path
    question: str
    display: str


IGNORED_DIRS = frozenset(
    {".git", ".hg", ".svn", ".venv", "venv", "env", "node_modules", "__pycache__",
     ".mypy_cache", ".pytest_cache", ".ruff_cache", ".tox", ".cache", "dist", "build", "site-packages"}
)
TRAILING_PUNCTUATION = ".,;:!?)]}'\""
PATH_LIKE_RE = re.compile(r"[/\\]|\.[A-Za-z0-9]{1,6}$")


def looks_like_path(target: str) -> bool:
    """`@notes.md` or `@src/app` look like files; `@decorator` or `@alice` do not."""
    return bool(PATH_LIKE_RE.search(target))


def resolve_single_mention(text: str, config: RagServiceConfig) -> ResolvedMention | None:
    """Find the one @file attachment in `text`.

    Mentions that look like paths must resolve, or an error explains why. Plain
    `@words` (decorators, handles) that match no file are left as ordinary text.
    """
    resolved: list[tuple[re.Match, str, Path]] = []
    for match in MENTION_RE.finditer(text):
        raw_target = match.group("target").strip().rstrip(TRAILING_PUNCTUATION)
        if not raw_target:
            continue
        path = _resolve_exact(raw_target, config)
        if path is None:
            try:
                path = _resolve_fuzzy(raw_target, config)
            except RagError:
                if looks_like_path(raw_target):
                    raise
                continue
        resolved.append((match, raw_target, path))

    if not resolved:
        return None
    if len(resolved) > 1:
        raise RagError("too_many_attachments", "Terminal RAG v1 supports exactly one @file attachment per prompt.")

    match, raw_target, path = resolved[0]
    question = f"{text[:match.start()]}{text[match.end():]}".strip()
    question = " ".join(question.split())
    if not question:
        question = "Summarize the attached file."

    return ResolvedMention(file_path=path, question=question, display=raw_target)


def _resolve_exact(raw_target: str, config: RagServiceConfig) -> Path | None:
    candidate = Path(raw_target).expanduser()
    candidates = [candidate] if candidate.is_absolute() else [Path.cwd() / candidate]
    for safe_root in config.safe_roots:
        if not candidate.is_absolute():
            candidates.append(safe_root / candidate)

    for item in candidates:
        resolved = item.resolve()
        if resolved.exists() and resolved.is_file() and any(is_under(resolved, root) for root in config.safe_roots):
            return resolved
    return None


def _resolve_fuzzy(raw_target: str, config: RagServiceConfig) -> Path:
    query = raw_target.lower().lstrip("@")
    matches: list[tuple[float, Path]] = []
    for root in config.safe_roots:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in config.supported_extensions:
                continue
            if any(part in IGNORED_DIRS for part in path.relative_to(root).parts):
                continue
            name_score = SequenceMatcher(None, query, path.name.lower()).ratio()
            stem_score = SequenceMatcher(None, query, path.stem.lower()).ratio()
            contains_score = 0.95 if query in path.name.lower() or query in str(path.relative_to(root)).lower() else 0.0
            score = max(name_score, stem_score, contains_score)
            if score >= 0.72:
                matches.append((score, path.resolve()))

    matches.sort(key=lambda item: (-item[0], len(str(item[1])), str(item[1])))
    if not matches:
        raise RagError("mention_not_found", f"No safe file matched @{raw_target}.")

    top_score = matches[0][0]
    top = [path for score, path in matches if score >= top_score - 0.03]
    if len(top) > 1:
        suggestions = ", ".join(str(path) for path in top[:5])
        raise RagError("ambiguous_mention", f"@{raw_target} is ambiguous. Try an exact path. Suggestions: {suggestions}")

    return matches[0][1]
