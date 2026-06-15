from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import json
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
from tools.search.hybrid_fetch import fetch_url_content_mvp
from tools.search.searxng import search_searxng
from tools.bash_ops import execute_bash
from tools.search.browse_url import browse_url
from tools.web_search import search_web
from tools.research.pipeline import research_query
from utils.parser import extract_json


@dataclass(frozen=True)
class ToolDefinition:
    function: Callable[..., Any]
    description: str
    permission: str = "safe"


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


AVAILABLE_TOOLS = {
    "create_file": ToolDefinition(create_file, "Creates or overwrites a file in the current project.", "risky"),
    "search_web": ToolDefinition(search_web, "Searches the web and returns structured evidence with sources.", "safe"),
    "research_query": ToolDefinition(research_query, "Researches complex analytical questions using multiple searches and citations.", "safe"),
    "remember_fact": ToolDefinition(remember_fact, "Saves a user fact or preference into long-term memory.", "safe"),
    "retrieve_facts": ToolDefinition(retrieve_facts, "Retrieves saved facts and preferences.", "safe"),
    "forget_fact": ToolDefinition(forget_fact, "Deletes a memory by id or content match.", "safe"),
    "open_app": ToolDefinition(open_app, "Opens a macOS application.", "risky"),
    "get_time": ToolDefinition(get_time, "Returns the current system time.", "safe"),
    "browse_url": ToolDefinition(browse_url, "Navigates to a specific website, executes JavaScript using Playwright, and extracts clean, readable text.", "safe"),
    "execute_bash": ToolDefinition(execute_bash, "Executes a single-shot bash command on the macOS host system within a 30-second timeout. For sequential dependent steps (like navigating directories), chain commands using &&.", "risky"),
    "read_file": ToolDefinition(read_file, "Reads a UTF-8 text file inside the project root.", "safe"),
    "write_file": ToolDefinition(write_file, "Creates or atomically overwrites a file inside the project root.", "risky"),
    "append_file": ToolDefinition(append_file, "Appends UTF-8 text to a file inside the project root.", "risky"),
    "delete_file": ToolDefinition(delete_file, "Permanently deletes a file or recursive directory inside the project root.", "risky"),
    "copy_file": ToolDefinition(copy_file, "Copies a file or directory inside the project root.", "risky"),
    "move_file": ToolDefinition(move_file, "Moves a file or directory inside the project root.", "risky"),
    "list_directory": ToolDefinition(list_directory, "Lists files and directories inside the project root.", "safe"),
    "search_text": ToolDefinition(search_text, "Searches UTF-8 text files inside the project root.", "safe"),
    "replace_text": ToolDefinition(replace_text, "Performs guarded literal text replacement inside one project file.", "risky"),
    "patch_file": ToolDefinition(patch_file, "Applies a guarded single-file unified patch inside the project root.", "risky"),
    "mkdir": ToolDefinition(mkdir, "Creates a directory inside the project root.", "risky"),
    "touch_file": ToolDefinition(touch_file, "Creates or updates a file timestamp inside the project root.", "risky"),
    "stat_file": ToolDefinition(stat_file, "Returns metadata for a project file or directory.", "safe"),
    "checksum_file": ToolDefinition(checksum_file, "Computes a checksum for a project file.", "safe"),
    "diff_text": ToolDefinition(diff_text, "Previews a unified diff between a project file and proposed content.", "safe"),
    "create_subagent": ToolDefinition(
        _create_subagent_lazy,
        "Creates a new subagent with a name, role, and optional comma-separated list of allowed tools. "
        "Returns the agent_id needed for delegation. Use for spawning focused child agents.",
        "safe",
    ),
    "delegate_task": ToolDefinition(
        _delegate_task_lazy,
        "Delegates a task to an existing subagent by agent_id. The subagent runs an agentic loop "
        "with its configured tools and role. Returns the subagent's final answer.",
        "safe",
    ),
    "delete_subagent": ToolDefinition(
        _delete_subagent_lazy,
        "Deletes a subagent by agent_id, freeing resources. Use after delegation is complete.",
        "safe",
    ),
    "list_subagents": ToolDefinition(
        _list_subagents_lazy,
        "Lists all active subagents with their names, ids, statuses, and roles.",
        "safe",
    ),
}

