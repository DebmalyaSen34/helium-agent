"""Detect and run a project's test suite."""

from __future__ import annotations

from pathlib import Path

from tools.bash_ops import _project_root, execute_bash

DEFAULT_TEST_TIMEOUT = 300


def detect_test_command(root: Path | None = None) -> str | None:
    root = root or _project_root()

    def exists(name: str) -> bool:
        return (root / name).exists()

    has_python_tests = exists("pytest.ini") or exists("tests") or exists("test") or exists("conftest.py")
    for config_name in ("pyproject.toml", "setup.cfg", "tox.ini"):
        config = root / config_name
        if config.exists() and "pytest" in config.read_text(encoding="utf-8", errors="ignore"):
            has_python_tests = True
    if has_python_tests:
        return "uv run pytest -q" if exists("uv.lock") else "python -m pytest -q"
    if exists("package.json"):
        return "npm test --silent"
    if exists("Cargo.toml"):
        return "cargo test"
    if exists("go.mod"):
        return "go test ./..."
    return None


def run_tests(command: str | None = None, timeout: int = DEFAULT_TEST_TIMEOUT) -> str:
    """Run the given test command, or auto-detect the project's test runner."""
    command = (command or "").strip() or detect_test_command()
    if not command:
        return "Could not detect a test command. Pass one explicitly, e.g. run_tests(command=\"pytest tests/test_x.py\")."
    return f"command: {command}\n" + execute_bash(command, timeout=timeout)


__all__ = ["detect_test_command", "run_tests"]
