"""Tests verifying graph_tools.py validation, configurable resilience, and boundary handling.

Ensures that traverse_knowledge_graph_tool safely handles None configurable dictionaries,
top-level user_id, coerces string/out-of-bounds hops, validates non-empty entities,
and returns structured error responses without unhandled exceptions.
"""

import os
import unittest
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock

import pytest

from testing.import_isolation import load_module_fresh, stub_modules

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)


def _module(name, **attrs):
    mod = ModuleType(name)
    for key, value in attrs.items():
        setattr(mod, key, value)
    return mod


def _package(name):
    mod = _module(name)
    mod.__path__ = []  # type: ignore[attr-defined]
    return mod


def _tool_decorator(fn=None, **kwargs):
    if fn is not None and callable(fn):
        fn.func = fn
        return fn

    def dec(func):
        func.func = func
        return func

    return dec


@pytest.fixture(scope="module", autouse=True)
def _graph_tools_module():
    """Load graph_tools with isolated dependencies."""
    langchain_tools = _module("langchain_core.tools", tool=_tool_decorator)
    langchain_runnables = _module("langchain_core.runnables", RunnableConfig=dict)

    mock_traverse = MagicMock(return_value={"subgraph": ["nodeA -> relation -> nodeB"]})
    mock_format = MagicMock(return_value="Formatted Graph: nodeA -> nodeB")
    mock_kg = _module(
        "utils.memory.kg_graph_traversal",
        traverse_knowledge_graph=mock_traverse,
        format_traversal_result=mock_format,
    )
    mock_sanitizer = _module("utils.log_sanitizer", sanitize=lambda s: s)

    stubs = {
        "langchain_core": _package("langchain_core"),
        "langchain_core.tools": langchain_tools,
        "langchain_core.runnables": langchain_runnables,
        "utils": _package("utils"),
        "utils.log_sanitizer": mock_sanitizer,
        "utils.memory": _package("utils.memory"),
        "utils.memory.kg_graph_traversal": mock_kg,
    }

    with stub_modules(stubs):
        module = load_module_fresh(
            "utils.retrieval.tools._graph_tools_test",
            str(BACKEND_DIR / "utils" / "retrieval" / "tools" / "graph_tools.py"),
        )
        globals()["graph_mod"] = module
        globals()["mock_traverse_fn"] = mock_traverse
        globals()["mock_format_fn"] = mock_format
        yield
        globals().pop("graph_mod", None)
        globals().pop("mock_traverse_fn", None)
        globals().pop("mock_format_fn", None)


class TestGraphTools(unittest.TestCase):
    def setUp(self):
        self.config = {"configurable": {"user_id": "test_uid"}}
        mock_traverse_fn.reset_mock()
        mock_format_fn.reset_mock()

    def test_missing_user_id_returns_error(self):
        res = graph_mod.traverse_knowledge_graph_tool.func("Project X", config={"configurable": None})
        self.assertEqual(res, "Error: User ID not found in configuration")

    def test_top_level_user_id_success(self):
        res = graph_mod.traverse_knowledge_graph_tool.func("Project X", config={"user_id": "top_uid"})
        self.assertEqual(res, "Formatted Graph: nodeA -> nodeB")
        mock_traverse_fn.assert_called_with("top_uid", "Project X", hops=1)

    def test_empty_or_none_entity_returns_error(self):
        res_none = graph_mod.traverse_knowledge_graph_tool.func(None, config=self.config)
        self.assertEqual(res_none, "Error: Entity name must not be empty")

        res_empty = graph_mod.traverse_knowledge_graph_tool.func("   ", config=self.config)
        self.assertEqual(res_empty, "Error: Entity name must not be empty")

    def test_coerces_string_hops(self):
        res = graph_mod.traverse_knowledge_graph_tool.func("Project X", hops="2", config=self.config)
        self.assertEqual(res, "Formatted Graph: nodeA -> nodeB")
        mock_traverse_fn.assert_called_with("test_uid", "Project X", hops=2)

    def test_clamps_hops_bounds(self):
        # Clamps > 2 down to 2
        graph_mod.traverse_knowledge_graph_tool.func("Project X", hops=10, config=self.config)
        mock_traverse_fn.assert_called_with("test_uid", "Project X", hops=2)

        # Clamps < 1 up to 1
        graph_mod.traverse_knowledge_graph_tool.func("Project X", hops=-5, config=self.config)
        mock_traverse_fn.assert_called_with("test_uid", "Project X", hops=1)

    def test_handles_exception_gracefully(self):
        mock_traverse_fn.side_effect = RuntimeError("KG connection failure")
        res = graph_mod.traverse_knowledge_graph_tool.func("Project X", config=self.config)
        self.assertEqual(res, "Error traversing knowledge graph: Unable to complete traversal.")
        mock_traverse_fn.side_effect = None


if __name__ == "__main__":
    unittest.main()