TOOL_PROMPT = """<available_tools>
<file_tools>
File tools are restricted to the current project root.
Use file tools instead of execute_bash for file manipulation.
Prefer read_file before editing existing files.
Prefer replace_text or patch_file for targeted edits.
Use diff_text to preview full-file rewrites when useful.
delete_file permanently deletes after user confirmation.

1. read_file(path: str, start_line: int | null = null, end_line: int | null = null, max_chars: int = 20000) - Reads a UTF-8 text file. Permission: safe.
2. write_file(path: str, content: str, mode: str = "overwrite") - Creates or atomically overwrites a UTF-8 text file. mode may be "overwrite" or "create_only". Permission: risky.
3. append_file(path: str, content: str) - Appends UTF-8 text to a file. Permission: risky.
4. delete_file(path: str, recursive: bool = false) - Permanently deletes a file, or a directory when recursive=true. Permission: risky.
5. copy_file(source: str, destination: str, overwrite: bool = false) - Copies a file or directory. Permission: risky.
6. move_file(source: str, destination: str, overwrite: bool = false) - Moves a file or directory. Permission: risky.
7. list_directory(path: str = ".", recursive: bool = false, max_entries: int = 200) - Lists project files and directories. Permission: safe.
8. search_text(query: str, path: str = ".", glob: str | null = null, case_sensitive: bool = false, max_matches: int = 100) - Searches UTF-8 text files. Permission: safe.
9. replace_text(path: str, old: str, new: str, expected_count: int | null = null) - Performs guarded literal text replacement in one file. Permission: risky.
10. patch_file(path: str, patch: str, expected_original_hash: str | null = null) - Applies a guarded single-file unified diff patch. Permission: risky.
11. mkdir(path: str, parents: bool = true, exist_ok: bool = true) - Creates a directory. Permission: risky.
12. touch_file(path: str) - Creates a file if absent or updates its timestamp. Permission: risky.
13. stat_file(path: str) - Returns file or directory metadata. Permission: safe.
14. checksum_file(path: str, algorithm: str = "sha256") - Computes a file checksum. Supported algorithms: sha256, sha1, md5. Permission: safe.
15. diff_text(path: str, proposed_content: str, context_lines: int = 3) - Shows a unified diff without modifying the file. Permission: safe.
16. create_file(filename: str, content: str) - Backwards-compatible alias for write_file(filename, content, mode="overwrite"). Permission: risky.
</file_tools>

<web_and_research_tools>
17. search_web(query: str, num_results: int = 5) - Searches the web and returns structured evidence.
   CRITICAL SEARCH RULES:
   - Use IMMEDIATELY for news, facts, scores, or any knowledge beyond your cutoff data.
   - Do NOT ask user to clarify broad requests. Invent a smart query and search immediately.
   - Extract exact facts (e.g. "Team X won 3-0"). Do NOT describe the articles.
18. research_query(query: str, max_sources: int = 8) - Researches complex analytical questions using multiple searches. Permission: safe.
   - Use for comparisons, detailed reports, market trends, policies, or complex why/how queries.
19. browse_url(url: str) - Navigates to a specific website, executes JavaScript using Playwright, and extracts clean, readable text. Use when a specific URL link is provided. Permission: safe.
</web_and_research_tools>

<memory_and_system_tools>
20. remember_fact(fact: str, category: str = "facts" | "preferences") - Saves a user fact/preference into persistent long-term memory. Permission: safe.
21. retrieve_facts(category: str = "facts" | "preferences") - Retrieves saved facts/preferences from persistent memory. Permission: safe.
22. forget_fact(identifier: str | int) - Deletes a memory by id (int) or content match (str). Permission: safe.
23. open_app(app_name: str) - Opens a macOS application. Permission: risky.
24. get_time() - Returns the current system time. Permission: safe.
25. execute_bash(command: str) - Executes a single-shot bash command on the macOS host system within a 30-second timeout. Read-only commands run automatically without prompt. Modifying commands require explicit user approval. Prefer file tools for file manipulation. Permission: conditional.
</memory_and_system_tools>

<subagent_tools>
25. create_subagent(name: str, role: str, allowed_tools: str | null = null, max_turns: int = 10) - Creates a child subagent. Returns agent_id. Permission: safe.
26. delegate_task(agent_id: str, task: str) - Delegates a task to a subagent. The subagent runs independently with its own tools and role. Permission: safe.
27. delete_subagent(agent_id: str) - Removes a subagent after use. Permission: safe.
28. list_subagents() - Lists all active subagents with status. Permission: safe.
</subagent_tools>

<subagent_workflow>
To use subagents:
1. create_subagent to spawn a focused child (e.g., name="reader", role="Read files", allowed_tools="read_file,list_directory")
2. delegate_task to assign work (the subagent runs its own agentic loop)
3. Read the result and continue your workflow
4. delete_subagent when done to free resources
Use subagents for parallel-safe isolated tasks: reading files, running tests, searching patterns.
</subagent_workflow>
</available_tools>

<json_contract>
When executing a tool, you MUST output a single valid JSON Action block enclosed strictly inside <action> and </action> tags.
- The JSON object must contain "tool" and "args" keys.
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
This is a targeted file edit. I should use replace_text with expected_count to avoid broad accidental edits.
</thought>
<action>
{"tool": "replace_text", "args": {"path": "config.py", "old": "DEBUG = True", "new": "DEBUG = False", "expected_count": 1}}
</action>
</example>

<example>
Input: Delete old_output.txt
<thought>
Deleting is permanent and risky, so this will require user confirmation.
</thought>
<action>
{"tool": "delete_file", "args": {"path": "old_output.txt"}}
</action>
</example>

<example>
Input: What's the latest tech news?
<thought>
The user is asking for recent tech news. I should formulate a broad search query to fetch the latest technology headlines.
</thought>
<action>
{"tool": "search_web", "args": {"query": "latest technology news headlines today"}}
</action>
</example>

<example>
Input: Compile the typescript project and list its build outputs
<thought>
The user wants to compile the project. This is not a file manipulation task, so execute_bash is appropriate.
</thought>
<action>
{"tool": "execute_bash", "args": {"command": "npm run build && ls -la dist"}}
</action>
</example>
</examples>

<evidence_handling>
- For web answers, use the structured evidence returned by search_web.
- Cite sources and URLs when they are present.
- If the evidence says confidence is low or partial, state that clearly instead of guessing.
</evidence_handling>"""

