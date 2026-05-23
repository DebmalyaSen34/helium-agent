import pytest
import subprocess
from unittest.mock import patch
from tools.bash_ops import execute_bash, is_command_safe

def test_execute_bash_success():
    # Simple echo command should succeed and return standard output
    result = execute_bash("echo 'Hello World'")
    assert "Hello World" in result
    assert "[stderr]" not in result

def test_execute_bash_stderr():
    # Non-existent command should return standard error
    result = execute_bash("ls /nonexistent_folder_abc_123")
    assert "[stderr]" in result or "No such file or directory" in result

def test_execute_bash_timeout():
    # A sleep command that exceeds the 30-second timeout should be terminated
    # We patch subprocess.run timeout to 0.1s to make the test fast
    with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="sleep 5", timeout=0.1,output=b"partial stdout", stderr=b"partial stderr")):
        result = execute_bash("sleep 5")
        assert "timed out" in result.lower()
        assert "partial stdout" in result
        assert "partial stderr" in result

def test_is_command_safe_safe_cases():
    assert is_command_safe("ls -la") is True
    assert is_command_safe("pwd") is True
    assert is_command_safe("git status") is True
    assert is_command_safe("git diff") is True
    assert is_command_safe("cat hello.py") is True
    assert is_command_safe("grep 'hello' hello.py") is True

def test_is_command_safe_risky_cases():
    assert is_command_safe("rm -rf /") is False
    assert is_command_safe("mkdir src") is False
    assert is_command_safe("touch newfile.txt") is False
    assert is_command_safe("echo 'hello' > test.txt") is False
    assert is_command_safe("git commit -m 'feat'") is False
    assert is_command_safe("python main.py") is False
    assert is_command_safe("pip install pytest") is False
    assert is_command_safe("ls -la && rm -rf test") is False

