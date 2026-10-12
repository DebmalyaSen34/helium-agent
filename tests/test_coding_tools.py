import subprocess
from pathlib import Path

import pytest

from tools import file_ops
from tools.file_service import FileOperationService
from tools.git_ops import git_diff, git_status
from tools.test_runner import detect_test_command


@pytest.fixture
def project(tmp_path):
    original = file_ops.PROJECT_ROOT
    file_ops.set_project_root(tmp_path)
    yield tmp_path
    file_ops.set_project_root(original)


def test_edit_file_applies_multiple_edits(project):
    (project / "a.py").write_text("x = 1\ny = 2\n")
    result = file_ops.edit_file("a.py", [{"old": "x = 1", "new": "x = 10"}, {"old": "y = 2", "new": "y = 20"}])
    assert "status: success" in result
    assert (project / "a.py").read_text() == "x = 10\ny = 20\n"


def test_edit_file_rejects_ambiguous_match_without_writing(project):
    (project / "a.py").write_text("v = 1\nv = 1\nz = 0\n")
    result = file_ops.edit_file("a.py", [{"old": "z = 0", "new": "z = 9"}, {"old": "v = 1", "new": "v = 2"}])
    assert "status: error" in result
    assert "matches 2 places" in result
    assert (project / "a.py").read_text() == "v = 1\nv = 1\nz = 0\n"


def test_edit_file_replace_all(project):
    (project / "a.py").write_text("v = 1\nv = 1\n")
    file_ops.edit_file("a.py", [{"old": "v = 1", "new": "v = 2", "replace_all": True}])
    assert (project / "a.py").read_text() == "v = 2\nv = 2\n"


def test_edit_file_missing_text(project):
    (project / "a.py").write_text("hello\n")
    result = file_ops.edit_file("a.py", [{"old": "nope", "new": "x"}])
    assert "not found" in result


def test_read_file_wrapper_numbers_lines(project):
    (project / "a.txt").write_text("one\ntwo\nthree\n")
    result = file_ops.read_file("a.txt", start_line=2, end_line=3)
    assert "     2\ttwo\n     3\tthree" in result


def test_glob_files_skips_ignored_dirs(project):
    (project / "src").mkdir()
    (project / "src" / "app.py").write_text("")
    (project / "node_modules").mkdir()
    (project / "node_modules" / "lib.py").write_text("")
    result = FileOperationService(project).glob_files("**/*.py")
    assert "src/app.py" in result.details
    assert "node_modules" not in result.details


def test_search_text_regex_context_and_ignores(project):
    (project / "m.py").write_text("a\ndef foo():\n    pass\nb\n")
    (project / ".venv").mkdir()
    (project / ".venv" / "x.py").write_text("def foo(): pass\n")
    result = FileOperationService(project).search_text(r"def \w+\(", regex=True, context_lines=1)
    assert "m.py:2:def foo():" in result.details
    assert "m.py-1-a" in result.details
    assert ".venv" not in result.details


def test_search_text_honours_gitignore(project):
    subprocess.run(["git", "init", "-q"], cwd=project, check=True)
    (project / ".gitignore").write_text("secret/\n")
    (project / "secret").mkdir()
    (project / "secret" / "s.txt").write_text("needle\n")
    (project / "ok.txt").write_text("needle\n")
    result = FileOperationService(project).search_text("needle")
    assert "ok.txt" in result.details
    assert "secret" not in result.details


def test_git_tools_in_temp_repo(project):
    assert git_status() == "Not a git repository."
    subprocess.run(["git", "init", "-q"], cwd=project, check=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "--allow-empty", "-m", "init"], cwd=project, check=True)
    (project / "f.txt").write_text("hi\n")
    assert "f.txt" in git_status()
    subprocess.run(["git", "add", "f.txt"], cwd=project, check=True)
    assert "+hi" in git_diff(staged=True)
    assert git_diff() == "No differences."


def test_detect_test_command(tmp_path):
    assert detect_test_command(tmp_path) is None
    (tmp_path / "tests").mkdir()
    assert detect_test_command(tmp_path) == "python -m pytest -q"
    (tmp_path / "uv.lock").write_text("")
    assert detect_test_command(tmp_path) == "uv run pytest -q"
    other = tmp_path / "js"
    other.mkdir()
    (other / "package.json").write_text("{}")
    assert detect_test_command(other) == "npm test --silent"


def test_confirm_tool_always_allow(monkeypatch):
    import main
    from core.session import SESSION
    from config.settings import ASSISTANT_SETTINGS

    monkeypatch.setitem(ASSISTANT_SETTINGS, "confirm_risky_tools", True)
    SESSION.allow_list.clear()
    answers = iter(["a"])
    monkeypatch.setattr(main.Prompt, "ask", lambda *a, **k: next(answers))
    monkeypatch.setattr(main.console, "print", lambda *a, **k: None)

    assert main.confirm_tool("execute_bash", {"command": "make build"}, "risky")
    # Second call must not prompt (the iterator is exhausted).
    assert main.confirm_tool("execute_bash", {"command": "make build"}, "risky")
    SESSION.allow_list.clear()
