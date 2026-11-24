"""Lease urgency only; never changes admission, merge membership or capture clocks."""

import math
import os

from config.refactor_modes import default_off

DEADLINE_SECONDS = 7200.0
MAX_DURATION_SECONDS = 7200.0
READY_OWNER_BUDGET = 16
READY_PAGE_SIZE = 8
RETRY_PAGE_SIZE = 100


def enabled() -> bool:
    return default_off('BATCH_PIPELINE_PROTECTED_SHARE_ENABLED')


def share_percent() -> int:
    try:
        value = int(os.getenv('BATCH_PIPELINE_PROTECTED_SHARE_PERCENT', '25'))
    except ValueError:
        return 25
    return value if 1 <= value <= 50 else 25


def capture_end(job: dict) -> float | None:
    """The original WorkItem clocks are immutable across enqueue/retry/repair.

    Receipt-clock recovery explicitly marks capture_time_trust=untrusted. Old
    rows without that marker retain their original capture clock, never enqueue
    or upload time. Bad/missing clocks fail closed without modifying the row.
    """
    start, duration = job.get('capture_at'), job.get('duration_seconds')
    if job.get('capture_time_trust') is not None:
        return None
    if not isinstance(start, (int, float)) or isinstance(start, bool):
        return None
    if not isinstance(duration, (int, float)) or isinstance(duration, bool):
        return None
    if not math.isfinite(start) or not math.isfinite(duration):
        return None
    if start <= 0 or not 0 < duration <= MAX_DURATION_SECONDS:
        return None
    end = start + duration
    return end if math.isfinite(end) else None


def eligible(job: dict, now: float) -> bool:
    end = capture_end(job)
    decision = job.get('compute_decision')
    return (
        end is not None
        and end <= now <= end + DEADLINE_SECONDS
        and job.get('merge_pending') is True
        and isinstance(decision, dict)
        and decision.get('outcome') in ('unattempted', 'allowed')
        and not job.get('last_policy_hold')
        and job.get('state') in ('ready', 'retry')
        and type(job.get('available_at')) in (int, float)
        and math.isfinite(job['available_at'])
        and job['available_at'] <= now
    )
