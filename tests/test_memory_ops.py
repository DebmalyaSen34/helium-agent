import os
import tempfile
import unittest
from tools import memory_ops


class MemoryOpsTests(unittest.TestCase):
    def setUp(self):
        self._tmp_dir = tempfile.mkdtemp()
        self._db_path = os.path.join(self._tmp_dir, "test_memory.db")
        memory_ops.initialize_session(db_path=self._db_path)

    def tearDown(self):
        memory_ops.shutdown_session()
        for suffix in ("", "-wal", "-shm"):
            try:
                os.remove(self._db_path + suffix)
            except FileNotFoundError:
                pass
        os.rmdir(self._tmp_dir)

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
