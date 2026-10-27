"""
Tools for managing user notification settings.
"""

import logging
from typing import Any, Optional

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool  # type: ignore[reportUnknownVariableType]  # langchain @tool decorator partially typed

import database.notifications as notification_db
from utils.retrieval.tools.integration_base import resolve_config_uid

logger = logging.getLogger(__name__)


def _resolve_uid(config: Optional[Any] = None) -> Optional[str]:
    """Extract uid from config via shared resolve_config_uid."""
    uid, _ = resolve_config_uid(config)
    return uid


def _format_hour(hour: int) -> str:
    """Convert 24-hour format to friendly 12-hour format."""
    if hour == 0:
        return "12:00 AM (midnight)"
    elif hour == 12:
        return "12:00 PM (noon)"
    elif hour < 12:
        return f"{hour}:00 AM"
    else:
        return f"{hour - 12}:00 PM"


@tool
def manage_daily_summary_tool(
    action: str,
    hour: Optional[int] = None,
    config: RunnableConfig = None,  # type: ignore[reportAssignmentType]  # langchain injects at runtime; None default for direct calls
) -> str:
    """
    Manage the user's daily summary/reflection notification settings.

    The daily summary is a notification sent at a specific time each day with a reflection
    on the user's conversations and activities. Also known as "reflection" notification.

    Use this tool when user asks to:
    - Enable or disable daily summary/reflection notifications
    - Change the time of their daily summary notification
    - Check their current notification settings

    Args:
        action: One of:
            - "enable" - Turn on daily summary notifications
            - "disable" - Turn off daily summary notifications
            - "set_time" - Change the notification time (requires hour parameter)
            - "get_settings" - Get current settings
        hour: Hour in 24-hour format (0-23) for "set_time" action.
              Examples: 21 = 9 PM, 22 = 10 PM, 8 = 8 AM, 9 = 9 AM

    Returns:
        Confirmation message about the change or current settings.

    Examples:
        - "disable reflection notifications" → action="disable"
        - "change daily summary to 10pm" → action="set_time", hour=22
        - "enable the reflection" → action="enable"
        - "what time is my daily summary?" → action="get_settings"
        - "set reflection to 9pm" → action="set_time", hour=21
    """
    logger.info(f"🔧 manage_daily_summary_tool called - action: {action}, hour: {hour}")

    if config is None:
        uid = _resolve_uid(None)
        if not uid:
            return "Error: Configuration not available"
    else:
        uid = _resolve_uid(config)
        if not uid:
            return "Error: User ID not found"
    assert uid is not None

    action_str = str(action or "").lower().strip()

    if action_str == "enable":
        notification_db.set_daily_summary_enabled(uid, True)
        _hour = notification_db.get_daily_summary_hour_local(uid)
        current_hour = 22 if _hour is None else _hour
        hour_str = _format_hour(current_hour)
        return f"Daily summary notifications enabled. You'll receive them at {hour_str}."

    elif action_str == "disable":
        notification_db.set_daily_summary_enabled(uid, False)
        return "Daily summary notifications disabled."

    elif action_str == "set_time":
        if hour is None or (isinstance(hour, str) and not hour.strip()):
            return "Error: Please specify the hour (0-23). Example: 22 for 10 PM, 9 for 9 AM."

        try:
            if isinstance(hour, bool):
                raise ValueError("Boolean is not a valid hour")
            parsed_hour = int(float(hour))
        except (TypeError, ValueError):
            return f"Error: Hour must be between 0 and 23. You provided {hour}."

        if not (0 <= parsed_hour <= 23):
            return f"Error: Hour must be between 0 and 23. You provided {parsed_hour}."

        notification_db.set_daily_summary_hour_local(uid, parsed_hour)
        hour_str = _format_hour(parsed_hour)

        # Also enable if currently disabled
        if not notification_db.get_daily_summary_enabled(uid):
            notification_db.set_daily_summary_enabled(uid, True)
            return f"Daily summary time changed to {hour_str} and notifications enabled."

        return f"Daily summary time changed to {hour_str}."

    elif action_str == "get_settings":
        enabled = notification_db.get_daily_summary_enabled(uid)
        _hour = notification_db.get_daily_summary_hour_local(uid)
        current_hour = 22 if _hour is None else _hour
        hour_str = _format_hour(current_hour)

        if enabled:
            return f"Daily summary is enabled, scheduled for {hour_str} daily."
        else:
            return f"Daily summary is currently disabled. Last set time was {hour_str}."

    else:
        return f"Unknown action: {action}. Use 'enable', 'disable', 'set_time', or 'get_settings'."
