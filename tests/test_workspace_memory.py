import pytest

from config.paths import workspace_data_dir, workspace_id
from core.project_context import load_project_instructions, project_instructions_section
from tools import memory_ops


@pytest.fixture(autouse=True)
def _close_memory():
    yield
    memory_ops.shutdown_session()


def test_workspace_id_is_stable_and_distinct(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir()
    b.mkdir()
    assert workspace_id(a) == workspace_id(a)
    assert workspace_id(a) != workspace_id(b)
    assert workspace_data_dir(a) != workspace_data_dir(b)
    assert (workspace_data_dir(a) / "workspace.json").exists()


def test_session_summary_round_trips_per_workspace(tmp_path):
    project, other = tmp_path / "project", tmp_path / "other"
    project.mkdir()
    other.mkdir()

    memory_ops.initialize_session(workspace=project)
    assert memory_ops.get_session_summary() is None
    memory_ops.record_turn("user", "Please remember the deploy script is scripts/ship.sh")
    memory_ops.record_turn("assistant", "Got it.")
    memory_ops.shutdown_session()

    memory_ops.initialize_session(workspace=project)
    summary = memory_ops.get_session_summary()
    assert summary is not None and "scripts/ship.sh" in summary
    memory_ops.shutdown_session()

    memory_ops.initialize_session(workspace=other)
    assert memory_ops.get_session_summary() is None


def test_long_turns_are_truncated(tmp_path):
    memory_ops.initialize_session(workspace=tmp_path)
    memory_ops.record_turn("user", "x" * 5000)
    memory_ops.shutdown_session()
    memory_ops.initialize_session(workspace=tmp_path)
    assert len(memory_ops.get_session_summary()) < 2000


def test_shutdown_twice_is_safe(tmp_path):
    memory_ops.initialize_session(workspace=tmp_path)
    memory_ops.shutdown_session()
    memory_ops.shutdown_session()


def test_project_instructions_loaded_and_injected(tmp_path, monkeypatch):
    from core.prompts import build_system_prompt
    from tools import file_ops

    assert load_project_instructions(tmp_path) is None
    (tmp_path / "HELIUM.md").write_text("Always run `make check` before finishing.")
    assert "make check" in project_instructions_section(tmp_path)

    monkeypatch.setattr(file_ops, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(memory_ops, "get_relevant_memories", lambda q: [])
    for mode in ("chat", "code", "skill", "subagent"):
        assert "make check" in build_system_prompt(mode, user_prompt="hi")


def test_helium_md_in_dot_helium_dir(tmp_path):
    (tmp_path / ".helium").mkdir()
    (tmp_path / ".helium" / "HELIUM.md").write_text("Use tabs.")
    assert load_project_instructions(tmp_path) == "Use tabs."


def test_previous_session_injected_into_chat_prompt(tmp_path, monkeypatch):
    from core.prompts import build_system_prompt

    monkeypatch.setattr(memory_ops, "_startup_context", "Session context:\nUser: we use poetry")
    monkeypatch.setattr(memory_ops, "get_relevant_memories", lambda q: [])
    prompt = build_system_prompt("chat", user_prompt="hi")
    assert "PREVIOUS SESSION" in prompt
    assert "we use poetry" in prompt
