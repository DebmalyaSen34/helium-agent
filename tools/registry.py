from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import json
from typing import Any

from tools.memory_ops import remember_fact, retrieve_facts
from tools.system_ops import open_app, get_time
from tools.file_ops import create_file
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


AVAILABLE_TOOLS = {
    "create_file": ToolDefinition(create_file, "Creates or overwrites a file in the current project.", "risky"),
    "search_web": ToolDefinition(search_web, "Searches the web and returns structured evidence with sources.", "safe"),
    "research_query": ToolDefinition(research_query, "Researches complex analytical questions using multiple searches and citations.", "safe"),
    "remember_fact": ToolDefinition(remember_fact, "Saves a user fact or preference into long-term memory.", "safe"),
    "retrieve_facts": ToolDefinition(retrieve_facts, "Retrieves saved facts and preferences.", "safe"),
    "open_app": ToolDefinition(open_app, "Opens a macOS application.", "risky"),
    "get_time": ToolDefinition(get_time, "Returns the current system time.", "safe"),
    "browse_url": ToolDefinition(browse_url, "Navigates to a specific website, executes JavaScript using Playwright, and extracts clean, readable text.", "safe"),
    "execute_bash": ToolDefinition(execute_bash, "Executes a single-shot bash command on the macOS host system within a 30-second timeout. For sequential dependent steps (like navigating directories), chain commands using &&.", "risky")
}

TOOL_PROMPT = """<available_tools>
1. create_file(filename: str, content: str) - Creates or overwrites a file in the project. Permission: risky (user confirmation required).
2. search_web(query: str, num_results: int = 5) - Searches the web and returns structured evidence.
   CRITICAL SEARCH RULES:
   - Use IMMEDIATELY for news, facts, scores, or any knowledge beyond your cutoff data.
   - Do NOT ask user to clarify broad requests. Invent a smart query and search immediately.
   - Extract exact facts (e.g. "Team X won 3-0"). Do NOT describe the articles.
3. research_query(query: str, max_sources: int = 8) - Researches complex analytical questions using multiple searches. Permission: safe.
   - Use for comparisons, detailed reports, market trends, policies, or complex why/how queries.
4. remember_fact(fact: str, category: str = "facts" | "preferences") - Saves a user fact/preference into long-term memory. Permission: safe.
5. retrieve_facts(category: str = "facts" | "preferences") - Retrieves saved facts/preferences. Permission: safe.
6. open_app(app_name: str) - Opens a macOS application. Permission: risky (user confirmation required).
7. get_time() - Returns the current system time. Permission: safe.
8. browse_url(url: str) - Navigates to a specific website, executes JavaScript using Playwright, and extracts clean, readable text. Use when a specific URL link is provided. Permission: safe.
9. execute_bash(command: str) - Executes a single-shot bash command on the macOS host system within a 30-second timeout. Read-only commands (like ls, cat, git diff) run automatically without prompt. Modifying commands (like rm, touch, python, npm) require explicit user approval. Chain sequential dependent commands using &&. Permission: conditional (automatic for safe read-only queries, risky for system modifications).
</available_tools>

<json_contract>
When executing a tool, you MUST output a single valid JSON Action block enclosed strictly inside <action> and </action> tags.
- The JSON object must contain "tool" and "args" keys.
- You MUST escape all double quotes inside content strings with \".
- Do NOT use raw newlines inside JSON content strings; use the literal characters \n instead.
</json_contract>

<examples>
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
Input: Write a hello world Python script in hello.py
<thought>
Writing a simple Python script as requested. This requires creating a file hello.py with the print statement content.
</thought>
<action>
{"tool": "create_file", "args": {"filename": "hello.py", "content": "print(\"Hello, World!\")\n"}}
</action>
</example>

<example>
Input: Compile the typescript project and list its build outputs
<thought>
The user wants to compile the typescript project and list build outputs. This requires chaining commands: compiling with tsc, then listing the contents of the dist folder using bash.
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
