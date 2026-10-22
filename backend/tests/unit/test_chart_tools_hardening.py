"""Unit tests verifying defensive title validation, case-insensitive chart types,
null and non-numeric value coercion, and None configurable guards in chart_tools.py.

Ensures that:
1. Empty or whitespace-only titles and invalid chart types are rejected immediately.
2. None labels or values lists do not raise TypeError during len() inspection.
3. String numeric values are cleanly coerced to float, while None or non-numeric values
   return descriptive validation errors.
4. None configurable dictionary mappings in agent_config_context do not raise TypeError
   during chart_data attachment.
"""

import unittest
from unittest.mock import patch

from utils.retrieval.tools.chart_tools import (
    create_chart_tool,
    agent_config_context,
)
import utils.retrieval.tools.chart_tools as chart_tools


class TestChartToolsHardening(unittest.TestCase):
    """Test chart validation, numeric coercion, and config handling."""

    def test_empty_or_whitespace_title_rejected(self):
        res_empty = create_chart_tool.func(chart_type="line", title="", labels=["A"], values=[1.0])
        self.assertEqual(res_empty, "Error: title cannot be empty.")

        res_spaces = create_chart_tool.func(chart_type="line", title="   ", labels=["A"], values=[1.0])
        self.assertEqual(res_spaces, "Error: title cannot be empty.")

        res_none = create_chart_tool.func(chart_type="line", title=None, labels=["A"], values=[1.0])
        self.assertEqual(res_none, "Error: title cannot be empty.")

    def test_case_insensitive_chart_type(self):
        res_upper = create_chart_tool.func(chart_type="LINE", title="Sleep", labels=["Mon"], values=[7.5])
        self.assertIn("line chart with 1 data points", res_upper)

        res_bar = create_chart_tool.func(chart_type="Bar", title="Steps", labels=["Mon"], values=[10000])
        self.assertIn("bar chart with 1 data points", res_bar)

        res_invalid = create_chart_tool.func(chart_type="pie", title="Invalid", labels=["Mon"], values=[10])
        self.assertEqual(res_invalid, "Error: chart_type must be 'line' or 'bar'.")

    def test_none_labels_or_values_guarded(self):
        res_none_labels = create_chart_tool.func(chart_type="line", title="Test", labels=None, values=[1.0])
        self.assertEqual(res_none_labels, "Error: labels and values must not be None.")

        res_none_values = create_chart_tool.func(chart_type="line", title="Test", labels=["A"], values=None)
        self.assertEqual(res_none_values, "Error: labels and values must not be None.")

    def test_mismatched_length_rejected(self):
        res = create_chart_tool.func(chart_type="line", title="Test", labels=["A", "B"], values=[1.0])
        self.assertEqual(res, "Error: labels and values must have the same length.")

    def test_empty_data_rejected(self):
        res = create_chart_tool.func(chart_type="line", title="Test", labels=[], values=[])
        self.assertEqual(res, "Error: at least one data point is required.")

    def test_numeric_coercion_and_invalid_values(self):
        res_coerced = create_chart_tool.func(
            chart_type="line",
            title="Weight",
            labels=["W1", "W2"],
            values=["70.5", 72],
        )
        self.assertIn("Chart created: Weight", res_coerced)

        res_none_val = create_chart_tool.func(
            chart_type="line",
            title="Weight",
            labels=["W1"],
            values=[None],
        )
        self.assertEqual(res_none_val, "Error: values cannot contain None.")

        res_invalid_val = create_chart_tool.func(
            chart_type="line",
            title="Weight",
            labels=["W1"],
            values=["not_a_number"],
        )
        self.assertIn("Error: all values must be valid numbers", res_invalid_val)

    def test_none_configurable_context_guarded(self):
        config_with_none_configurable = {"configurable": None}
        token = agent_config_context.set(config_with_none_configurable)
        try:
            res = create_chart_tool.func(chart_type="line", title="Context Test", labels=["A"], values=[1.0])
            self.assertIn("Chart created: Context Test", res)
            self.assertIsInstance(config_with_none_configurable.get("configurable"), dict)
            self.assertIn("chart_data", config_with_none_configurable["configurable"])
        finally:
            agent_config_context.reset(token)


if __name__ == "__main__":
    unittest.main()
