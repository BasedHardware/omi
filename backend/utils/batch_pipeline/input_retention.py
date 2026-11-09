"""Current staging-input age; legacy admission uses enqueue time, never GCS metadata."""

import math

STAGING_BUCKET = 'based-hardware-batch-pipeline-staging'
WARNING_SECONDS = 21 * 86400
TERMINAL_SECONDS = 29 * 86400
REASON = 'input_expiring'


def input_expiring(job: dict) -> bool:
    return job.get('state') == 'dead' and job.get('dead_letter_reason') == REASON


def staged_enqueue(job: dict) -> float | None:
    uri = job.get('audio_uri')
    stamp = job.get('audio_staged_at', job.get('enqueued_at'))
    if (
        not isinstance(uri, str)
        or not uri.startswith(f'gs://{STAGING_BUCKET}/')
        or not isinstance(stamp, (int, float))
        or isinstance(stamp, bool)
        or not math.isfinite(stamp)
        or stamp <= 0
    ):
        return None
    return float(stamp)


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
