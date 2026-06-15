from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from core.subagent import SubAgent, SubAgentStatus, AgentRegistry
from core.subagent_manager import SubAgentManager
from tools.subagent_tools import (
    create_subagent,
    delegate_task,
    delete_subagent,
    list_subagents,
    _get_manager,
    _set_manager,
)


class SubagentToolsTests(unittest.TestCase):
    def setUp(self):
        self.registry = AgentRegistry()
        self.manager = SubAgentManager(registry=self.registry)
        _set_manager(self.manager)

    def tearDown(self):
        _set_manager(None)

    def test_create_subagent_tool(self):
        result = create_subagent(name="reader", role="Read and summarize files")
        self.assertIn("reader", result)
        self.assertIn("created", result.lower())
        agents = self.registry.list_all()
        self.assertEqual(len(agents), 1)
        self.assertEqual(agents[0].name, "reader")

    def test_create_subagent_with_allowed_tools(self):
        result = create_subagent(
            name="tester",
            role="Run tests",
            allowed_tools="read_file,execute_bash,list_directory",
        )
        self.assertIn("tester", result)
        agent = self.registry.find_by_name("tester")
        self.assertIsNotNone(agent)
        self.assertEqual(agent.allowed_tools, {"read_file", "execute_bash", "list_directory"})

    def test_create_subagent_duplicate_name(self):
        create_subagent(name="reader", role="role1")
        result = create_subagent(name="reader", role="role2")
        # Should still work — names aren't unique, agent_ids are
        self.assertIn("reader", result)
        self.assertEqual(len(self.registry.list_all()), 2)

    def test_list_subagents_empty(self):
        result = list_subagents()
        self.assertIn("No subagents", result)

    def test_list_subagents_with_agents(self):
        create_subagent(name="a", role="role a")
        create_subagent(name="b", role="role b")
        result = list_subagents()
        self.assertIn("a", result)
        self.assertIn("b", result)

    def test_delete_subagent(self):
        create_subagent(name="temp", role="temporary")
        agent = self.registry.find_by_name("temp")
        self.assertIsNotNone(agent)

        result = delete_subagent(agent_id=agent.agent_id)
        self.assertIn("deleted", result.lower())
        self.assertIsNone(self.registry.get(agent.agent_id))

    def test_delete_nonexistent_subagent(self):
        result = delete_subagent(agent_id="nonexistent")
        self.assertIn("not found", result.lower())

    def test_delegate_task(self):
        create_subagent(name="reader", role="read files")
        agent = self.registry.find_by_name("reader")

        mock_loop = MagicMock()
        mock_loop.run.return_value = MagicMock(
            final_answer="File contains hello world",
            stop_reason="final",
            tools_used=["read_file"],
            observations=["obs"],
        )

        with patch("core.subagent_manager.AgenticLoop", return_value=mock_loop):
            result = delegate_task(
                agent_id=agent.agent_id,
                task="Read README.md",
            )

        self.assertIn("File contains hello world", result)
        self.assertEqual(agent.status, SubAgentStatus.COMPLETED)

    def test_delegate_task_nonexistent_agent(self):
        result = delegate_task(agent_id="nonexistent", task="do stuff")
        self.assertIn("not found", result.lower())

    def test_list_subagents_shows_status(self):
        create_subagent(name="w", role="work")
        agent = self.registry.find_by_name("w")
        agent.status = SubAgentStatus.RUNNING
        result = list_subagents()
        self.assertIn("running", result)


if __name__ == "__main__":
    unittest.main()
