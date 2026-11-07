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
