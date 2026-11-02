"""2-hour batch timeliness alarm (David, 2026-11-02): default on; BATCH_TIMELINESS_ALARM_ENABLED=false turns it off.

Units admitted before the epoch are backlog: exported as counts, never alarmed, so the alarm can be enabled on
day one without firing permanently on rows that were already late when the target was set.
"""

import datetime as dt
import os

SLA_SECONDS = 7200
DEFAULT_EPOCH = '2026-11-02T06:09:00Z'
DEFAULT_INTERVAL_SECONDS = 300.0


def batch_timeliness_alarm_enabled() -> bool:
    return os.getenv('BATCH_TIMELINESS_ALARM_ENABLED', '').strip().lower() not in {
        '0',
        'false',
        'off',
        'no',
        'disabled',
    }


def timeliness_epoch() -> float:
    raw = os.getenv('BATCH_TIMELINESS_EPOCH', '').strip() or DEFAULT_EPOCH
    try:
        return dt.datetime.fromisoformat(raw.replace('Z', '+00:00')).timestamp()
    except ValueError:
        return dt.datetime.fromisoformat(DEFAULT_EPOCH.replace('Z', '+00:00')).timestamp()


def timeliness_interval_seconds() -> float:
    try:
        value = float(os.getenv('BATCH_TIMELINESS_INTERVAL_SECONDS', '') or DEFAULT_INTERVAL_SECONDS)
    except ValueError:
        return DEFAULT_INTERVAL_SECONDS
    return min(3600.0, max(60.0, value)) if value == value else DEFAULT_INTERVAL_SECONDS
