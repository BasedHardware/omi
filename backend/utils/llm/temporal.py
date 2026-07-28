"""Current-date grounding for LLM prompts.

Several generators (proactive insight notifications, memory extraction) ask the model to
reason about whether the user's dated content is upcoming, overdue, or in the future, but
did not tell the model what "today" is. With no anchor the model falls back to its
training-cutoff year, so it flags correctly recorded future-year dates as errors ("your
clock is wrong", "this date is two years in the future"). These helpers produce a date to
inject into those prompts.

``current_date_in_tz`` and ``date_in_tz`` are pure and import no DB layer, so a module can
use them without pulling the Firestore client in at import time; only ``current_date_for_uid``
touches the database, and it does so lazily.
"""

import logging
from datetime import datetime, timezone
from typing import Optional
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)


def _zone(tz: Optional[str]):
    try:
        return ZoneInfo(tz) if tz else timezone.utc
    except Exception:  # noqa: BLE001 - any unknown/invalid tz falls back to UTC
        return timezone.utc


def current_date_in_tz(tz: Optional[str] = None) -> str:
    """Current calendar date as YYYY-MM-DD in ``tz``.

    A missing or invalid timezone falls back to UTC. Only the date is returned; the year is
    the part that actually fixes the "treats real future-year dates as wrong" bug, and a
    date-only string keeps the prompt cache-friendly within a day.
    """
    return datetime.now(_zone(tz)).strftime('%Y-%m-%d')


def date_in_tz(dt: datetime, tz: Optional[str] = None) -> str:
    """Calendar date (YYYY-MM-DD) of ``dt`` rendered in ``tz`` (UTC fallback).

    Used to ground memory extraction in the date the content was captured rather than the
    processing time, so relative expressions in delayed or backfilled content resolve
    correctly. A naive datetime is treated as UTC.
    """
    aware = dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)
    return aware.astimezone(_zone(tz)).strftime('%Y-%m-%d')


def current_date_for_uid(uid: str) -> str:
    """Current date (YYYY-MM-DD) in the user's saved timezone, UTC fallback on any error.

    The ``database.notifications`` import is deferred so importing this module for the pure
    helpers above never pulls the Firestore client (which initializes at import time), and a
    timezone lookup failure falls back to UTC rather than raising.
    """
    import database.notifications as notification_db

    try:
        tz = notification_db.get_user_time_zone(uid)
    except Exception as e:  # noqa: BLE001 - lookup failure must not abort generation
        logger.warning(f"current_date_for_uid - timezone lookup failed, using UTC: {e}")
        tz = None
    return current_date_in_tz(tz)
