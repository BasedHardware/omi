"""Tests verifying chart_tools.py functionality, validation, and configuration persistence.

Ensures that create_chart_tool safely binds chart_data into configurable even when
configurable is omitted or None, and coerces malformed data points without raising.
"""

import unittest
from pathlib import Path
from types import ModuleType
from unittest.mock import patch

import pytest

from testing.import_isolation import load_module_fresh, stub_modules

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent


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
def _chart_tools_module():
    """Load chart_tools with isolated dependencies."""
    langchain_tools = _module("langchain_core.tools", tool=_tool_decorator)
    langchain_runnables = _module("langchain_core.runnables", RunnableConfig=dict)

    stubs = {
        "langchain_core": _package("langchain_core"),
        "langchain_core.tools": langchain_tools,
        "langchain_core.runnables": langchain_runnables,
    }

    with stub_modules(stubs):
        module = load_module_fresh(
            "utils.retrieval.tools._chart_tools_test",
            str(BACKEND_DIR / "utils" / "retrieval" / "tools" / "chart_tools.py"),
        )
        globals()["chart_mod"] = module
        yield
        globals().pop("chart_mod", None)


class TestChartTools(unittest.TestCase):
    def test_create_chart_tool_persists_to_configurable_when_absent(self):
        config = {"user_id": "test_uid_123"}
        token = chart_mod.agent_config_context.set(config)
        try:
            res = chart_mod.create_chart_tool.func(
                chart_type="line",
                title="Steps Progress",
                labels=["Mon", "Tue", "Wed"],
                values=[5000.0, 7500.0, 10000.0],
            )
            self.assertIn("Chart created: Steps Progress", res)
            self.assertIn("configurable", config)
            self.assertIn("chart_data", config["configurable"])
            chart_data = config["configurable"]["chart_data"]
            self.assertEqual(chart_data["title"], "Steps Progress")
            self.assertEqual(chart_data["chart_type"], "line")
            self.assertEqual(len(chart_data["datasets"][0]["data_points"]), 3)
        finally:
            chart_mod.agent_config_context.reset(token)

    def test_create_chart_tool_handles_configurable_none(self):
        config = {"configurable": None}
        token = chart_mod.agent_config_context.set(config)
        try:
            res = chart_mod.create_chart_tool.func(
                chart_type="bar",
                title="Sleep Hours",
                labels=["Day 1", "Day 2"],
                values=[7.5, 8.0],
            )
            self.assertIn("Chart created: Sleep Hours", res)
            self.assertIsInstance(config["configurable"], dict)
            self.assertIn("chart_data", config["configurable"])
        finally:
            chart_mod.agent_config_context.reset(token)

    def test_create_chart_tool_coerces_values_and_labels(self):
        config = {"configurable": {}}
        token = chart_mod.agent_config_context.set(config)
        try:
            res = chart_mod.create_chart_tool.func(
                chart_type="bar",
                title="Activity",
                labels=["Mon", None, "Wed"],
                values=["12.5", None, True],
            )
            self.assertIn("Chart created: Activity", res)
            points = config["configurable"]["chart_data"]["datasets"][0]["data_points"]
            self.assertEqual(points[0], {"label": "Mon", "value": 12.5})
            self.assertEqual(points[1], {"label": "", "value": 0.0})
            self.assertEqual(points[2], {"label": "Wed", "value": 1.0})
        finally:
            chart_mod.agent_config_context.reset(token)

    def test_create_chart_tool_validations(self):
        # Mismatched length
        err1 = chart_mod.create_chart_tool.func(
            chart_type="line",
            title="Mismatch",
            labels=["Mon"],
            values=[1.0, 2.0],
        )
        self.assertEqual(err1, "Error: labels and values must have the same length.")

        # Invalid chart type
        err2 = chart_mod.create_chart_tool.func(
            chart_type="pie",
            title="Pie",
            labels=["A"],
            values=[1.0],
        )
        self.assertEqual(err2, "Error: chart_type must be 'line' or 'bar'.")

        # Empty labels
        err3 = chart_mod.create_chart_tool.func(
            chart_type="line",
            title="Empty",
            labels=[],
            values=[],
        )
        self.assertEqual(err3, "Error: at least one data point is required.")

    def test_create_chart_tool_works_without_context(self):
        # When context var is unset
        res = chart_mod.create_chart_tool.func(
            chart_type="line",
            title="No Context",
            labels=["Mon", "Tue"],
            values=[10.0, 20.0],
        )
        self.assertIn("Chart created: No Context", res)

    def test_create_chart_tool_context_is_none(self):
        # When context var is explicitly None
        token = chart_mod.agent_config_context.set(None)
        try:
            res = chart_mod.create_chart_tool.func(
                chart_type="line",
                title="Context None",
                labels=["Mon", "Tue"],
                values=[10.0, 20.0],
            )
            self.assertIn("Chart created: Context None", res)
        finally:
            chart_mod.agent_config_context.reset(token)

    def test_create_chart_tool_non_dict_truthy_context_skips_attachment(self):
        # When context var is a non-dict truthy value (e.g. string or object)
        token = chart_mod.agent_config_context.set("non_dict_context_string")
        try:
            res = chart_mod.create_chart_tool.func(
                chart_type="line",
                title="Non Dict Context",
                labels=["Mon", "Tue"],
                values=[10.0, 20.0],
            )
            self.assertIn("Chart created: Non Dict Context", res)
        finally:
            chart_mod.agent_config_context.reset(token)


if __name__ == "__main__":
    unittest.main()
