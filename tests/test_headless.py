import json
import os

import pytest

from core import headless, project_context
from core.headless import EXIT_ERROR, EXIT_MAX_TURNS, EXIT_OK, headless_main, make_headless_confirm, run_headless
from core.model_client import LegacyTextModel


def scripted(*replies):
    """A text-protocol model that returns `replies` in order, then repeats the last."""
    queue = list(replies)

    def ask(messages):
        return queue.pop(0) if len(queue) > 1 else queue[0]

    return LegacyTextModel(ask)


EDIT_THEN_DONE = (
    '<action>{"tool": "write_file", "args": {"path": "hello.py", "content": "print(1)\\n"}}</action>',
    "Created hello.py.",
)


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    from tools import file_ops

    original_cwd = os.getcwd()
    monkeypatch.setenv("HELIUM_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setattr(project_context, "_snapshots", {})
    project = tmp_path / "project"
    project.mkdir()
    original_root = file_ops.PROJECT_ROOT
    file_ops.set_project_root(project)
    yield project
    file_ops.set_project_root(original_root)
    os.chdir(original_cwd)


def test_confirm_modes():
    denied = []
    assert make_headless_confirm("all", denied)("execute_bash", {}, "risky")
    assert make_headless_confirm("accept-edits", denied)("edit_file", {}, "risky")
    assert not make_headless_confirm("accept-edits", denied)("execute_bash", {}, "risky")
    assert not make_headless_confirm("deny", denied)("edit_file", {}, "risky")
    assert denied == ["execute_bash", "edit_file"]
    with pytest.raises(ValueError):
        make_headless_confirm("maybe", [])


def test_edits_are_denied_by_default(workspace):
    result = run_headless("make hello.py", model=scripted(*EDIT_THEN_DONE))
    assert result.stop_reason == "final"
    assert not (workspace / "hello.py").exists()
    assert result.denied_tools == ["write_file"]


def test_accept_edits_lets_the_agent_write(workspace):
    result = run_headless("make hello.py", permission_mode="accept-edits", model=scripted(*EDIT_THEN_DONE))
    assert (workspace / "hello.py").read_text() == "print(1)\n"
    assert result.result == "Created hello.py."
    assert result.tools_used == ["write_file"]
    assert result.exit_code == EXIT_OK


def test_turn_limit_gives_its_own_exit_code(workspace):
    looping = scripted('<action>{"tool": "list_directory", "args": {"path": "."}}</action>')
    result = run_headless("loop", max_turns=2, model=looping)
    assert result.stop_reason == "max_turns"
    assert result.exit_code == EXIT_MAX_TURNS


def test_model_errors_become_an_error_result(workspace):
    def boom(messages):
        raise RuntimeError("endpoint down")

    result = run_headless("anything", model=LegacyTextModel(boom))
    assert result.stop_reason == "error"
    assert result.exit_code == EXIT_ERROR
    assert "endpoint down" in result.result


def test_json_output_is_the_only_thing_on_stdout(workspace, capsys, tmp_path):
    transcript = tmp_path / "out" / "transcript.json"
    code = headless_main(
        workspace,
        "make hello.py",
        permission_mode="accept-edits",
        output_json=True,
        transcript_path=transcript,
        model=scripted(*EDIT_THEN_DONE),
    )
    out = capsys.readouterr().out
    assert code == EXIT_OK
    payload = json.loads(out)  # fails if diffs or logs leaked onto stdout
    assert payload["result"] == "Created hello.py."
    assert payload["stop_reason"] == "final"
    assert payload["tools_used"] == {"write_file": 1}
    assert json.loads(transcript.read_text())[0]["role"] == "system"


def test_plain_output_prints_the_answer(workspace, capsys):
    code = headless_main(workspace, "hi", model=scripted("Hello there."))
    assert code == EXIT_OK
    assert capsys.readouterr().out == "Hello there.\n"


def test_empty_task_is_an_error(workspace, capsys):
    assert headless_main(workspace, "  ", model=scripted("x")) == EXIT_ERROR


def test_missing_config_is_reported_without_prompting(workspace, monkeypatch, capsys):
    class Incomplete:
        is_complete = False

    monkeypatch.setattr("config.runtime_config.load_llm_runtime_config", lambda: Incomplete())
    assert headless_main(workspace, "hi") == EXIT_ERROR
    assert "helium --setup" in capsys.readouterr().err


def test_headless_is_wired_into_the_cli(monkeypatch):
    import main

    calls = {}

    def fake_headless_main(workspace, task, **kwargs):
        calls.update(task=task, **kwargs)
        return 0

    monkeypatch.setattr(headless, "headless_main", fake_headless_main)
    monkeypatch.setattr("sys.argv", ["helium", ".", "-p", "fix it", "--accept-edits", "--json", "--max-turns", "5"])
    with pytest.raises(SystemExit) as exit_info:
        main.cli_entrypoint()
    assert exit_info.value.code == 0
    assert calls["task"] == "fix it"
    assert calls["permission_mode"] == "accept-edits"
    assert calls["output_json"] is True
    assert calls["max_turns"] == 5
