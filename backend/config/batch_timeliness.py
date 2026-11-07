"""2-hour batch timeliness alarm (David, 2026-11-02): default on; BATCH_TIMELINESS_ALARM_ENABLED=false turns it off.

Units admitted before the epoch are backlog: excluded from the 2-hour delivery alarm, so it can be enabled on
day one without firing permanently on rows already late. A separate alert watches assignment-held backlog
growth or saturation of its bounded count.
"""

import datetime as dt
import os

SLA_SECONDS = 7200
DEFAULT_EPOCH = '2026-11-02T06:09:00Z'
DEFAULT_INTERVAL_SECONDS = 300.0
# Keep successful samples fresh (<900s) continuously through the held-backlog
# alert's 15m pending window, with 60s collection/lease refresh grace.
MAX_INTERVAL_SECONDS = 600.0
# David, 2026-11-02 10:45Z: "finished recording counts as processed". A terminal empty_asr unit with no recoverable
# speech (failed held, measured held VAD speech exactly 0) leaves the 2h alarm; it stays a visible count. False puts
# it back in the alarm.
TERMINAL_EMPTY_IS_PROCESSED = True


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
    return min(MAX_INTERVAL_SECONDS, max(60.0, value)) if value == value else DEFAULT_INTERVAL_SECONDS
