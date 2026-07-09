from datetime import datetime, timedelta, timezone
from typing import Any, Optional


def normalize_server_update_time(value: Any) -> Optional[datetime]:
    """Normalize Firestore and protobuf timestamps to an aware datetime."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)

    to_datetime = getattr(value, 'ToDatetime', None)
    if callable(to_datetime):
        try:
            normalized = to_datetime(tzinfo=timezone.utc)
        except TypeError:
            normalized = to_datetime()
        if not isinstance(normalized, datetime):
            raise TypeError(f'Unsupported server update_time conversion result: {type(normalized)!r}')
        return normalized if normalized.tzinfo is not None else normalized.replace(tzinfo=timezone.utc)

    seconds = getattr(value, 'seconds', None)
    nanos = getattr(value, 'nanos', None)
    if seconds is not None and nanos is not None:
        whole_seconds = int(seconds)
        if isinstance(nanos, str):
            # fake-firestore stores the fractional digits from a float rather than
            # protobuf's integer nanosecond count.
            microseconds = int((nanos + '000000')[:6])
        else:
            microseconds = int(nanos) // 1_000
        return datetime.fromtimestamp(whole_seconds, tz=timezone.utc) + timedelta(microseconds=microseconds)

    raise TypeError(f'Unsupported server update_time type: {type(value)!r}')


def server_version_data(update_time: Any) -> tuple[Optional[datetime], Optional[str]]:
    normalized = normalize_server_update_time(update_time)
    return normalized, normalized.isoformat() if normalized is not None else None
