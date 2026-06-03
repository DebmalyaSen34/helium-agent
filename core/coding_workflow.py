from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from config.settings import ASSISTANT_PERSONA
from tools.registry import TOOL_PROMPT
from core.llm import AgenticLoop, call_llm_once, execute_agent_tool

CODING_AUTO_APPROVED_TOOLS = frozenset(
    {
        "write_file",
        "append_file",
        "replace_text",
        "patch_file",
        "mkdir",
        "touch_file",
        "create_file",
    }
)

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


def build_coding_system_prompt(task: str) -> str:
    return (
        f"{ASSISTANT_PERSONA}\n\n"
        f"{TOOL_PROMPT}\n\n"
        "<coding_workflow_mode>\n"
        "You are running Helium's /code workflow for a coding task.\n"
        f"User coding task: {task}\n\n"
        "Rules:\n"
        "- inspect relevant files before editing\n"
        "- create or maintain a short task plan before making changes\n"
        "- prefer targeted edits with replace_text or patch_file\n"
        "- use file tools instead of execute_bash for file manipulation\n"
        "- run focused verification when the task changes code, tests, or configuration\n"
        "- never claim tests passed unless a verification command actually ran and succeeded\n"
        "- if verification cannot run, say why\n"
        "- if the task is incomplete, say exactly what remains\n"
        "- if you do not know or are unsure about the programming language, the syntax, or anything related to the task, search the web to get the appropriate data to enhance your workflow\n"
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
    max_turns: int = 30,
) -> CodingWorkflowResult:
    
    changed_files: list[str] = []
    verification_commands: list[str] = []

    system_prompt = build_coding_system_prompt(task)

    if ask_model is None:
        def ask_model(messages: list[dict[str, str]]) -> str:
            reply, _tokens = call_llm_once(messages)
            return reply

    # if execute_tool_call is None:
    #     execute_tool_call = execute_agent_tool

    base_execute_tool_call = execute_tool_call or execute_agent_tool

    def execute_for_coding(
        action: dict[str, Any],
        confirm_tool: Callable[[str, dict[str, Any], str], bool] | None = None,
    ) -> str | None:
        tool_name = str(action.get("tool", ""))
        args = action.get("args", {})
        if not isinstance(args, dict):
            args = {}

        if tool_name in CODING_AUTO_APPROVED_TOOLS:
            path = args.get("path") or args.get("filename")
            if isinstance(path, str) and path not in changed_files:
                changed_files.append(path)

        if tool_name == "execute_bash":
            command = args.get("command")
            if isinstance(command, str):
                verification_commands.append(command)

        return base_execute_tool_call(action, confirm_tool=confirm_tool)


    def confirm_for_coding(
        tool_name: str,
        args: dict[str, Any],
        permission: str,
    ) -> bool:
        return coding_confirm_tool(tool_name, args, permission, confirm_tool)

    loop = AgenticLoop(
        ask_model=ask_model,
        execute_tool_call=execute_for_coding,
        max_turns=max_turns,
    )
    result = loop.run(
        system_prompt=system_prompt,
        user_prompt=task,
        history=None,
        confirm_tool=confirm_for_coding,
    )
    return CodingWorkflowResult(
        final_answer=result.final_answer,
        stop_reason=result.stop_reason,
        tools_used=result.tools_used,
        observations=result.observations,
        changed_files=changed_files,
        verification_commands=verification_commands,
    )