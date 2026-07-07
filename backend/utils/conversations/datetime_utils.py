from datetime import datetime, timezone
from typing import Any


def coerce_utc_datetime(value: Any) -> datetime | None:
    """Coerce a datetime/ISO timestamp to a timezone-aware UTC datetime.

    Returns None for missing or malformed values so callers can retain records
    while emitting domain-specific metrics instead of crashing on mixed timestamp
    shapes.
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        except ValueError:
            return None
    else:
        return None

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)
