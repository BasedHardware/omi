"""Pure timestamp and document-path values shared by finalization and recovery."""

from datetime import datetime, timezone
import math
from typing import Any


def parse_timestamp(value: Any) -> datetime | None:
    """Parse aware/naive datetimes, ISO-8601 strings, and numeric epoch timestamps to UTC."""
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        clean = value.strip()
        if not clean:
            return None
        try:
            dt = datetime.fromisoformat(clean.replace('Z', '+00:00'))
            return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            pass
        try:
            sec = float(clean)
            if not math.isnan(sec) and not math.isinf(sec) and 0 <= sec <= 253402300799:
                return datetime.fromtimestamp(sec, timezone.utc)
        except (ValueError, TypeError, OverflowError):
            pass
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        try:
            sec = float(value)
            if not math.isnan(sec) and not math.isinf(sec) and 0 <= sec <= 253402300799:
                return datetime.fromtimestamp(sec, timezone.utc)
        except (ValueError, TypeError, OverflowError):
            pass
        return None
    return None


def uid_from_conversation_path(path: str) -> str | None:
    """Return the uid from a ``users/{uid}/conversations/{conversation_id}`` path."""
    parts = path.split('/')
    if len(parts) == 4 and parts[0] == 'users' and parts[2] == 'conversations':
        return parts[1]
    return None
