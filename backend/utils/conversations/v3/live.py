"""Which open row the live read may serve as the conversation in progress."""

from datetime import datetime, timedelta, timezone
from typing import Any, Mapping, Optional, Sequence

from config.conversations_v3 import SPEECH_LANDED_FIELD

# The v3 window cap: an open conversation idle for longer is not in progress.
MAX_IDLE = timedelta(hours=2)
FINISH_WINDOW_FIELD = 'v3_finish_no_pointer_window_id'
FINISH_RECORDING_FIELD = 'v3_finish_no_pointer_recording'
# A live-window Finish stamps its request time and path (``FINISH_STAMP_PATHS``) on its response target's source
# with the first write it stores there. The planner carries the stamp to the derived row that shows that source, and
# that row's first manual-end settlement observes ``FINISH_TO_VISIBLE`` once. Older than ``FINISH_STAMP_MAX_AGE``, the
# stamp is dropped instead of observed.
FINISH_STAMP_FIELD = 'v3_finish_requested'
FINISH_STAMP_PATHS = ('tail', 'newer', 'newer_dual')
FINISH_STAMP_MAX_AGE = timedelta(hours=2)
FINISH_FIELDS = [
    'started_at',
    'finished_at',
    'status',
    'tile_state',
    'v3_derived',
    'recording',
    'home_hidden',
    'deleted',
    'discarded',
    'is_locked',
    'v3_recording_ids',
]


FINISH_SOURCE_FIELDS = [
    FINISH_WINDOW_FIELD,
    FINISH_RECORDING_FIELD,
    'v3_manual_end_requested',
    'v3_manual_end',
    'v3_pending_since',
    'recording',
    'status',
    'finished_at',
    'record_audio_partial',
    'record_upload_failed',
    'is_locked',
    'deleted',
    'discarded',
    'sync_merged_into',
    'data_protection_level',
    'record_upload_revision',
    'record_projection_revision',
    'has_content',
    SPEECH_LANDED_FIELD,
]


def has_finish_content(row: Mapping[str, Any], window: Mapping[str, Any], recording_id: str) -> bool:
    # Raw audio custody can set has_content before any transcript lands.
    source_has_speech = row.get('has_content') and (
        row.get('record_projection_revision') or row.get(SPEECH_LANDED_FIELD)
    )
    return bool(source_has_speech or any(rid != recording_id for rid in window.get('v3_recording_ids') or ()))


def _aware(value: Any) -> Optional[datetime]:
    if not isinstance(value, datetime):
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def finish_stamp(at: datetime, path: str) -> dict:
    return {'at': at, 'path': path}


def finish_stamp_sample(stamp: Any, now: datetime) -> Optional[tuple]:
    """``(path, seconds)`` from a Finish stamp, or None when it is malformed or older than ``FINISH_STAMP_MAX_AGE``."""
    if not isinstance(stamp, Mapping) or stamp.get('path') not in FINISH_STAMP_PATHS:
        return None
    at = _aware(stamp.get('at'))
    if at is None or now - at > FINISH_STAMP_MAX_AGE:
        return None
    return stamp['path'], max(0.0, (now - at).total_seconds())


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
