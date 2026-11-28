"""Current staging-input age; legacy admission uses enqueue time, never GCS metadata."""

import math

from config.batch_pipeline_retention import (
    LIFECYCLE_DAYS as LIFECYCLE_DAYS,
    TERMINAL_SECONDS as TERMINAL_SECONDS,
    WARNING_SECONDS as WARNING_SECONDS,
)

STAGING_BUCKET = 'based-hardware-batch-pipeline-staging'
REASON = 'input_expiring'


def input_expiring(job: dict) -> bool:
    return job.get('state') == 'dead' and job.get('dead_letter_reason') == REASON


def _clock(value: object) -> float | None:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return None
    try:
        stamp = float(value)
    except OverflowError:
        return None
    return stamp if math.isfinite(stamp) and stamp > 0 else None


def staged_at(job: dict) -> float | None:
    return _clock(job.get('audio_staged_at'))


def staged_enqueue(job: dict) -> float | None:
    uri = job.get('audio_uri')
    if not isinstance(uri, str) or not uri.startswith(f'gs://{STAGING_BUCKET}/'):
        return None
    # Corrupt replacement metadata must not hide the older admission clock.
    return staged_at(job) or _clock(job.get('enqueued_at'))


def invalid_staged_clock(job: dict) -> bool:
    uri = job.get('audio_uri')
    return (
        isinstance(uri, str)
        and uri.startswith(f'gs://{STAGING_BUCKET}/')
        and (('audio_staged_at' in job and staged_at(job) is None) or staged_enqueue(job) is None)
    )


def allowance_exhausted_retry(job: dict) -> bool:
    """Only explicit current allowance_exhausted policy holds in retry count as allowance stock."""
    if job.get('state') != 'retry':
        return False
    decision = job.get('compute_decision')
    return (
        isinstance(decision, dict)
        and decision.get('outcome') == 'held'
        and decision.get('reason') == 'allowance_exhausted'
    )


def _non_provider_route(job: dict) -> bool:
    route = job.get('stt_route')
    if route is None:
        return True
    if not isinstance(route, dict):
        return False
    return route.get('stt_route') != 'provider'


def held_input_leg(job: dict) -> str | None:
    recovery_state = job.get('recovery_state')
    if recovery_state in {'held', 'failed_held'}:
        if job.get('state') == 'committed' and recovery_state == 'held':
            return 'assignment'
        if (
            job.get('state') == 'quarantined'
            and job.get('quarantine_reason') == 'worker_failed'
            and _non_provider_route(job)
        ):
            return 'gpu'
        return None
    if recovery_state not in (None, ''):
        return None
    if job.get('result') or job.get('source_alias_of') or job.get('source_alias'):
        return None
    if (job.get('state') == 'allowance_held' or allowance_exhausted_retry(job)) and _non_provider_route(job):
        return 'allowance'
    return None
