import unittest

from core.todo import TodoList, TodoStatus


class TodoListTests(unittest.TestCase):
    def test_lifecycle_methods_return_updated_items(self):
        todos = TodoList()
        item = todos.add("  Verify   sources  ", " research   check ")

        self.assertEqual(item.title, "Verify sources")
        self.assertEqual(item.kind, "research check")
        self.assertEqual(item.status, TodoStatus.PENDING)
        self.assertEqual(item.notes, [])
        self.assertEqual(len(item.id), 8)

        started = todos.start(item.id)
        self.assertIs(started, item)
        self.assertEqual(started.status, TodoStatus.IN_PROGRESS)

        completed = todos.complete(item.id, note="Evidence confirmed")
        self.assertIs(completed, item)
        self.assertEqual(completed.status, TodoStatus.COMPLETED)
        self.assertEqual(completed.notes, ["Evidence confirmed"])

    def test_block_records_reason_as_note(self):
        todos = TodoList()
        item = todos.add("Fetch page", "source")

        blocked = todos.block(item.id, "Search provider unavailable")

        self.assertEqual(blocked.status, TodoStatus.BLOCKED)
        self.assertEqual(blocked.notes, ["Search provider unavailable"])

    def test_pending_returns_only_pending_items(self):
        todos = TodoList()
        first = todos.add("Plan queries", "research")
        second = todos.add("Fetch official source", "fetch")
        third = todos.add("Cross-check claim", "verify")

        todos.start(second.id)
        todos.block(third.id, "No corroborating source")

        self.assertEqual(todos.pending(), [first])
        self.assertEqual(todos.by_status(TodoStatus.IN_PROGRESS), [second])
        self.assertEqual(todos.by_status("blocked"), [third])

    def test_summary_counts_items_by_status(self):
        todos = TodoList()
        pending = todos.add("Plan queries", "research")
        in_progress = todos.add("Fetch official source", "fetch")
        completed = todos.add("Extract claims", "extract")
        blocked = todos.add("Cross-check claim", "verify")

        todos.start(in_progress.id)
        todos.complete(completed.id)
        todos.block(blocked.id, "No second source")

        self.assertEqual(
            todos.summary(),
            {
                "total": 4,
                "pending": 1,
                "in_progress": 1,
                "completed": 1,
                "blocked": 1,
            },
        )
        self.assertEqual(todos.by_status(TodoStatus.PENDING), [pending])

    def test_unknown_ids_raise_key_error(self):
        todos = TodoList()

        with self.assertRaises(KeyError):
            todos.start("missing")
        with self.assertRaises(KeyError):
            todos.complete("missing")
        with self.assertRaises(KeyError):
            todos.block("missing", "No such todo")


if __name__ == "__main__":
    unittest.main()
