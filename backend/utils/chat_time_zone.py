"""Client-reported IANA timezone sync for chat and profile."""

from __future__ import annotations

import logging
from typing import Optional

from zoneinfo import ZoneInfo

import database.notifications as notification_db

logger = logging.getLogger(__name__)


def get_user_timezone(uid: str) -> str:
    """Resolve the user's timezone, falling back to UTC when missing/invalid."""
    tz = notification_db.get_user_time_zone(uid)
    if tz is None:
        return "UTC"
    try:
        ZoneInfo(tz)
        return tz
    except Exception:
        return "UTC"


def sync_user_time_zone_from_client(uid: str, request_tz: Optional[str]) -> str:
    """Apply a client-reported IANA timezone for this chat turn and return the resolved zone."""
    if not request_tz:
        return get_user_timezone(uid)
    try:
        ZoneInfo(request_tz)
    except Exception:
        logger.warning("sync_user_time_zone_from_client - invalid request_tz, ignoring")
        return get_user_timezone(uid)
    stored = notification_db.get_user_time_zone(uid)
    if stored != request_tz:
        notification_db.set_user_time_zone(uid, request_tz)
    return request_tz
