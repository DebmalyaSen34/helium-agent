from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_manager = None  # PersistentMemoryManager instance, set by initialize_session()


# ---------------------------------------------------------------------------
# Public API — delegates to PersistentMemoryManager
# ---------------------------------------------------------------------------

# Category mapping: old plural names -> new singular names
_CATEGORY_MAP = {
    "facts": "fact",
    "preferences": "preference",
    "fact": "fact",
    "preference": "preference",
    "project": "project",
}


_startup_context: str | None = None

MAX_TURN_CHARS = 1_000
MAX_SUMMARY_CHARS = 4_000
LEGACY_GLOBAL_DB_NAME = "memory.db"


def default_db_path(workspace: Path | None = None) -> Path:
    """Memory lives in the user's data dir, one database per workspace."""
    from config.paths import workspace_data_dir

    return workspace_data_dir(workspace or Path.cwd()) / "memory.db"


def legacy_global_db() -> Path | None:
    """The pre-0.2 global database that lived next to the installed package, if present."""
    from config.settings import BASE_DIR

    path = BASE_DIR / LEGACY_GLOBAL_DB_NAME
    return path if path.exists() else None


def initialize_session(db_path=None, workspace: Path | None = None) -> None:
    """Start a session backed by PersistentMemoryManager (on-disk).

    Args:
        db_path: Optional database path. Defaults to this workspace's database
            under the user data directory.
        workspace: Workspace whose memory to open; defaults to the cwd.

    shutdown_session() should run on process exit to store the session summary.
    """
    from memory.manager import PersistentMemoryManager

    global _manager, _startup_context
    path = str(db_path or default_db_path(workspace))
    _manager = PersistentMemoryManager(path)
    session_id, context = _manager.startup()
    _manager.session_id = session_id
    _startup_context = context
    logger.debug(
        "Session memory initialized (PersistentMemoryManager, db=%s) session_id=%s.",
        path, session_id,
    )


def get_session_summary(max_chars: int = MAX_SUMMARY_CHARS) -> str | None:
    """The previous session's conversation summary for this workspace, if any."""
    if not _startup_context:
        return None
    text = _startup_context.strip()
    if text.startswith("Session context:"):
        text = text[len("Session context:"):].strip()
    if len(text) > max_chars:
        text = "..." + text[-max_chars:]
    return text or None


def record_turn(role: str, content: str) -> None:
    """Store one user/assistant turn so it can be summarized at shutdown."""
    if _manager is None or not content or role not in ("user", "assistant"):
        return
    session_id = getattr(_manager, "session_id", None)
    if not session_id:
        return
    text = content.strip()
    if len(text) > MAX_TURN_CHARS:
        text = text[:MAX_TURN_CHARS] + " ...[truncated]"
    try:
        _manager.append_conversation(session_id, role, text)
    except Exception as e:
        logger.debug("Could not record conversation turn: %s", e)


def _infer_category(fact: str, category: str | None) -> str:
    if category in _CATEGORY_MAP:
        return _CATEGORY_MAP[category]

    lower_fact = fact.lower()
    preference_markers = ("prefer", "preference", "like", "dislike", "favorite", "favourite")
    if any(marker in lower_fact for marker in preference_markers):
        return "preference"
    return "fact"


def remember_fact(fact: str, category: str | None = None) -> str:
    """Saves a fact or preference into structured session-scoped memory."""
    if _manager is None:
        return "Error: Session not initialized. Call initialize_session() first."

    fact = fact.strip()
    if not fact:
        return "Error: Fact cannot be empty."

    # Deduplicate: check if the fact already exists in the flat store
    existing = _manager.flat_store.search(fact, limit=1)
    if existing and existing[0]["content"].lower() == fact.lower():
        return f"Already remembered: {fact}"

    target_category = _infer_category(fact, category)
    try:
        _manager.remember_fact(fact, category=target_category)
        return f"Remembered {target_category}: {fact}"
    except Exception as e:
        logger.error("Error remembering fact: %s", e)
        return f"Error saving memory: {e}"


def retrieve_facts(category: str | None = None) -> str:
    """Retrieves saved session memories."""
    if _manager is None:
        return "Error: Session not initialized. Call initialize_session() first."

    try:
        mapped = _CATEGORY_MAP.get(category) if category else None
        rows = _manager.flat_store.list_all(category=mapped)

        if mapped:
            values = [r["content"] for r in rows]
            saved_label = f"Saved {category}" if category in {"facts", "preferences"} else f"Saved {mapped}s"
            return (saved_label + ": " + ", ".join(values)) if values else f"No saved {mapped}s yet."

        facts = []
        preferences = []
        for r in rows:
            if r["category"] == "fact":
                facts.append(r["content"])
            elif r["category"] == "preference":
                preferences.append(r["content"])

        parts = []
        if facts:
            parts.append("Facts: " + ", ".join(facts))
        if preferences:
            parts.append("Preferences: " + ", ".join(preferences))

        return " | ".join(parts) if parts else "No memories saved yet."
    except Exception as e:
        logger.error("Error retrieving memories: %s", e)
        return f"Error retrieving memories: {e}"


def get_relevant_memories(query: str) -> list[str]:
    """Finds memories relevant to the user query via FTS + graph lookup."""
    if _manager is None:
        logger.warning("get_relevant_memories called before session initialized.")
        return []

    try:
        # Session summaries are injected separately; keep them out of fact recall.
        return [m for m in _manager.retrieve(query) if not m.startswith("Session context:")]
    except Exception as e:
        logger.error("Error retrieving relevant memories: %s", e)
        return []


def forget_fact(identifier: str | int) -> str:
    """Deletes a memory by id or content match."""
    if _manager is None:
        return "Error: Session not initialized. Call initialize_session() first."
    try:
        count = _manager.forget(identifier)
        if count:
            return f"Forgot {count} memory/memories."
        return f"No memory matching '{identifier}' found."
    except Exception as e:
        logger.error("Error forgetting fact: %s", e)
        return f"Error forgetting memory: {e}"


def shutdown_session() -> None:
    """Persists session data and cleans up on process exit."""
    global _manager
    if _manager is None:
        return
    try:
        session_id = getattr(_manager, 'session_id', None)
        if session_id:
            _manager.shutdown(session_id)
        _manager.close()
        logger.debug("Session memory shutdown complete.")
    except Exception as e:
        logger.error("Error during memory shutdown: %s", e)
    finally:
        _manager = None
