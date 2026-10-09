"""Bounded labels for dream health; never include identities or provider bodies."""

from prometheus_client import Counter

DIRTY = Counter('omi_dream_dirty_enqueue_total', 'Dream dirty enqueue outcomes', ['outcome'])
PASSES = Counter('omi_dream_pass_total', 'Dream terminal pass outcomes', ['status', 'error_type'])
TOKENS = Counter('omi_dream_tokens_total', 'Observed dream model tokens')
CANARY = Counter('omi_dream_canary_total', 'Dream synthetic loop outcomes', ['status', 'stage'])

ERROR_TYPES = {
    'TimeoutError',
    'ValueError',
    'ValidationError',
    'RuntimeError',
    'PreTokenFailure',
    'ReadError',
    'ReadTimeout',
    'ConnectError',
    'ConnectTimeout',
    'PermissionDenied',
    'ServiceUnavailable',
    'NotFound',
    'DeadlineExceeded',
    'AdmissionDenied',
}


def record_pass(report):
    status = report.get('status', 'failed')
    if status not in {'complete', 'failed', 'deadline', 'not_admitted'}:
        status = 'failed'
    error = report.get('error_type')
    PASSES.labels(status, error if error in ERROR_TYPES else 'other' if error else 'none').inc()
    TOKENS.inc(max(0, int(report.get('tokens', 0))))
