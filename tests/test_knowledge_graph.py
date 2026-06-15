import sqlite3
import sys
import types
from unittest.mock import MagicMock

import pytest

# Mock spacy before importing memory.graph, since spacy is not
# available in the test environment and the module-level import
# would otherwise fail.
_spacy_mock = MagicMock()
sys.modules.setdefault("spacy", _spacy_mock)
sys.modules.setdefault("spacy.cli", _spacy_mock.cli)
sys.modules.setdefault("spacy.cli.download", _spacy_mock.cli.download)

from memory.graph import KnowledgeGraph  # noqa: E402


# --- Fixtures ---

@pytest.fixture
def shared_conn():
    """In-memory connection shared between test and KnowledgeGraph."""
    conn = sqlite3.connect(":memory:")
    yield conn
    conn.close()


@pytest.fixture
def kg_shared(shared_conn):
    """KnowledgeGraph that does NOT own its connection."""
    return KnowledgeGraph(conn=shared_conn)


@pytest.fixture
def kg_own(tmp_path):
    """KnowledgeGraph that owns its connection (uses a temp file)."""
    db = tmp_path / "test.db"
    return KnowledgeGraph(db_path=str(db))


# --- Constructor / ownership ---

class TestConstructor:
    def test_shared_connection_uses_provided_conn(self, shared_conn):
        kg = KnowledgeGraph(conn=shared_conn)
        assert kg.conn is shared_conn
        assert kg._owns_conn is False

    def test_own_connection_creates_new(self, tmp_path):
        db = tmp_path / "test.db"
        kg = KnowledgeGraph(db_path=str(db))
        assert kg._owns_conn is True
        assert kg.conn is not None
        kg.close()

    def test_tables_created(self, kg_shared):
        cursor = kg_shared.conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {row[0] for row in cursor.fetchall()}
        assert "Entities" in tables
        assert "Triplets" in tables


# --- close / context manager ---

class TestConnectionOwnership:
    def test_close_on_owned_connection(self, tmp_path):
        db = tmp_path / "test.db"
        kg = KnowledgeGraph(db_path=str(db))
        kg.close()
        # After close, operations should fail
        with pytest.raises(sqlite3.ProgrammingError):
            kg.conn.execute("SELECT 1")

    def test_close_on_shared_connection_does_not_close(self, shared_conn):
        kg = KnowledgeGraph(conn=shared_conn)
        kg.close()
        # Shared connection should still be usable
        cursor = shared_conn.execute("SELECT 1")
        assert cursor.fetchone() == (1,)

    def test_context_manager_closes_owned_connection(self, tmp_path):
        db = tmp_path / "test.db"
        with KnowledgeGraph(db_path=str(db)) as kg:
            assert kg._owns_conn is True
        # After exiting context, connection should be closed
        with pytest.raises(sqlite3.ProgrammingError):
            kg.conn.execute("SELECT 1")

    def test_context_manager_does_not_close_shared(self, shared_conn):
        with KnowledgeGraph(conn=shared_conn) as kg:
            assert kg._owns_conn is False
        # Shared connection still alive
        cursor = shared_conn.execute("SELECT 1")
        assert cursor.fetchone() == (1,)


# --- add_knowledge ---

class TestAddKnowledge:
    def test_add_single_fact(self, kg_shared):
        kg_shared.add_knowledge([{"s": "Python", "p": "is_a", "o": "language"}])
        cursor = kg_shared.conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM Triplets")
        assert cursor.fetchone()[0] == 1

    def test_add_duplicate_fact_not_duplicated(self, kg_shared):
        fact = {"s": "Python", "p": "is_a", "o": "language"}
        kg_shared.add_knowledge([fact])
        kg_shared.add_knowledge([fact])
        cursor = kg_shared.conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM Triplets")
        assert cursor.fetchone()[0] == 1

    def test_add_multiple_facts(self, kg_shared):
        facts = [
            {"s": "Python", "p": "is_a", "o": "language"},
            {"s": "Java", "p": "is_a", "o": "language"},
            {"s": "Python", "p": "used_by", "o": "google"},
        ]
        kg_shared.add_knowledge(facts)
        cursor = kg_shared.conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM Triplets")
        assert cursor.fetchone()[0] == 3

    def test_add_malformed_fact_skipped(self, kg_shared):
        """Missing key should be caught by KeyError and skipped."""
        kg_shared.add_knowledge([{"s": "Python", "p": "is_a"}])  # missing 'o'
        cursor = kg_shared.conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM Triplets")
        assert cursor.fetchone()[0] == 0

    def test_add_empty_fact_skipped(self, kg_shared):
        """Facts with empty strings should be skipped."""
        kg_shared.add_knowledge([{"s": "", "p": "is_a", "o": "language"}])
        cursor = kg_shared.conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM Triplets")
        assert cursor.fetchone()[0] == 0


# --- query_entity ---

class TestQueryEntity:
    def test_query_existing_entity(self, kg_shared):
        kg_shared.add_knowledge([{"s": "Python", "p": "is_a", "o": "language"}])
        results = kg_shared.query_entity("Python")
        assert len(results) == 1
        assert results[0]["subject"] == "python"
        assert results[0]["predicate"] == "is_a"
        assert results[0]["object"] == "language"

    def test_query_nonexistent_entity(self, kg_shared):
        kg_shared.add_knowledge([{"s": "Python", "p": "is_a", "o": "language"}])
        results = kg_shared.query_entity("Rust")
        assert results == []

    def test_query_entity_as_object(self, kg_shared):
        kg_shared.add_knowledge([{"s": "Python", "p": "is_a", "o": "language"}])
        results = kg_shared.query_entity("language")
        assert len(results) == 1
        assert results[0]["subject"] == "python"

    def test_query_entity_case_insensitive(self, kg_shared):
        kg_shared.add_knowledge([{"s": "Python", "p": "is_a", "o": "language"}])
        results = kg_shared.query_entity("PYTHON")
        assert len(results) == 1

    def test_query_entity_limit(self, kg_shared):
        facts = [{"s": "Python", "p": f"rel_{i}", "o": f"obj_{i}"} for i in range(100)]
        kg_shared.add_knowledge(facts)
        results = kg_shared.query_entity("Python", limit=10)
        assert len(results) == 10

    def test_query_entity_default_limit(self, kg_shared):
        facts = [{"s": "Python", "p": f"rel_{i}", "o": f"obj_{i}"} for i in range(60)]
        kg_shared.add_knowledge(facts)
        results = kg_shared.query_entity("Python")
        assert len(results) == 50

    def test_query_result_has_confidence_and_source(self, kg_shared):
        kg_shared.add_knowledge([{"s": "Python", "p": "is_a", "o": "language"}])
        results = kg_shared.query_entity("Python")
        assert results[0]["confidence"] == 1.0
        assert results[0]["source"] == "stored"
