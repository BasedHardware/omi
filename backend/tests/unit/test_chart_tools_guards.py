"""Unit tests for chart_tools input coercion, guards, and config resilience."""

import pytest
from utils.retrieval.tools.chart_tools import create_chart_tool, agent_config_context


class TestChartToolsGuards:
    """Hermetic unit tests verifying input validation, coercions, and config resilience."""

    def test_create_chart_valid_execution(self):
        """create_chart_tool creates chart_data and returns confirmation string."""
        config = {"configurable": {}}
        token = agent_config_context.set(config)
        try:
            res = create_chart_tool.invoke({
                "chart_type": "line",
                "title": "Sleep Duration",
                "labels": ["Mon", "Tue", "Wed"],
                "values": [7.5, 6.8, 8.2],
                "dataset_label": "Hours",
                "color": "#4CAF50",
                "x_label": "Day",
                "y_label": "Hours",
            })

            assert "Chart created: Sleep Duration (line chart with 3 data points)" in res
            chart_data = config["configurable"]["chart_data"]
            assert chart_data["chart_type"] == "line"
            assert chart_data["title"] == "Sleep Duration"
            assert chart_data["datasets"][0]["data_points"] == [
                {"label": "Mon", "value": 7.5},
                {"label": "Tue", "value": 6.8},
                {"label": "Wed", "value": 8.2},
            ]
            assert chart_data["datasets"][0]["color"] == "#4CAF50"
        finally:
            agent_config_context.reset(token)

    def test_create_chart_case_insensitive_type(self):
        """chart_type handles uppercase and whitespace, and rejects invalid types."""
        config = {"configurable": {}}
        token = agent_config_context.set(config)
        try:
            # Upper case "BAR "
            res_bar = create_chart_tool.invoke({
                "chart_type": "BAR ",
                "title": "Steps",
                "labels": ["Today"],
                "values": [10000],
            })
            assert "Chart created: Steps (bar chart with 1 data points)" in res_bar
            assert config["configurable"]["chart_data"]["chart_type"] == "bar"

            # Invalid chart type
            res_invalid = create_chart_tool.invoke({
                "chart_type": "pie",
                "title": "Steps",
                "labels": ["Today"],
                "values": [10000],
            })
            assert res_invalid == "Error: chart_type must be 'line' or 'bar'."
        finally:
            agent_config_context.reset(token)

    def test_create_chart_numeric_value_coercion(self):
        """Numeric strings and ints are safely coerced to floats."""
        config = {"configurable": {}}
        token = agent_config_context.set(config)
        try:
            res = create_chart_tool.invoke({
                "chart_type": "line",
                "title": "Mixed Values",
                "labels": ["A", "B", "C"],
                "values": ["7.2", 8, "9.5"],
            })

            assert "Chart created" in res
            points = config["configurable"]["chart_data"]["datasets"][0]["data_points"]
            assert points == [
                {"label": "A", "value": 7.2},
                {"label": "B", "value": 8.0},
                {"label": "C", "value": 9.5},
            ]
        finally:
            agent_config_context.reset(token)

    def test_create_chart_invalid_numeric_values(self):
        """Non-numeric values, booleans, and None return descriptive validation errors."""
        config = {"configurable": {}}

        # Text in values
        res_text = create_chart_tool.func(
            chart_type="line",
            title="Bad Values",
            labels=["A"],
            values=["not_a_number"],
            config=config,
        )
        assert "Error: Invalid numeric value 'not_a_number' in values." in res_text

        # Boolean in values
        res_bool = create_chart_tool.func(
            chart_type="line",
            title="Bad Values",
            labels=["A"],
            values=[True],
            config=config,
        )
        assert res_bool == "Error: values must be numeric."

        # None in values
        res_none = create_chart_tool.func(
            chart_type="line",
            title="Bad Values",
            labels=["A"],
            values=[None],
            config=config,
        )
        assert res_none == "Error: values must be numeric."

    def test_create_chart_labels_coercion(self):
        """Integer labels (e.g. days or hours) are safely coerced to strings."""
        config = {"configurable": {}}
        res = create_chart_tool.func(
            chart_type="bar",
            title="Hourly Count",
            labels=[1, 2, 3],
            values=[10, 20, 30],
            config=config,
        )

        assert "Chart created" in res
        points = config["configurable"]["chart_data"]["datasets"][0]["data_points"]
        assert points[0]["label"] == "1"
        assert points[1]["label"] == "2"
        assert points[2]["label"] == "3"

    def test_create_chart_none_and_non_list_guards(self):
        """None or non-list labels or values return error without raising TypeError."""
        config = {"configurable": {}}

        # None labels
        assert create_chart_tool.func(
            chart_type="line",
            title="Title",
            labels=None,
            values=[1.0],
            config=config,
        ) == "Error: labels and values must be lists."

        # None values
        assert create_chart_tool.func(
            chart_type="line",
            title="Title",
            labels=["A"],
            values=None,
            config=config,
        ) == "Error: labels and values must be lists."

        # Non-list type
        assert create_chart_tool.func(
            chart_type="line",
            title="Title",
            labels="A,B",
            values=123,
            config=config,
        ) == "Error: labels and values must be lists."

    def test_create_chart_length_mismatch_and_empty(self):
        """Mismatched lengths or empty data return clear error messages."""
        config = {"configurable": {}}

        # Length mismatch
        res_mismatch = create_chart_tool.func(
            chart_type="line",
            title="Mismatch",
            labels=["A", "B"],
            values=[1.0],
            config=config,
        )
        assert res_mismatch == "Error: labels and values must have the same length."

        # Empty data
        res_empty = create_chart_tool.func(
            chart_type="line",
            title="Empty",
            labels=[],
            values=[],
            config=config,
        )
        assert res_empty == "Error: at least one data point is required."

    def test_create_chart_title_guard(self):
        """Missing, whitespace, or None title returns error."""
        config = {"configurable": {}}

        assert create_chart_tool.func(
            chart_type="line",
            title="",
            labels=["A"],
            values=[1.0],
            config=config,
        ) == "Error: title is required."

        assert create_chart_tool.func(
            chart_type="line",
            title="   \t  ",
            labels=["A"],
            values=[1.0],
            config=config,
        ) == "Error: title is required."

        assert create_chart_tool.func(
            chart_type="line",
            title=None,
            labels=["A"],
            values=[1.0],
            config=config,
        ) == "Error: title is required."

    def test_create_chart_config_none_configurable_resilience(self):
        """Config with configurable=None or missing configurable does not crash."""
        config_none_configurable = {"configurable": None}
        res1 = create_chart_tool.func(
            chart_type="bar",
            title="Steps",
            labels=["Mon"],
            values=[5000],
            config=config_none_configurable,
        )
        assert "Chart created" in res1
        assert config_none_configurable["configurable"]["chart_data"]["title"] == "Steps"

        config_empty = {}
        res2 = create_chart_tool.func(
            chart_type="line",
            title="Sleep",
            labels=["Tue"],
            values=[7.0],
            config=config_empty,
        )
        assert "Chart created" in res2
        assert config_empty["configurable"]["chart_data"]["title"] == "Sleep"
