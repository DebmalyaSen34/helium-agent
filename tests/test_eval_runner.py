import os
import tempfile
from unittest.mock import patch, MagicMock
from evals.runner import run_single_task
from evals.schema import TaskConfig

def test_run_single_task_setup_teardown():
    # Verify setup and teardown commands are executed correctly
    with tempfile.TemporaryDirectory() as tmpdir:
        test_file = os.path.join(tmpdir, "setup_test.txt")
        
        task = TaskConfig(
            id="test_setup_teardown",
            description="Verify environment automation",
            category="coding",
            input_prompt="Perform setup",
            setup=f"echo 'setup_ran' > {test_file}",
            teardown=f"rm {test_file}",
            graders=[]
        )
        
        # We mock execute_agent_loop to isolate the setup/teardown and runner flow
        def mock_execute(prompt):
            # Assert file exists during execution (setup has run)
            assert os.path.exists(test_file) is True
            with open(test_file, "r") as f:
                assert f.read().strip() == "setup_ran"
            return "agent reply", "agent transcript"
            
        with patch("evals.runner.execute_agent_loop", side_effect=mock_execute):
            result = run_single_task(task)
            assert result["success"] is True
            assert result["response"] == "agent reply"
            
        # Assert file is removed after execution (teardown has run)
        assert os.path.exists(test_file) is False
