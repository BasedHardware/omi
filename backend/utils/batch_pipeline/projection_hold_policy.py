"""Classify writer waits from capture age, retaining terminal assignment fences."""

import logging
import math
import time

from config.batch_pipeline import projection_hold_recovery_enabled
from utils.sync.assignment_errors import (
    SyncAssignmentConflict,
    SyncAssignmentConflictReason,
    bounded_sync_assignment_subtype,
    sync_assignment_conflict_strikes,
)

logger = logging.getLogger(__name__)
AWAITING_WRITER_AGE_SECONDS = 6 * 3600.0
PROJECTION_TERMINAL_CONFLICTS = frozenset(
    {SyncAssignmentConflictReason.RECORD_TARGET_DISCARDED, SyncAssignmentConflictReason.LINEAGE_OWNERSHIP_AMBIGUOUS}
)


def quarantines_assignment_conflict(error: BaseException, job: dict | None, *, now: float | None = None) -> bool:
    """Structural conflicts hold; recent/unknown writer waits use the retry bound.

    A scheduling lane is not evidence that a target writer is hours late.
    Discard and ambiguous ownership remain held on every lane.
    """
    if not isinstance(error, SyncAssignmentConflict):
        return False
    lane = 'backfill' if (job or {}).get('fresh_capture') is False else 'fresh'
    if not projection_hold_recovery_enabled():
        return sync_assignment_conflict_strikes(error.subtype, lane)
    if error.subtype in PROJECTION_TERMINAL_CONFLICTS:
        return True
    # Use capture end, never enqueue/commit/first-attempt time. Unknown age
    # waits under the existing durable 24-hour bound rather than guessing old.
    capture, duration = (job or {}).get('capture_at'), (job or {}).get('duration_seconds')
    if not (
        isinstance(capture, (int, float))
        and not isinstance(capture, bool)
        and isinstance(duration, (int, float))
        and not isinstance(duration, bool)
        and math.isfinite(capture)
        and math.isfinite(duration)
        and capture >= 0
        and duration > 0
        and (time.time() if now is None else now) - (capture + duration) >= AWAITING_WRITER_AGE_SECONDS
    ):
        lane = 'fresh'
    return sync_assignment_conflict_strikes(error.subtype, lane)


def log_conflict_hold(error: SyncAssignmentConflict) -> None:
    from utils.batch_pipeline.correctness_metrics import record_conflict_hold

    subtype = bounded_sync_assignment_subtype(error.subtype)
    logger.info('event=batch_projection action=assignment outcome=conflict_held conflict_subtype=%s', subtype)
    record_conflict_hold(subtype)
