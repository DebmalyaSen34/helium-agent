import os
import tempfile
from unittest.mock import patch
from evals.graders import FileModifiedGrader, PytestRunGrader, ContentMatchGrader, LlmRubricGrader

def test_file_modified_grader():
    # Use temporary file to test baseline detection
    with tempfile.NamedTemporaryFile(delete=False) as f:
        f.write(b"original content")
        file_path = f.name

    try:
        grader = FileModifiedGrader(path=file_path)
        # Should be false initially since it hasn't changed
        assert grader.grade() is False

        # Modify file
        with open(file_path, "wb") as f:
            f.write(b"new content")

        # Should be true now
        assert grader.grade() is True
    finally:
        if os.path.exists(file_path):
            os.remove(file_path)

def test_content_match_grader():
    grader = ContentMatchGrader(keywords=["Helium", "Agent"], case_sensitive=False)
    assert grader.grade("Hello helium agent!") is True
    assert grader.grade("Only helium is here") is False

    grader_sensitive = ContentMatchGrader(keywords=["Helium"], case_sensitive=True)
    assert grader_sensitive.grade("Helium agent") is True
    assert grader_sensitive.grade("helium agent") is False

def test_pytest_run_grader():
    # Test with a mock success/fail run
    with patch("subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0
        grader = PytestRunGrader(test_path="tests/test_dummy.py")
        assert grader.grade() is True

        mock_run.return_value.returncode = 1
        assert grader.grade() is False

def test_llm_rubric_grader():
    # Test LlmRubricGrader with mocked OpenRouter API response
    with tempfile.NamedTemporaryFile(delete=False, mode="w") as f:
        f.write("Evaluate response tone and facts.")
        rubric_path = f.name

    try:
        grader = LlmRubricGrader(rubric_path=rubric_path)
        
        mock_llm_reply = '{"score": 0.85, "passed": true, "reasoning": "Empathy shown, response complete."}'
        
        with patch("evals.graders.call_llm_once", return_value=(mock_llm_reply, 10)) as mock_call:
            res = grader.grade(
                prompt="Customer is frustrated",
                response="I am so sorry for the delay",
                transcript="Agent transitions to Using search_web"
            )
            assert res["passed"] is True
            assert res["score"] == 0.85
            assert res["reasoning"] == "Empathy shown, response complete."
            assert mock_call.called
    finally:
        if os.path.exists(rubric_path):
            os.remove(rubric_path)
