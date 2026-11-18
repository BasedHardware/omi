"""Which stored row is the v3 live tile (``GET /v1/conversations/live``). Pure; no IO.

Only an open v3 window qualifies. A legacy in-progress row (not ``v3_derived``)
never does, however new: a stale one left by an old capture path rendered as an
untitled live tile. An open window must also have spoken recently, because a
parked or stalled builder can leave it ``in_progress`` long after the speech.
"""

from datetime import datetime, timedelta
from typing import Any, Mapping

from utils.conversations.list_filters import aware_datetime

# A v3 window is capped at two hours (``planner.CAP``) and its ``created_at`` is
# its first speech, so an open window always starts inside this lookback.
MAX_SPAN = timedelta(hours=2)
# A window whose last speech is older than this is not live, whatever its status.
MAX_IDLE = timedelta(minutes=30)
# Visible in-progress rows read inside the lookback: the open window plus any
# legacy capture rows created after it started. Recordings are hidden and do
# not count toward it.
SCAN_ROWS = 10


def lookback_start(now: datetime) -> datetime:
    return now - MAX_SPAN - MAX_IDLE


def is_open(row: Mapping[str, Any], now: datetime) -> bool:
    if row.get('recording') or not row.get('v3_derived') or row.get('tile_state') != 'live':
        return False
    last = row.get('finished_at') or row.get('started_at') or row.get('created_at')
    if not isinstance(last, datetime):
        return False
    return now - aware_datetime(last) <= MAX_IDLE
