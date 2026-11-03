"""Resolve the display clock a user's model-facing timestamps are rendered in.

Owns the stored-timezone lookup so ``utils.model_text`` stays a pure formatter that models and
offline tooling can import without a database client.
"""

import logging
from typing import Any, Mapping, Optional

import database.notifications as notification_db
from utils.model_text import DisplayClock

logger = logging.getLogger(__name__)


def clock_for_uid(uid: str) -> DisplayClock:
    """Resolve from the stored user timezone. Only for callers without a chat turn (MCP, REST)."""
    try:
        return DisplayClock.from_name(notification_db.get_user_time_zone(uid))
    except Exception as error:
        logger.warning('clock_for_uid: timezone lookup failed error_type=%s', type(error).__name__)
        return DisplayClock.utc()


def clock_for_turn(configurable: Optional[Mapping[str, Any]], uid: Optional[str] = None) -> DisplayClock:
    """Resolve the clock for a chat turn.

    Prefers the zone the turn already resolved (the same one the prompt's current-datetime block
    uses), so tool output and prompt can never disagree. Falls back to the stored timezone only
    when the turn did not carry one.
    """
    name = (configurable or {}).get('user_timezone')
    if name:
        return DisplayClock.from_name(str(name))
    if uid:
        return clock_for_uid(uid)
    return DisplayClock.utc()


def clock_for_config(config: Any, uid: Optional[str] = None) -> DisplayClock:
    """Resolve from a LangChain ``RunnableConfig`` (or ``None``) as chat tools receive it."""
    configurable = config.get('configurable') if isinstance(config, Mapping) else None
    return clock_for_turn(configurable if isinstance(configurable, Mapping) else None, uid)
