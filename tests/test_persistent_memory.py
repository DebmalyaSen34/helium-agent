"""Tests for PersistentMemoryManager."""

import sqlite3
import sys
import time
import types
from unittest.mock import MagicMock

import pytest

# Mock spacy before importing memory.graph (module-level import).
_spacy_mock = MagicMock()
sys.modules.setdefault("spacy", _spacy_mock)
sys.modules.setdefault("spacy.cli", _spacy_mock.cli)
sys.modules.setdefault("spacy.cli.download", _spacy_mock.cli.download)

from memory.manager import PersistentMemoryManager  # noqa: E402


# --- Fixtures ---

@pytest.fixture
def mgr(tmp_path):
    """PersistentMemoryManager backed by a temp database."""
    db = tmp_path / "test.db"
    m = PersistentMemoryManager(db_path=str(db))
    yield m
    m.conn.close()


# --- Constructor ---

class TestConstructor:
    def test_creates_tables(self, mgr):
        cursor = mgr.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        tables = {row[0] for row in cursor.fetchall()}
        assert "memories" in tables
        assert "Entities" in tables
        assert "Triplets" in tables
        assert "conversation_threads" in tables

    def test_shares_single_connection(self, mgr):
        assert mgr.flat_store.conn is mgr.conn
        assert mgr.graph.conn is mgr.conn
        assert mgr.conversation.conn is mgr.conn


# --- remember_fact ---

class TestRememberFact:
    def test_stores_in_flat_store(self, mgr):
        row_id = mgr.remember_fact("Python is great", category="fact")
        assert row_id is not None
        mem = mgr.flat_store.get_by_id(row_id)
        assert mem is not None
        assert mem["content"] == "Python is great"

    def test_returns_row_id(self, mgr):
        row_id = mgr.remember_fact("Test fact")
        assert isinstance(row_id, int)
        assert row_id > 0

    def test_stores_with_category(self, mgr):
        row_id = mgr.remember_fact("I prefer dark mode", category="preference")
        mem = mgr.flat_store.get_by_id(row_id)
        assert mem["category"] == "preference"

    def test_stores_with_tags_and_importance(self, mgr):
        row_id = mgr.remember_fact("Important fact", tags="core,urgent", importance=2.5)
        mem = mgr.flat_store.get_by_id(row_id)
        assert mem["tags"] == "core,urgent"
        assert mem["importance"] == 2.5

    def test_extract_triplets_when_multiple_keywords(self, mgr):
        """When _extract_keywords returns 2+ items, triplets should be stored."""
        mgr._extract_keywords = MagicMock(return_value=["python", "language", "programming"])
        mgr.remember_fact("Python is a programming language")
        results = mgr.graph.query_entity("python")
        assert len(results) >= 1
        predicates = {r["predicate"] for r in results}
        assert "related_to" in predicates

    def test_no_triplets_when_single_keyword(self, mgr):
        mgr._extract_keywords = MagicMock(return_value=["python"])
        mgr.remember_fact("Python")
        cursor = mgr.conn.execute("SELECT COUNT(*) FROM Triplets")
        assert cursor.fetchone()[0] == 0

    def test_no_triplets_when_no_keywords(self, mgr):
        mgr._extract_keywords = MagicMock(return_value=[])
        mgr.remember_fact("...")
        cursor = mgr.conn.execute("SELECT COUNT(*) FROM Triplets")
        assert cursor.fetchone()[0] == 0


# --- retrieve ---

class TestRetrieve:
    def test_returns_list(self, mgr):
        result = mgr.retrieve("nonexistent query xyz")
        assert isinstance(result, list)

    def test_flat_store_results_included(self, mgr):
        mgr.remember_fact("Python is a programming language", category="fact")
        results = mgr.retrieve("Python")
        assert any("Python" in r for r in results)

    def test_graph_results_included(self, mgr):
        mgr.graph.add_knowledge([{"s": "Python", "p": "is_a", "o": "language"}])
        # Override _extract_keywords to return a keyword that matches the graph
        mgr._extract_keywords = MagicMock(return_value=["Python"])
        results = mgr.retrieve("Python")
        # Graph stores entities lowercased; verify the triplet shape is present
        assert any("is_a" in r and "language" in r for r in results)

    def test_deduplicates_results(self, mgr):
        mgr.remember_fact("Python is great", category="fact")
        # Both flat and graph could return the same content
        results = mgr.retrieve("Python")
        assert len(results) == len(set(results))

    def test_respects_max_results(self, mgr):
        for i in range(20):
            mgr.remember_fact(f"Fact number {i} about testing", category="fact")
        results = mgr.retrieve("testing", max_results=5)
        assert len(results) <= 5

    def test_max_results_default_is_10(self, mgr):
        for i in range(15):
            mgr.remember_fact(f"Unique fact {i} about memory", category="fact")
        results = mgr.retrieve("memory")
        assert len(results) <= 10

    def test_empty_query_returns_empty(self, mgr):
        results = mgr.retrieve("")
        assert results == []


