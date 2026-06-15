"""PersistentMemoryManager — orchestrates flat store, knowledge graph, and conversation store."""

import sqlite3
import uuid
import logging

from memory.flat_store import FlatMemoryStore
from memory.graph import KnowledgeGraph
from memory.conversation import ConversationStore

logger = logging.getLogger(__name__)


class PersistentMemoryManager:
    """Orchestrator tying FlatMemoryStore, KnowledgeGraph, and ConversationStore
    over a single shared SQLite connection."""

    def __init__(self, db_path="memory.db"):
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.flat_store = FlatMemoryStore(self.conn)
        self.graph = KnowledgeGraph(conn=self.conn)
        self.conversation = ConversationStore(self.conn)

    # -- public API ----------------------------------------------------------

    def remember_fact(self, fact, category="fact", tags=None, importance=1.0):
        """Store a fact in the flat store and extract knowledge-graph triplets."""
        row_id = self.flat_store.add(fact, category, tags=tags, importance=importance)
        self._extract_and_store_triplets(fact)
        return row_id

    def retrieve(self, query, max_results=10):
        """Merge flat-store FTS search and graph entity lookup, deduplicate, sort by score."""
        if not query or not query.strip():
            return []

        flat_hits = self.flat_store.search(query, limit=max_results)
        seen = set()
        combined = []

        for hit in flat_hits:
            content = hit["content"]
            if content not in seen:
                seen.add(content)
                combined.append((content, hit.get("score", 1.0)))

        keywords = self._extract_keywords(query)
        for kw in keywords:
            for triplet in self.graph.query_entity(kw):
                line = f"{triplet['subject']} {triplet['predicate']} {triplet['object']}"
                if line not in seen:
                    seen.add(line)
                    combined.append((line, triplet.get("confidence", 1.0)))

        combined.sort(key=lambda x: x[1], reverse=True)
        return [content for content, _ in combined[:max_results]]

    def forget(self, identifier):
        """Delegate deletion to the flat store."""
        return self.flat_store.forget(identifier)

    def append_conversation(self, session_id, role, content):
        """Append a conversation turn."""
        return self.conversation.append(session_id, role, content)

    def get_conversation_context(self, session_id, n=20):
        """Return formatted recent conversation for a session."""
        turns = self.conversation.get_recent(session_id, n=n)
        lines = [f"{t['role'].capitalize()}: {t['content']}" for t in turns]
        return "\n".join(lines)

    def startup(self):
        """Generate a session id and load the most recent session summary."""
        session_id = str(uuid.uuid4())
        context = self._load_recent_summary()
        return session_id, context

    def shutdown(self, session_id):
        """Persist session context and prune old conversations."""
        self.conversation.store_session_context(self.flat_store, session_id)
        self.conversation.prune()

    # -- internals -----------------------------------------------------------

    def _extract_and_store_triplets(self, text):
        """Extract SPO triplets from text and store them in the graph."""
        keywords = self._extract_keywords(text)
        if len(keywords) < 2:
            return
        facts = [{"s": keywords[0], "p": "related_to", "o": kw} for kw in keywords[1:]]
        self.graph.add_knowledge(facts)

    def _extract_keywords(self, text):
        """Extract keywords, falling back to simple split if spaCy is unavailable."""
        try:
            return self.graph._extract_keywords(text)
        except Exception:
            return [w.lower() for w in text.split() if len(w) > 3]

    def _load_recent_summary(self):
        """Return content of the most recent session-summary memory, or None."""
        rows = self.conn.execute(
            "SELECT content FROM memories WHERE tags = 'session-summary' "
            "ORDER BY created_at DESC LIMIT 1"
        ).fetchall()
        return rows[0][0] if rows else None
