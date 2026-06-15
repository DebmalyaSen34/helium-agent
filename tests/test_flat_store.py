import unittest
import sqlite3

from memory.flat_store import FlatMemoryStore


class FlatMemoryStoreTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.store = FlatMemoryStore(self.conn)

    def tearDown(self):
        self.conn.close()

    # --- Table init ---

    def test_tables_created(self):
        tables = {r[0] for r in self.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        self.assertIn("memories", tables)
        self.assertIn("memories_fts", tables)

    def test_triggers_created(self):
        triggers = {r[0] for r in self.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='trigger'"
        ).fetchall()}
        self.assertIn("memories_ai", triggers)
        self.assertIn("memories_ad", triggers)
        self.assertIn("memories_au", triggers)

    # --- add ---

    def test_add_returns_id(self):
        rid = self.store.add("test content", "fact")
        self.assertIsInstance(rid, int)
        self.assertGreater(rid, 0)

    def test_add_with_all_fields(self):
        rid = self.store.add("important fact", "fact", tags="python,code", importance=2.5)
        mem = self.store.get_by_id(rid)
        self.assertEqual(mem["content"], "important fact")
        self.assertEqual(mem["category"], "fact")
        self.assertEqual(mem["tags"], "python,code")
        self.assertEqual(mem["importance"], 2.5)

    def test_add_invalid_category_raises(self):
        with self.assertRaises(ValueError):
            self.store.add("bad", "invalid_category")

    def test_add_default_importance(self):
        rid = self.store.add("simple", "preference")
        mem = self.store.get_by_id(rid)
        self.assertEqual(mem["importance"], 1.0)

    # --- get_by_id ---

    def test_get_by_id_returns_dict(self):
        rid = self.store.add("find me", "fact")
        mem = self.store.get_by_id(rid)
        self.assertIsNotNone(mem)
        self.assertEqual(mem["content"], "find me")
        self.assertEqual(mem["category"], "fact")
        self.assertEqual(mem["access_count"], 0)

    def test_get_by_id_not_found(self):
        self.assertIsNone(self.store.get_by_id(9999))

    # --- forget ---

    def test_forget_by_id(self):
        rid = self.store.add("to delete", "fact")
        count = self.store.forget(rid)
        self.assertEqual(count, 1)
        self.assertIsNone(self.store.get_by_id(rid))

    def test_forget_by_content(self):
        self.store.add("unique content xyz", "fact")
        count = self.store.forget("unique content xyz")
        self.assertEqual(count, 1)
        self.assertEqual(self.store.list_all(), [])

    def test_forget_nonexistent_returns_zero(self):
        count = self.store.forget(9999)
        self.assertEqual(count, 0)

    # --- list_all ---

    def test_list_all_returns_all(self):
        self.store.add("a", "fact")
        self.store.add("b", "preference")
        self.store.add("c", "project")
        self.assertEqual(len(self.store.list_all()), 3)

    def test_list_all_filter_by_category(self):
        self.store.add("fact1", "fact")
        self.store.add("pref1", "preference")
        self.store.add("fact2", "fact")

        facts = self.store.list_all(category="fact")
        self.assertEqual(len(facts), 2)
        self.assertTrue(all(m["category"] == "fact" for m in facts))

    def test_list_all_empty(self):
        self.assertEqual(self.store.list_all(), [])

    # --- _touch ---

    def test_touch_updates_access(self):
        rid = self.store.add("touch me", "fact")
        self.store._touch(rid)
        mem = self.store.get_by_id(rid)
        self.assertEqual(mem["access_count"], 1)
        self.assertIsNotNone(mem["last_accessed"])

    def test_touch_increments(self):
        rid = self.store.add("count me", "fact")
        self.store._touch(rid)
        self.store._touch(rid)
        mem = self.store.get_by_id(rid)
        self.assertEqual(mem["access_count"], 2)

    # --- search ---

    def test_search_finds_match(self):
        self.store.add("Python is a programming language", "fact", tags="python")
        self.store.add("I prefer dark mode", "preference")

        results = self.store.search("Python")
        self.assertEqual(len(results), 1)
        self.assertIn("Python", results[0]["content"])

    def test_search_no_results(self):
        self.store.add("unrelated content", "fact")
        results = self.store.search("nonexistent term xyz")
        self.assertEqual(len(results), 0)

    def test_search_respects_limit(self):
        for i in range(20):
            self.store.add(f"python tutorial part {i}", "fact")
        results = self.store.search("python", limit=5)
        self.assertEqual(len(results), 5)

    def test_search_scores_by_importance(self):
        self.store.add("low importance python", "fact", importance=1.0)
        self.store.add("high importance python", "fact", importance=5.0)

        results = self.store.search("python")
        self.assertEqual(len(results), 2)
        # Higher importance should score higher
        self.assertGreater(results[0]["importance"], results[1]["importance"])

    def test_search_touches_results(self):
        rid = self.store.add("searchable content", "fact")
        self.store.search("searchable")
        mem = self.store.get_by_id(rid)
        self.assertEqual(mem["access_count"], 1)

    def test_search_returns_score_field(self):
        self.store.add("scored result", "fact")
        results = self.store.search("scored")
        self.assertIn("score", results[0])

    def test_search_matches_tags(self):
        self.store.add("some content", "fact", tags="machine-learning,ai")
        results = self.store.search("machine-learning")
        self.assertEqual(len(results), 1)

    def test_search_multiple_tokens_or(self):
        self.store.add("apple pie recipe", "fact")
        self.store.add("banana smoothie", "fact")
        self.store.add("apple cider", "fact")

        results = self.store.search("apple banana")
        # Both apple entries and banana should match (OR logic)
        self.assertEqual(len(results), 3)

    # --- FTS sync triggers ---

    def test_fts_sync_on_delete(self):
        rid = self.store.add("will be deleted", "fact")
        self.store.forget(rid)
        results = self.store.search("deleted")
        self.assertEqual(len(results), 0)

    def test_fts_sync_on_update(self):
        rid = self.store.add("original text", "fact")
        self.conn.execute("UPDATE memories SET content = 'updated text' WHERE id = ?", (rid,))
        self.conn.commit()
        # Old content should not be found
        results_old = self.store.search("original")
        self.assertEqual(len(results_old), 0)
        # New content should be found
        results_new = self.store.search("updated")
        self.assertEqual(len(results_new), 1)

    # --- Idempotent init ---

    def test_double_init_no_error(self):
        store2 = FlatMemoryStore(self.conn)
        rid = store2.add("after reinit", "fact")
        self.assertIsNotNone(rid)


if __name__ == "__main__":
    unittest.main()
