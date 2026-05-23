from __future__ import annotations

import logging
import sqlite3
import threading

logger = logging.getLogger(__name__)


class SessionMemoryManager:
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


def initialize_session() -> None:
    """Explicitly starts a fresh session-scoped memory database."""
    SessionMemoryManager().initialize()


def _infer_category(fact: str, category: str | None) -> str:
    if category in {"facts", "preferences"}:
        return category

    lower_fact = fact.lower()
    preference_markers = ("prefer", "preference", "like", "dislike", "favorite", "favourite")
    if any(marker in lower_fact for marker in preference_markers):
        return "preferences"
    return "facts"


def remember_fact(fact: str, category: str | None = None) -> str:
    """Saves a fact or preference into structured session-scoped memory."""
    fact = fact.strip()
    if not fact:
        return "Error: Fact cannot be empty."

    target_category = _infer_category(fact, category)
    conn = SessionMemoryManager().get_connection()
    try:
        with SessionMemoryManager().lock:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT OR IGNORE INTO session_memories (fact, category) VALUES (?, ?)",
                (fact, target_category)
            )
            conn.commit()
        return f"Remembered {target_category[:-1]}: {fact}"
    except Exception as e:
        logger.error("Error remembering fact: %s", e)
        return f"Error saving memory: {e}"


def retrieve_facts(category: str | None = None) -> str:
    """Retrieves saved session memories."""
    conn = SessionMemoryManager().get_connection()
    try:
        with SessionMemoryManager().lock:
            cursor = conn.cursor()
            if category in {"facts", "preferences"}:
                cursor.execute(
                    "SELECT fact FROM session_memories WHERE category = ? ORDER BY timestamp DESC",
                    (category,)
                )
                rows = cursor.fetchall()
                values = [r[0] for r in rows]
                return f"Saved {category}: " + ", ".join(values) if values else f"No saved {category} yet."
            
            cursor.execute("SELECT fact, category FROM session_memories ORDER BY timestamp DESC")
            rows = cursor.fetchall()
            
        facts = []
        preferences = []
        for fact, cat in rows:
            if cat == "facts":
                facts.append(fact)
            else:
                preferences.append(fact)
                
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
    """Finds memories in the session SQLite database relevant to the user query."""
    words = [
        w.strip("?,.!:;\"'()").lower()
        for w in query.split()
    ]
    stopwords = {
        "i", "me", "my", "myself", "we", "our", "ours", "ourselves", "you", "your",
        "yours", "yourself", "yourselves", "he", "him", "his", "himself", "she",
        "her", "hers", "herself", "it", "its", "itself", "they", "them", "their",
        "theirs", "themselves", "what", "which", "who", "whom", "this", "that",
        "these", "those", "am", "is", "are", "was", "were", "be", "been", "being",
        "have", "has", "had", "having", "do", "does", "did", "doing", "a", "an",
        "the", "and", "but", "if", "or", "because", "as", "until", "while", "of",
        "at", "by", "for", "with", "about", "against", "between", "into", "through",
        "during", "before", "after", "above", "below", "to", "from", "up", "down",
        "in", "out", "on", "off", "over", "under", "again", "further", "then",
        "once", "here", "there", "when", "where", "why", "how", "all", "any",
        "both", "each", "few", "more", "most", "other", "some", "such", "no",
        "nor", "not", "only", "own", "same", "so", "than", "too", "very", "s",
        "t", "can", "will", "just", "don", "should", "now"
    }
    
    keywords = [w for w in words if len(w) >= 3 and w not in stopwords]
    if not keywords:
        return []
        
    conn = SessionMemoryManager().get_connection()
    relevant = []
    
    try:
        with SessionMemoryManager().lock:
            cursor = conn.cursor()
            seen_facts = set()
            for kw in keywords:
                like_pattern = f"%{kw}%"
                cursor.execute(
                    "SELECT fact FROM session_memories WHERE fact LIKE ? ORDER BY timestamp DESC LIMIT 5",
                    (like_pattern,)
                )
                rows = cursor.fetchall()
                for row in rows:
                    fact = row[0]
                    if fact not in seen_facts:
                        seen_facts.add(fact)
                        relevant.append(fact)
                        
        return relevant
    except Exception as e:
        logger.error("Error retrieving relevant session memories: %s", e)
        return []
