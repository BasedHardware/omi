"""Process capacity for record admission; never part of a job's policy snapshot."""

import os


def _drain_setting(name: str, default: int, maximum: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError:
        value = default
    return max(1, min(value, maximum))


def record_drain_batch() -> int:
    return _drain_setting('RECORD_DRAIN_BATCH', 100, 500)


def record_drain_concurrency() -> int:
    return _drain_setting('RECORD_DRAIN_CONCURRENCY', 16, 64)


def record_drain_lease_seconds() -> int:
    """How long a selected row stays invisible to other replicas' drain pages."""
    return max(60, _drain_setting('RECORD_DRAIN_LEASE_SECONDS', 900, 3600))


def record_drain_privacy_defer_seconds() -> int:
    """How long a privacy-blocked record_pending row leaves the drain page (privacy ruling faf00e).

    Kill switch: 0 restores the previous behavior (the blocked row stays due and is retried every pass).
    """
    try:
        value = int(os.getenv('RECORD_DRAIN_PRIVACY_DEFER_SECONDS', '900'))
    except ValueError:
        value = 900
    return max(0, min(value, 86400))


# A record_pending row whose capture upload/finalization barrier is still open cannot be
# admitted until its conversation completes and its upload sessions close. Retrying every
# 60 s re-read ~19k such rows per minute (2026-11-07). Young rows keep the fast retry.
BARRIER_RETRY_STEPS = ((600, 60), (86400, 900))
BARRIER_RETRY_MAX_SECONDS = 3600


def record_drain_barrier_backoff_enabled() -> bool:
    """Kill switch: RECORD_DRAIN_BARRIER_BACKOFF=off restores the flat 60 s retry."""
    return os.getenv('RECORD_DRAIN_BARRIER_BACKOFF', 'on').strip().lower() != 'off'


def barrier_retry_delay(age_seconds: float) -> int:
    """Retry delay for a barrier-blocked row by its record_pending age."""
    for limit, delay in BARRIER_RETRY_STEPS:
        if age_seconds < limit:
            return delay
    return BARRIER_RETRY_MAX_SECONDS


def record_drain_idle_without_progress_enabled() -> bool:
    """A full page that admitted nothing keeps the idle wait instead of rescanning at once.

    Kill switch: RECORD_DRAIN_IDLE_WITHOUT_PROGRESS=off restores "every full page runs again".
    """
    return os.getenv('RECORD_DRAIN_IDLE_WITHOUT_PROGRESS', 'on').strip().lower() != 'off'
