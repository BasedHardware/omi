import math
import os
import importlib.util

try:
    from utils.retrieval.tools.chart_tools import create_chart_tool, agent_config_context
except Exception:
    file_path = os.path.join(os.path.dirname(__file__), "..", "..", "utils", "retrieval", "tools", "chart_tools.py")
    spec = importlib.util.spec_from_file_location("chart_tools", os.path.abspath(file_path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    create_chart_tool = mod.create_chart_tool
    agent_config_context = mod.agent_config_context


def test_create_chart_tool_valid_line():
    config = {"configurable": {}}
    token = agent_config_context.set(config)
    try:
        res = create_chart_tool.invoke({
            "chart_type": "line",
            "title": "Sleep Stats",
            "labels": ["Mon", "Tue"],
            "values": [7.5, 8.0],
            "dataset_label": "Hours",
        })
        assert "Chart created: Sleep Stats (line chart with 2 data points)" in res
        chart = config["configurable"]["chart_data"]
        assert chart["chart_type"] == "line"
        assert chart["title"] == "Sleep Stats"
        assert len(chart["datasets"][0]["data_points"]) == 2
        assert chart["datasets"][0]["data_points"][0] == {"label": "Mon", "value": 7.5}
        assert chart["datasets"][0]["data_points"][1] == {"label": "Tue", "value": 8.0}
    finally:
        agent_config_context.reset(token)


def test_create_chart_tool_valid_bar_with_colors():
    config = {"configurable": {}}
    token = agent_config_context.set(config)
    try:
        res = create_chart_tool.invoke({
            "chart_type": "bar",
            "title": "Step Count",
            "labels": ["Today"],
            "values": [10500],
            "color": "#4CAF50",
            "x_label": "Day",
            "y_label": "Steps",
        })
        assert "Chart created: Step Count (bar chart with 1 data points)" in res
        chart = config["configurable"]["chart_data"]
        assert chart["chart_type"] == "bar"
        assert chart["datasets"][0]["color"] == "#4CAF50"
        assert chart["x_label"] == "Day"
        assert chart["y_label"] == "Steps"
    finally:
        agent_config_context.reset(token)


def test_create_chart_tool_case_insensitive_normalization():
    res_line = create_chart_tool.invoke({
        "chart_type": "Line ",
        "title": "Test",
        "labels": ["A"],
        "values": [1.0],
    })
    assert "line chart with 1 data points" in res_line

    res_bar = create_chart_tool.invoke({
        "chart_type": "BAR",
        "title": "Test",
        "labels": ["A"],
        "values": [1.0],
    })
    assert "bar chart with 1 data points" in res_bar


def test_create_chart_tool_invalid_chart_type():
    res = create_chart_tool.invoke({
        "chart_type": "pie",
        "title": "Test",
        "labels": ["A"],
        "values": [1.0],
    })
    assert "Error: chart_type must be 'line' or 'bar'." in res


def test_create_chart_tool_guard_none_labels_and_values():
    res_none_labels = create_chart_tool.invoke({
        "chart_type": "line",
        "title": "Test",
        "labels": None,
        "values": [1.0],
    })
    assert "Error: labels must be a non-empty list of data labels." in res_none_labels

    res_none_values = create_chart_tool.invoke({
        "chart_type": "line",
        "title": "Test",
        "labels": ["A"],
        "values": None,
    })
    assert "Error: values must be a non-empty list of numeric values." in res_none_values


def test_create_chart_tool_empty_labels():
    res = create_chart_tool.invoke({
        "chart_type": "line",
        "title": "Test",
        "labels": [],
        "values": [],
    })
    assert "Error: at least one data point is required." in res


def test_create_chart_tool_mismatched_lengths():
    res = create_chart_tool.invoke({
        "chart_type": "line",
        "title": "Test",
        "labels": ["A", "B"],
        "values": [1.0],
    })
    assert "Error: labels and values must have the same length." in res


def test_create_chart_tool_coerces_string_numbers_and_integer_labels():
    config = {"configurable": {}}
    token = agent_config_context.set(config)
    try:
        res = create_chart_tool.invoke({
            "chart_type": "line",
            "title": "Growth",
            "labels": [2024, 2025],
            "values": ["10.5", 20],
        })
        assert "Chart created" in res
        points = config["configurable"]["chart_data"]["datasets"][0]["data_points"]
        assert points[0] == {"label": "2024", "value": 10.5}
        assert points[1] == {"label": "2025", "value": 20.0}
    finally:
        agent_config_context.reset(token)


def test_create_chart_tool_rejects_invalid_numeric_values():
    res_nan = create_chart_tool.invoke({
        "chart_type": "line",
        "title": "Test",
        "labels": ["A"],
        "values": [float("nan")],
    })
    assert "Error: non-finite numeric value" in res_nan

    res_inf = create_chart_tool.invoke({
        "chart_type": "line",
        "title": "Test",
        "labels": ["A"],
        "values": [float("inf")],
    })
    assert "Error: non-finite numeric value" in res_inf

    res_str = create_chart_tool.invoke({
        "chart_type": "line",
        "title": "Test",
        "labels": ["A"],
        "values": ["not_a_number"],
    })
    assert "Error: invalid numeric value" in res_str


def test_create_chart_tool_configurable_none_resilience():
    # When configurable exists but is explicitly None
    config = {"configurable": None}
    token = agent_config_context.set(config)
    try:
        res = create_chart_tool.invoke({
            "chart_type": "line",
            "title": "",
            "labels": ["Day 1"],
            "values": [5.0],
        })
        assert "Chart created: Chart" in res
        assert config["configurable"] is not None
        assert "chart_data" in config["configurable"]
    finally:
        agent_config_context.reset(token)