# --- forget ---

class TestForget:
    def test_forget_by_id(self, mgr):
        row_id = mgr.remember_fact("Disposable fact")
        count = mgr.forget(row_id)
        assert count == 1
        assert mgr.flat_store.get_by_id(row_id) is None

    def test_forget_by_content(self, mgr):
        mgr.remember_fact("Disposable fact")
        count = mgr.forget("Disposable fact")
        assert count == 1

    def test_forget_nonexistent_returns_zero(self, mgr):
        count = mgr.forget(99999)
        assert count == 0


# --- append_conversation / get_conversation_context ---

class TestConversation:
    def test_append_and_retrieve(self, mgr):
        sid = "session-1"
        mgr.append_conversation(sid, "user", "Hello")
        mgr.append_conversation(sid, "assistant", "Hi there")
        context = mgr.get_conversation_context(sid)
        assert "User: Hello" in context
        assert "Assistant: Hi there" in context

    def test_context_respects_n(self, mgr):
        sid = "session-n"
        for i in range(10):
            mgr.append_conversation(sid, "user", f"msg {i}")
        context = mgr.get_conversation_context(sid, n=3)
        lines = context.strip().split("\n")
        assert len(lines) == 3

    def test_context_empty_session(self, mgr):
        context = mgr.get_conversation_context("nonexistent")
        assert context == ""

    def test_separate_sessions_isolated(self, mgr):
        mgr.append_conversation("s1", "user", "hello s1")
        mgr.append_conversation("s2", "user", "hello s2")
        ctx1 = mgr.get_conversation_context("s1")
        ctx2 = mgr.get_conversation_context("s2")
        assert "hello s1" in ctx1
        assert "hello s1" not in ctx2


# --- startup / shutdown ---

class TestStartupShutdown:
    def test_startup_returns_session_id_and_context(self, mgr):
        session_id, context = mgr.startup()
        assert isinstance(session_id, str)
        assert len(session_id) > 0
        assert context is None  # no prior sessions

    def test_startup_generates_unique_ids(self, mgr):
        id1, _ = mgr.startup()
        id2, _ = mgr.startup()
        assert id1 != id2

    def test_startup_loads_recent_summary(self, mgr):
        # Create a session-summary memory directly
        mgr.flat_store.add("Session context:\nUser: hi\nAssistant: hello", category="project", tags="session-summary")
        _, context = mgr.startup()
        assert context is not None
        assert "Session context" in context

    def test_shutdown_stores_session_context(self, mgr):
        sid = "shutdown-test"
        mgr.append_conversation(sid, "user", "Hello")
        mgr.append_conversation(sid, "assistant", "Hi")
        mgr.shutdown(sid)
        # Verify session-summary was stored
        rows = mgr.conn.execute(
            "SELECT content FROM memories WHERE tags = 'session-summary'"
        ).fetchall()
        assert len(rows) == 1
        assert "User: Hello" in rows[0][0]

    def test_shutdown_prunes_old_conversations(self, mgr):
        sid = "prune-test"
        mgr.append_conversation(sid, "user", "old message")
        # Manually backdate the conversation
        mgr.conn.execute(
            "UPDATE conversation_threads SET created_at = datetime('now', '-30 days')"
        )
        mgr.conn.commit()
        mgr.shutdown(sid)
        remaining = mgr.conn.execute(
            "SELECT COUNT(*) FROM conversation_threads"
        ).fetchone()[0]
        assert remaining == 0


# --- _extract_keywords fallback ---

class TestExtractKeywordsFallback:
    def test_fallback_on_spacy_failure(self, mgr):
        """When graph._extract_keywords raises, fallback to simple split."""
        mgr.graph._extract_keywords = MagicMock(side_effect=RuntimeError("no spacy"))
        kws = mgr._extract_keywords("Python is a programming language")
        assert "python" in kws
        assert "programming" in kws
        # Words <= 3 chars should be filtered
        assert "is" not in kws

    def test_normal_extraction_delegates_to_graph(self, mgr):
        mgr.graph._extract_keywords = MagicMock(return_value=["python", "language"])
        kws = mgr._extract_keywords("Python language")
        mgr.graph._extract_keywords.assert_called_once_with("Python language")
        assert kws == ["python", "language"]


# --- Persistence integration tests ---


