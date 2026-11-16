"""Current staging-input age; legacy admission uses enqueue time, never GCS metadata."""

import math

STAGING_BUCKET = 'based-hardware-batch-pipeline-staging'
WARNING_SECONDS = 21 * 86400
TERMINAL_SECONDS = 29 * 86400
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


def held_input_leg(job: dict) -> str | None:
    if job.get('recovery_state') not in {'held', 'failed_held'}:
        return None
    if job.get('state') == 'committed' and job.get('recovery_state') == 'held':
        return 'assignment'
    if (
        job.get('state') == 'quarantined'
        and job.get('quarantine_reason') == 'worker_failed'
        and (job.get('stt_route') or {}).get('stt_route') != 'provider'
    ):
        return 'gpu'
    return None
