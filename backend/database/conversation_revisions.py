"""Firestore revision normalization shared by conversation persistence paths."""

from datetime import datetime, timezone
from typing import Any, Optional

from utils.conversations.datetime_utils import coerce_utc_datetime


def ensure_timezone_aware(value: Any) -> datetime:
    """Return an aware datetime, treating legacy naive values, ISO strings, and invalid inputs gracefully."""
    coerced = coerce_utc_datetime(value)
    if coerced is not None:
        return coerced
    if isinstance(value, datetime):
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value
    return datetime.min.replace(tzinfo=timezone.utc)


def firestore_revision_datetime(value: Any) -> Optional[datetime]:
    """Normalize Firestore snapshot metadata to an aware API datetime."""
    if isinstance(value, datetime):
        return ensure_timezone_aware(value)

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
