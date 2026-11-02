"""Retry fingerprints retained when terminal sync jobs release their claim."""

from typing import Any


def terminal_repeat_failure_kwargs(job: dict[str, Any]) -> dict[str, str | None]:
    """Carry a terminal job's strike through racing poll/task claim cleanup."""
    if job.get('status') not in {'failed', 'partial_failure'}:
        return {}
    if job.get('status') == 'failed' and job.get('reason_code') == 'sync_invalid_audio':
        return {'failure_key': 'invalid_audio'}
    result = job.get('result')
    if isinstance(result, dict) and result.get('repeat_failure_key') == 'persistent_persistence':
        return {
            'failure_key': 'persistent_persistence',
            'failure_fingerprint': result.get('repeat_failure_fingerprint'),
        }
    return {}
