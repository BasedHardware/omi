"""Current-date grounding for LLM prompts.

Several generators (proactive insight notifications, memory extraction) ask the model to
reason about whether the user's dated content is upcoming, overdue, or in the future, but
did not tell the model what "today" is. With no anchor the model falls back to its
training-cutoff year, so it flags correctly recorded future-year dates as errors ("your
clock is wrong", "this date is two years in the future"). These helpers produce a present
date to inject into those prompts.
"""

import logging
from datetime import datetime, timezone
from typing import Optional
from zoneinfo import ZoneInfo

import database.notifications as notification_db

logger = logging.getLogger(__name__)


def current_date_in_tz(tz: Optional[str] = None) -> str:
    """Current calendar date as YYYY-MM-DD in ``tz``.

    A missing or invalid timezone falls back to UTC. Only the date is returned; the year is
    the part that actually fixes the "treats real future-year dates as wrong" bug, and a
    date-only string keeps the prompt cache-friendly within a day.
    """
    try:
        zone = ZoneInfo(tz) if tz else timezone.utc
    except Exception:  # noqa: BLE001 - any unknown/invalid tz falls back to UTC
        zone = timezone.utc
    return datetime.now(zone).strftime('%Y-%m-%d')


def current_date_for_uid(uid: str) -> str:
    """Current date (YYYY-MM-DD) in the user's saved timezone, UTC fallback on any error.

    A timezone lookup failure must never break generation, so fall back to UTC rather than
    raising.
    """
    try:
        tz = notification_db.get_user_time_zone(uid)
    except Exception as e:  # noqa: BLE001 - lookup failure must not abort generation
        logger.warning(f"current_date_for_uid - timezone lookup failed, using UTC: {e}")
        tz = None
    return current_date_in_tz(tz)
