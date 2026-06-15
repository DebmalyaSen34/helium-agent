import unittest
from unittest.mock import MagicMock, patch

from core.subagent import SubAgent, SubAgentStatus, AgentRegistry
from core.subagent_manager import SubAgentManager


class SubAgentManagerTests(unittest.TestCase):
    def setUp(self):
        self.registry = AgentRegistry()
        self.manager = SubAgentManager(registry=self.registry)

    def test_create_subagent(self):
        agent = self.manager.create_agent(
            name="reader",
            role="Read and summarize files",
        )
        self.assertEqual(agent.name, "reader")
        self.assertEqual(agent.role, "Read and summarize files")
        self.assertEqual(agent.status, SubAgentStatus.IDLE)
        self.assertIsNotNone(self.registry.get(agent.agent_id))

    def test_create_subagent_with_parent(self):
        parent = self.manager.create_agent(name="parent", role="coordinator")
        child = self.manager.create_agent(
            name="child",
            role="worker",
            parent_id=parent.agent_id,
        )
        self.assertEqual(child.parent_id, parent.agent_id)

    def test_create_subagent_with_allowed_tools(self):
        agent = self.manager.create_agent(
            name="reader",
            role="read files",
            allowed_tools={"read_file", "list_directory"},
        )
        self.assertEqual(agent.allowed_tools, {"read_file", "list_directory"})

    def test_delete_agent(self):
        agent = self.manager.create_agent(name="temp", role="temporary")
        agent_id = agent.agent_id
        self.manager.delete_agent(agent_id)
        self.assertIsNone(self.registry.get(agent_id))

    def test_delete_nonexistent_raises(self):
        with self.assertRaises(KeyError):
            self.manager.delete_agent("nonexistent")

    def test_get_agent(self):
        agent = self.manager.create_agent(name="x", role="y")
        self.assertIs(self.manager.get_agent(agent.agent_id), agent)

    def test_list_agents(self):
        self.manager.create_agent(name="a", role="r1")
        self.manager.create_agent(name="b", role="r2")
        self.assertEqual(len(self.manager.list_agents()), 2)

    def test_run_subagent_calls_agentic_loop(self):
        agent = self.manager.create_agent(name="reader", role="read files")

        mock_loop = MagicMock()
        mock_loop.run.return_value = MagicMock(
            final_answer="file contents here",
            stop_reason="final",
            tools_used=["read_file"],
            observations=["obs1"],
        )

        with patch("core.subagent_manager.AgenticLoop", return_value=mock_loop):
            result = self.manager.run_agent(
                agent_id=agent.agent_id,
                task="Read README.md",
                ask_model=MagicMock(),
                execute_tool_call=MagicMock(),
            )

        self.assertEqual(result, "file contents here")
        self.assertEqual(agent.status, SubAgentStatus.COMPLETED)
        self.assertEqual(agent.result, "file contents here")
        mock_loop.run.assert_called_once()

    def test_run_subagent_sets_running_status(self):
        agent = self.manager.create_agent(name="worker", role="work")

        mock_loop = MagicMock()
        mock_loop.run.return_value = MagicMock(
            final_answer="done",
            stop_reason="final",
            tools_used=[],
            observations=[],
        )

        with patch("core.subagent_manager.AgenticLoop", return_value=mock_loop):
            self.manager.run_agent(
                agent_id=agent.agent_id,
                task="do something",
                ask_model=MagicMock(),
                execute_tool_call=MagicMock(),
            )

        self.assertEqual(agent.status, SubAgentStatus.COMPLETED)

    def test_run_nonexistent_agent_raises(self):
        with self.assertRaises(KeyError):
            self.manager.run_agent(
                agent_id="nonexistent",
                task="x",
                ask_model=MagicMock(),
                execute_tool_call=MagicMock(),
            )

    def test_run_agent_with_tool_filtering(self):
        agent = self.manager.create_agent(
            name="reader",
            role="read only",
            allowed_tools={"read_file", "list_directory"},
        )

        captured_execute = None

        mock_loop = MagicMock()
        mock_loop.run.return_value = MagicMock(
            final_answer="ok",
            stop_reason="final",
            tools_used=[],
            observations=[],
        )

        def capture_loop(ask_model, execute_tool_call, max_turns):
            nonlocal captured_execute
            captured_execute = execute_tool_call
            return mock_loop

        with patch("core.subagent_manager.AgenticLoop", side_effect=capture_loop):
            self.manager.run_agent(
                agent_id=agent.agent_id,
                task="read files",
                ask_model=MagicMock(),
                execute_tool_call=MagicMock(),
            )

        self.assertIsNotNone(captured_execute)

    def test_terminate_agent(self):
        agent = self.manager.create_agent(name="x", role="y")
        agent.status = SubAgentStatus.RUNNING
        self.manager.terminate_agent(agent.agent_id)
        self.assertEqual(agent.status, SubAgentStatus.TERMINATED)

    def test_cleanup_completed_agents(self):
        a1 = self.manager.create_agent(name="a", role="r1")
        a2 = self.manager.create_agent(name="b", role="r2")
        a3 = self.manager.create_agent(name="c", role="r3")

        a1.status = SubAgentStatus.COMPLETED
        a2.status = SubAgentStatus.RUNNING
        a3.status = SubAgentStatus.FAILED

        removed = self.manager.cleanup_completed()
        self.assertIn(a1.agent_id, removed)
        self.assertIn(a3.agent_id, removed)
        self.assertNotIn(a2.agent_id, removed)
        self.assertIsNone(self.registry.get(a1.agent_id))
        self.assertIsNotNone(self.registry.get(a2.agent_id))

    def test_get_children(self):
        parent = self.manager.create_agent(name="parent", role="coord")
        c1 = self.manager.create_agent(name="c1", role="r1", parent_id=parent.agent_id)
        c2 = self.manager.create_agent(name="c2", role="r2", parent_id=parent.agent_id)

        children = self.manager.get_children(parent.agent_id)
        self.assertEqual(len(children), 2)


if __name__ == "__main__":
    unittest.main()
