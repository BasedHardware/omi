"""Live sweep admission limits; never alter durable obligations or initial enqueue."""

import math
import os

from config.batch_pipeline_retention import LIFECYCLE_SECONDS

DEFAULT_MAX_AGE_DAYS = 14.0


def enabled() -> bool:
    """Default on; only explicit off restores the previous sweep behavior."""
    return os.getenv('BATCH_PIPELINE_SWEEP_AGE_GATE', 'on').strip().lower() != 'off'


def _days(raw: str) -> float:
    try:
        days = float(raw)
    except ValueError:
        return DEFAULT_MAX_AGE_DAYS
    return days if math.isfinite(days) and 0 < days <= 3650 else DEFAULT_MAX_AGE_DAYS


def max_age_seconds(queue: str) -> float:
    if queue == 'provider-stt':
        # Recovery must reach the final provider recheck without exceeding audio retention.
        # A separate day override could strand still-live inputs or outlive the bucket.
        return float(LIFECYCLE_SECONDS)
    elif queue == 'enrichment-fresh':
        days = _days(os.getenv('BATCH_PIPELINE_ENRICHMENT_FRESH_SWEEP_MAX_AGE_DAYS', '14'))
    else:
        raise ValueError('unknown sweep age queue')
    return days * 86400
