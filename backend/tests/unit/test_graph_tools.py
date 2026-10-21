"""Unit tests verifying user ID resolution, hops coercion, and entity validation in graph_tools.py.

Ensures that:
1. _resolve_uid checks both nested configurable.get('user_id') and top-level cfg.get('user_id'),
   preventing failure when configurable is None or user_id is passed at the top level.
2. String hops inputs (e.g. hops="2") are coerced to int and clamped to [1, 2],
   preventing downstream TypeError comparisons.
3. Blank or None entity names return immediate descriptive validation errors.
"""

import sys
import unittest
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock

# Ensure scratch workspace is on sys.path
TEST_DIR = Path(__file__).resolve().parent
if str(TEST_DIR) not in sys.path:
    sys.path.insert(0, str(TEST_DIR))

# Create dummy modules for imports if not present
for mod_name in [
    "langchain_core", "langchain_core.tools", "langchain_core.runnables",
    "utils", "utils.log_sanitizer", "utils.memory", "utils.memory.kg_graph_traversal",
    "utils.retrieval", "utils.retrieval.agentic"
]:
    if mod_name not in sys.modules:
        m = ModuleType(mod_name)
        sys.modules[mod_name] = m

sys.modules["langchain_core.tools"].tool = lambda f: f
sys.modules["langchain_core.runnables"].RunnableConfig = dict
sys.modules["utils.log_sanitizer"].sanitize = lambda s: str(s)
sys.modules["utils.memory.kg_graph_traversal"].traverse_knowledge_graph = MagicMock(return_value={"nodes": ["A", "B"]})
sys.modules["utils.memory.kg_graph_traversal"].format_traversal_result = MagicMock(return_value="Connected Subgraph: A -> B")

from graph_tools import _resolve_uid, traverse_knowledge_graph_tool


class TestGraphToolsHardening(unittest.TestCase):
    """Test user_id resolution, hops coercion, and entity validation."""

    def test_resolve_uid_nested(self):
        cfg = {"configurable": {"user_id": "nested_user_123"}}
        self.assertEqual(_resolve_uid(cfg), "nested_user_123")

    def test_resolve_uid_top_level(self):
        cfg = {"user_id": "top_level_user_456"}
        self.assertEqual(_resolve_uid(cfg), "top_level_user_456")

    def test_resolve_uid_none_configurable_with_fallback(self):
        cfg = {"configurable": None, "user_id": "fallback_user_789"}
        self.assertEqual(_resolve_uid(cfg), "fallback_user_789")

    def test_resolve_uid_missing(self):
        self.assertIsNone(_resolve_uid(None))
        self.assertIsNone(_resolve_uid({}))
        self.assertIsNone(_resolve_uid({"configurable": {}}))

    def test_entity_validation_empty_or_none(self):
        cfg = {"user_id": "test_user"}
        self.assertEqual(
            traverse_knowledge_graph_tool(None, config=cfg),
            "Error: Entity name must not be empty"
        )
        self.assertEqual(
            traverse_knowledge_graph_tool("", config=cfg),
            "Error: Entity name must not be empty"
        )
        self.assertEqual(
            traverse_knowledge_graph_tool("   ", config=cfg),
            "Error: Entity name must not be empty"
        )

    def test_hops_coercion_string_input(self):
        cfg = {"user_id": "test_user"}
        mock_traverse = sys.modules["utils.memory.kg_graph_traversal"].traverse_knowledge_graph
        mock_traverse.reset_mock()

        # String hops="2" coerced to integer 2
        res = traverse_knowledge_graph_tool("Apple", hops="2", config=cfg)
        self.assertIn("Connected Subgraph", res)
        mock_traverse.assert_called_once_with("test_user", "Apple", hops=2)

    def test_hops_clamping_bounds(self):
        cfg = {"user_id": "test_user"}
        mock_traverse = sys.modules["utils.memory.kg_graph_traversal"].traverse_knowledge_graph
        mock_traverse.reset_mock()

        # hops > 2 clamped to 2
        traverse_knowledge_graph_tool("ProjectX", hops=5, config=cfg)
        mock_traverse.assert_called_with("test_user", "ProjectX", hops=2)

        # hops < 1 clamped to 1
        traverse_knowledge_graph_tool("ProjectX", hops=-3, config=cfg)
        mock_traverse.assert_called_with("test_user", "ProjectX", hops=1)


if __name__ == "__main__":
    unittest.main()
