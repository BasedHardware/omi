"""
Tool for creating inline chart visualizations in chat responses.
"""

import contextvars
import math
from typing import Any, Dict, List, Optional

from langchain_core.tools import tool  # type: ignore[reportUnknownVariableType]  # langchain @tool decorator partially typed

try:
    from utils.retrieval.agentic import agent_config_context
except (ImportError, Exception):
    agent_config_context = contextvars.ContextVar('agent_config', default=None)


def _agent_config() -> Optional[Dict[str, Any]]:
    """Retrieve the agent config dict from the context var, or None if unset."""
    try:
        return agent_config_context.get()
    except LookupError:
        return None


@tool
def create_chart_tool(
    chart_type: str,
    title: str,
    labels: Optional[List[Any]] = None,
    values: Optional[List[Any]] = None,
    dataset_label: str = "Data",
    color: Optional[str] = None,
    x_label: Optional[str] = None,
    y_label: Optional[str] = None,
) -> str:
    """
    Create an inline chart visualization in the chat response.

    Use this tool AFTER retrieving data with other tools (e.g. Apple Health, Whoop, conversations)
    when the user asks to "show", "graph", "chart", "plot", or "visualize" data.

    The chart will be rendered inline in the chat message on the user's device.

    IMPORTANT: You must first fetch the data using the appropriate tool (e.g. get_apple_health_sleep_tool,
    get_apple_health_steps_tool, get_whoop_sleep_tool), then extract the numerical values and call this tool.

    Args:
        chart_type: Type of chart - "line" or "bar"
        title: Chart title displayed above the chart (e.g. "Sleep - Last 7 Days")
        labels: X-axis labels in order (e.g. ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"])
        values: Y-axis values corresponding to each label (e.g. [7.2, 6.8, 8.1, 7.5, 6.9, 8.5, 7.8])
        dataset_label: Label for this data series (e.g. "Sleep Hours", "Steps", "Heart Rate")
        color: Optional hex color for the data series (e.g. "#4CAF50" for green). Default: blue
        x_label: Optional x-axis label (e.g. "Day")
        y_label: Optional y-axis label (e.g. "Hours")

    Returns:
        Confirmation message. The chart data is automatically attached to the response.
    """
    if labels is None or not isinstance(labels, (list, tuple)):
        return "Error: labels must be a non-empty list of data labels."

    if values is None or not isinstance(values, (list, tuple)):
        return "Error: values must be a non-empty list of numeric values."

    if len(labels) == 0:
        return "Error: at least one data point is required."

    if len(labels) != len(values):
        return "Error: labels and values must have the same length."

    normalized_type = str(chart_type or "").strip().lower()
    if normalized_type not in ('line', 'bar'):
        return "Error: chart_type must be 'line' or 'bar'."

    # Coerce and validate numeric values and sanitize label strings
    data_points = []
    for l, v in zip(labels, values):
        try:
            num = float(v)
            if math.isnan(num) or math.isinf(num):
                return f"Error: non-finite numeric value '{v}' for label '{l}'."
        except (ValueError, TypeError):
            return f"Error: invalid numeric value '{v}' for label '{l}'."
        data_points.append({"label": str(l), "value": num})

    safe_title = str(title or "Chart").strip() or "Chart"

    chart_data = {
        "chart_type": normalized_type,
        "title": safe_title,
        "x_label": x_label,
        "y_label": y_label,
        "datasets": [
            {
                "label": dataset_label or "Data",
                "data_points": data_points,
                "color": color,
            }
        ],
    }

    config = _agent_config()
    if isinstance(config, dict):
        configurable = config.get('configurable')
        if not isinstance(configurable, dict):
            configurable = {}
            config['configurable'] = configurable
        configurable['chart_data'] = chart_data

    return f"Chart created: {safe_title} ({normalized_type} chart with {len(labels)} data points). The chart will be displayed inline in the chat."
