import os
import tempfile
import unittest

from tools.memory_ops import (
    initialize_session,
    remember_fact,
    retrieve_facts,
    get_relevant_memories,
    shutdown_session,
)


class SessionMemoryTests(unittest.TestCase):
    def setUp(self):
        # Each test gets a fresh temporary database for isolation
        self._tmp_dir = tempfile.mkdtemp()
        self._db_path = os.path.join(self._tmp_dir, "test_memory.db")
        initialize_session(db_path=self._db_path)

    def tearDown(self):
        shutdown_session()
        # Clean up temp files
        for suffix in ("", "-wal", "-shm"):
            try:
                os.remove(self._db_path + suffix)
            except FileNotFoundError:
                pass
        os.rmdir(self._tmp_dir)

    def test_initial_db_is_empty(self):
        # Retrieve facts should return no memories initially
        retrieved = retrieve_facts()
        self.assertEqual(retrieved, "No memories saved yet.")

    def test_remember_fact_saves_and_categorizes(self):
        # Remember standard fact
        res1 = remember_fact("The capital of France is Paris")
        self.assertIn("Remembered fact", res1)

        # Remember user preference (automatically inferred by preference keywords)
        res2 = remember_fact("I prefer dark mode in all my applications")
        self.assertIn("Remembered preference", res2)

        # Retrieve structured facts
        retrieved = retrieve_facts()
        self.assertIn("Facts: The capital of France is Paris", retrieved)
        self.assertIn("Preferences: I prefer dark mode in all my applications", retrieved)

    def test_category_filtering(self):
        remember_fact("I prefer dark mode", "preferences")
        remember_fact("Water freezes at 0 degrees", "facts")

        pref_only = retrieve_facts("preferences")
        self.assertIn("Saved preferences: I prefer dark mode", pref_only)
        self.assertNotIn("Water freezes", pref_only)

        facts_only = retrieve_facts("facts")
        self.assertIn("Saved facts: Water freezes at 0 degrees", facts_only)
        self.assertNotIn("dark mode", facts_only)

    def test_get_relevant_memories_keyword_matching(self):
        remember_fact("I prefer Python for server-side programming")
        remember_fact("JavaScript is great for frontend development")
        remember_fact("My dog's name is Rusty")

        # Query relevant to "programming in python"
        relevant = get_relevant_memories("Can we build a server with python?")
        self.assertGreaterEqual(len(relevant), 1)
        self.assertIn("I prefer Python for server-side programming", relevant)

        # Query relevant to "dog"
        relevant_dog = get_relevant_memories("What was the name of the dog?")
        self.assertGreaterEqual(len(relevant_dog), 1)
        self.assertIn("My dog's name is Rusty", relevant_dog)

        # FTS5 matches real words like "way" — pure-stopword filtering is no longer
        # the retrieval strategy, so this query may return results.
        relevant_stopwords = get_relevant_memories("is there a way to do this?")
        self.assertIsInstance(relevant_stopwords, list)

    def test_persistence_across_sessions(self):
        # 1. Store a memory in session 1
        remember_fact("Deb likes spicy food")
        retrieved_s1 = retrieve_facts()
        self.assertIn("Deb likes spicy food", retrieved_s1)

        # 2. Shutdown and re-initialize with the SAME db path
        shutdown_session()
        initialize_session(db_path=self._db_path)

        # 3. Memory should persist (that's the whole point of persistent memory)
        retrieved_s2 = retrieve_facts()
        self.assertIn("Deb likes spicy food", retrieved_s2)


if __name__ == "__main__":
    unittest.main()
