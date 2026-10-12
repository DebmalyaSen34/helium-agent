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



@pytest.mark.parametrize(
    "command",
    [
        "find . -delete",
        "find . -name '*.pyc' -exec rm {} ;",
        "ls\nshutdown -h now",
        "ls\rrm x",
        "git branch -D main",
        "git -c core.pager=sh log",
        "git diff --output=out.txt",
        "git push",
        "echo `id`",
        "echo $(id)",
        "echo ${HOME}",
        "printenv",
        "env",
        "cat ~/.ssh/id_rsa",
        "cat /etc/passwd",
        "cat ../secret.txt",
        "cat .env",
        "cat config/.env.local",
        "cat .e*",
        "ls & rm x",
        "sleep 100 &",
        "FOO=bar ls",
        "sort -o out.txt in.txt",
        "uniq in.txt out.txt",
        "rg --pre sh foo",
        "cat < file.txt",
        "ls | sh",
        "xargs rm",
        "",
    ],
)
def test_is_command_safe_rejects_known_bypasses(command):
    assert is_command_safe(command) is False


@pytest.mark.parametrize(
    "command",
    [
        "ls -la && git status",
        "git log --oneline -5",
        "git branch",
        "git branch --show-current",
        "grep -rn TODO .",
        "find . -name '*.py'",
        "cat README.md | head -20",
        "wc -l main.py",
    ],
)
def test_is_command_safe_allows_read_only_project_commands(command):
    assert is_command_safe(command) is True


def test_execute_bash_reports_exit_code_and_runs_in_project_root(tmp_path):
    from tools import file_ops

    original = file_ops.PROJECT_ROOT
    file_ops.set_project_root(tmp_path)
    try:
        result = execute_bash("pwd")
    finally:
        file_ops.set_project_root(original)
    assert result.startswith("exit_code: 0")
    assert str(tmp_path.resolve()) in result


def test_execute_bash_caps_long_output():
    result = execute_bash("python3 -c \"print('x' * 50000)\"")
    assert "characters omitted" in result
    assert len(result) < 20_000
