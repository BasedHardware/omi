"""Which open row the live read may serve as the conversation in progress."""

from datetime import datetime, timedelta, timezone
from typing import Any, Mapping, Optional, Sequence

# The v3 window cap: an open conversation idle for longer is not in progress.
MAX_IDLE = timedelta(hours=2)
# A v3 window is capped at two hours (``planner.CAP``) and its ``created_at`` is its first
# speech, so an open window that spoke within MAX_IDLE started inside this lookback.
LOOKBACK = timedelta(hours=2) + MAX_IDLE
SCAN = 10
# The bounded page the live read scans: a stale stub may sort ahead of the open conversation.
# List fields only: the live tile needs no transcript blob.
OPEN_ROWS = dict(limit=SCAN, statuses=['in_progress'], hide_home=True, list_fields_only=True)


def open_rows(now: datetime) -> dict:
    """The live read's query: open rows created inside the lookback, never the whole backlog."""
    return dict(OPEN_ROWS, start_date=now - LOOKBACK)


def active(rows: Sequence[Mapping[str, Any]], now: Optional[datetime] = None) -> Optional[Mapping[str, Any]]:
    """First open v3 window with activity inside the cap.

    A capture that never closed stays in_progress for days. Served as live, it hides the
    client's capture card and sits under its own start date, so Home shows nothing in progress.
    A legacy in-progress row (not ``v3_derived``) is never the live tile, however new: one left
    by an old capture path rendered as an untitled live tile.
    """
    fresh_after = (now or datetime.now(timezone.utc)) - MAX_IDLE
    for row in rows:
        if row.get('recording') or not row.get('v3_derived') or row.get('tile_state') != 'live':
            continue
        last = next(
            (row[k] for k in ('finished_at', 'started_at', 'created_at') if isinstance(row.get(k), datetime)), None
        )
        if last is not None and (last if last.tzinfo else last.replace(tzinfo=timezone.utc)) >= fresh_after:
            return row
    return None
