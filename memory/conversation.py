import sqlite3
import logging

logger = logging.getLogger(__name__)


class ConversationStore:
    """Stores and retrieves conversation turns, backed by SQLite."""

    def __init__(self, conn):
        """Initialize with an existing sqlite3.Connection."""
        self.conn = conn
        self._init_table()

    def _init_table(self):
        """Create conversation_threads table."""
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS conversation_threads (
                id INTEGER PRIMARY KEY,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('user', 'assistant')),
                content TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_threads_session "
            "ON conversation_threads(session_id, id)"
        )
        self.conn.commit()

    def append(self, session_id, role, content):
        """Insert a conversation turn. Returns the new row id.

        Args:
            session_id: Session identifier string.
            role: Either 'user' or 'assistant'.
            content: The message text.
        """
        if not session_id or not isinstance(session_id, str) or not session_id.strip():
            raise ValueError("session_id must be a non-empty string.")

        if role not in ('user', 'assistant'):
            raise ValueError(f"Invalid role: {role}. Must be 'user' or 'assistant'.")

        cursor = self.conn.execute(
            "INSERT INTO conversation_threads (session_id, role, content) VALUES (?, ?, ?)",
            (session_id, role, content)
        )
        self.conn.commit()
        return cursor.lastrowid

    def get_recent(self, session_id, n=20):
        """Get the n most recent turns for a session, oldest first.

        Args:
            session_id: Session identifier string.
            n: Number of turns to return (default 20).
        """
        n = max(n, 1)
        rows = self.conn.execute(
            "SELECT id, session_id, role, content, created_at "
            "FROM conversation_threads WHERE session_id = ? "
            "ORDER BY id DESC LIMIT ?",
            (session_id, n)
        ).fetchall()

        # Reverse so oldest comes first
        return [
            {
                'id': r[0], 'session_id': r[1], 'role': r[2],
                'content': r[3], 'created_at': r[4],
            }
            for r in reversed(rows)
        ]

    def store_session_context(self, memory_store, session_id):
        """Format and store the last 20 turns as a memory entry.

        Concatenates recent turns verbatim (no LLM summarization).
        Stored content is a plain "Role: text" listing for context retrieval.

        Args:
            memory_store: A FlatMemoryStore instance to persist the formatted turns.
            session_id: Session identifier string.
        """
        turns = self.get_recent(session_id, n=20)
        if not turns:
            return None

        lines = []
        for turn in turns:
            lines.append(f"{turn['role'].capitalize()}: {turn['content']}")

        content = "Session context:\n" + "\n".join(lines)

        return memory_store.add(
            content=content,
            category='project',
            tags='session-summary'
        )

    def prune(self, days=7):
        """Delete conversation threads older than the given number of days.

        Args:
            days: Age threshold in days (default 7).
        """
        cursor = self.conn.execute(
            "DELETE FROM conversation_threads WHERE created_at < datetime('now', ?)",
            (f'-{days} days',)
        )
        self.conn.commit()
        return cursor.rowcount
