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

    def test_delegate_task_exception_returns_error(self):
        create_subagent(name="reader", role="read files")
        agent = self.registry.find_by_name("reader")

        with patch("core.subagent_manager.AgenticLoop") as mock_cls:
            mock_cls.return_value.run.side_effect = RuntimeError("LLM timeout")
            result = delegate_task(
                agent_id=agent.agent_id,
                task="Read README.md",
            )

        self.assertIn("failed", result.lower())
        self.assertIn("LLM timeout", result)

    def test_list_subagents_shows_status(self):
        create_subagent(name="w", role="work")
        agent = self.registry.find_by_name("w")
        agent.status = SubAgentStatus.RUNNING
        result = list_subagents()
        self.assertIn("running", result)


class SubagentIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.registry = AgentRegistry()
        self.manager = SubAgentManager(registry=self.registry)
        _set_manager(self.manager)

    def tearDown(self):
        _set_manager(None)

    def test_full_lifecycle_create_delegate_delete(self):
        """End-to-end: create agent, delegate task, verify result, delete."""
        # Step 1: Create
        create_result = create_subagent(name="reader", role="Read files")
        self.assertIn("created", create_result.lower())

        agent = self.registry.find_by_name("reader")
        self.assertIsNotNone(agent)
        self.assertEqual(agent.status, SubAgentStatus.IDLE)

        # Step 2: Delegate
        mock_loop = MagicMock()
        mock_loop.run.return_value = MagicMock(
            final_answer="README: Helium Agent is a terminal AI agent.",
            stop_reason="final",
            tools_used=["read_file"],
            observations=["file contents"],
        )

        with patch("core.subagent_manager.AgenticLoop", return_value=mock_loop):
            delegate_result = delegate_task(
                agent_id=agent.agent_id,
                task="Read and summarize README.md",
            )

        self.assertIn("README", delegate_result)
        self.assertEqual(agent.status, SubAgentStatus.COMPLETED)

        # Step 3: List
        list_result = list_subagents()
        self.assertIn("reader", list_result)
        self.assertIn("completed", list_result)

        # Step 4: Delete
        delete_result = delete_subagent(agent_id=agent.agent_id)
        self.assertIn("deleted", delete_result.lower())
        self.assertIsNone(self.registry.get(agent.agent_id))

        # Step 5: Verify empty
        final_list = list_subagents()
        self.assertIn("No subagents", final_list)

    def test_create_multiple_subagents_and_list(self):
        create_subagent(name="reader", role="Read files")
        create_subagent(name="writer", role="Write code")
        create_subagent(name="tester", role="Run tests")

        result = list_subagents()
        self.assertIn("reader", result)
        self.assertIn("writer", result)
        self.assertIn("tester", result)

        self.assertEqual(len(self.registry.list_all()), 3)

    def test_delegate_to_multiple_agents_sequentially(self):
        create_subagent(name="a", role="task a")
        create_subagent(name="b", role="task b")

        agent_a = self.registry.find_by_name("a")
        agent_b = self.registry.find_by_name("b")

        mock_loop_a = MagicMock()
        mock_loop_a.run.return_value = MagicMock(
            final_answer="result from a",
            stop_reason="final",
            tools_used=[],
            observations=[],
        )

        mock_loop_b = MagicMock()
        mock_loop_b.run.return_value = MagicMock(
            final_answer="result from b",
            stop_reason="final",
            tools_used=[],
            observations=[],
        )

        with patch("core.subagent_manager.AgenticLoop", return_value=mock_loop_a):
            result_a = delegate_task(agent_id=agent_a.agent_id, task="do task a")

        with patch("core.subagent_manager.AgenticLoop", return_value=mock_loop_b):
            result_b = delegate_task(agent_id=agent_b.agent_id, task="do task b")

        self.assertIn("result from a", result_a)
        self.assertIn("result from b", result_b)
        self.assertEqual(agent_a.status, SubAgentStatus.COMPLETED)
        self.assertEqual(agent_b.status, SubAgentStatus.COMPLETED)

    def test_cleanup_removes_finished_agents(self):
        create_subagent(name="a", role="r1")
        create_subagent(name="b", role="r2")
        create_subagent(name="c", role="r3")

        a = self.registry.find_by_name("a")
        b = self.registry.find_by_name("b")
        c = self.registry.find_by_name("c")

        a.status = SubAgentStatus.COMPLETED
        b.status = SubAgentStatus.RUNNING
        c.status = SubAgentStatus.FAILED

        removed = self.manager.cleanup_completed()
        self.assertEqual(len(removed), 2)
        self.assertIn(a.agent_id, removed)
        self.assertIn(c.agent_id, removed)
        self.assertIsNotNone(self.registry.get(b.agent_id))


if __name__ == "__main__":
    unittest.main()
