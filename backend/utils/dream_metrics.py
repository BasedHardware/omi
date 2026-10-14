"""Bounded labels for dream health; never include identities or provider bodies."""

import logging
import json

from prometheus_client import Counter
from utils.dream_diagnostics import counts_only

PASSES = Counter('omi_dream_pass_total', 'Dream terminal pass outcomes', ['status', 'error_type'])
ABANDONED = Counter('omi_dream_abandoned_total', 'Dream abandoned leases reclaimed', ['context_mode'])

POLICY_WARNINGS = Counter('omi_dream_policy_warning_total', 'Ignored auto-apply policy kinds')

TOKENS = Counter('omi_dream_tokens_total', 'Observed dream model tokens')
RESPONSE_RETRIES = Counter('omi_dream_response_retries_total', 'Dream malformed/truncated JSON response retries')
DECISIONS = Counter('omi_dream_decision_total', 'Full-mode Dream decisions', ['decision'])
DECISION_COUNTS = ('auto_applied_unanimous', 'suggested_majority', 'questions_offered', 'questions_dropped_low_value')
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
    'invalid_spelling',
    'stale_task_evidence',
    'task_too_recent',
    'bad_target',
    'common_word',
    'context_target',
    'ungrounded_spelling',
    'edit_cap',
    'invalid_edit',
    'duplicate_edit',
    'noop',
    'contradictory_spelling',
    'invalid_question_evidence',
    'consensus_rejected',
}

logger = logging.getLogger(__name__)
EVIDENCE_CHARS = Counter('omi_dream_evidence_chars_total', 'Projected dream evidence characters', ['lane'])
RETRIEVAL = Counter(
    'omi_dream_retrieval_total', 'Dream retrieval operations and candidate dispositions', ['path', 'count']
)
RETRIEVAL_FAILURES = Counter(
    'omi_dream_retrieval_failure_total', 'Dream retrieval exception classes', ['path', 'exception_class']
)
TARGET_CONTEXT = Counter('omi_dream_target_context_total', 'Dream target retrieval coverage', ['coverage'])
DIRTY_READS = Counter('omi_dream_dirty_read_total', 'Dream queue selection dispositions', ['count'])
INPUT_CONTENT = Counter('omi_dream_input_content_total', 'Dream input content availability', ['count'])
CONTEXT_BUDGET = Counter('omi_dream_context_budget_total', 'Dream context allocation diagnostics', ['count'])

ERROR_TYPES = {
    'TimeoutError',
    'ValueError',
    'ValidationError',
    'RuntimeError',
    'PreTokenFailure',
    'CapacityWait',
    'ReadError',
    'ReadTimeout',
    'ConnectError',
    'ConnectTimeout',
    'PermissionDenied',
    'ServiceUnavailable',
    'NotFound',
    'DeadlineExceeded',
    'AdmissionDenied',
    'DreamTranscriptReadError',
    'InvalidModelResponse',
    'LeaseAbandoned',
}


# An exact allowlist, rather than logging arbitrary messages beginning with dream_.
DREAM_VALUE_ERROR_CODES = frozenset(
    {
        'dream_reasoning_budget',
        'dream_sample_plan',
        'dream_triage_budget',
        'dream_unknown_cluster',
        'dream_unknown_target',
        'dream_no_samples',
        'dream_settlement_limit',
        'dream_input_token_budget',
        'dream_model_context_budget',
        'dream_invalid_usage',
        'dream_evidence_token_budget',
        'dream_transcript_shape',
        'dream_history_collection',
        'dream_history_key',
        'dream_review_read_limit',
        'dream_temporal_collection',
        'dream_invalid_target',
        'dream_invalid_spelling',
        'dream_unknown_evidence',
        'dream_invalid_question_evidence',
        'dream_unsupported_edit',
        'dream_unsupported_spelling_target',
        'dream_invalid_task',
        'dream_invalid_memory',
        'dream_missing_duplicate',
        'dream_invalid_entity',
        'dream_invalid_entity_summary',
        'dream_invalid_person_merge',
        'dream_vocabulary_requires_acceptance',
        'dream_common_word',
        'dream_invalid_vocabulary',
        'dream_question_kind',
        'dream_frame_evidence',
        'dream_task_evidence',
        'dream_ungrounded_spelling',
        'dream_stale_task_evidence',
        'dream_task_too_recent',
        'dream_bad_target',
        'dream_canary_configuration',
        'dream_canary_existing_owner',
        'dream_summary_nonempty_field',
        'dream_summary_insufficient_speech',
        'dream_summary_placeholder',
        'dream_summary_ungrounded',
        'dream_summary_overview_format',
        'dream_summary_ref_leak',
    }
)


def error_code(exc):
    code = exc.args[0] if type(exc) is ValueError and len(exc.args) == 1 else None
    return code if isinstance(code, str) and code in DREAM_VALUE_ERROR_CODES else None


