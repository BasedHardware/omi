from datetime import datetime, timezone
from typing import Any


def coerce_utc_datetime(value: Any) -> datetime | None:
    """Coerce a datetime, ISO timestamp or epoch seconds to aware UTC.

    Returns None for missing or malformed values so callers can retain records
    while emitting domain-specific metrics instead of crashing on mixed timestamp
    shapes.
    """
    try:
        if isinstance(value, datetime):
            parsed = value
        elif isinstance(value, str):
            parsed = datetime.fromisoformat(value.strip().replace('Z', '+00:00'))
        elif isinstance(value, (int, float)) and not isinstance(value, bool):
            parsed = datetime.fromtimestamp(value, tz=timezone.utc)
        else:
            return None

        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except (ValueError, OverflowError, OSError):
        return None
