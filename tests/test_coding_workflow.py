import unittest

from core.coding_workflow import (
    CODING_AUTO_APPROVED_TOOLS,
    CODING_CONFIRMED_TOOLS,
    build_coding_system_prompt,
    coding_confirm_tool,
    run_coding_workflow,
)


class CodingWorkflowPromptTests(unittest.TestCase):
    def test_coding_prompt_contains_workflow_rules(self):
        prompt = build_coding_system_prompt("fix the failing todo test")

        self.assertIn("inspect relevant files before editing", prompt)
        self.assertIn("short task plan", prompt)
        self.assertIn("never claim tests passed", prompt)
        self.assertIn("Changed files", prompt)
        self.assertIn("Verification", prompt)
        self.assertIn("Remaining risks", prompt)

    def test_coding_prompt_includes_user_task(self):
        prompt = build_coding_system_prompt("add parser tests")

        self.assertIn("add parser tests", prompt)


class CodingWorkflowPermissionTests(unittest.TestCase):
    def test_auto_approved_edit_tools_do_not_call_confirmation(self):
        called = []

        def confirm_tool(name, args, permission):
            called.append((name, args, permission))
            return False

        for tool_name in CODING_AUTO_APPROVED_TOOLS:
            allowed = coding_confirm_tool(
                tool_name,
                {"path": "example.py"},
                "risky",
                confirm_tool,
            )
            self.assertTrue(allowed, tool_name)

        self.assertEqual(called, [])

    def test_confirmed_tools_delegate_to_confirmation(self):
        called = []

        def confirm_tool(name, args, permission):
            called.append((name, args, permission))
            return False

        for tool_name in CODING_CONFIRMED_TOOLS:
            allowed = coding_confirm_tool(
                tool_name,
                {"path": "example.py"},
                "risky",
                confirm_tool,
            )
            self.assertFalse(allowed, tool_name)

        self.assertEqual(len(called), len(CODING_CONFIRMED_TOOLS))

    def test_missing_confirmation_denies_confirmed_tool(self):
        allowed = coding_confirm_tool(
            "delete_file",
            {"path": "example.py"},
            "risky",
            None,
        )

        self.assertFalse(allowed)

    def test_execute_bash_delegates_to_confirmation_when_risky(self):
        called = []

        def confirm_tool(name, args, permission):
            called.append((name, args, permission))
            return True

        allowed = coding_confirm_tool(
            "execute_bash",
            {"command": "python -m unittest discover -s tests"},
            "risky",
            confirm_tool,
        )

        self.assertTrue(allowed)
        self.assertEqual(
            called,
            [
                (
                    "execute_bash",
                    {"command": "python -m unittest discover -s tests"},
                    "risky",
                )
            ],
        )

class CodingWorkflowRunTests(unittest.TestCase):
    def test_run_coding_workflow_uses_agentic_loop_and_permission_wrapper(self):
        replies = iter(
            [
                '<action>{"tool": "read_file", "args": {"path": "core/todo.py"}}</action>',
                '<action>{"tool": "replace_text", "args": {"path": "core/todo.py", "old": "bad", "new": "good"}}</action>',
                (
                    "Changed files:\n"
                    "- core/todo.py\n\n"
                    "Verification:\n"
                    "- Not run: unit test added in next step\n\n"
                    "Remaining risks:\n"
                    "- None"
                ),
            ]
        )
        executed = []

        def ask_model(messages):
            return next(replies)

        def execute_tool_call(action, confirm_tool=None):
            executed.append(action["tool"])
            if action["tool"] == "replace_text":
                self.assertIsNotNone(confirm_tool)
                allowed = confirm_tool("replace_text", action["args"], "risky")
                self.assertTrue(allowed)
            return f"{action['tool']} result"

        result = run_coding_workflow(
            "fix todo normalization",
            ask_model=ask_model,
            execute_tool_call=execute_tool_call,
            max_turns=4,
        )

        self.assertEqual(executed, ["read_file", "replace_text"])
        self.assertEqual(result.stop_reason, "final")
        self.assertEqual(result.tools_used, ["read_file", "replace_text"])
        self.assertIn("Changed files", result.final_answer)

    def test_run_coding_workflow_tracks_changed_files_and_verification_commands(self):
        replies = iter(
            [
                '<action>{"tool": "write_file", "args": {"path": "tests/test_example.py", "content": "x"}}'
                '</action>',
                '<action>{"tool": "execute_bash", "args": {"command": "python -m unittest tests.test_example -v"}}'
                '</action>',
                (
                    "Changed files:\n"
                    "- tests/test_example.py\n\n"
                    "Verification:\n"
                    "- python -m unittest tests.test_example -v passed\n\n"
                    "Remaining risks:\n"
                    "- None"
                ),
            ]
        )

        def ask_model(messages):
            return next(replies)

        def execute_tool_call(action, confirm_tool=None):
            if confirm_tool is not None:
                confirm_tool(action["tool"], action.get("args", {}), "risky")
            return "ok"

        result = run_coding_workflow(
            "add example test",
            ask_model=ask_model,
            execute_tool_call=execute_tool_call,
            confirm_tool=lambda *_args: True,
            max_turns=4,
        )

        self.assertEqual(result.changed_files, ["tests/test_example.py"])
        self.assertEqual(result.verification_commands, ["python -m unittest tests.test_example -v"])


if __name__ == "__main__":
    unittest.main()