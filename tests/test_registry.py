import unittest

from tools.registry import execute_tool


class RegistryTests(unittest.TestCase):
    def test_risky_tool_requires_confirmation(self):
        response = '{"tool": "create_file", "args": {"filename": "x.txt", "content": "hi"}}'
        self.assertIn("needs confirmation", execute_tool(response))

    def test_risky_tool_can_be_cancelled(self):
        response = '{"tool": "open_app", "args": {"app_name": "Calculator"}}'
        result = execute_tool(response, confirm_tool=lambda name, args, permission: False)
        self.assertIn("cancelled", result)

    def test_safe_tool_runs_without_confirmation(self):
        response = '{"tool": "get_time", "args": {}}'
        self.assertIn("executed successfully", execute_tool(response))

    def test_bash_tool_modifying_requires_confirmation(self):
        response = '{"tool": "execute_bash", "args": {"command": "rm -rf test"}}'
        self.assertIn("needs confirmation", execute_tool(response))

    def test_bash_tool_safe_runs_without_confirmation(self):
        response = '{"tool": "execute_bash", "args": {"command": "echo hello"}}'
        self.assertIn("executed successfully", execute_tool(response))


    def test_bash_tool_can_be_cancelled(self):
        # execute_bash can be cancelled by user
        response = '{"tool": "execute_bash", "args": {"command": "echo risky > dummy.txt"}}'
        result = execute_tool(response, confirm_tool=lambda name, args, permission: False)
        self.assertIn("cancelled", result)

    def test_bash_tool_can_be_approved(self):
        # execute_bash runs when approved
        response = '{"tool": "execute_bash", "args": {"command": "echo risky > dummy.txt"}}'
        result = execute_tool(response, confirm_tool=lambda name, args, permission: True)
        self.assertIn("executed successfully", result)
        # Cleanup
        import os
        if os.path.exists("dummy.txt"):
            os.remove("dummy.txt")

    def test_file_read_tool_runs_without_confirmation(self):
        response = '{"tool": "list_directory", "args": {"path": "."}}'
        self.assertIn("executed successfully", execute_tool(response))

    def test_file_write_tool_requires_confirmation(self):
        response = '{"tool": "write_file", "args": {"path": "x.txt", "content": "hi"}}'
        self.assertIn("needs confirmation", execute_tool(response))

    def test_delete_file_requires_confirmation(self):
        response = '{"tool": "delete_file", "args": {"path": "x.txt"}}'
        self.assertIn("needs confirmation", execute_tool(response))



if __name__ == "__main__":
    unittest.main()
