"""Content-free owner-load contract shared by ramp admission and shadow checks.

No clients or IO: operator tooling can load this source from the release ref.
The limits classify new partial-ramp admissions, never accepted obligations.
"""

import math
import os
from typing import TypeGuard

MAX_OPEN = 30
MAX_AUDIO_SECONDS = 6 * 3600
OPEN_WINDOW_SECONDS = 6 * 3600
READ_LIMIT = 512
SWITCH = 'BATCH_PIPELINE_RAMP_EXCLUDE_HEAVY_OWNERS'


def exclusion_enabled(percent, flags=None):
    env = os.environ if flags is None else flags
    return 0 < percent < 100 and env.get(SWITCH, 'on').strip().lower() != 'off'


def nonnegative(value: object) -> TypeGuard[int | float]:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value >= 0


def audio_span(payload):
    if not isinstance(payload, dict):
        return None
    start, end = payload.get('audio_start_seconds'), payload.get('audio_end_seconds')
    return end - start if nonnegative(start) and nonnegative(end) and end >= start else None


def owner_load(open_rows, pending_rows, now, *, incoming_audio_seconds=0):
    """A bounded snapshot of recent open batch units plus waiting legacy uploads.

    Pending rows include the normalized sequencer active payload (deduplicated
    by job id by the reader). All waiting/active uploads count regardless of age. Recently admitted completed
    and quarantined batch units do not count. A saturated read cannot certify
    a light owner. Unknown pending durations cannot certify the audio budget.
    """
    unknown = len(open_rows) >= READ_LIMIT or len(pending_rows) >= READ_LIMIT
    count, seconds = 0, 0.0
    for row in open_rows:
        if row.get('client_status') == 'completed' or row.get('state') == 'quarantined':
            continue
        admitted = row.get('enqueued_at')
        if not nonnegative(admitted):
            unknown = True
            continue
        if now - admitted > OPEN_WINDOW_SECONDS:
            continue
        count += 1
        duration = row.get('duration_seconds')
        # Native record_pending rows have no final duration yet; their queue
        # slot still counts. Waiting legacy audio below has explicit bounds.
        if nonnegative(duration):
            seconds += duration
    for row in pending_rows:
        count += 1
        duration = audio_span(row.get('payload'))
        if duration is None:
            unknown = True
        else:
            seconds += duration
    if nonnegative(incoming_audio_seconds):
        seconds += incoming_audio_seconds
    else:
        unknown = True
    return {'open_backlog': count, 'recording_seconds': seconds, 'complete': not unknown}


def exclusion_reason(load):
    if not isinstance(load, dict):
        return 'load_unavailable'
    count, seconds = load.get('open_backlog'), load.get('recording_seconds')
    if nonnegative(count) and count > MAX_OPEN:
        return 'open_backlog'
    if nonnegative(seconds) and seconds > MAX_AUDIO_SECONDS:
        return 'recording_hours'
    if load.get('complete') is not True or not nonnegative(count) or not nonnegative(seconds):
        return 'load_unavailable'
    return None
