"""
Tool for creating inline chart visualizations in chat responses.
"""

import contextvars
from typing import Any, Dict, List, Optional, cast

from langchain_core.tools import tool  # type: ignore[reportUnknownVariableType]  # langchain @tool decorator partially typed
from langchain_core.runnables import RunnableConfig

try:
    from utils.retrieval.agentic import agent_config_context
except ImportError:
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
    labels: Any,
    values: Any,
    dataset_label: str = "Data",
    color: Optional[str] = None,
    x_label: Optional[str] = None,
    y_label: Optional[str] = None,
    config: RunnableConfig = None,  # type: ignore[reportAssignmentType]  # langchain injects at runtime; None default for direct calls
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
    if labels is None or values is None or not isinstance(labels, (list, tuple)) or not isinstance(values, (list, tuple)):
        return "Error: labels and values must be lists."

    if len(labels) != len(values):
        return "Error: labels and values must have the same length."

    if len(labels) == 0:
        return "Error: at least one data point is required."

    normalized_type = chart_type.lower().strip() if isinstance(chart_type, str) else ""
    if normalized_type not in ('line', 'bar'):
        return "Error: chart_type must be 'line' or 'bar'."
    chart_type = normalized_type

    if not title or not str(title).strip():
        return "Error: title is required."
    title = str(title).strip()

    coerced_values: List[float] = []
    for v in values:
        if v is None or isinstance(v, bool):
            return "Error: values must be numeric."
        try:
            coerced_values.append(float(v))
        except (TypeError, ValueError):
            return f"Error: Invalid numeric value '{v}' in values."

    coerced_labels = [str(l) for l in labels]

    chart_data = {
        "chart_type": chart_type,
        "title": title,
        "x_label": x_label,
        "y_label": y_label,
        "datasets": [
            {
                "label": dataset_label,
                "data_points": [{"label": l, "value": v} for l, v in zip(coerced_labels, coerced_values)],
                "color": color,
            }
        ],
    }

    cfg: Optional[Dict[str, Any]] = cast(Optional[Dict[str, Any]], config)
    ctx_cfg = _agent_config()
    targets = [c for c in (cfg, ctx_cfg) if isinstance(c, dict)]
    for target in targets:
        if not isinstance(target.get('configurable'), dict):
            target['configurable'] = {}
        target['configurable']['chart_data'] = chart_data

    return f"Chart created: {title} ({chart_type} chart with {len(coerced_labels)} data points). The chart will be displayed inline in the chat."
