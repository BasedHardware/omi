from pathlib import Path
import sys
import unittest
from unittest.mock import MagicMock, patch

backend_dir = str(Path(__file__).resolve().parent.parent.parent)
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from testing.import_isolation import AutoMockModule, load_module_fresh, stub_modules


def _fake_tool(fn=None, *args, **kwargs):
    if fn is not None and callable(fn):
        return fn
    def decorator(func):
        return func
    return decorator


class TestGraphToolsSanitization(unittest.TestCase):
    def setUp(self):
        tools_mock = AutoMockModule("langchain_core.tools")
        tools_mock.tool = _fake_tool

        self._stub_cm = stub_modules({
            "langchain_core": AutoMockModule("langchain_core"),
            "langchain_core.tools": tools_mock,
            "langchain_core.runnables": AutoMockModule("langchain_core.runnables"),
            "utils.memory": AutoMockModule("utils.memory"),
            "utils.memory.kg_graph_traversal": AutoMockModule("utils.memory.kg_graph_traversal"),
            "utils.retrieval.agentic": AutoMockModule("utils.retrieval.agentic"),
        })
        self._stub_cm.__enter__()
        tools_path = str(Path(backend_dir) / "utils" / "retrieval" / "tools" / "graph_tools.py")
        self.graph_tools = load_module_fresh("utils.retrieval.tools.graph_tools", tools_path)

    def tearDown(self):
        self._stub_cm.__exit__(None, None, None)

    def test_traverse_knowledge_graph_tool_exception_sanitized(self):
        with patch.object(
            self.graph_tools,
            "traverse_knowledge_graph",
            MagicMock(
                side_effect=RuntimeError("Neo4j Bolt connection error: bolt://neo4j:secret_password@db.internal:7687")
            ),
        ):
            res = self.graph_tools.traverse_knowledge_graph_tool(
                entity="Project Omi",
                hops=1,
                config={"configurable": {"user_id": "u1"}},
            )
            self.assertEqual(res, "Error traversing knowledge graph")
            self.assertNotIn("secret_password", res)
            self.assertNotIn("Neo4j", res)
            self.assertNotIn("bolt://", res)

    def test_traverse_knowledge_graph_tool_success_path(self):
        with (
            patch.object(self.graph_tools, "traverse_knowledge_graph", MagicMock(return_value={"nodes": []})),
            patch.object(
                self.graph_tools, "format_traversal_result", MagicMock(return_value="Connected graph: Project Omi")
            ),
        ):
            res = self.graph_tools.traverse_knowledge_graph_tool(
                entity="Project Omi",
                hops=1,
                config={"configurable": {"user_id": "u1"}},
            )
            self.assertEqual(res, "Connected graph: Project Omi")


if __name__ == "__main__":
    unittest.main()
