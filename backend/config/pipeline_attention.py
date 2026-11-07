"""Pure dark pipeline policy. Firestore custody always wins over scheduling.

Lifecycle: rollout, default off; owner pipeline-approved; review 2026-11-21.
"""

from collections.abc import Mapping
from datetime import datetime
import math
import os

DISPATCH_AFTER_SECONDS = 1680
PROCESSING_RESERVE_SECONDS = 120
LEASE_SECONDS = 90
COHORT_KEY = 'pipeline_attention'
FIELD = 'pipeline_attention'


def mode() -> str:
    value = os.getenv('PIPELINE_ATTENTION_MODE', 'off').strip().lower()
    return value if value in {'off', 'shadow', 'serve'} else 'off'


def seal_fast_enabled() -> bool:
    return os.getenv('PIPELINE_SEAL_FAST_ENABLED', 'false').strip().lower() == 'true'


def record_fast_enabled() -> bool:
    return os.getenv('PIPELINE_RECORD_FAST_ENABLED', 'false').strip().lower() == 'true'


def close_on_seal_enabled() -> bool:
    # Separate from hold bypass: requires the F-join owner's full-ramp receipt.
    return os.getenv('PIPELINE_CLOSE_ON_SEAL_ENABLED', 'false').strip().lower() == 'true'


def skip_silence_enabled() -> bool:
    return os.getenv('PIPELINE_SKIP_SILENCE_ON_SEAL_ENABLED', 'false').strip().lower() == 'true'


def capture_cost_enabled() -> bool:
    return os.getenv('PIPELINE_CAPTURE_COST_ENABLED', 'false').strip().lower() == 'true'


def seconds(value) -> float | None:
    if isinstance(value, datetime):
        value = value.timestamp()
    if isinstance(value, bool):
        return None
    try:
        result = float(value)
        return result if math.isfinite(result) and result > 0 else None
    except (TypeError, ValueError):
        return None


def capture_end(row: Mapping) -> float | None:
    # recorded_end is the captured span; finished_at is kept separately as the
    # close-trigger clock. Never silently substitute acceptance for capture.
    return seconds(row.get('recorded_end'))


def seal_snapshot(row: Mapping) -> dict | None:
    revision = row.get('record_upload_revision')
    if (
        row.get('record_lane_owner') not in {'batch_live_v1', 'batch_sync_v1'}
        or row.get('status') != 'completed'
        or seconds(row.get('finished_at')) is None
        or row.get('record_audio_closed') is not True
        or row.get('record_audio_partial')
        or row.get('record_upload_failed')
        or row.get('record_upload_sessions')
        or row.get('deleted')
        or row.get('discarded')
        or type(revision) is not int
        or revision < 0
    ):
        return None
    return {
        'owner': row['record_lane_owner'],
        'upload_revision': revision,
        'content_revision': row.get('sync_content_revision'),
        'finished_at': seconds(row['finished_at']),
    }


def dispatch_at(row: Mapping, obligation: Mapping) -> float | None:
    """An earlier accepted deadline survives joins, new evidence and rollback."""
    saved = seconds(obligation.get('pipeline_dispatch_at'))
    end = capture_end(row)
    proposed = end + DISPATCH_AFTER_SECONDS if end is not None else None
    values = [at for at in (saved, proposed) if at is not None]
    return min(values) if values else None


def snapshot_matches(row: Mapping, expected: Mapping) -> bool:
    return seal_snapshot(row) == expected
