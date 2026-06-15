from __future__ import annotations

from core.subagent_manager import SubAgentManager

_manager: SubAgentManager | None = None


def _get_manager() -> SubAgentManager:
    global _manager
    if _manager is None:
        _manager = SubAgentManager()
    return _manager


def _set_manager(manager: SubAgentManager | None) -> None:
    global _manager
    _manager = manager


def create_subagent(
    name: str,
    role: str,
    allowed_tools: str | None = None,
    max_turns: int = 10,
) -> str:
    """Create a new subagent with a name, role, and optional tool restrictions."""
    manager = _get_manager()

    tool_set = None
    if allowed_tools:
        tool_set = {t.strip() for t in allowed_tools.split(",") if t.strip()}

    agent = manager.create_agent(
        name=name,
        role=role,
        allowed_tools=tool_set,
        max_turns=max_turns,
    )
    return f"Subagent '{name}' created (id={agent.agent_id}, role={role})."


def delegate_task(
    agent_id: str,
    task: str,
) -> str:
    """Delegate a task to an existing subagent by its agent_id."""
    manager = _get_manager()

    agent = manager.get_agent(agent_id)
    if agent is None:
        return f"Subagent with id '{agent_id}' not found."

    from core.llm import call_llm_once, execute_agent_tool

    def ask_model(messages):
        reply, _ = call_llm_once(messages)
        return reply

    try:
        result = manager.run_agent(
            agent_id=agent_id,
            task=task,
            ask_model=ask_model,
            execute_tool_call=execute_agent_tool,
        )
        return f"Subagent '{agent.name}' completed task. Result:\n{result}"
    except Exception as e:
        return f"Subagent '{agent.name}' failed: {e}"


def delete_subagent(agent_id: str) -> str:
    """Delete a subagent by its agent_id."""
    manager = _get_manager()
    agent = manager.get_agent(agent_id)
    if agent is None:
        return f"Subagent with id '{agent_id}' not found."
    name = agent.name
    manager.delete_agent(agent_id)
    return f"Subagent '{name}' (id={agent_id}) deleted."


def list_subagents() -> str:
    """List all active subagents and their statuses."""
    manager = _get_manager()
    agents = manager.list_agents()
    if not agents:
        return "No subagents registered."

    lines = ["Active subagents:"]
    for agent in agents:
        children = manager.get_children(agent.agent_id)
        child_info = f" ({len(children)} children)" if children else ""
        lines.append(
            f"  - {agent.name} (id={agent.agent_id}) "
            f"[{agent.status.value}]{child_info}: {agent.role}"
        )
    return "\n".join(lines)


__all__ = [
    "create_subagent",
    "delegate_task",
    "delete_subagent",
    "list_subagents",
]
