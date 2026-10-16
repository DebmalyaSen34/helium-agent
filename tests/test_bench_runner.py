import json
import sys
from pathlib import Path

import pytest

from evals.bench import run as bench

FAKE_HELIUM = Path(__file__).parent / "fixtures" / "fake_helium.py"


def args(**overrides):
    defaults = dict(helium_cmd=f"{sys.executable} {FAKE_HELIUM}", model=None, max_turns=None)
    return type("Args", (), {**defaults, **overrides})()


def task(task_id):
    return next(t for t in bench.load_tasks() if t.id == task_id)


def test_there_are_twenty_tasks_with_metadata():
    tasks = bench.load_tasks()
    assert len(tasks) == 20
    assert {t.difficulty for t in tasks} <= {"easy", "medium", "hard"}
    assert all(t.prompt for t in tasks)


def test_filter_by_substring():
    assert [t.id for t in bench.load_tasks(["lru"])] == ["05-lru-cache"]


def test_solved_attempt_passes(tmp_path, monkeypatch):
    pagination = task("01-pagination-off-by-one")
    monkeypatch.setenv("FAKE_HELIUM_OVERLAY", str(pagination.path / "solution"))
    attempt = bench.run_attempt(pagination, 1, args(), tmp_path)
    assert attempt.passed, attempt.reason
    assert attempt.files_changed == ["shop/pagination.py"]
    assert attempt.prompt_tokens == 1000
    assert "paginate" in (Path(attempt.artifacts) / "diff.patch").read_text()


def test_untouched_attempt_fails_with_a_reason(tmp_path, monkeypatch):
    monkeypatch.delenv("FAKE_HELIUM_OVERLAY", raising=False)
    attempt = bench.run_attempt(task("02-mutable-default"), 1, args(), tmp_path)
    assert not attempt.passed
    assert attempt.reason.startswith("FAILED")


def test_editing_protected_files_fails(tmp_path, monkeypatch):
    failing_tests = task("07-failing-tests")
    cheat = tmp_path / "cheat"
    (cheat / "tests").mkdir(parents=True)
    (cheat / "tests" / "test_stock.py").write_text("def test_nothing():\n    pass\n")
    monkeypatch.setenv("FAKE_HELIUM_OVERLAY", str(cheat))
    attempt = bench.run_attempt(failing_tests, 1, args(), tmp_path / "out")
    assert not attempt.passed
    assert "protected" in attempt.reason


def test_missing_report_is_a_failure(tmp_path):
    attempt = bench.run_attempt(task("09-slugify"), 1, args(helium_cmd=f"{sys.executable} -c pass"), tmp_path)
    assert not attempt.passed
    assert "no report" in attempt.reason


def test_main_writes_summary(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("FAKE_HELIUM_OVERLAY", raising=False)
    out = tmp_path / "results"
    code = bench.main(["--tasks", "09-slugify", "--helium-cmd", f"{sys.executable} {FAKE_HELIUM}", "--model", "fake", "--out", str(out)])
    assert code == 0
    summary = json.loads((out / "summary.json").read_text())
    assert summary["pass_rate"] == 0.0
    assert summary["by_task"] == {"09-slugify": 0.0}
    assert "09-slugify" in (out / "summary.md").read_text()
    assert len((out / "results.jsonl").read_text().splitlines()) == 1


def test_markdown_comparison_with_baseline():
    attempts = [bench.Attempt("a", 1, "bugfix", "easy", passed=True, reason="ok")]
    summary = bench.summarize(attempts, {"model": "m", "started": "now", "runs": 1})
    text = bench.render_markdown(summary, attempts, {"model": "old", "started": "then", "pass_rate": 50.0, "by_task": {"a": 0.0}})
    assert "50.0% → 100.0% (+50.0)" in text
    assert "PASS (was 0.0%)" in text


@pytest.mark.parametrize("task_id", ["01-pagination-off-by-one", "17-stale-cache"])
def test_check_mode_accepts_valid_tasks(task_id, capsys):
    assert bench.check_tasks([task(task_id)]) == 0
