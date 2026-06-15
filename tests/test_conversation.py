import unittest
import sqlite3
from datetime import datetime, timedelta

from memory.conversation import ConversationStore
from memory.flat_store import FlatMemoryStore


class ConversationStoreTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.store = ConversationStore(self.conn)

    def tearDown(self):
        self.conn.close()

    # --- Table init ---

    def test_table_created(self):
        tables = {r[0] for r in self.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        self.assertIn("conversation_threads", tables)

    def test_double_init_no_error(self):
        store2 = ConversationStore(self.conn)
        rid = store2.append("s1", "user", "hello")
        self.assertIsNotNone(rid)

    # --- append ---

    def test_append_returns_id(self):
        rid = self.store.append("s1", "user", "hello")
        self.assertIsInstance(rid, int)
        self.assertGreater(rid, 0)

    def test_append_user_role(self):
        rid = self.store.append("s1", "user", "hi")
        row = self.conn.execute(
            "SELECT role, content FROM conversation_threads WHERE id = ?", (rid,)
        ).fetchone()
        self.assertEqual(row[0], "user")
        self.assertEqual(row[1], "hi")

    def test_append_assistant_role(self):
        rid = self.store.append("s1", "assistant", "hello back")
        row = self.conn.execute(
            "SELECT role, content FROM conversation_threads WHERE id = ?", (rid,)
        ).fetchone()
        self.assertEqual(row[0], "assistant")
        self.assertEqual(row[1], "hello back")

    def test_append_invalid_role_raises(self):
        with self.assertRaises(ValueError):
            self.store.append("s1", "system", "bad")

    def test_append_multiple_turns(self):
        self.store.append("s1", "user", "q1")
        self.store.append("s1", "assistant", "a1")
        self.store.append("s1", "user", "q2")
        rows = self.conn.execute(
            "SELECT COUNT(*) FROM conversation_threads WHERE session_id = 's1'"
        ).fetchone()
        self.assertEqual(rows[0], 3)

    # --- get_recent ---

    def test_get_recent_returns_list(self):
        self.store.append("s1", "user", "hello")
        result = self.store.get_recent("s1")
        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 1)

    def test_get_recent_returns_dicts_with_expected_keys(self):
        self.store.append("s1", "user", "hello")
        result = self.store.get_recent("s1")[0]
        self.assertIn("id", result)
        self.assertIn("session_id", result)
        self.assertIn("role", result)
        self.assertIn("content", result)
        self.assertIn("created_at", result)

    def test_get_recent_oldest_first(self):
        self.store.append("s1", "user", "first")
        self.store.append("s1", "assistant", "second")
        self.store.append("s1", "user", "third")
        result = self.store.get_recent("s1", n=3)
        self.assertEqual(result[0]["content"], "first")
        self.assertEqual(result[1]["content"], "second")
        self.assertEqual(result[2]["content"], "third")

    def test_get_recent_respects_n(self):
        for i in range(10):
            self.store.append("s1", "user", f"msg{i}")
        result = self.store.get_recent("s1", n=3)
        self.assertEqual(len(result), 3)
        # Should be the last 3, oldest first
        self.assertEqual(result[0]["content"], "msg7")
        self.assertEqual(result[1]["content"], "msg8")
        self.assertEqual(result[2]["content"], "msg9")

    def test_get_recent_default_n_is_20(self):
        for i in range(25):
            self.store.append("s1", "user", f"msg{i}")
        result = self.store.get_recent("s1")
        self.assertEqual(len(result), 20)
        self.assertEqual(result[0]["content"], "msg5")

    def test_get_recent_empty_session(self):
        result = self.store.get_recent("nonexistent")
        self.assertEqual(result, [])

    def test_get_recent_isolates_sessions(self):
        self.store.append("s1", "user", "in s1")
        self.store.append("s2", "user", "in s2")
        result = self.store.get_recent("s1")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["content"], "in s1")

    def test_get_recent_fewer_than_n(self):
        self.store.append("s1", "user", "only one")
        result = self.store.get_recent("s1", n=20)
        self.assertEqual(len(result), 1)

    # --- summarize_and_store ---

    def test_summarize_and_store_returns_id(self):
        mem_store = FlatMemoryStore(self.conn)
        self.store.append("s1", "user", "What is Python?")
        self.store.append("s1", "assistant", "A programming language.")
        rid = self.store.summarize_and_store(mem_store, "s1")
        self.assertIsInstance(rid, int)
        self.assertGreater(rid, 0)

    def test_summarize_and_store_content_format(self):
        mem_store = FlatMemoryStore(self.conn)
        self.store.append("s1", "user", "hi")
        self.store.append("s1", "assistant", "hello")
        rid = self.store.summarize_and_store(mem_store, "s1")
        mem = mem_store.get_by_id(rid)
        self.assertIn("User: hi", mem["content"])
        self.assertIn("Assistant: hello", mem["content"])
        self.assertTrue(mem["content"].startswith("Session summary:"))

    def test_summarize_and_store_tags_and_category(self):
        mem_store = FlatMemoryStore(self.conn)
        self.store.append("s1", "user", "test")
        rid = self.store.summarize_and_store(mem_store, "s1")
        mem = mem_store.get_by_id(rid)
        self.assertEqual(mem["category"], "project")
        self.assertEqual(mem["tags"], "session-summary")

    def test_summarize_and_store_empty_session(self):
        mem_store = FlatMemoryStore(self.conn)
        result = self.store.summarize_and_store(mem_store, "nonexistent")
        self.assertIsNone(result)

    def test_summarize_and_store_limit_20(self):
        mem_store = FlatMemoryStore(self.conn)
        for i in range(25):
            self.store.append("s1", "user", f"msg{i}")
        rid = self.store.summarize_and_store(mem_store, "s1")
        mem = mem_store.get_by_id(rid)
        # Should not contain msg0-msg4 (only last 20)
        self.assertNotIn("msg0", mem["content"])
        self.assertNotIn("msg4", mem["content"])
        self.assertIn("msg5", mem["content"])
        self.assertIn("msg24", mem["content"])

    # --- prune ---

    def test_prune_deletes_old_threads(self):
        self.store.append("s1", "user", "old message")
        # Backdate the created_at
        self.conn.execute(
            "UPDATE conversation_threads SET created_at = datetime('now', '-10 days')"
        )
        self.conn.commit()

        count = self.store.prune(days=7)
        self.assertEqual(count, 1)
        self.assertEqual(self.conn.execute(
            "SELECT COUNT(*) FROM conversation_threads"
        ).fetchone()[0], 0)

    def test_prune_keeps_recent_threads(self):
        self.store.append("s1", "user", "recent message")
        count = self.store.prune(days=7)
        self.assertEqual(count, 0)
        self.assertEqual(self.conn.execute(
            "SELECT COUNT(*) FROM conversation_threads"
        ).fetchone()[0], 1)

    def test_prune_mixed_ages(self):
        self.store.append("s1", "user", "old")
        self.store.append("s1", "user", "recent")
        # Backdate only the first
        self.conn.execute(
            "UPDATE conversation_threads SET created_at = datetime('now', '-10 days') WHERE id = 1"
        )
        self.conn.commit()

        count = self.store.prune(days=7)
        self.assertEqual(count, 1)
        remaining = self.conn.execute(
            "SELECT content FROM conversation_threads"
        ).fetchone()
        self.assertEqual(remaining[0], "recent")

    def test_prune_custom_days(self):
        self.store.append("s1", "user", "message")
        self.conn.execute(
            "UPDATE conversation_threads SET created_at = datetime('now', '-3 days')"
        )
        self.conn.commit()

        # Should not prune with default 7 days
        count = self.store.prune()
        self.assertEqual(count, 0)

        # Should prune with 1 day threshold
        count = self.store.prune(days=1)
        self.assertEqual(count, 1)

    def test_prune_empty_table(self):
        count = self.store.prune(days=7)
        self.assertEqual(count, 0)

    def test_prune_returns_count(self):
        for i in range(5):
            self.store.append("s1", "user", f"old{i}")
        self.conn.execute(
            "UPDATE conversation_threads SET created_at = datetime('now', '-10 days')"
        )
        self.conn.commit()

        count = self.store.prune(days=7)
        self.assertEqual(count, 5)

    # --- Idempotent init ---

    def test_double_init_preserves_data(self):
        self.store.append("s1", "user", "before reinit")
        store2 = ConversationStore(self.conn)
        store2.append("s1", "user", "after reinit")
        result = self.store.get_recent("s1", n=20)
        self.assertEqual(len(result), 2)


if __name__ == "__main__":
    unittest.main()
