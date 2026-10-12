from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

from tools.memory_ops import remember_fact, retrieve_facts, forget_fact
from tools.system_ops import open_app, get_time
from tools.file_ops import (
    append_file,
    checksum_file,
    copy_file,
    create_file,
    delete_file,
    diff_text,
    list_directory,
    mkdir,
    move_file,
    patch_file,
    read_file,
    replace_text,
    search_text,
    stat_file,
    touch_file,
    write_file,
)
from tools.bash_ops import execute_bash, is_command_safe
from tools.search.browse_url import browse_url
from tools.web_search import search_web
from tools.research.pipeline import research_query
from tools.schema import function_to_schema, render_tool_list, validate_args
from utils.parser import extract_json


ConfirmTool = Callable[[str, dict[str, Any], str], bool]


@dataclass(frozen=True)
class ToolDefinition:
    function: Callable[..., Any]
    description: str
    permission: str = "safe"
    param_docs: dict[str, str] = field(default_factory=dict)
    # Explicit JSON schema; required for wrappers whose signature is *args/**kwargs.
    parameters: dict[str, Any] | None = None

    def schema(self) -> dict[str, Any]:
        if self.parameters is not None:
            return self.parameters
        return function_to_schema(self.function, self.param_docs)


def _create_subagent_lazy(*args, **kwargs):
    from tools.subagent_tools import create_subagent
    return create_subagent(*args, **kwargs)

def _delegate_task_lazy(*args, **kwargs):
    from tools.subagent_tools import delegate_task
    return delegate_task(*args, **kwargs)

def _delete_subagent_lazy(*args, **kwargs):
    from tools.subagent_tools import delete_subagent
    return delete_subagent(*args, **kwargs)

def _list_subagents_lazy(*args, **kwargs):
    from tools.subagent_tools import list_subagents
    return list_subagents(*args, **kwargs)


