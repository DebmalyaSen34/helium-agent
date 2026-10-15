from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from config.settings import AGENT_SETTINGS
from core.llm import run_agent
from core.prompts import build_system_prompt
from tools.registry import tools_for

CODING_AUTO_APPROVED_TOOLS = frozenset(
    {
        "edit_file",
        "write_file",
        "append_file",
        "replace_text",
        "patch_file",
        "mkdir",
        "touch_file",
        "create_file",
    }
)

VERIFICATION_TOOLS = frozenset({"execute_bash", "run_tests"})

CODING_CONFIRMED_TOOLS = frozenset(
    {
        "delete_file",
        "move_file",
        "copy_file",
        "open_app",
    }
)


@dataclass(frozen=True)
class CodingWorkflowResult:
    final_answer: str
    stop_reason: str
    tools_used: list[str]
    observations: list[str]
    changed_files: list[str]
    verification_commands: list[str]


def build_coding_system_prompt(task: str, project_context: str | None = None) -> str:
    rules = _coding_rules(task)
    if project_context:
        rules += f"\n\n<project_snapshot>\n{project_context}\n</project_snapshot>"
    return build_system_prompt("code", extra=rules)


def _coding_rules(task: str) -> str:
    return (
        "<coding_workflow_mode>\n"
        "You are running Helium's /code workflow: an autonomous coding agent working in the user's project.\n"
        f"User coding task: {task}\n\n"
        "Workflow:\n"
        "1. Explore: inspect relevant files before editing. Use glob_files and search_text to locate code, "
        "then read_file the parts you need. Batch independent reads in one turn when you can.\n"
        "2. Plan: write a short task plan (3-6 bullets) before making changes, and keep it updated as you learn.\n"
        "3. Edit: prefer targeted edits with edit_file; use write_file only for new files "
        "or complete rewrites. Keep diffs minimal and do not reformat unrelated code.\n"
        "4. Verify: run focused verification when the task changes code, tests, or configuration "
        "(run_tests with a focused command, or execute_bash). Read failures carefully and fix the cause.\n"
        "5. Report: finish with the final answer format below.\n\n"
        "Rules:\n"
        "- read a file before editing it, and never invent file contents\n"
        "- read_file output has line-number prefixes; never copy them into edit text\n"
        "- use file tools instead of execute_bash for file manipulation\n"
        "- never claim tests passed unless a verification command actually ran and succeeded\n"
        "- if verification cannot run, say why\n"
        "- if two attempts to fix the same failure don't work, stop and report what you found instead of looping\n"
        "- if the task is incomplete, say exactly what remains\n"
        "- if you do not know or are unsure about the programming language, the syntax, or a library API, "
        "search the web to get the appropriate data to enhance your workflow\n"
        "- do not get stuck in a research loop. Start writing code and implementing changes as soon as you have sufficient information.\n"
        "- prioritize implementation and verification; do not exhaust all your turns on research or searching.\n\n"
        "Final answer format:\n"
        "Changed files:\n"
        "- <file or None>\n\n"
        "Verification:\n"
        "- <command and result, or Not run with reason>\n\n"
        "Remaining risks:\n"
        "- <risk or None>\n"
        "</coding_workflow_mode>"
    )


def gather_project_context(max_entries: int = 150) -> str:
    """Git status plus a shallow file tree, so the agent starts oriented."""
    from tools import file_ops
    from tools.file_service import IGNORED_DIRS
    from tools.git_ops import git_status

    root = file_ops.PROJECT_ROOT
    entries: list[str] = []
    try:
        for child in sorted(root.iterdir()):
            if child.name in IGNORED_DIRS or child.name.startswith(".") and child.name not in {".github", ".helium"}:
                continue
            if child.is_dir():
                entries.append(f"{child.name}/")
                for grandchild in sorted(child.iterdir()):
                    if grandchild.name in IGNORED_DIRS or grandchild.name.startswith("."):
                        continue
                    entries.append(f"  {grandchild.name}{'/' if grandchild.is_dir() else ''}")
                    if len(entries) >= max_entries:
                        break
            else:
                entries.append(child.name)
            if len(entries) >= max_entries:
                entries.append("  ...")
                break
    except OSError:
        pass

    return f"Project root: {root}\n\nGit status:\n{git_status()}\n\nFiles (depth 2):\n" + "\n".join(entries)


def _succeeded(result: str | None) -> bool:
    text = str(result or "")
    return not any(marker in text for marker in ("status: error", "was cancelled", "needs confirmation", "Error executing tool"))


def coding_confirm_tool(
    tool_name: str,
    args: dict[str, Any],
    permission: str,
    confirm_tool: Callable[[str, dict[str, Any], str], bool] | None,
) -> bool:
    if permission != "risky":
        return True
    if tool_name in CODING_AUTO_APPROVED_TOOLS:
        return True
    if tool_name in CODING_CONFIRMED_TOOLS or tool_name == "execute_bash":
        if confirm_tool is None:
            return False
        return confirm_tool(tool_name, args, permission)
    if confirm_tool is None:
        return False
    return confirm_tool(tool_name, args, permission)

def run_coding_workflow(
    task: str,
    confirm_tool: Callable[[str, dict[str, Any], str], bool] | None = None,
    ask_model: Callable[[list[dict[str, str]]], str] | None = None,
    execute_tool_call: Callable[..., str | None] | None = None,
    max_turns: int | None = None,
    on_event: Callable[[str, Any], None] | None = None,
) -> CodingWorkflowResult:
    
    changed_files: list[str] = []
    verification_commands: list[str] = []

    project_context = None
    if ask_model is None:
        try:
            project_context = gather_project_context()
        except Exception:
            project_context = None
    system_prompt = build_coding_system_prompt(task, project_context)

    if execute_tool_call is None:
        from core.llm import execute_agent_tool

        def base_execute_tool_call(action, confirm_tool=None):
            return execute_agent_tool(action, confirm_tool=confirm_tool)
    else:
        base_execute_tool_call = execute_tool_call

    def execute_for_coding(
        action: dict[str, Any],
        confirm_tool: Callable[[str, dict[str, Any], str], bool] | None = None,
    ) -> str | None:
        tool_name = str(action.get("tool", ""))
        args = action.get("args", {})
        if not isinstance(args, dict):
            args = {}

        result = base_execute_tool_call(action, confirm_tool=confirm_tool)
        if not _succeeded(result):
            return result

        if tool_name in CODING_AUTO_APPROVED_TOOLS:
            path = args.get("path") or args.get("filename")
            if isinstance(path, str) and path not in changed_files:
                changed_files.append(path)

        if tool_name in VERIFICATION_TOOLS:
            command = args.get("command")
            if tool_name == "run_tests" and not command:
                from tools.test_runner import detect_test_command

                command = detect_test_command() or "run_tests (auto-detect)"
            if isinstance(command, str):
                verification_commands.append(command)

        return result


    def confirm_for_coding(
        tool_name: str,
        args: dict[str, Any],
        permission: str,
    ) -> bool:
        return coding_confirm_tool(tool_name, args, permission, confirm_tool)

    result = run_agent(
        system_prompt,
        task,
        confirm_tool=confirm_for_coding,
        tool_names=tools_for("code"),
        max_turns=max_turns or int(AGENT_SETTINGS.get("code_max_turns", 40)),
        on_event=on_event,
        execute_tool_call=execute_for_coding,
        ask_model=ask_model,
    )
    return CodingWorkflowResult(
        final_answer=result.final_answer,
        stop_reason=result.stop_reason,
        tools_used=result.tools_used,
        observations=result.observations,
        changed_files=changed_files,
        verification_commands=verification_commands,
    )
