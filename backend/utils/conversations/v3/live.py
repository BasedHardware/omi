"""Which open row the live read may serve as the conversation in progress."""

from datetime import datetime, timedelta, timezone
from typing import Any, Mapping, Optional, Sequence

# The v3 window cap: an open conversation idle for longer is not in progress.
MAX_IDLE = timedelta(hours=2)


def _aware(value: Any) -> Optional[datetime]:
    if not isinstance(value, datetime):
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def active(rows: Sequence[Mapping[str, Any]], now: Optional[datetime] = None) -> Optional[Mapping[str, Any]]:
    """The newest open v3 window with activity inside the cap.

    A capture that never closed stays in_progress for days. Served as live, it hides the
    client's capture card and sits under its own start date, so Home shows nothing in progress.
    A legacy in-progress row (not ``v3_derived``) is never the live tile, however new: one left
    by an old capture path rendered as an untitled live tile. Rows come from the indexed v3
    read, so legacy rows cannot crowd the window out; the checks here are the visibility rule.
    """
    fresh_after = (now or datetime.now(timezone.utc)) - MAX_IDLE
    best, best_last = None, None
    for row in rows:
        if (
            not row.get('v3_derived')
            or row.get('status') != 'in_progress'
            or row.get('tile_state') != 'live'
            or row.get('recording')
            or row.get('home_hidden')
            or row.get('deleted')
            or row.get('discarded')
        ):
            continue
        last = next(
            (_aware(row.get(k)) for k in ('finished_at', 'started_at', 'created_at') if _aware(row.get(k))), None
        )
        if last is None or last < fresh_after:
            continue
        if best_last is None or last > best_last:
            best, best_last = row, last
    return best
