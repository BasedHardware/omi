"""
Tool for creating inline chart visualizations in chat responses.
"""

import contextvars
from typing import List, Optional

from langchain_core.tools import tool

try:
    from utils.retrieval.agentic import agent_config_context
except ImportError:
    agent_config_context = contextvars.ContextVar('agent_config', default=None)


@tool
def create_chart_tool(
    chart_type: str,
    title: str,
    labels: List[str],
    values: List[float],
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
    if len(labels) != len(values):
        return "Error: labels and values must have the same length."

    if chart_type not in ('line', 'bar'):
        return "Error: chart_type must be 'line' or 'bar'."

    if len(labels) == 0:
        return "Error: at least one data point is required."

    chart_data = {
        "chart_type": chart_type,
        "title": title,
        "x_label": x_label,
        "y_label": y_label,
        "datasets": [
            {
                "label": dataset_label,
                "data_points": [{"label": l, "value": v} for l, v in zip(labels, values)],
                "color": color,
            }
        ],
    }

    try:
        config = agent_config_context.get()
    except LookupError:
        config = None

    if config:
        configurable = config.get('configurable', {})
        configurable['chart_data'] = chart_data

    return f"Chart created: {title} ({chart_type} chart with {len(labels)} data points). The chart will be displayed inline in the chat."
