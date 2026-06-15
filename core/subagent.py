from __future__ import annotations

from uuid import uuid4
import time
from dataclasses import dataclass, field
from enum import Enum


class SubAgentStatus(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    TERMINATED = "terminated"


@dataclass
class SubAgent:
    name: str
    role: str
    agent_id: str = field(default_factory=lambda: uuid4().hex[:12])
    status: SubAgentStatus = SubAgentStatus.IDLE
    parent_id: str | None = None
    max_turns: int = 10
    allowed_tools: set[str] | None = None
    system_prompt_override: str | None = None
    created_at: float = field(default_factory=time.time)
    result: str | None = None


class AgentRegistry:
    def __init__(self) -> None:
        self._agents: dict[str, SubAgent] = {}

    def register(self, agent: SubAgent) -> None:
        self._agents[agent.agent_id] = agent

    def get(self, agent_id: str) -> SubAgent | None:
        return self._agents.get(agent_id)

    def list_all(self) -> list[SubAgent]:
        return list(self._agents.values())

    def remove(self, agent_id: str) -> None:
        if agent_id not in self._agents:
            raise KeyError(f"Agent '{agent_id}' not found")
        del self._agents[agent_id]

    def find_by_name(self, name: str) -> SubAgent | None:
        for agent in self._agents.values():
            if agent.name == name:
                return agent
        return None

    def list_children(self, parent_id: str) -> list[SubAgent]:
        return [a for a in self._agents.values() if a.parent_id == parent_id]


__all__ = ["SubAgent", "SubAgentStatus", "AgentRegistry"]
