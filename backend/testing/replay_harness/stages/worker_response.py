"""Closed-vocabulary worker diagnostics; no response text reaches a report."""

import json

# routers/conversation_finalization.py: run_listen_finalization_job and
# database/conversation_finalization_jobs.py: _claim_finalization_job_txn.
STATUSES = frozenset(
    {
        'priority_wait',
        'locked',
        'leased',
        'acked',
        'dropped',
        'skipped',
        'completion_conflict',
        'deferred',
        'dead_letter',
        'retry',
        'done',
        'invalid_payload',
        'invalid_enrichment_task',
    }
)
REASONS = frozenset(
    {
        'invalid_payload',
        'stale_generation',
        'account_cutover',
        'account_pending_deletion',
        'identity_mismatch',
        'fenced',
        'blocked_byok',
        'missing',
        'not_actionable',
        'completed',
        'dead_letter',
        'persistence_fenced',
    }
)


def read_worker_response(response):
    try:
        value = json.loads(response.body)
    except (ValueError, TypeError, AttributeError, UnicodeDecodeError):
        value = {}
    if not isinstance(value, dict):
        value = {}
    raw_status, raw_reason = value.get('status'), value.get('reason')
    status = raw_status if isinstance(raw_status, str) and raw_status in STATUSES else 'unknown'
    reason = raw_reason if isinstance(raw_reason, str) and raw_reason in REASONS else None
    job_status = 'completed' if value.get('job_status') == 'completed' else None
    return {'status': status, 'reason': reason, 'job_status': job_status}


def worker_precondition(body):
    status, reason = body['status'], body['reason']
    if status == 'done':
        return None
    if status == 'acked':
        return 'already_completed'
    if status in {'skipped', 'dropped'}:
        return reason or 'unknown_' + status
    if status == 'retry':
        return reason or 'worker_retry'
    if status != 'unknown':
        return status
    return None
