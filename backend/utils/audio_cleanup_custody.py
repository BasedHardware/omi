"""Capture-window preservation for routine cleanup only, never privacy erasure."""

from datetime import datetime, timezone
import math
import os

DEFAULT_HOLD_WINDOWS = '2026-10-22T13:36:30Z..2026-10-24T07:16:00Z'


def _epoch(value):
    if isinstance(value, str):
        return _epoch(datetime.fromisoformat(value.replace('Z', '+00:00')))
    if isinstance(value, datetime):
        if value.tzinfo is None:
            raise ValueError('capture timestamp must have a timezone')
        epoch = value.timestamp()
    elif isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value):
        epoch = float(value)
    else:
        raise ValueError('invalid capture timestamp')
    # Finite numbers can still be malformed epoch-milliseconds or outside the
    # representable UTC calendar. They must not release an incident hold.
    datetime.fromtimestamp(epoch, timezone.utc)
    return epoch


def cleanup_hold_reason(capture_at, duration_seconds=None) -> str | None:
    """Closed intervals; missing provenance/config holds rather than authorizes.

    An unknown end can overlap any later window. This deliberately retains
    older legacy artifacts lacking duration until their range is established.
    Only the explicit kill switch disables preservation, not empty config.
    """
    if os.getenv('AUDIO_CLEANUP_HOLD_ENABLED', 'true').strip().lower() == 'false':
        return None
    try:
        windows = []
        for window in os.getenv('AUDIO_CLEANUP_HOLD_WINDOWS', DEFAULT_HOLD_WINDOWS).split(','):
            start, end = window.strip().split('..')
            lower, upper = _epoch(start), _epoch(end)
            if lower > upper:
                raise ValueError('reversed hold window')
            windows.append((lower, upper))
    except (ValueError, OverflowError, OSError):
        return 'invalid_hold_config'
    try:
        start = _epoch(capture_at)
        if duration_seconds is None:
            end = math.inf
        elif (
            isinstance(duration_seconds, (int, float))
            and not isinstance(duration_seconds, bool)
            and math.isfinite(duration_seconds)
            and duration_seconds >= 0
        ):
            end = start + duration_seconds
        else:
            raise ValueError('invalid capture duration')
    except (ValueError, OverflowError, OSError):
        return 'unknown_capture_range'
    return 'capture_window' if any(start <= upper and end >= lower for lower, upper in windows) else None
