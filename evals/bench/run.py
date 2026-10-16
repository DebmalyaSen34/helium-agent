"""Helium coding benchmark: run every task in a fresh repo and grade it with hidden tests.

    python -m evals.bench.run                      # all tasks, configured model
    python -m evals.bench.run --model qwen3-coder --runs 3 --jobs 2
    python -m evals.bench.run --tasks pagination,lru   # substring filter on task ids
    python -m evals.bench.run --compare evals/bench/results/<old>/summary.json
    python -m evals.bench.run --check              # validate the tasks themselves, no LLM

Each attempt copies the task's `repo/` into a temporary git repository, runs
`helium -p` there with every tool allowed, then copies the task's hidden
`tests/` in and runs them. The agent never sees the hidden tests. See
evals/bench/README.md for the task format.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

BENCH_DIR = Path(__file__).resolve().parent
TASKS_DIR = BENCH_DIR / "tasks"
RESULTS_DIR = BENCH_DIR / "results"
REPO_ROOT = BENCH_DIR.parents[1]
HIDDEN_DIR = ".bench_hidden"
DEFAULT_TEST_COMMAND = "{python} -m pytest -q -p no:cacheprovider " + HIDDEN_DIR
GIT_ENV = {
    "GIT_AUTHOR_NAME": "bench", "GIT_AUTHOR_EMAIL": "bench@example.com",
    "GIT_COMMITTER_NAME": "bench", "GIT_COMMITTER_EMAIL": "bench@example.com",
}


@dataclass(frozen=True)
class Task:
    id: str
    prompt: str
    category: str
    difficulty: str
    path: Path
    protected: tuple[str, ...] = ()
    test_command: str = DEFAULT_TEST_COMMAND
    timeout_s: int = 900

    @classmethod
    def load(cls, task_dir: Path) -> "Task":
        data = yaml.safe_load((task_dir / "task.yaml").read_text(encoding="utf-8"))
        return cls(
            id=data.get("id", task_dir.name),
            prompt=data["prompt"].strip(),
            category=data.get("category", "other"),
            difficulty=data.get("difficulty", "medium"),
            path=task_dir,
            protected=tuple(data.get("protected", ())),
            test_command=data.get("test_command", DEFAULT_TEST_COMMAND),
            timeout_s=int(data.get("timeout_s", 900)),
        )


@dataclass
class Attempt:
    task: str
    run: int
    category: str
    difficulty: str
    passed: bool
    reason: str
    stop_reason: str = ""
    exit_code: int | None = None
    duration_s: float = 0.0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    requests: int = 0
    tool_calls: int = 0
    tools_used: dict[str, int] = field(default_factory=dict)
    files_changed: list[str] = field(default_factory=list)
    artifacts: str = ""


def load_tasks(filters: list[str] | None = None) -> list[Task]:
    tasks = [Task.load(d) for d in sorted(TASKS_DIR.iterdir()) if (d / "task.yaml").is_file()]
    if filters:
        tasks = [t for t in tasks if any(f in t.id for f in filters)]
    return tasks


# -- workspace -----------------------------------------------------------------

def _git(cwd: Path, *args: str) -> str:
    env = {**os.environ, **GIT_ENV}
    return subprocess.run(["git", *args], cwd=cwd, env=env, capture_output=True, text=True, check=True).stdout


def prepare_workspace(task: Task, dest: Path, *, overlay: Path | None = None) -> Path:
    """Copy the task repo into `dest`, commit it, and optionally lay `overlay` on top."""
    shutil.copytree(task.path / "repo", dest)
    _git(dest, "init", "-q", "-b", "main")
    _git(dest, "add", "-A")
    _git(dest, "commit", "-q", "-m", "task start")
    if overlay is not None and overlay.is_dir():
        shutil.copytree(overlay, dest, dirs_exist_ok=True)
    return dest


def changed_files(workspace: Path) -> list[str]:
    _git(workspace, "add", "-A")
    out = _git(workspace, "diff", "--cached", "--name-only")
    return [line for line in out.splitlines() if line and not line.startswith(HIDDEN_DIR)]


def save_diff(workspace: Path, dest: Path) -> None:
    _git(workspace, "add", "-A")
    dest.write_text(_git(workspace, "diff", "--cached"), encoding="utf-8")


def run_hidden_tests(task: Task, workspace: Path, timeout: int = 300) -> tuple[bool, str]:
    hidden = workspace / HIDDEN_DIR
    if hidden.exists():
        shutil.rmtree(hidden)
    shutil.copytree(task.path / "tests", hidden)
    command = task.test_command.format(python=shlex.quote(sys.executable))
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    try:
        proc = subprocess.run(command, shell=True, cwd=workspace, env=env, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return False, f"hidden tests timed out after {timeout}s"
    finally:
        shutil.rmtree(hidden, ignore_errors=True)
    return proc.returncode == 0, proc.stdout + proc.stderr


# -- one attempt ---------------------------------------------------------------

def helium_command(args: argparse.Namespace) -> list[str]:
    if args.helium_cmd:
        return shlex.split(args.helium_cmd)
    return [sys.executable, str(REPO_ROOT / "main.py")]


def run_attempt(task: Task, run: int, args: argparse.Namespace, out_dir: Path) -> Attempt:
    artifacts = out_dir / "attempts" / f"{task.id}__{run}"
    artifacts.mkdir(parents=True, exist_ok=True)
    attempt = Attempt(task.id, run, task.category, task.difficulty, passed=False, reason="", artifacts=str(artifacts))

    with tempfile.TemporaryDirectory(prefix=f"helium-bench-{task.id}-") as tmp:
        workspace = prepare_workspace(task, Path(tmp) / "repo")
        command = [
            *helium_command(args), str(workspace), "-p", task.prompt,
            "--yes", "--json", "--verbose",
            "--transcript", str(artifacts / "transcript.json"),
        ]
        if args.model:
            command += ["--model", args.model]
        if args.max_turns:
            command += ["--max-turns", str(args.max_turns)]
        # Fresh memory per attempt, so earlier runs can't leak into the prompt.
        env = {**os.environ, "HELIUM_DATA_DIR": str(Path(tmp) / "data"), "PYTHONDONTWRITEBYTECODE": "1"}

        started = time.time()
        try:
            proc = subprocess.run(command, cwd=workspace, env=env, capture_output=True, text=True, timeout=task.timeout_s)
            attempt.exit_code = proc.returncode
            stdout, stderr = proc.stdout, proc.stderr
        except subprocess.TimeoutExpired as exc:
            stdout = exc.stdout.decode() if isinstance(exc.stdout, bytes) else (exc.stdout or "")
            stderr = exc.stderr.decode() if isinstance(exc.stderr, bytes) else (exc.stderr or "")
            attempt.stop_reason = "timeout"
        attempt.duration_s = round(time.time() - started, 1)
        (artifacts / "agent.log").write_text(stderr, encoding="utf-8")

        report = _parse_report(stdout)
        if report:
            (artifacts / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
            attempt.stop_reason = attempt.stop_reason or report.get("stop_reason", "")
            attempt.prompt_tokens = report.get("usage", {}).get("prompt_tokens", 0)
            attempt.completion_tokens = report.get("usage", {}).get("completion_tokens", 0)
            attempt.requests = report.get("num_requests", 0)
            attempt.tool_calls = report.get("num_tool_calls", 0)
            attempt.tools_used = report.get("tools_used", {})

        attempt.files_changed = changed_files(workspace)
        save_diff(workspace, artifacts / "diff.patch")

        touched = sorted(set(attempt.files_changed) & set(task.protected))
        if attempt.stop_reason in ("timeout", "error") or not report:
            attempt.reason = attempt.stop_reason or "no report from helium (see agent.log)"
            if attempt.stop_reason == "error":
                attempt.reason = f"error: {report.get('result', '')[:200]}"
        elif touched:
            attempt.reason = f"modified protected files: {', '.join(touched)}"
        else:
            attempt.passed, output = run_hidden_tests(task, workspace)
            (artifacts / "hidden_tests.log").write_text(output, encoding="utf-8")
            attempt.reason = "hidden tests passed" if attempt.passed else _first_failure(output)
    return attempt


def _parse_report(stdout: str) -> dict[str, Any]:
    for line in reversed(stdout.strip().splitlines()):
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    return {}


def _first_failure(output: str) -> str:
    for line in output.splitlines():
        if line.startswith(("FAILED", "ERROR")):
            return line[:200]
    tail = [line for line in output.strip().splitlines() if line.strip()]
    return (tail[-1] if tail else "hidden tests failed")[:200]


# -- reporting -----------------------------------------------------------------

def summarize(attempts: list[Attempt], meta: dict[str, Any]) -> dict[str, Any]:
    def rate(items: list[Attempt]) -> float:
        return round(100 * sum(a.passed for a in items) / len(items), 1) if items else 0.0

    def group(key: str) -> dict[str, float]:
        names = sorted({getattr(a, key) for a in attempts})
        return {name: rate([a for a in attempts if getattr(a, key) == name]) for name in names}

    n = len(attempts) or 1
    return {
        **meta,
        "attempts": len(attempts),
        "pass_rate": rate(attempts),
        "by_task": group("task"),
        "by_category": group("category"),
        "by_difficulty": group("difficulty"),
        "avg_duration_s": round(sum(a.duration_s for a in attempts) / n, 1),
        "avg_tokens": round(sum(a.prompt_tokens + a.completion_tokens for a in attempts) / n),
        "avg_tool_calls": round(sum(a.tool_calls for a in attempts) / n, 1),
        "stop_reasons": {r: sum(a.stop_reason == r for a in attempts) for r in sorted({a.stop_reason for a in attempts})},
    }


def render_markdown(summary: dict[str, Any], attempts: list[Attempt], baseline: dict[str, Any] | None) -> str:
    lines = [
        f"# Helium benchmark: {summary['pass_rate']}% pass",
        "",
        f"- Model: `{summary['model']}`",
        f"- Date: {summary['started']}",
        f"- Attempts: {summary['attempts']} ({summary['runs']} per task)",
        f"- Average per attempt: {summary['avg_duration_s']}s, {summary['avg_tokens']:,} tokens, {summary['avg_tool_calls']} tool calls",
        f"- Stop reasons: {', '.join(f'{k or 'none'} {v}' for k, v in summary['stop_reasons'].items())}",
    ]
    if baseline:
        delta = summary["pass_rate"] - baseline.get("pass_rate", 0.0)
        lines.append(f"- Compared with `{baseline.get('model')}` on {baseline.get('started')}: {baseline.get('pass_rate')}% → {summary['pass_rate']}% ({delta:+.1f})")
    lines += ["", "| Category | Pass % |", "| --- | --- |"]
    lines += [f"| {k} | {v} |" for k, v in summary["by_category"].items()]
    lines += ["", "| Difficulty | Pass % |", "| --- | --- |"]
    lines += [f"| {k} | {v} |" for k, v in summary["by_difficulty"].items()]

    lines += ["", "## Attempts", "", "| Task | Run | Result | Stop | Time | Tokens | Tools | Reason |", "| --- | --- | --- | --- | --- | --- | --- | --- |"]
    before = (baseline or {}).get("by_task", {})
    for a in sorted(attempts, key=lambda a: (a.task, a.run)):
        mark = "PASS" if a.passed else "FAIL"
        if a.task in before and a.run == 1:
            mark += f" (was {before[a.task]}%)"
        reason = a.reason.replace("|", "\\|")
        lines.append(f"| {a.task} | {a.run} | {mark} | {a.stop_reason} | {a.duration_s}s | {a.prompt_tokens + a.completion_tokens:,} | {a.tool_calls} | {reason} |")
    return "\n".join(lines) + "\n"


# -- task validation -----------------------------------------------------------

def check_tasks(tasks: list[Task]) -> int:
    """Each task's hidden tests must fail on the starting repo and pass with its reference solution."""
    problems = 0
    for task in tasks:
        issues = []
        if not (task.path / "tests").is_dir():
            issues.append("missing tests/")
        if not (task.path / "solution").is_dir():
            issues.append("missing solution/")
        if not issues:
            with tempfile.TemporaryDirectory() as tmp:
                start = prepare_workspace(task, Path(tmp) / "start")
                passed, _ = run_hidden_tests(task, start)
                if passed:
                    issues.append("hidden tests already pass on the starting repo")
                solved = prepare_workspace(task, Path(tmp) / "solved", overlay=task.path / "solution")
                passed, output = run_hidden_tests(task, solved)
                if not passed:
                    issues.append("reference solution fails hidden tests: " + _first_failure(output))
                if (solved / "tests").is_dir():
                    proc = subprocess.run(
                        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "tests"],
                        cwd=solved, capture_output=True, text=True, timeout=300,
                    )
                    if proc.returncode != 0:
                        issues.append("reference solution fails the repo's own tests: " + _first_failure(proc.stdout))
                touched = sorted(set(changed_files(solved)) & set(task.protected))
                if touched:
                    issues.append(f"reference solution modifies protected files: {', '.join(touched)}")
        status = "ok" if not issues else "PROBLEM"
        print(f"{status:8} {task.id}" + "".join(f"\n         - {issue}" for issue in issues))
        problems += bool(issues)
    print(f"\n{len(tasks) - problems}/{len(tasks)} tasks valid")
    return 1 if problems else 0


