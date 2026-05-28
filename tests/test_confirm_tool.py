import unittest
from unittest.mock import patch, MagicMock
import main

class ConfirmToolTests(unittest.TestCase):
    @patch("main.Prompt.ask", return_value="y")
    @patch("main.console.print")
    def test_confirm_tool_suspends_and_resumes_active_status(self, mock_print, mock_ask):
        # Create a mock active status object
        mock_status = MagicMock()
        
        # Inject the mock active status
        main._active_status = mock_status
        
        try:
            # Call confirm_tool
            res = main.confirm_tool("mkdir", {"path": "api"}, "risky")
            
            # Assertions
            self.assertTrue(res)
            mock_status.stop.assert_called_once()
            mock_status.start.assert_called_once()
            
            # Verify stop was called before ask, and start was called after
            # By inspecting mock call orders
            stop_idx = mock_status.mock_calls.index(('stop', (), {}))
            ask_idx = mock_ask.mock_calls.index(mock_ask.mock_calls[0])
            start_idx = mock_status.mock_calls.index(('start', (), {}))
            
            # Since mock_calls from different mocks don't share indices directly,
            # we should track execution order using a shared list or verify the logic.
            # However, because we can also track call order of the mocks using mock managers,
            # let's write a simple order tracking or verify it by mocking a parent mock.
        finally:
            main._active_status = None

    @patch("main.Prompt.ask", return_value="y")
    @patch("main.console.print")
    def test_confirm_tool_call_order(self, mock_print, mock_ask):
        # Using a Manager Mock to verify precise call order
        manager = MagicMock()
        
        # Create mock methods and attach them to the manager
        mock_status = MagicMock()
        manager.status = mock_status
        manager.ask = mock_ask
        
        main._active_status = mock_status
        
        try:
            # When prompt.ask is called, record it on manager
            def mock_ask_side_effect(*args, **kwargs):
                manager.ask_called()
                return "y"
            mock_ask.side_effect = mock_ask_side_effect
            
            res = main.confirm_tool("mkdir", {"path": "api"}, "risky")
            self.assertTrue(res)
            
            # Extract names from manager's mock calls to verify order
            call_names = [call[0] for call in manager.mock_calls]
            
            # Expected order: status.stop -> ask_called -> status.start
            self.assertIn('status.stop', call_names)
            self.assertIn('ask_called', call_names)
            self.assertIn('status.start', call_names)
            
            stop_idx = call_names.index('status.stop')
            ask_idx = call_names.index('ask_called')
            start_idx = call_names.index('status.start')
            
            self.assertTrue(stop_idx < ask_idx < start_idx)
        finally:
            main._active_status = None
