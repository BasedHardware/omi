"""Bounded labels for dream health; never include identities or provider bodies."""

import logging
import json

from prometheus_client import Counter

PASSES = Counter('omi_dream_pass_total', 'Dream terminal pass outcomes', ['status', 'error_type'])
TOKENS = Counter('omi_dream_tokens_total', 'Observed dream model tokens')
CANARY = Counter('omi_dream_canary_total', 'Dream synthetic loop outcomes', ['status', 'stage'])

REJECTED = Counter('omi_dream_rejected_total', 'Dream deterministic proposal rejections', ['reason'])
REJECTION_REASONS = {
    'nonempty_field',
    'insufficient_speech',
    'placeholder',
    'ungrounded',
    'overview_format',
    'language_not_defect',
    'not_a_failure',
    'ref_leak',
    'feedback_cap',
    'privacy_rejected',
    'invalid_evidence',
}

logger = logging.getLogger(__name__)
EVIDENCE_CHARS = Counter('omi_dream_evidence_chars_total', 'Projected dream evidence characters', ['lane'])

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

    for reason, count in report.get('rejected', {}).items():
        if reason in REJECTION_REASONS:
            REJECTED.labels(reason).inc(max(0, int(count)))

    triage = max(0, int(report.get('triage_evidence_chars', 0)))
    reasoning = max(0, int(report.get('reasoning_evidence_chars', 0)))
    EVIDENCE_CHARS.labels('triage').inc(triage)
    EVIDENCE_CHARS.labels('reasoning').inc(reasoning)
    logger.info(
        'Dream pass status=%s triage_evidence_chars=%d reasoning_evidence_chars=%d '
        'dropped_invalid=%s validation_errors=%s rejected=%s poisoned=%d',
        status,
        triage,
        reasoning,
        json.dumps(report.get('dropped_invalid', {}), sort_keys=True),
        json.dumps(report.get('validation_errors', {}), sort_keys=True),
        json.dumps(report.get('rejected', {}), sort_keys=True),
        max(0, int(report.get('poisoned', 0))),
    )