class TestPersistenceIntegration:
    """Cross-session persistence tests using file-backed SQLite."""

    def test_e2e_persistence_across_sessions(self, tmp_path):
        """Store facts in session 1, close, reopen same DB, verify survival."""
        db = str(tmp_path / "persist.db")

        # Session 1: store facts and shut down
        mgr1 = PersistentMemoryManager(db_path=db)
        sid1, _ = mgr1.startup()
        mgr1.remember_fact("Python is a programming language", category="fact")
        mgr1.remember_fact("The user prefers dark mode", category="preference")
        mgr1.remember_fact("Project uses FastAPI", category="project")
        mgr1.shutdown(sid1)
        mgr1.close()

        # Session 2: reopen same DB, verify facts survived
        mgr2 = PersistentMemoryManager(db_path=db)
        sid2, context = mgr2.startup()
        assert sid2 != sid1

        results = mgr2.retrieve("Python programming")
        assert any("Python" in r for r in results)

        results = mgr2.retrieve("dark mode preference")
        assert any("dark mode" in r for r in results)

        results = mgr2.retrieve("FastAPI project")
        assert any("FastAPI" in r for r in results)
        mgr2.close()

    def test_session_summary_persisted_after_shutdown(self, tmp_path):
        """After shutdown, session summary is written to the memories table."""
        db = str(tmp_path / "summary.db")

        mgr = PersistentMemoryManager(db_path=db)
        sid, _ = mgr.startup()
        mgr.append_conversation(sid, "user", "What is the capital of France?")
        mgr.append_conversation(sid, "assistant", "The capital of France is Paris.")
        mgr.shutdown(sid)
        mgr.close()

        # Reopen and check the memories table directly
        mgr2 = PersistentMemoryManager(db_path=db)
        rows = mgr2.conn.execute(
            "SELECT content FROM memories WHERE tags = 'session-summary'"
        ).fetchall()
        assert len(rows) >= 1
        content = rows[0][0]
        assert "Session context" in content
        assert "What is the capital of France?" in content
        assert "Paris" in content
        mgr2.close()

    def test_session_summary_available_on_next_startup(self, tmp_path):
        """Session summary from session 1 is returned as context in session 2."""
        db = str(tmp_path / "ctx.db")

        mgr1 = PersistentMemoryManager(db_path=db)
        sid1, _ = mgr1.startup()
        mgr1.append_conversation(sid1, "user", "Remember: I like Rust")
        mgr1.append_conversation(sid1, "assistant", "Noted, you like Rust.")
        mgr1.shutdown(sid1)
        mgr1.close()

        mgr2 = PersistentMemoryManager(db_path=db)
        _, context = mgr2.startup()
        assert context is not None
        assert "Rust" in context
        mgr2.close()

    def test_large_corpus_retrieval_speed(self, tmp_path):
        """Store 1000+ memories and verify retrieval completes in <100ms."""
        db = str(tmp_path / "large.db")
        mgr = PersistentMemoryManager(db_path=db)
        mgr.startup()

        # Insert 1200 memories with varied content
        for i in range(1200):
            mgr.remember_fact(
                f"Memory entry {i}: topic-{i % 10} data point about testing",
                category="fact",
            )

        # Measure retrieval time
        start = time.perf_counter()
        results = mgr.retrieve("topic-5 testing")
        elapsed = time.perf_counter() - start

        assert elapsed < 0.1, f"Retrieval took {elapsed:.3f}s, expected <0.1s"
        assert len(results) > 0
        mgr.close()

    def test_duplicate_facts_deduplicated_on_retrieve(self, tmp_path):
        """Storing the same fact twice still returns only one copy on retrieval."""
        db = str(tmp_path / "dedup.db")
        mgr = PersistentMemoryManager(db_path=db)
        mgr.startup()

        fact = "Docker containers are lightweight"
        mgr.remember_fact(fact, category="fact")
        mgr.remember_fact(fact, category="fact")

        # Verify two rows exist in the DB (no insert-level dedup)
        count = mgr.conn.execute(
            "SELECT COUNT(*) FROM memories WHERE content = ?", (fact,)
        ).fetchone()[0]
        assert count == 2

        # But retrieval returns only one copy
        results = mgr.retrieve("Docker lightweight")
        occurrences = sum(1 for r in results if fact in r)
        assert occurrences == 1
        mgr.close()

    def test_empty_db_clean_state(self, tmp_path):
        """Fresh DB has no memories and startup returns no prior context."""
        db = str(tmp_path / "empty.db")
        mgr = PersistentMemoryManager(db_path=db)

        # Verify tables exist but are empty
        count = mgr.conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
        assert count == 0

        # Startup returns a session id but no context
        session_id, context = mgr.startup()
        assert isinstance(session_id, str)
        assert len(session_id) > 0
        assert context is None

        # Retrieve on empty DB returns empty list
        results = mgr.retrieve("anything")
        assert results == []

        # Shutdown on empty session does not crash
        mgr.shutdown(session_id)

        # Still no session summaries (no conversation was recorded)
        count = mgr.conn.execute(
            "SELECT COUNT(*) FROM memories WHERE tags = 'session-summary'"
        ).fetchone()[0]
        assert count == 0
        mgr.close()
