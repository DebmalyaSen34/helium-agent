import unittest
from unittest.mock import patch, MagicMock
import main
from config.settings import ASSISTANT_SETTINGS

class NuclearFlagTests(unittest.TestCase):
    def setUp(self):
        # Backup original setting
        self.original_confirm = ASSISTANT_SETTINGS.get("confirm_risky_tools", True)

    def tearDown(self):
        # Restore original setting
        ASSISTANT_SETTINGS["confirm_risky_tools"] = self.original_confirm

    @patch("main.console.print")
    @patch("main.Path")
    @patch("main.os.chdir")
    @patch("main.set_project_root")
    @patch("tools.memory_ops.initialize_session")
    def test_main_with_nuclear_disables_confirmation_and_prints_warning(
        self, mock_init, mock_set_root, mock_chdir, mock_path, mock_print
    ):
        # Mock Path().resolve() and HOME / env existence
        mock_path.return_value.resolve.return_value = MagicMock()
        
        # We also mock internal methods in main() to avoid running the full main loop during tests
        with patch("utils.system_check.check_llm_api", return_value=True), \
             patch("main.ensure_llm_runtime_config"), \
             patch("main.print_header"), \
             patch("main.PromptSession") as mock_session:
            
            # Raise EOFError to immediately exit the while True loop
            mock_session.return_value.prompt.side_effect = EOFError()
            
            main.main(mode="text", target_path=".", nuclear=True)
            
            # Assertions
            self.assertFalse(ASSISTANT_SETTINGS["confirm_risky_tools"])
            
            # Verify the warning banner was printed
            banner_printed = False
            for call in mock_print.call_args_list:
                args = call[0]
                if args and hasattr(args[0], "title") and args[0].title == " WARNING ":
                    banner_printed = True
                    self.assertIn("Nuclear mode active", args[0].renderable.plain)
            self.assertTrue(banner_printed)

    @patch("main.Prompt.ask")
    def test_confirm_tool_bypasses_prompt_when_nuclear(self, mock_ask):
        ASSISTANT_SETTINGS["confirm_risky_tools"] = False
        
        res = main.confirm_tool("mkdir", {"path": "api"}, "risky")
        
        # Should return True without calling Prompt.ask
        self.assertTrue(res)
        mock_ask.assert_not_called()
