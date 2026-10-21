"""Tests verifying demand_processing_tools.py validation, configurable resilience, and boundary handling.

Ensures that process_recent_conversations safely handles None configurable dictionaries,
coerces string/out-of-bound hours and limit, and returns structured responses without unhandled exceptions.
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
def _demand_processing_tools_module():
    """Load demand_processing_tools with isolated dependencies."""
    langchain_tools = _module("langchain_core.tools", tool=_tool_decorator)
    langchain_runnables = _module("langchain_core.runnables", RunnableConfig=dict)

    mock_process_recent = MagicMock(return_value={"status": "processing", "ready": False, "promoted": 2})
    mock_demand = _module("utils.conversations.demand_processing", process_recent=mock_process_recent)

    stubs = {
        "langchain_core": _package("langchain_core"),
        "langchain_core.tools": langchain_tools,
        "langchain_core.runnables": langchain_runnables,
        "utils": _package("utils"),
        "utils.conversations": _package("utils.conversations"),
        "utils.conversations.demand_processing": mock_demand,
    }

    with stub_modules(stubs):
        module = load_module_fresh(
            "utils.retrieval.tools._demand_processing_tools_test",
            str(BACKEND_DIR / "utils" / "retrieval" / "tools" / "demand_processing_tools.py"),
        )
        globals()["demand_mod"] = module
        globals()["mock_demand_fn"] = mock_process_recent
        yield
        globals().pop("demand_mod", None)
        globals().pop("mock_demand_fn", None)


class TestDemandProcessingTools(unittest.TestCase):
    def setUp(self):
        self.config = {"configurable": {"user_id": "test_uid"}}
        mock_demand_fn.reset_mock()

    def test_permission_error_on_configurable_none(self):
        with self.assertRaises(PermissionError):
            demand_mod.process_recent_conversations.func({"configurable": None})

    def test_top_level_user_id_success(self):
        res = demand_mod.process_recent_conversations.func({"user_id": "top_uid"})
        self.assertIn('"status": "processing"', res)
        mock_demand_fn.assert_called_with("top_uid", hours=6, limit=20)

    def test_coerces_string_hours_and_limit(self):
        res = demand_mod.process_recent_conversations.func(self.config, hours="4", limit="10")
        self.assertIn('"status": "processing"', res)
        mock_demand_fn.assert_called_with("test_uid", hours=4, limit=10)

    def test_clamps_out_of_bounds_parameters(self):
        # Clamps hours > 6 down to 6, and limit > 20 down to 20
        res = demand_mod.process_recent_conversations.func(self.config, hours=100, limit=500)
        self.assertIn('"status": "processing"', res)
        mock_demand_fn.assert_called_with("test_uid", hours=6, limit=20)

        # Clamps hours < 1 up to 1, and limit < 1 up to 1
        res = demand_mod.process_recent_conversations.func(self.config, hours=-5, limit=0)
        self.assertIn('"status": "processing"', res)
        mock_demand_fn.assert_called_with("test_uid", hours=1, limit=1)

    def test_handles_downstream_exception_gracefully(self):
        mock_demand_fn.side_effect = RuntimeError("Redis connection failure")
        res = demand_mod.process_recent_conversations.func(self.config)
        self.assertIn('"error": "Redis connection failure"', res)
        self.assertIn('"ready": false', res)
        mock_demand_fn.side_effect = None


if __name__ == "__main__":
    unittest.main()
