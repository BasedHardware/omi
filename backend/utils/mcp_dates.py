"""Timezone-aware date windows and wire timestamps for external reads.

Omitted timezone preserves the released UTC-day contract. ``profile`` resolves
an owner's configured zone; an explicit IANA zone avoids profile reads.
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import database.users as users_db

from utils.mcp_data import parse_date_only_utc
from utils.mcp_server.errors import ToolExecutionError


def resolve_timezone(uid: str, name: Optional[str] = None) -> ZoneInfo:
    if name == 'profile':
        profile = users_db.get_user_profile(uid)
        name = profile.get('time_zone') or 'UTC'
    if name is not None and not isinstance(name, str):
        raise ToolExecutionError('timezone must be an IANA zone name or profile', code=-32602)
    try:
        return ZoneInfo(name or 'UTC')
    except (ZoneInfoNotFoundError, ValueError, TypeError) as exc:
        raise ToolExecutionError(
            'Invalid timezone. Use an IANA zone name, e.g. Asia/Ho_Chi_Minh.', code=-32602
        ) from exc


def local_date_window(uid: str, start: Optional[str], end: Optional[str], name: Optional[str] = None):
    zone = resolve_timezone(uid, name)
    try:
        start_dt = parse_date_only_utc(start).replace(tzinfo=zone) if start else None
        end_dt = (
            (parse_date_only_utc(end).replace(tzinfo=zone) + timedelta(days=1) - timedelta(microseconds=1))
            if end
            else None
        )
    except (ValueError, TypeError) as exc:
        raise ToolExecutionError('Invalid date format. Expected YYYY-MM-DD.', code=-32602) from exc
    if start_dt and end_dt and start_dt > end_dt:
        raise ToolExecutionError('start_date must be on or before end_date', code=-32602)
    return (
        start_dt.astimezone(timezone.utc) if start_dt else None,
        end_dt.astimezone(timezone.utc) if end_dt else None,
        zone,
    )


def offset_timestamp(value: Any, zone: ZoneInfo) -> Any:
    if value is None:
        return None
    try:
        stamp = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=timezone.utc)
        return stamp.astimezone(zone).isoformat()
    except (TypeError, ValueError):
        return value


def localize_timestamps(value: Any, zone: ZoneInfo) -> Any:
    """Only timestamp-named fields; date labels and prose remain untouched."""
    if isinstance(value, list):
        return [localize_timestamps(item, zone) for item in value]
    if isinstance(value, dict):
        return {
            key: (
                offset_timestamp(item, zone)
                if key.endswith('_at')
                or key in {'timestamp', 'first_seen', 'last_seen', 'first_observed_at', 'last_observed_at'}
                else localize_timestamps(item, zone)
            )
            for key, item in value.items()
        }
    return value


def rest_datetime_window(uid: str, start: Optional[datetime], end: Optional[datetime], name: Optional[str]):
    zone = resolve_timezone(uid, name)

    def boundary(value, is_end=False):
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=zone)
            if name is not None and is_end and value.time().isoformat() == '00:00:00':
                value += timedelta(days=1, microseconds=-1)
        return value.astimezone(timezone.utc)

    start, end = boundary(start), boundary(end, True)
    if start and end and start > end:
        raise ToolExecutionError('start_date must be on or before end_date', code=-32602)
    return start, end, zone
