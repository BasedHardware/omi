"""Bounded operator retries. Historical and uncertain attempts fail closed."""

from copy import deepcopy


def retryable(marker, state):
    return (
        state == 'failed_held'
        and marker.get('paid_state') == 'attempted'
        and type(marker.get('attempt_count')) is int
        and marker['attempt_count'] == 1
        and marker.get('max_attempts') == 2
        and bool(marker.get('settled_at'))
        and (marker.get('failure') or {}).get('stage') == 'provider'
        and (marker.get('failure') or {}).get('reason') in {'provider_failed', 'operation_failed'}
        and ((marker.get('recognizers') or {}).get(marker.get('paid_provider')) or {}).get('outcome')
        in {None, 'error', 'refused'}
    )


def attempted(marker, provider=None, *, max_attempts=None):
    marker.update(
        paid_state='attempted',
        attempt_count=marker.get('attempt_count', 0) + 1,
        paid_provider=provider or marker['provider'],
        max_attempts=max_attempts or marker.get('max_attempts', 1),
    )


def renewed(marker, token):
    """Rotate the fence; retain the failed receipt and immutable plan identity."""
    result = deepcopy(marker)
    result['attempt_history'] = [
        {
            key: deepcopy(marker[key])
            for key in ('token', 'started_at', 'settled_at', 'failure', 'recognizers', 'paid_state', 'attempt_count')
            if key in marker
        }
    ]
    result.setdefault('original_token', marker['token'])
    result['token'] = token
    for key in ('started_at', 'settled_at', 'failure', 'recognizers'):
        result.pop(key, None)
    return result
