from __future__ import annotations

import logging
import sqlite3
import threading

logger = logging.getLogger(__name__)

_manager = None  # PersistentMemoryManager instance, set by initialize_session()


# ---------------------------------------------------------------------------
# Deprecated: SessionMemoryManager — replaced by PersistentMemoryManager
# ---------------------------------------------------------------------------

class SessionMemoryManager:
    """DEPRECATED: Use PersistentMemoryManager instead.

    Kept temporarily for reference; will be removed in a future cleanup.
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self.conn = None
        self.lock = threading.Lock()
        self._initialized = True

    def initialize(self):
        """Initializes a fresh, empty in-memory SQLite database."""
        with self.lock:
            if self.conn:
                try:
                    self.conn.close()
                except Exception as e:
                    logger.debug("Failed closing old connection: %s", e)

            self.conn = sqlite3.connect(":memory:", check_same_thread=False)
            self._init_db()
            logger.info("Session memory initialized (in-memory SQLite).")

    def _init_db(self):
        cursor = self.conn.cursor()
        cursor.executescript("""
            CREATE TABLE IF NOT EXISTS session_memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fact TEXT UNIQUE NOT NULL,
                category TEXT CHECK(category IN ('facts', 'preferences')),
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_memories_fact ON session_memories(fact);
        """)
        self.conn.commit()

    def get_connection(self):
        with self.lock:
            if self.conn is None:
                self.conn = sqlite3.connect(":memory:", check_same_thread=False)
                self._init_db()
            return self.conn


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


def initialize_session() -> None:
    """Start a fresh session backed by PersistentMemoryManager (in-memory).

    Note: shutdown() should be called on process exit to persist session data.
    Will be wired in Task 9 via main.py atexit/signal handling.
    """
    from memory.manager import PersistentMemoryManager

    global _manager
    _manager = PersistentMemoryManager(":memory:")
    session_id, _context = _manager.startup()
    _manager.session_id = session_id
    logger.info(
        "Session memory initialized (PersistentMemoryManager, in-memory) session_id=%s.",
        session_id,
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
