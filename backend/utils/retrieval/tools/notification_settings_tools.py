"""
Tools for managing user notification settings.
"""

from typing import Any, Dict, Optional, cast
import contextvars

from langchain_core.tools import tool  # type: ignore[reportUnknownVariableType]  # langchain @tool decorator partially typed
from langchain_core.runnables import RunnableConfig

import database.notifications as notification_db
import logging

logger = logging.getLogger(__name__)

# Import agent_config_context for fallback config access
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


def _coerce_hour(hour: Any) -> Optional[int]:
    """Coerce an LLM-supplied hour into an int, or None when it is not numeric.

    Tool-calling models frequently emit numbers as strings (``hour="22"``), and
    some emit ``"10 PM"``-style text or ``None``. Returning ``None`` lets callers
    respond with a validation message instead of raising ``TypeError``.
    """
    if hour is None or isinstance(hour, bool):
        return None
    try:
        return int(hour)
    except (TypeError, ValueError):
        return None


def _format_hour(hour: Any) -> str:
    """Convert 24-hour format to friendly 12-hour format.

    Accepts ints or numeric strings and never raises: unparseable input degrades
    to a plain label rather than crashing the agent pipeline.
    """
    hour_int = _coerce_hour(hour)
    if hour_int is None:
        return f"{hour}:00"
    hour = hour_int

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
    # Optional[...] rather than str/int: model tool-calling can emit None or a
    # numeric string, and both are handled defensively below instead of raising.
    action: Optional[str],
    hour: Optional[Any] = None,
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

    # config may be None when called directly (not via langchain injection)
    cfg: Optional[Dict[str, Any]] = cast(Optional[Dict[str, Any]], config)
    if cfg is None:
        cfg = _agent_config()
    if cfg is None:
        return "Error: Configuration not available"

    try:
        raw_configurable = cfg.get('configurable')
        if isinstance(raw_configurable, dict):
            configurable: Dict[str, Any] = cast(Dict[str, Any], raw_configurable)
            uid = configurable.get('user_id')
        else:
            uid = None
        # Defensive fallback: some call paths place user_id at the top level of the config.
        if not uid:
            uid = cfg.get('user_id')
    except (KeyError, TypeError):
        return "Error: Configuration not available"

    if not uid:
        return "Error: User ID not found"

    if not isinstance(action, str):
        return (
            f"Unknown action: {action}. Use 'enable', 'disable', 'set_time', or 'get_settings'."
        )

    action = action.lower().strip()
    if not action:
        return "Error: Please specify an action: 'enable', 'disable', 'set_time', or 'get_settings'."

    try:
        if action == "enable":
            notification_db.set_daily_summary_enabled(uid, True)
            _hour = notification_db.get_daily_summary_hour_local(uid)
            current_hour = 22 if _hour is None else _hour
            hour_str = _format_hour(current_hour)
            return f"Daily summary notifications enabled. You'll receive them at {hour_str}."

        elif action == "disable":
            notification_db.set_daily_summary_enabled(uid, False)
            return "Daily summary notifications disabled."

        elif action == "set_time":
            if hour is None:
                return "Error: Please specify the hour (0-23). Example: 22 for 10 PM, 9 for 9 AM."

            hour_int = _coerce_hour(hour)
            if hour_int is None:
                return (
                    "Error: Hour must be a whole number between 0 and 23. "
                    f"You provided {hour!r}."
                )

            if not (0 <= hour_int <= 23):
                return f"Error: Hour must be between 0 and 23. You provided {hour_int}."

            notification_db.set_daily_summary_hour_local(uid, hour_int)
            hour_str = _format_hour(hour_int)

            # Also enable if currently disabled
            if not notification_db.get_daily_summary_enabled(uid):
                notification_db.set_daily_summary_enabled(uid, True)
                return f"Daily summary time changed to {hour_str} and notifications enabled."

            return f"Daily summary time changed to {hour_str}."

        elif action == "get_settings":
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

    except Exception as e:
        logger.error(
            "manage_daily_summary_tool failed for action '%s': %s",
            action,
            e,
            exc_info=True,
        )
        return "Error: Unable to access daily summary settings right now. Please try again later."
