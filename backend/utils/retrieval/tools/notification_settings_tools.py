"""
Tools for managing user notification settings.
"""

from typing import Optional
import contextvars

from langchain_core.tools import tool
from langchain_core.runnables import RunnableConfig

import database.notifications as notification_db

# Import agent_config_context for fallback config access
try:
    from utils.retrieval.agentic import agent_config_context
except ImportError:
    agent_config_context = contextvars.ContextVar('agent_config', default=None)


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
    config: RunnableConfig = None,
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
    print(f"🔧 manage_daily_summary_tool called - action: {action}, hour: {hour}")

    # Get config from parameter or context variable
    if config is None:
        try:
            config = agent_config_context.get()
        except LookupError:
            config = None

    if config is None:
        return "Error: Configuration not available"

    try:
        uid = config['configurable'].get('user_id')
    except (KeyError, TypeError):
        return "Error: Configuration not available"

    if not uid:
        return "Error: User ID not found"

    action = action.lower().strip()

    if action == "enable":
        notification_db.set_daily_summary_enabled(uid, True)
        current_hour = notification_db.get_daily_summary_hour_local(uid) or 22
        hour_str = _format_hour(current_hour)
        return f"Daily summary notifications enabled. You'll receive them at {hour_str}."

    elif action == "disable":
        notification_db.set_daily_summary_enabled(uid, False)
        return "Daily summary notifications disabled."

    elif action == "set_time":
        if hour is None:
            return "Error: Please specify the hour (0-23). Example: 22 for 10 PM, 9 for 9 AM."

        if not (0 <= hour <= 23):
            return f"Error: Hour must be between 0 and 23. You provided {hour}."

        notification_db.set_daily_summary_hour_local(uid, hour)
        hour_str = _format_hour(hour)

        # Also enable if currently disabled
        if not notification_db.get_daily_summary_enabled(uid):
            notification_db.set_daily_summary_enabled(uid, True)
            return f"Daily summary time changed to {hour_str} and notifications enabled."

        return f"Daily summary time changed to {hour_str}."

    elif action == "get_settings":
        enabled = notification_db.get_daily_summary_enabled(uid)
        current_hour = notification_db.get_daily_summary_hour_local(uid) or 22
        hour_str = _format_hour(current_hour)

        if enabled:
            return f"Daily summary is enabled, scheduled for {hour_str} daily."
        else:
            return f"Daily summary is currently disabled. Last set time was {hour_str}."

    else:
        return f"Unknown action: {action}. Use 'enable', 'disable', 'set_time', or 'get_settings'."

