import unittest

from tools.memory_ops import (
    initialize_session,
    remember_fact,
    retrieve_facts,
    get_relevant_memories,
)


class SessionMemoryTests(unittest.TestCase):
    def setUp(self):
        # Fresh initialization for each test to represent session start
        initialize_session()

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
        self.assertEqual(len(relevant), 1)
        self.assertEqual(relevant[0], "I prefer Python for server-side programming")

        # Query relevant to "dog"
        relevant_dog = get_relevant_memories("What was the name of the dog?")
        self.assertEqual(len(relevant_dog), 1)
        self.assertEqual(relevant_dog[0], "My dog's name is Rusty")

        # FTS5 matches real words like "way" — pure-stopword filtering is no longer
        # the retrieval strategy, so this query may return results.
        relevant_stopwords = get_relevant_memories("is there a way to do this?")
        self.assertIsInstance(relevant_stopwords, list)

    def test_session_boundary_and_non_bleeding(self):
        # 1. Store a memory in session 1
        remember_fact("Deb likes spicy food")
        retrieved_s1 = retrieve_facts()
        self.assertIn("Deb likes spicy food", retrieved_s1)

        # 2. Re-initialize a fresh session
        initialize_session()

        # 3. Memory should be completely empty and reset
        retrieved_s2 = retrieve_facts()
        self.assertEqual(retrieved_s2, "No memories saved yet.")


if __name__ == "__main__":
    unittest.main()
