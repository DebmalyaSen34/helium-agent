import unittest
from tools import memory_ops


class MemoryOpsTests(unittest.TestCase):
    def setUp(self):
        memory_ops.initialize_session()

    def test_remember_and_retrieve_ops(self):
        # Store facts
        memory_ops.remember_fact("Hello, I am Debmalya")
        memory_ops.remember_fact("I prefer markdown formatting", "preferences")

        # Retrieve facts
        retrieved = memory_ops.retrieve_facts()
        self.assertIn("Facts: Hello, I am Debmalya", retrieved)
        self.assertIn("Preferences: I prefer markdown formatting", retrieved)


if __name__ == "__main__":
    unittest.main()
