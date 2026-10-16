from unittest.mock import patch

from core import project_context
from core.prompts import build_system_prompt
from tools import memory_ops


def _quiet_memory(monkeypatch):
    monkeypatch.setattr(memory_ops, "get_relevant_memories", lambda q: [])
    monkeypatch.setattr(memory_ops, "_startup_context", None, raising=False)


def test_main_prompt_carries_coding_guidelines_and_snapshot(tmp_path, monkeypatch):
    from tools import file_ops

    _quiet_memory(monkeypatch)
    (tmp_path / "app.py").write_text("print('hi')\n")
    monkeypatch.setattr(file_ops, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(project_context, "_snapshots", {})

    prompt = build_system_prompt("main", user_prompt="fix the bug")

    assert "<coding_guidelines>" in prompt
    assert "<project_snapshot>" in prompt
    assert "app.py" in prompt


def test_skill_and_subagent_prompts_skip_coding_guidelines(monkeypatch):
    _quiet_memory(monkeypatch)
    assert "<coding_guidelines>" not in build_system_prompt("subagent", persona="You are a helper.")
    assert "<project_snapshot>" not in build_system_prompt("subagent", persona="You are a helper.")


def test_snapshot_is_taken_once_per_session(tmp_path, monkeypatch):
    monkeypatch.setattr(project_context, "_snapshots", {})
    calls = []

    def fake_snapshot(root):
        calls.append(root)
        return f"snapshot {len(calls)}"

    monkeypatch.setattr(project_context, "gather_project_snapshot", fake_snapshot)

    first = project_context.project_snapshot_section(tmp_path)
    (tmp_path / "new.py").write_text("")
    second = project_context.project_snapshot_section(tmp_path)

    assert first == second
    assert "snapshot 1" in first
    assert len(calls) == 1


def test_main_prompt_is_stable_across_turns(tmp_path, monkeypatch):
    """Identical system prompts let local servers reuse their prompt cache."""
    from tools import file_ops

    _quiet_memory(monkeypatch)
    monkeypatch.setattr(file_ops, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(project_context, "_snapshots", {})

    first = build_system_prompt("main", user_prompt="one")
    (tmp_path / "changed.py").write_text("")
    assert build_system_prompt("main", user_prompt="two") == first


@patch("main.print_metrics")
@patch("main.generate_response")
def test_main_turn_warns_when_turn_limit_is_hit(mock_generate, _mock_metrics):
    import main

    def fake_generate(prompt, **kwargs):
        kwargs["on_metrics"]({"stop_reason": "max_turns"})
        yield "Partial work."

    mock_generate.side_effect = fake_generate
    with patch.object(main.console, "print") as mock_print:
        main.run_main_turn("refactor everything", confirm_tool=lambda *a: True)

    printed = " ".join(str(call.args[0]) for call in mock_print.call_args_list if call.args)
    assert "turn limit" in printed
