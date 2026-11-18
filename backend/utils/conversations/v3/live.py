"""Which open row the live read may serve as the conversation in progress."""

from datetime import datetime, timedelta, timezone
from typing import Any, Mapping, Optional, Sequence

# The v3 window cap: an open conversation idle for longer is not in progress.
MAX_IDLE = timedelta(hours=2)
SCAN = 10
# The bounded page the live read scans: a stale stub may sort ahead of the open conversation.
OPEN_ROWS = dict(limit=SCAN, statuses=['in_progress'], hide_home=True)


def active(rows: Sequence[Mapping[str, Any]], now: Optional[datetime] = None) -> Optional[Mapping[str, Any]]:
    """First non-recording open row with activity inside the cap.

    A capture that never closed stays in_progress for days. Served as live, it hides the
    client's capture card and sits under its own start date, so Home shows nothing in progress.
    """
    fresh_after = (now or datetime.now(timezone.utc)) - MAX_IDLE
    for row in rows:
        if row.get('recording'):
            continue
        last = next(
            (row[k] for k in ('finished_at', 'started_at', 'created_at') if isinstance(row.get(k), datetime)), None
        )
        if last is not None and (last if last.tzinfo else last.replace(tzinfo=timezone.utc)) >= fresh_after:
            return row
    return None
