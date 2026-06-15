from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from core.subagent import SubAgent, SubAgentStatus, AgentRegistry
from core.llm import AgenticLoop

logger = logging.getLogger(__name__)


class SubAgentManager:
    def __init__(self, registry: AgentRegistry | None = None) -> None:
        self.registry = registry or AgentRegistry()

    def create_agent(
        self,
        name: str,
        role: str,
        parent_id: str | None = None,
        max_turns: int = 10,
        allowed_tools: set[str] | None = None,
        system_prompt_override: str | None = None,
    ) -> SubAgent:
        agent = SubAgent(
            name=name,
            role=role,
            parent_id=parent_id,
            max_turns=max_turns,
            allowed_tools=allowed_tools,
            system_prompt_override=system_prompt_override,
        )
        self.registry.register(agent)
        logger.info(f"Created subagent '{name}' (id={agent.agent_id})")
        return agent

    def get_agent(self, agent_id: str) -> SubAgent | None:
        return self.registry.get(agent_id)

    def list_agents(self) -> list[SubAgent]:
        return self.registry.list_all()

    def delete_agent(self, agent_id: str) -> None:
        agent = self.registry.get(agent_id)
        if agent is None:
            raise KeyError(f"Agent '{agent_id}' not found")
        self.registry.remove(agent_id)
        logger.info(f"Deleted subagent '{agent.name}' (id={agent_id})")

    def terminate_agent(self, agent_id: str) -> None:
        agent = self.registry.get(agent_id)
        if agent is None:
            raise KeyError(f"Agent '{agent_id}' not found")
        agent.status = SubAgentStatus.TERMINATED
        logger.info(f"Terminated subagent '{agent.name}' (id={agent_id})")

    def cleanup_completed(self) -> list[str]:
        removed = []
        for agent in self.registry.list_all():
            if agent.status in (SubAgentStatus.COMPLETED, SubAgentStatus.FAILED, SubAgentStatus.TERMINATED):
                self.registry.remove(agent.agent_id)
                removed.append(agent.agent_id)
                logger.info(f"Cleaned up subagent '{agent.name}' (id={agent.agent_id})")
        return removed

    def get_children(self, parent_id: str) -> list[SubAgent]:
        return self.registry.list_children(parent_id)

    def _build_system_prompt(self, agent: SubAgent, task: str) -> str:
        if agent.system_prompt_override:
            return agent.system_prompt_override

        tool_constraint = ""
        if agent.allowed_tools:
            tool_list = ", ".join(sorted(agent.allowed_tools))
            tool_constraint = f"\nYou may ONLY use these tools: {tool_list}."

        return (
            f"You are a subagent named '{agent.name}'.\n"
            f"Your role: {agent.role}\n"
            f"Task: {task}\n"
            f"Work within {agent.max_turns} tool turns. "
            f"Be focused and precise.{tool_constraint}\n"
        )

    def _wrap_execute_tool(
        self,
        execute_tool_call: Callable[..., str | None],
        agent: SubAgent,
    ) -> Callable[..., str | None]:
        def wrapped(
            action: dict[str, Any],
            confirm_tool: Callable[[str, dict[str, Any], str], bool] | None = None,
        ) -> str | None:
            tool_name = str(action.get("tool", "unknown"))
            if agent.allowed_tools and tool_name not in agent.allowed_tools:
                return f"Tool '{tool_name}' is not allowed for this subagent. Allowed: {', '.join(sorted(agent.allowed_tools))}"
            return execute_tool_call(action, confirm_tool=confirm_tool)
        return wrapped

    def run_agent(
        self,
        agent_id: str,
        task: str,
        ask_model: Callable[[list[dict[str, str]]], str],
        execute_tool_call: Callable[..., str | None],
        confirm_tool: Callable[[str, dict[str, Any], str], bool] | None = None,
    ) -> str:
        agent = self.registry.get(agent_id)
        if agent is None:
            raise KeyError(f"Agent '{agent_id}' not found")

        agent.status = SubAgentStatus.RUNNING

        try:
            system_prompt = self._build_system_prompt(agent, task)
            wrapped_execute = self._wrap_execute_tool(execute_tool_call, agent)

            loop = AgenticLoop(
                ask_model=ask_model,
                execute_tool_call=wrapped_execute,
                max_turns=agent.max_turns,
            )
            result = loop.run(
                system_prompt=system_prompt,
                user_prompt=task,
                confirm_tool=confirm_tool,
            )

            agent.status = SubAgentStatus.COMPLETED
            agent.result = result.final_answer
            return result.final_answer

        except Exception:
            agent.status = SubAgentStatus.FAILED
            raise


__all__ = ["SubAgentManager"]
