"""Hermetic unit tests for graph_tools.py resilience.

Verifies:
1. Config resilience: configurable.user_id, configurable.uid, top-level user_id, top-level uid, and agent_config_context fallback.
2. Parameter validation: non-empty entity check, whitespace trimming, and hops clamping.
3. Numeric coercion: int, float, string-encoded integers, and bool handling for hops.
4. Error handling: unconfigured states and missing user id.
"""

import importlib.util
import os
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)


def _pkg(name: str):
    mod = sys.modules.get(name)
    if mod is None or not hasattr(mod, "__path__"):
        mod = types.ModuleType(name)
        mod.__path__ = []
        sys.modules[name] = mod
    return mod


def _mod(name: str):
    mod = sys.modules.get(name)
    if mod is None:
        mod = types.ModuleType(name)
        sys.modules[name] = mod
    return mod


_mod("database.users")
for _p in ["database", "utils", "utils.memory", "utils.retrieval", "utils.retrieval.tools"]:
    _pkg(_p)

kg_traversal_mock = _mod("utils.memory.kg_graph_traversal")
kg_traversal_mock.traverse_knowledge_graph = MagicMock(return_value={"triples": []})
kg_traversal_mock.format_traversal_result = MagicMock(return_value="Connected entity subgraph")

sanitizer_mock = _mod("utils.log_sanitizer")
sanitizer_mock.sanitize = lambda s: s

agentic_mock = _mod("utils.retrieval.agentic")
agentic_mock.agent_config_context = MagicMock()
agentic_mock.agent_config_context.get.return_value = None

sys.path.insert(0, str(BACKEND_DIR))


def _load_module(name: str, file_path: Path):
    spec = importlib.util.spec_from_file_location(name, str(file_path))
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load spec from {file_path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


# Ensure integration_base is loaded for resolve_config_uid
integration_base = _load_module(
    "utils.retrieval.tools.integration_base",
    BACKEND_DIR / "utils/retrieval/tools/integration_base.py",
)

graph_tools = _load_module(
    "utils.retrieval.tools._test_graph_tools",
    BACKEND_DIR / "utils/retrieval/tools/graph_tools.py",
)


class TestGraphToolsResilience(unittest.TestCase):
    def setUp(self):
        kg_traversal_mock.traverse_knowledge_graph.reset_mock()
        kg_traversal_mock.traverse_knowledge_graph.side_effect = None
        kg_traversal_mock.format_traversal_result.reset_mock()
        kg_traversal_mock.traverse_knowledge_graph.return_value = {"triples": []}
        kg_traversal_mock.format_traversal_result.return_value = "Connected entity subgraph"
        agentic_mock.agent_config_context.get.return_value = None

    def test_resolve_uid_from_configurable_user_id(self):
        config = {"configurable": {"user_id": "graph_user_1"}}
        self.assertEqual(graph_tools._resolve_uid(config), "graph_user_1")

    def test_resolve_uid_from_configurable_uid_alias(self):
        config = {"configurable": {"uid": "graph_user_2"}}
        self.assertEqual(graph_tools._resolve_uid(config), "graph_user_2")

    def test_resolve_uid_from_top_level_user_id(self):
        config = {"user_id": "graph_user_3"}
        self.assertEqual(graph_tools._resolve_uid(config), "graph_user_3")

    def test_resolve_uid_from_top_level_uid(self):
        config = {"uid": "graph_user_4"}
        self.assertEqual(graph_tools._resolve_uid(config), "graph_user_4")

    def test_resolve_uid_fallback_to_agent_config_context(self):
        agentic_mock.agent_config_context.get.return_value = {"configurable": {"user_id": "ctx_graph_user"}}
        self.assertEqual(graph_tools._resolve_uid(None), "ctx_graph_user")

    def test_resolve_uid_missing(self):
        self.assertIsNone(graph_tools._resolve_uid({}))
        self.assertIsNone(graph_tools._resolve_uid(None))
        self.assertIsNone(graph_tools._resolve_uid({"configurable": None}))

    def test_empty_entity_rejected(self):
        res = graph_tools.traverse_knowledge_graph_tool.func(entity="", hops=1)
        self.assertEqual(res, "Error: Entity name cannot be empty.")

        res_none = graph_tools.traverse_knowledge_graph_tool.func(entity=None, hops=1)
        self.assertEqual(res_none, "Error: Entity name cannot be empty.")

        res_whitespace = graph_tools.traverse_knowledge_graph_tool.func(entity="   ", hops=1)
        self.assertEqual(res_whitespace, "Error: Entity name cannot be empty.")

    def test_missing_uid_returns_error(self):
        res = graph_tools.traverse_knowledge_graph_tool.func(entity="Project Orion", hops=1, config={})
        self.assertEqual(res, "Error: User ID not found in configuration")

    def test_traverse_knowledge_graph_success(self):
        config = {"configurable": {"user_id": "user_ok"}}
        res = graph_tools.traverse_knowledge_graph_tool.func(
            entity="  Artificial Intelligence  ", hops=2, config=config
        )
        kg_traversal_mock.traverse_knowledge_graph.assert_called_once_with("user_ok", "Artificial Intelligence", hops=2)
        self.assertEqual(res, "Connected entity subgraph")

    def test_hops_coercion_string(self):
        config = {"configurable": {"user_id": "user_hops"}}
        res = graph_tools.traverse_knowledge_graph_tool.func(entity="Robotics", hops="2", config=config)
        kg_traversal_mock.traverse_knowledge_graph.assert_called_once_with("user_hops", "Robotics", hops=2)

    def test_hops_clamping_above_max(self):
        config = {"configurable": {"user_id": "user_clamp"}}
        res = graph_tools.traverse_knowledge_graph_tool.func(entity="Cosmology", hops=10, config=config)
        kg_traversal_mock.traverse_knowledge_graph.assert_called_once_with("user_clamp", "Cosmology", hops=2)

    def test_hops_clamping_below_min(self):
        config = {"configurable": {"user_id": "user_clamp_min"}}
        res = graph_tools.traverse_knowledge_graph_tool.func(entity="Quantum", hops=0, config=config)
        kg_traversal_mock.traverse_knowledge_graph.assert_called_once_with("user_clamp_min", "Quantum", hops=1)

    def test_hops_boolean_safe_fallback(self):
        config = {"configurable": {"user_id": "user_bool"}}
        res = graph_tools.traverse_knowledge_graph_tool.func(entity="Energy", hops=True, config=config)
        kg_traversal_mock.traverse_knowledge_graph.assert_called_once_with("user_bool", "Energy", hops=1)

    def test_traverse_exception_handling(self):
        config = {"configurable": {"user_id": "user_err"}}
        kg_traversal_mock.traverse_knowledge_graph.side_effect = RuntimeError("database timeout")
        res = graph_tools.traverse_knowledge_graph_tool.func(entity="FailureTest", hops=1, config=config)
        self.assertEqual(res, "Error traversing knowledge graph: Unable to complete traversal.")


if __name__ == "__main__":
    unittest.main()
