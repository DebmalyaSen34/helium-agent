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
        self.conn.commit()

    def append(self, session_id, role, content):
        """Insert a conversation turn. Returns the new row id.

        Args:
            session_id: Session identifier string.
            role: Either 'user' or 'assistant'.
            content: The message text.
        """
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

    def summarize_and_store(self, memory_store, session_id):
        """Summarize last 20 turns and store as a memory.

        Args:
            memory_store: A FlatMemoryStore instance to persist the summary.
            session_id: Session identifier string.
        """
        turns = self.get_recent(session_id, n=20)
        if not turns:
            return None

        # Pair turns as "User: X / Assistant: Y" lines
        lines = []
        for turn in turns:
            lines.append(f"{turn['role'].capitalize()}: {turn['content']}")

        summary = "Session summary:\n" + "\n".join(lines)

        return memory_store.add(
            content=summary,
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
