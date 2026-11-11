"""Pod-local daily peak of visible Home rows.

``uid`` is an in-memory key and is never a Prometheus label. A later report
on the same UTC day raises the stored peak and adds only the delta, so
``sum / count`` is the average of each user's best settled Home that day.
A user who hits two pods is counted twice. Fail-open.
"""

from __future__ import annotations

import threading
from datetime import datetime, timezone

from prometheus_client import Counter

MAX_ROWS = 500
MAX_KEYS = 50_000

# Names include _total so the exported series matches the Cloud Monitoring type.
OMI_HOME_ROWS_USER_DAY_SUM = Counter(
    'omi_home_rows_user_day_sum_total',
    'Sum of per-user daily peak visible Home row counts. Never labeled by uid.',
)
OMI_HOME_ROWS_USER_DAY_COUNT = Counter(
    'omi_home_rows_user_day_count_total',
    'User-days that reported a Home row count. Never labeled by uid.',
)
OMI_HOME_ROWS_USER_DAY_SUM.inc(0)
OMI_HOME_ROWS_USER_DAY_COUNT.inc(0)

_lock = threading.Lock()
_peaks: dict[tuple[str, str], int] = {}


def reset_home_rows_for_tests() -> None:
    with _lock:
        _peaks.clear()


def observe_home_rows(uid: str, row_count: object) -> bool:
    """Record one Home snapshot. Returns whether it changed the daily peak."""
    if not uid or isinstance(row_count, bool) or not isinstance(row_count, int):
        return False
    if row_count < 0 or row_count > MAX_ROWS:
        return False
    day = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    key = (uid, day)
    delta = 0
    new_day = False
    try:
        with _lock:
            if key not in _peaks and len(_peaks) >= MAX_KEYS:
                stale = min((item[1] for item in _peaks), default=day)
                for old in [item for item in _peaks if item[1] <= stale]:
                    _peaks.pop(old, None)
            previous = _peaks.get(key)
            if previous is None:
                _peaks[key] = row_count
                new_day = True
                delta = row_count
            elif row_count > previous:
                _peaks[key] = row_count
                delta = row_count - previous
        if new_day:
            OMI_HOME_ROWS_USER_DAY_COUNT.inc()
        if delta:
            OMI_HOME_ROWS_USER_DAY_SUM.inc(delta)
        return new_day or delta > 0
    except Exception:
        return False
