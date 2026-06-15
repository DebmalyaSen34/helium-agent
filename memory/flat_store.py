import sqlite3
import math
import logging

logger = logging.getLogger(__name__)

VALID_CATEGORIES = ('preference', 'fact', 'project')


class FlatMemoryStore:
    """Persistent flat memory store backed by SQLite with FTS5 search."""

    def __init__(self, conn):
        """Initialize with an existing sqlite3.Connection."""
        self.conn = conn
        self._init_table()

    def _init_table(self):
        """Create memories table, FTS5 virtual table, and sync triggers."""
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS memories (
                id INTEGER PRIMARY KEY,
                content TEXT NOT NULL,
                category TEXT NOT NULL CHECK(category IN ('preference', 'fact', 'project')),
                tags TEXT,
                importance REAL DEFAULT 1.0,
                access_count INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_accessed TIMESTAMP
            );

            CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(
                content, tags,
                content=memories,
                content_rowid=id
            );

            CREATE TRIGGER IF NOT EXISTS memories_ai AFTER INSERT ON memories BEGIN
                INSERT INTO memories_fts(rowid, content, tags)
                VALUES (new.id, new.content, new.tags);
            END;

            CREATE TRIGGER IF NOT EXISTS memories_ad AFTER DELETE ON memories BEGIN
                INSERT INTO memories_fts(memories_fts, rowid, content, tags)
                VALUES ('delete', old.id, old.content, old.tags);
            END;

            CREATE TRIGGER IF NOT EXISTS memories_au AFTER UPDATE ON memories BEGIN
                INSERT INTO memories_fts(memories_fts, rowid, content, tags)
                VALUES ('delete', old.id, old.content, old.tags);
                INSERT INTO memories_fts(rowid, content, tags)
                VALUES (new.id, new.content, new.tags);
            END;
        """)
        self.conn.commit()

    def add(self, content, category, tags=None, importance=1.0):
        """Add a memory. Returns the new row id.

        Args:
            content: The memory text.
            category: One of 'preference', 'fact', 'project'.
            tags: Optional comma-separated tags string.
            importance: Importance weight (default 1.0).
        """
        if category not in VALID_CATEGORIES:
            raise ValueError(f"Invalid category: {category}. Must be one of {VALID_CATEGORIES}")

        cursor = self.conn.execute(
            "INSERT INTO memories (content, category, tags, importance) VALUES (?, ?, ?, ?)",
            (content, category, tags, importance)
        )
        self.conn.commit()
        return cursor.lastrowid

    def _touch(self, memory_id):
        """Update access_count and last_accessed for a memory."""
        self.conn.execute(
            "UPDATE memories SET access_count = access_count + 1, last_accessed = CURRENT_TIMESTAMP WHERE id = ?",
            (memory_id,)
        )
        self.conn.commit()

    def search(self, query, limit=10):
        """Search memories using FTS5. Returns list of dicts sorted by relevance.

        Scoring: fts_rank * importance * (1 + log(access_count + 1))
        """
        # Escape FTS5 special chars — wrapping in double quotes forces literal
        # interpretation, neutralizing *, AND, OR, NOT, NEAR, col:, and parens.
        sanitized = query.replace('"', '""')
        # Wrap each word as a prefix token for flexible matching
        tokens = sanitized.split()
        if not tokens:
            return []

        fts_query = " OR ".join(f'"{t}"' for t in tokens)

        rows = self.conn.execute(
            """
            SELECT m.id, m.content, m.category, m.tags, m.importance,
                   m.access_count, m.created_at, m.last_accessed,
                   rank
            FROM memories_fts
            JOIN memories m ON memories_fts.rowid = m.id
            WHERE memories_fts MATCH ?
            ORDER BY rank
            """,
            (fts_query,)
        ).fetchall()

        results = []
        for row in rows:
            mem_id, content, category, tags, importance, access_count, created, last_accessed, fts_rank = row
            # FTS5 rank is negative (lower = better), take absolute value for scoring
            score = abs(fts_rank) * importance * (1 + math.log(access_count + 1))
            results.append({
                'id': mem_id,
                'content': content,
                'category': category,
                'tags': tags,
                'importance': importance,
                'access_count': access_count,
                'created_at': created,
                'last_accessed': last_accessed,
                'score': score,
            })

        results.sort(key=lambda r: r['score'], reverse=True)

        # Batch-touch accessed memories
        top = results[:limit]
        if top:
            self.conn.executemany(
                "UPDATE memories SET access_count = access_count + 1, last_accessed = CURRENT_TIMESTAMP WHERE id = ?",
                [(r['id'],) for r in top]
            )
            self.conn.commit()

        return top

    def forget(self, identifier):
        """Delete a memory by id (int) or by content match (str).

        Returns number of deleted rows.
        """
        if isinstance(identifier, int):
            cursor = self.conn.execute("DELETE FROM memories WHERE id = ?", (identifier,))
        else:
            cursor = self.conn.execute("DELETE FROM memories WHERE content = ?", (str(identifier),))
        self.conn.commit()
        return cursor.rowcount

    def list_all(self, category=None):
        """List all memories, optionally filtered by category."""
        if category and category not in VALID_CATEGORIES:
            raise ValueError(f"Invalid category: {category}. Must be one of {VALID_CATEGORIES}")
        if category:
            rows = self.conn.execute(
                "SELECT id, content, category, tags, importance, access_count, created_at, last_accessed "
                "FROM memories WHERE category = ? ORDER BY created_at DESC",
                (category,)
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT id, content, category, tags, importance, access_count, created_at, last_accessed "
                "FROM memories ORDER BY created_at DESC"
            ).fetchall()

        return [
            {
                'id': r[0], 'content': r[1], 'category': r[2], 'tags': r[3],
                'importance': r[4], 'access_count': r[5],
                'created_at': r[6], 'last_accessed': r[7],
            }
            for r in rows
        ]

    def get_by_id(self, memory_id):
        """Get a single memory by id. Returns dict or None."""
        row = self.conn.execute(
            "SELECT id, content, category, tags, importance, access_count, created_at, last_accessed "
            "FROM memories WHERE id = ?",
            (memory_id,)
        ).fetchone()

        if not row:
            return None

        return {
            'id': row[0], 'content': row[1], 'category': row[2], 'tags': row[3],
            'importance': row[4], 'access_count': row[5],
            'created_at': row[6], 'last_accessed': row[7],
        }
