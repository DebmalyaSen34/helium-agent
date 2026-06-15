import unittest
from core.subagent import SubAgent, SubAgentStatus, AgentRegistry


class SubAgentTests(unittest.TestCase):
    def test_subagent_creation_with_defaults(self):
        agent = SubAgent(name="reader", role="Read and summarize files")
        self.assertEqual(agent.name, "reader")
        self.assertEqual(agent.role, "Read and summarize files")
        self.assertEqual(agent.status, SubAgentStatus.IDLE)
        self.assertIsNone(agent.parent_id)
        self.assertEqual(agent.max_turns, 10)
        self.assertIsNone(agent.allowed_tools)
        self.assertIsNotNone(agent.agent_id)
        self.assertIsNotNone(agent.created_at)

    def test_subagent_creation_with_custom_config(self):
        agent = SubAgent(
            name="tester",
            role="Run tests",
            max_turns=5,
            allowed_tools={"read_file", "execute_bash", "list_directory"},
        )
        self.assertEqual(agent.max_turns, 5)
        self.assertEqual(agent.allowed_tools, {"read_file", "execute_bash", "list_directory"})

class AgentRegistryTests(unittest.TestCase):
    def test_register_and_get(self):
        registry = AgentRegistry()
        agent = SubAgent(name="reader", role="Read files")
        registry.register(agent)
        retrieved = registry.get(agent.agent_id)
        self.assertIs(retrieved, agent)

    def test_get_nonexistent_returns_none(self):
        registry = AgentRegistry()
        self.assertIsNone(registry.get("nonexistent-id"))

    def test_list_all_agents(self):
        registry = AgentRegistry()
        a1 = SubAgent(name="a", role="role a")
        a2 = SubAgent(name="b", role="role b")
        registry.register(a1)
        registry.register(a2)
        agents = registry.list_all()
        self.assertEqual(len(agents), 2)
        self.assertIn(a1, agents)
        self.assertIn(a2, agents)

    def test_list_empty_registry(self):
        registry = AgentRegistry()
        self.assertEqual(registry.list_all(), [])

    def test_remove_agent(self):
        registry = AgentRegistry()
        agent = SubAgent(name="temp", role="temporary")
        registry.register(agent)
        self.assertIsNotNone(registry.get(agent.agent_id))

        registry.remove(agent.agent_id)
        self.assertIsNone(registry.get(agent.agent_id))

    def test_remove_nonexistent_raises(self):
        registry = AgentRegistry()
        with self.assertRaises(KeyError):
            registry.remove("nonexistent-id")

    def test_find_by_name(self):
        registry = AgentRegistry()
        a1 = SubAgent(name="reader", role="Read files")
        a2 = SubAgent(name="writer", role="Write files")
        registry.register(a1)
        registry.register(a2)

        found = registry.find_by_name("reader")
        self.assertIs(found, a1)

    def test_find_by_name_not_found(self):
        registry = AgentRegistry()
        self.assertIsNone(registry.find_by_name("ghost"))

    def test_agent_id_uniqueness(self):
        a1 = SubAgent(name="a", role="r")
        a2 = SubAgent(name="a", role="r")
        self.assertNotEqual(a1.agent_id, a2.agent_id)

    def test_parent_id_tracking(self):
        registry = AgentRegistry()
        parent = SubAgent(name="parent", role="coordinator")
        child = SubAgent(name="child", role="worker", parent_id=parent.agent_id)
        registry.register(parent)
        registry.register(child)

        self.assertEqual(child.parent_id, parent.agent_id)

    def test_list_children(self):
        registry = AgentRegistry()
        parent = SubAgent(name="parent", role="coordinator")
        child1 = SubAgent(name="c1", role="r1", parent_id=parent.agent_id)
        child2 = SubAgent(name="c2", role="r2", parent_id=parent.agent_id)
        orphan = SubAgent(name="orphan", role="r3")
        registry.register(parent)
        registry.register(child1)
        registry.register(child2)
        registry.register(orphan)

        children = registry.list_children(parent.agent_id)
        self.assertEqual(len(children), 2)
        self.assertIn(child1, children)
        self.assertIn(child2, children)
        self.assertNotIn(orphan, children)


if __name__ == "__main__":
    unittest.main()
