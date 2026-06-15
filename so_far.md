# Session Log

## Subagent System (2026-06-15)

Added creation, delegation, deletion, and maintenance of subagents for coding workflows.

### New files
- `core/subagent.py` — `SubAgent` dataclass (name, role, status, allowed_tools, parent_id), `SubAgentStatus` enum, `AgentRegistry` (register/get/list/remove/find_by_name/list_children)
- `core/subagent_manager.py` — `SubAgentManager` orchestrating lifecycle (create/run/delete/terminate/cleanup), tool filtering per agent, system prompt generation
- `tools/subagent_tools.py` — LLM-facing tool functions: `create_subagent`, `delegate_task`, `delete_subagent`, `list_subagents`

### Modified files
- `tools/registry.py` — Registered 4 new tools in `AVAILABLE_TOOLS` and `TOOL_PROMPT`; used lazy imports to break circular dependency

### Design decisions
- Subagents reuse `AgenticLoop` — no new execution engine
- Tool filtering is enforced at the `SubAgentManager._wrap_execute_tool` layer
- Names aren't unique (agent_ids are) — allows multiple instances of the same role
- Parent-child tracking via `parent_id` for hierarchical delegation
- `cleanup_completed()` removes COMPLETED/FAILED/TERMINATED agents in bulk
- Lazy imports in `tools/registry.py` to avoid circular import chain
- `SubAgentStatus(str, Enum)` follows `TodoStatus` pattern for JSON-safe serialization