def execute_react_tool(action_dict: dict) -> str:
    """Execute a ReAct-style JSON action from the local orchestrator."""
    if "research_query" in action_dict:
        query = action_dict["research_query"].get("query", "")
        max_sources = action_dict["research_query"].get("max_sources", 8)
        # results = research_query(query, max_sources)
        return research_query(query, max_sources)
        # return json.dumps(results)
    
    if "search_web" in action_dict:
        query = action_dict["search_web"].get("query", "")
        # results = search_searxng(query)
        # return json.dumps(results)
        return search_web(query)

    if "fetch_url" in action_dict:
        url = action_dict["fetch_url"].get("url", "")
        return fetch_url_content_mvp(url)

    if "browse_url" in action_dict:
        url = action_dict["browse_url"].get("url", "")
        return browse_url(url)

    if "finish" in action_dict:
        return action_dict["finish"].get("answer", "")

    return "Error: Unknown tool."

def execute_tool(
    llm_response: str,
    confirm_tool: Callable[[str, dict[str, Any], str], bool] | None = None,
) -> str | None:
    # call_data = extract_json(llm_response)
    call_data = extract_json(llm_response)

    if not isinstance(call_data, dict) or "tool" not in call_data:
        return None

    tool_name = call_data.get("tool")
    args = call_data.get("args", {})

    if tool_name in AVAILABLE_TOOLS:
        try:
            tool = AVAILABLE_TOOLS[tool_name]
            
            # Dynamic permission check for execute_bash
            permission = tool.permission
            if tool_name == "execute_bash":
                from tools.bash_ops import is_command_safe
                if is_command_safe(args.get("command", "")):
                    permission = "safe"
                else:
                    permission = "risky"

            if permission == "risky":
                if confirm_tool is None:
                    return f"Tool '{tool_name}' needs confirmation before it can run."
                if not confirm_tool(tool_name, args, permission):
                    return f"Tool '{tool_name}' was cancelled by the user."

            result = tool.function(**args)
            return f"Tool '{tool_name}' executed successfully. Result: {result}"
        except Exception as e:
            return f"Error executing tool '{tool_name}': {e}"

    return f"Tool '{tool_name}' is not available."
