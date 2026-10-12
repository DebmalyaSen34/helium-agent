from __future__ import annotations

import logging

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


def initialize_session(db_path=None) -> None:
    """Start a session backed by PersistentMemoryManager (on-disk).

    Args:
        db_path: Optional database path. Defaults to MEMORY_DB from config.

    Note: shutdown() should be called on process exit to persist session data.
    Will be wired in Task 9 via main.py atexit/signal handling.
    """
    from memory.manager import PersistentMemoryManager
    from config.settings import MEMORY_DB

    global _manager
    path = db_path or str(MEMORY_DB)
    _manager = PersistentMemoryManager(path)
    session_id, _context = _manager.startup()
    _manager.session_id = session_id
    logger.info(
        "Session memory initialized (PersistentMemoryManager, db=%s) session_id=%s.",
        path, session_id,
    )


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
        return _manager.retrieve(query)
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
    if _manager is None:
        return
    try:
        session_id = getattr(_manager, 'session_id', None)
        if session_id:
            _manager.shutdown(session_id)
        _manager.close()
        logger.info("Session memory shutdown complete.")
    except Exception as e:
        logger.error("Error during memory shutdown: %s", e)