def _object_schema(properties: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
    schema: dict[str, Any] = {"type": "object", "properties": properties, "additionalProperties": False}
    if required:
        schema["required"] = required
    return schema


AVAILABLE_TOOLS: dict[str, ToolDefinition] = {
    # ── file tools ────────────────────────────────────────────────────────
    "read_file": ToolDefinition(
        read_file,
        "Reads a UTF-8 text file inside the project root.",
        "safe",
        {"start_line": "1-based first line to read", "end_line": "1-based last line to read (inclusive)"},
    ),
    "write_file": ToolDefinition(
        write_file,
        "Creates or atomically overwrites a file inside the project root. Prefer targeted edits for existing files.",
        "risky",
        {"mode": '"overwrite" or "create_only"'},
    ),
    "append_file": ToolDefinition(append_file, "Appends UTF-8 text to a file inside the project root.", "risky"),
    "delete_file": ToolDefinition(
        delete_file,
        "Permanently deletes a file, or a directory when recursive=true, inside the project root.",
        "risky",
    ),
    "copy_file": ToolDefinition(copy_file, "Copies a file or directory inside the project root.", "risky"),
    "move_file": ToolDefinition(move_file, "Moves a file or directory inside the project root.", "risky"),
    "list_directory": ToolDefinition(list_directory, "Lists files and directories inside the project root.", "safe"),
    "search_text": ToolDefinition(
        search_text,
        "Searches UTF-8 text files inside the project root for a literal string.",
        "safe",
        {"glob": "optional filename pattern such as *.py"},
    ),
    "replace_text": ToolDefinition(
        replace_text,
        "Performs a guarded literal text replacement in one project file.",
        "risky",
        {"expected_count": "fail unless exactly this many occurrences exist"},
    ),
    "patch_file": ToolDefinition(patch_file, "Applies a guarded single-file unified diff patch inside the project root.", "risky"),
    "mkdir": ToolDefinition(mkdir, "Creates a directory inside the project root.", "risky"),
    "touch_file": ToolDefinition(touch_file, "Creates a file if absent or updates its timestamp inside the project root.", "risky"),
    "stat_file": ToolDefinition(stat_file, "Returns metadata for a project file or directory.", "safe"),
    "checksum_file": ToolDefinition(
        checksum_file,
        "Computes a checksum for a project file.",
        "safe",
        {"algorithm": "sha256, sha1, or md5"},
    ),
    "diff_text": ToolDefinition(diff_text, "Previews a unified diff between a project file and proposed content without modifying it.", "safe"),
    "create_file": ToolDefinition(create_file, "Backwards-compatible alias for write_file(filename, content).", "risky"),
    # ── web and research ─────────────────────────────────────────────────
    "search_web": ToolDefinition(
        search_web,
        "Searches the web and returns structured evidence with sources and a confidence level. "
        "Use immediately for news, facts, scores, or anything beyond your knowledge cutoff; "
        "do not ask the user to clarify broad requests, invent a good query instead.",
        "safe",
    ),
    "research_query": ToolDefinition(
        research_query,
        "Researches complex analytical questions (comparisons, reports, trends, policies, why/how) "
        "using multiple searches and returns a cited report.",
        "safe",
    ),
    "browse_url": ToolDefinition(
        browse_url,
        "Opens a specific URL (rendering JavaScript with Playwright when needed) and extracts readable text.",
        "safe",
    ),
    # ── memory and system ────────────────────────────────────────────────
    "remember_fact": ToolDefinition(
        remember_fact,
        "Saves a user fact or preference into persistent long-term memory.",
        "safe",
        {"category": '"facts" or "preferences"; inferred when omitted'},
    ),
    "retrieve_facts": ToolDefinition(
        retrieve_facts,
        "Retrieves saved facts and preferences.",
        "safe",
        {"category": '"facts" or "preferences"; all memories when omitted'},
    ),
    "forget_fact": ToolDefinition(forget_fact, "Deletes a memory by id (int) or exact content (str).", "safe"),
    "open_app": ToolDefinition(open_app, "Opens a macOS application.", "risky"),
    "get_time": ToolDefinition(get_time, "Returns the current system time.", "safe"),
    "execute_bash": ToolDefinition(
        execute_bash,
        "Runs a single-shot bash command in the project root and returns the exit code and output. "
        "Read-only commands run automatically; anything else asks the user first. "
        "Chain dependent steps with &&. Prefer file tools for file manipulation.",
        "risky",
        {"timeout": "seconds before the command is killed (max 600)"},
    ),
    # ── subagents ────────────────────────────────────────────────────────
    "create_subagent": ToolDefinition(
        _create_subagent_lazy,
        "Creates a focused child agent and returns its agent_id.",
        "safe",
        parameters=_object_schema(
            {
                "name": {"type": "string"},
                "role": {"type": "string", "description": "what the subagent is responsible for"},
                "allowed_tools": {"type": "string", "description": "comma-separated tool names; all tools when omitted"},
                "max_turns": {"type": "integer", "default": 10},
            },
            ["name", "role"],
        ),
    ),
    "delegate_task": ToolDefinition(
        _delegate_task_lazy,
        "Delegates a task to an existing subagent, which runs its own agent loop and returns its final answer.",
        "safe",
        parameters=_object_schema(
            {"agent_id": {"type": "string"}, "task": {"type": "string"}},
            ["agent_id", "task"],
        ),
    ),
    "delete_subagent": ToolDefinition(
        _delete_subagent_lazy,
        "Deletes a subagent by agent_id after delegation is complete.",
        "safe",
        parameters=_object_schema({"agent_id": {"type": "string"}}, ["agent_id"]),
    ),
    "list_subagents": ToolDefinition(
        _list_subagents_lazy,
        "Lists all active subagents with their names, ids, statuses, and roles.",
        "safe",
        parameters=_object_schema({}),
    ),
}


# Guidance that applies whichever tool-calling protocol is in use.
TOOL_POLICY = """<tool_policy>
<file_tools>
File tools are restricted to the current project root; .git is protected.
Use file tools instead of execute_bash for reading, searching, and editing files.
Read a file before editing it. Prefer targeted edits over full rewrites.
delete_file permanently deletes after user confirmation.
</file_tools>

<evidence_handling>
- For web answers, use the structured evidence returned by search_web.
- Cite sources and URLs when they are present.
- If the evidence says confidence is low or partial, state that clearly instead of guessing.
</evidence_handling>

<subagent_workflow>
Subagents are focused child agents for isolated tasks such as reading files, running tests, or searching patterns:
create_subagent, then delegate_task, read the result, and delete_subagent when done.
Subagents cannot create further subagents.
</subagent_workflow>
</tool_policy>"""


TEXT_PROTOCOL_CONTRACT = """<json_contract>
When executing a tool, you MUST output a single valid JSON Action block enclosed strictly inside <action> and </action> tags.
- The JSON object must contain "tool" and "args" keys.
- Use at most one tool per reply. When no tool is needed, answer normally without an <action> block.
- You MUST escape all double quotes inside content strings with \\".
- Do NOT use raw newlines inside JSON content strings; use the literal characters \\n instead.
</json_contract>

<examples>
<example>
Input: Read the first 40 lines of tools/registry.py
<thought>
The user wants to inspect a project file, so I should use read_file.
</thought>
<action>
{"tool": "read_file", "args": {"path": "tools/registry.py", "start_line": 1, "end_line": 40}}
</action>
</example>

<example>
Input: Replace DEBUG = True with DEBUG = False in config.py
<thought>
This is a targeted file edit, so I should use replace_text with expected_count.
</thought>
<action>
{"tool": "replace_text", "args": {"path": "config.py", "old": "DEBUG = True", "new": "DEBUG = False", "expected_count": 1}}
</action>
</example>

<example>
Input: What's the latest tech news?
<thought>
The user is asking for recent news, so I should search the web.
</thought>
<action>
{"tool": "search_web", "args": {"query": "latest technology news headlines today"}}
</action>
</example>
</examples>"""


def tool_names(names: Iterable[str] | None = None) -> list[str]:
    if names is None:
        return list(AVAILABLE_TOOLS)
    return [name for name in names if name in AVAILABLE_TOOLS]


@lru_cache(maxsize=32)
def _openai_tools_cached(names: tuple[str, ...]) -> tuple[dict[str, Any], ...]:
    return tuple(
        {
            "type": "function",
            "function": {
                "name": name,
                "description": AVAILABLE_TOOLS[name].description,
                "parameters": AVAILABLE_TOOLS[name].schema(),
            },
        }
        for name in names
    )


def build_openai_tools(names: Iterable[str] | None = None) -> list[dict[str, Any]]:
    """Tool definitions for the OpenAI-compatible `tools` request field."""
    return list(_openai_tools_cached(tuple(tool_names(names))))


def render_text_protocol_prompt(names: Iterable[str] | None = None) -> str:
    """Tool list plus the <action> JSON contract, for endpoints without native tools."""
    entries = [
        (name, AVAILABLE_TOOLS[name].description, AVAILABLE_TOOLS[name].permission, AVAILABLE_TOOLS[name].schema())
        for name in tool_names(names)
    ]
    return f"<available_tools>\n{render_tool_list(entries)}\n</available_tools>\n\n{TEXT_PROTOCOL_CONTRACT}"


def __getattr__(name: str) -> Any:
    # TOOL_PROMPT is kept for callers (evals, older skills) that expect the
    # full text-protocol prompt; it is built lazily to keep imports cheap.
    if name == "TOOL_PROMPT":
        return f"{TOOL_POLICY}\n\n{render_text_protocol_prompt()}"
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def tool_permission(tool_name: str, args: dict[str, Any]) -> str:
    """Effective permission for a call; execute_bash is decided per command."""
    tool = AVAILABLE_TOOLS.get(tool_name)
    if tool is None:
        return "risky"
    if tool_name == "execute_bash":
        return "safe" if is_command_safe(str(args.get("command", ""))) else "risky"
    return tool.permission


def execute_tool_call(
    tool_name: str,
    args: dict[str, Any] | None,
    confirm_tool: ConfirmTool | None = None,
) -> str:
    """Run one tool by name with structured arguments and return its observation."""
    if tool_name not in AVAILABLE_TOOLS:
        return f"Tool '{tool_name}' is not available."

    args = args or {}
    if not isinstance(args, dict):
        return f"Error executing tool '{tool_name}': args must be a JSON object."

    tool = AVAILABLE_TOOLS[tool_name]
    try:
        problem = validate_args(tool.schema(), args)
        if problem:
            return f"Error executing tool '{tool_name}': {problem}"

        permission = tool_permission(tool_name, args)
        if permission == "risky":
            if confirm_tool is None:
                return f"Tool '{tool_name}' needs confirmation before it can run."
            if not confirm_tool(tool_name, args, permission):
                return f"Tool '{tool_name}' was cancelled by the user."

        from core.agent_context import confirm_tool_scope

        with confirm_tool_scope(confirm_tool):
            result = tool.function(**args)
        return f"Tool '{tool_name}' executed successfully. Result: {result}"
    except Exception as e:
        return f"Error executing tool '{tool_name}': {e}"


def execute_tool(
    llm_response: str,
    confirm_tool: ConfirmTool | None = None,
) -> str | None:
    """Parse a text-protocol JSON action and run it."""
    call_data = extract_json(llm_response)

    if not isinstance(call_data, dict) or "tool" not in call_data:
        return None

    return execute_tool_call(str(call_data.get("tool")), call_data.get("args", {}), confirm_tool)
