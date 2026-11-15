"""Age persisted deadlines without sleeping or changing the process wall clock."""

from datetime import datetime, timedelta
import math

JOB_CLOCK_FIELDS = (
    'enqueued_at',
    'available_at',
    'committed_at',
    'created_at',
    'updated_at',
    'next_attempt_at',
    'lease_expires_at',
    'held_deadline_at',
    'held_expired_at',
)


def aged_job_fields(row: dict, seconds: float) -> dict:
    if not math.isfinite(seconds) or seconds < 0:
        raise ValueError('age must be finite and nonnegative')
    updates = {}
    for key in JOB_CLOCK_FIELDS:
        value = row.get(key)
        if isinstance(value, datetime):
            updates[key] = value - timedelta(seconds=seconds)
        elif isinstance(value, (int, float)) and not isinstance(value, bool):
            updates[key] = value - seconds
    return updates


def age_job_row(reference, seconds: float) -> dict:
    """Shift a batch or finalization DocumentReference's existing clock fields."""
    row = reference.get().to_dict()
    if row is None:
        raise ValueError('cannot age an absent job')
    updates = aged_job_fields(row, seconds)
    if not updates:
        raise ValueError('job has no supported clock fields')
    reference.update(updates)
    return updates
