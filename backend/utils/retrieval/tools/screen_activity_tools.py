"""
Tools for accessing screen/computer activity data from the desktop app.
"""

from typing import Optional

from langchain_core.tools import tool  # type: ignore[reportUnknownVariableType]  # langchain @tool decorator partially typed
from langchain_core.runnables import RunnableConfig

import logging

logger = logging.getLogger(__name__)

SCREEN_ACTIVITY_CLOUD_UNAVAILABLE = (
    "Screen activity is no longer available from cloud chat. "
    "Captures stay on the user's computer in the Omi desktop app (Rewind). "
    "Tell the user to check screen history there, or use desktop chat on that Mac. "
    "Do not invent screen history from other tools."
)


@tool
def get_screen_activity_tool(
    start_date: str,
    end_date: str,
    app_filter: Optional[str] = None,
    config: RunnableConfig = None,  # type: ignore[reportAssignmentType]  # langchain injects at runtime; None default for direct calls
) -> str:
    """
    Screen activity is no longer available via cloud chat.

    Desktop captures stay on the user's computer. Tell the user to use the Omi
    desktop app (Rewind) or desktop chat on the Mac that recorded the activity.
    Do not invent screen history from other tools.

    Args:
        start_date: Start of the range (ISO format with timezone, e.g. "2025-01-15T00:00:00+00:00")
        end_date: End of the range (ISO format with timezone)
        app_filter: Optional app name to filter to a single application

    Returns:
        A message that cloud screen activity is unavailable.
    """
    logger.info(
        f"get_screen_activity_tool called - start_date={start_date}, end_date={end_date}, app_filter={app_filter}"
    )
    return SCREEN_ACTIVITY_CLOUD_UNAVAILABLE


@tool
def search_screen_activity_tool(
    query: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = 10,
    config: RunnableConfig = None,  # type: ignore[reportAssignmentType]  # langchain injects at runtime; None default for direct calls
) -> str:
    """
    Screen activity search is no longer available via cloud chat.

    Desktop captures stay on the user's computer. Tell the user to use the Omi
    desktop app (Rewind) or desktop chat on the Mac that recorded the activity.
    Do not invent screen history from other tools.

    Args:
        query: Natural language description of what to search for in screen content
        start_date: Optional start date filter (ISO format with timezone)
        end_date: Optional end date filter (ISO format with timezone)
        limit: Number of results to return (default 10, max 20)

    Returns:
        A message that cloud screen activity is unavailable.
    """
    logger.info(f"search_screen_activity_tool called - query='{query}', start_date={start_date}, end_date={end_date}")
    return SCREEN_ACTIVITY_CLOUD_UNAVAILABLE