# -- main ----------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--tasks", help="comma-separated substrings; only matching task ids run")
    parser.add_argument("--model", help="model to benchmark (defaults to the configured one)")
    parser.add_argument("--runs", type=int, default=1, help="attempts per task (default 1)")
    parser.add_argument("--jobs", type=int, default=1, help="attempts run in parallel (default 1)")
    parser.add_argument("--max-turns", type=int, help="tool turn limit per attempt")
    parser.add_argument("--helium-cmd", help='command that runs helium (default: this checkout, e.g. "helium" for the installed one)')
    parser.add_argument("--out", type=Path, help="results directory (default evals/bench/results/<time>-<model>)")
    parser.add_argument("--compare", type=Path, help="summary.json of an earlier run to compare against")
    parser.add_argument("--check", action="store_true", help="validate the tasks without running the agent")
    parser.add_argument("--list", action="store_true", help="list the tasks and exit")
    args = parser.parse_args(argv)

    tasks = load_tasks(args.tasks.split(",") if args.tasks else None)
    if not tasks:
        print("No tasks matched.", file=sys.stderr)
        return 1
    if args.list:
        for task in tasks:
            print(f"{task.id:32} {task.category:10} {task.difficulty}")
        return 0
    if args.check:
        return check_tasks(tasks)

    model = args.model or _configured_model()
    started = datetime.now().strftime("%Y-%m-%d %H:%M")
    out_dir = args.out or RESULTS_DIR / f"{datetime.now():%Y%m%d-%H%M%S}-{re.sub(r'[^A-Za-z0-9._-]+', '_', model)}"
    out_dir.mkdir(parents=True, exist_ok=True)
    baseline = json.loads(args.compare.read_text()) if args.compare else None

    jobs = [(task, run) for task in tasks for run in range(1, args.runs + 1)]
    print(f"Running {len(jobs)} attempts on {model}; results in {out_dir}", flush=True)
    attempts: list[Attempt] = []
    with ThreadPoolExecutor(max_workers=max(1, args.jobs)) as pool, (out_dir / "results.jsonl").open("w") as log:
        futures = {pool.submit(run_attempt, task, run, args, out_dir): (task, run) for task, run in jobs}
        for future in as_completed(futures):
            task, run = futures[future]
            try:
                attempt = future.result()
            except Exception as exc:  # a broken attempt must not lose the others
                attempt = Attempt(task.id, run, task.category, task.difficulty, passed=False, reason=f"runner error: {exc}")
            attempts.append(attempt)
            log.write(json.dumps(asdict(attempt)) + "\n")
            log.flush()
            mark = "PASS" if attempt.passed else "FAIL"
            print(f"[{len(attempts)}/{len(jobs)}] {mark} {attempt.task} #{run} ({attempt.duration_s}s) {'' if attempt.passed else attempt.reason}", flush=True)

    summary = summarize(attempts, {"model": model, "started": started, "runs": args.runs})
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    (out_dir / "summary.md").write_text(render_markdown(summary, attempts, baseline), encoding="utf-8")
    print(f"\nPass rate: {summary['pass_rate']}% ({sum(a.passed for a in attempts)}/{len(attempts)})")
    print(f"Report: {out_dir / 'summary.md'}")
    return 0


def _configured_model() -> str:
    try:
        sys.path.insert(0, str(REPO_ROOT))
        from core.session import get_active_model

        return get_active_model()
    except Exception:
        return "configured-model"


if __name__ == "__main__":
    sys.exit(main())
