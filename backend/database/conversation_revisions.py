"""Firestore revision normalization shared by conversation persistence paths."""

from datetime import datetime, timezone
from typing import Any, Optional


def ensure_timezone_aware(value: Any) -> datetime:
    """Return an aware datetime, treating legacy naive values as UTC, or parsing ISO strings/timestamps."""
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str) and value.strip():
        try:
            dt = datetime.fromisoformat(value.strip().replace('Z', '+00:00'))
            return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            pass
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        try:
            return datetime.fromtimestamp(value, tz=timezone.utc)
        except (ValueError, OverflowError, OSError):
            pass
    to_datetime = getattr(value, 'ToDatetime', None)
    if callable(to_datetime):
        try:
            converted = to_datetime(tzinfo=timezone.utc)
            if isinstance(converted, datetime):
                return converted if converted.tzinfo is not None else converted.replace(tzinfo=timezone.utc)
        except Exception:
            pass
    return datetime.min.replace(tzinfo=timezone.utc)


def firestore_revision_datetime(value: Any) -> Optional[datetime]:
    """Normalize Firestore snapshot metadata to an aware API datetime."""
    if isinstance(value, datetime):
        return ensure_timezone_aware(value)

    if isinstance(value, str) and value.strip():
        try:
            parsed = datetime.fromisoformat(value.strip().replace('Z', '+00:00'))
            return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            pass

    to_datetime = getattr(value, 'ToDatetime', None)
    if callable(to_datetime):
        try:
            converted = to_datetime(tzinfo=timezone.utc)
            return ensure_timezone_aware(converted) if isinstance(converted, datetime) else None
        except (TypeError, ValueError, OverflowError):
            return None

    try:
        seconds = getattr(value, 'seconds')
        nanos = getattr(value, 'nanos')
        if isinstance(seconds, str) and isinstance(nanos, str):
            timestamp = float(f'{seconds}.{nanos}')
        else:
            timestamp = float(seconds) + (float(nanos) / 1_000_000_000)
        return datetime.fromtimestamp(timestamp, tz=timezone.utc)
    except (AttributeError, IndexError, TypeError, ValueError, OverflowError):
        return None
