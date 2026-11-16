"""Current staging-input age; legacy admission uses enqueue time, never GCS metadata."""

import json
import math
from pathlib import Path

STAGING_BUCKET = 'based-hardware-batch-pipeline-staging'
# This reviewed contract is also consumed by lifecycle validation/drift tools.
# No environment override: changing a bucket requires updating this contract first.
_CONTRACT = Path(__file__).resolve().parents[2] / 'deploy/storage-lifecycle/retention_contract.json'
LIFECYCLE_DAYS = json.loads(_CONTRACT.read_text())['batch_staging_delete_age_days']
if type(LIFECYCLE_DAYS) is not int or LIFECYCLE_DAYS <= 9:
    raise ValueError('batch staging lifecycle must exceed the nine-day warning margin')
WARNING_SECONDS = (LIFECYCLE_DAYS - 9) * 86400
TERMINAL_SECONDS = (LIFECYCLE_DAYS - 1) * 86400
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
