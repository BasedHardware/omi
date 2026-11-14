"""Observe the first Home-readable notes revision seen by this process, without IO."""

from collections import OrderedDict
from datetime import datetime
import math
from threading import Lock
import time

from prometheus_client import Histogram

NOTES_TO_HOME = Histogram(
    'omi_record_notes_to_home_read_seconds',
    'Notes write to first Home-ready row observed per process/revision; excludes client rendering',
    buckets=(0.1, 1, 2, 5, 10, 30, 60, 120, 300, 600, 1800, 3600),
)
_SEEN: OrderedDict[tuple[str, float], None] = OrderedDict()
_LOCK = Lock()
_LIMIT = 8192


def observe(row: dict, *, now: float | None = None) -> None:
    """No identifiers in metrics; bounded local dedupe, no database reads or writes."""
    if row.get('record_lane_owner') not in {'batch_live_v1', 'batch_sync_v1'} or not row.get('id'):
        return
    written = row.get('notes_written_at')
    if isinstance(written, datetime):
        written = written.timestamp()
    if isinstance(written, bool) or not isinstance(written, (float, int)) or not math.isfinite(written):
        return
    elapsed = (time.time() if now is None else now) - written
    if elapsed < 0 or not math.isfinite(elapsed):
        return
    key = (str(row['id']), float(written))
    with _LOCK:
        if key in _SEEN:
            return
        _SEEN[key] = None
        if len(_SEEN) > _LIMIT:
            _SEEN.popitem(last=False)
    NOTES_TO_HOME.observe(elapsed)