def record_pass(report):
    status = report.get('status', 'failed')
    if status not in {'complete', 'failed', 'deadline', 'not_admitted', 'waiting'}:
        status = 'failed'
    error = report.get('error_type')
    PASSES.labels(status, error if error in ERROR_TYPES else 'other' if error else 'none').inc()
    TOKENS.inc(max(0, int(report.get('tokens', 0))))
    retries = max(0, int(report.get('response_retries', 0)))
    RESPONSE_RETRIES.inc(retries)
    if report.get('context_mode') == 'full':
        for decision in DECISION_COUNTS:
            DECISIONS.labels(decision).inc(max(0, int(report.get(decision, 0))))

    for reason, count in report.get('rejected', {}).items():
        if reason in REJECTION_REASONS:
            REJECTED.labels(reason).inc(max(0, int(count)))

    triage = max(0, int(report.get('triage_evidence_chars', 0)))
    reasoning = max(0, int(report.get('reasoning_evidence_chars', 0)))
    EVIDENCE_CHARS.labels('triage').inc(triage)
    EVIDENCE_CHARS.labels('reasoning').inc(reasoning)
    diagnostics = counts_only(report)
    for path, counts in diagnostics['retrieval_counts'].items():
        for key, count in counts.items():
            RETRIEVAL.labels(path, key).inc(count)
    for path, counts in diagnostics['retrieval_failure_counts'].items():
        for name, count in counts.items():
            RETRIEVAL_FAILURES.labels(path, name).inc(count)
    for key, count in diagnostics['dirty_counts'].items():
        DIRTY_READS.labels(key).inc(count)
    for key, count in diagnostics['target_context_counts'].items():
        TARGET_CONTEXT.labels(key).inc(count)
    for key, count in diagnostics['input_content_counts'].items():
        INPUT_CONTENT.labels(key).inc(count)
    for key, count in diagnostics['context_budget_counts'].items():
        CONTEXT_BUDGET.labels(key).inc(count)
    logger.info(
        'Dream pass status=%s error_code=%s context_mode=%s input_tokens_estimate=%d targets=%d records=%d response_retries=%d '
        'samples_requested=%d samples_returned=%d samples_failed=%d consensus_threshold=%d '
        'samples_attempted=%d samples_capacity_wait=%d capacity_retries=%d '
        'triage_evidence_chars=%d reasoning_evidence_chars=%d '
        'dropped_invalid=%s validation_errors=%s rejected=%s poisoned=%d retrieval_counts=%s '
        'retrieval_failure_counts=%s dirty_counts=%s target_context_counts=%s input_content_counts=%s context_budget_counts=%s',
        status,
        report.get('error_code') if report.get('error_code') in DREAM_VALUE_ERROR_CODES else 'none',
        'full' if report.get('context_mode') == 'full' else 'bounded',
        max(0, int(report.get('input_tokens_estimate', 0))),
        max(0, int(report.get('targets', 0))),
        max(0, int(report.get('records', 0))),
        retries,
        max(0, int(report.get('samples_requested', 0))),
        max(0, int(report.get('samples_returned', 0))),
        max(0, int(report.get('samples_failed', 0))),
        max(0, int(report.get('consensus_threshold', 0))),
        max(0, int(report.get('samples_attempted', 0))),
        max(0, int(report.get('samples_capacity_wait', 0))),
        max(0, int(report.get('capacity_retries', 0))),
        triage,
        reasoning,
        json.dumps(report.get('dropped_invalid', {}), sort_keys=True),
        json.dumps(report.get('validation_errors', {}), sort_keys=True),
        json.dumps(
            {
                reason: max(0, int(count))
                for reason, count in report.get('rejected', {}).items()
                if reason in REJECTION_REASONS
            },
            sort_keys=True,
        ),
        max(0, int(report.get('poisoned', 0))),
        json.dumps(diagnostics['retrieval_counts'], sort_keys=True),
        json.dumps(diagnostics['retrieval_failure_counts'], sort_keys=True),
        json.dumps(diagnostics['dirty_counts'], sort_keys=True),
        json.dumps(diagnostics['target_context_counts'], sort_keys=True),
        json.dumps(diagnostics['input_content_counts'], sort_keys=True),
        json.dumps(diagnostics['context_budget_counts'], sort_keys=True),
    )
    if report.get('context_mode') == 'full':
        logger.info(
            'Dream decisions=%s',
            json.dumps({key: max(0, int(report.get(key, 0))) for key in DECISION_COUNTS}, sort_keys=True),
        )


def record_reclaimed(age_s, context_mode):
    PASSES.labels('failed', 'LeaseAbandoned').inc()
    ABANDONED.labels(context_mode).inc()
    logger.info('Dream lease reclaimed age_s=%d mode=%s', age_s, context_mode)
