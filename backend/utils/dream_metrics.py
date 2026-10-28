"""Count-only Dream harness health with bounded labels; no owner or content labels."""

import logging
from prometheus_client import Counter, Histogram
from config.dream_agent import KNOWN_KINDS
from utils.agent_capabilities.errors import CONFLICT_CODES

logger = logging.getLogger(__name__)
PASSES = Counter('omi_dream_pass_total', 'Dream terminal outcomes', ['status', 'error_type'])
TOKENS = Counter('omi_dream_tokens_total', 'Observed billable Dream tokens')
SESSION_TOKENS = Histogram(
    'omi_dream_session_tokens',
    'Observed model tokens per owner size bucket',
    ['bucket'],
    buckets=(1000, 5000, 10000, 25000, 50000, 100000, 200000, 300000),
)
TURNS = Counter('omi_dream_turns_total', 'Dream reasoning turns')
TOOLS = Counter('omi_dream_tool_total', 'Dream tool calls', ['tool'])
REJECTED = Counter('omi_dream_rejected_total', 'Immediate proposal rejection reasons', ['reason'])
RESUBMITS = Counter('omi_dream_resubmits_succeeded_total', 'Rejected proposals successfully restaged')
DECISIONS = Counter('omi_dream_verifier_total', 'Independent verifier decisions', ['decision'])
APPLIED = Counter('omi_dream_applied_total', 'Journaled verified changes', ['kind'])
UNDO = Counter('omi_dream_undo_total', 'Applied changes undone', ['kind'])
CACHE = Counter('omi_dream_cache_tokens_total', 'Reported cache usage; unknown is separate', ['status'])
CANARY = Counter('omi_dream_canary_total', 'Synthetic harness outcomes', ['status', 'stage'])
ABANDONED = Counter('omi_dream_abandoned_total', 'Stale owner leases reclaimed')

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
    'FirestoreContentionExhausted',
    'AdmissionDenied',
    'AgentTranscriptReadError',
    'InvalidModelResponse',
    'LeaseAbandoned',
    'DestructiveOperationInProgress',
}


# An exact allowlist, rather than logging arbitrary messages beginning with dream_.
LEGACY_ERROR_CODES = frozenset(
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


BASE_VALUE_ERROR_CODES = (
    LEGACY_ERROR_CODES
    | frozenset(CONFLICT_CODES.values())
    | frozenset(
        [
            'dream_argument_budget',
            'agent_person_already_merged',
            'dream_capacity_wait',
            'dream_capture_speech_insufficient',
            'dream_capture_speech_mismatch',
            'dream_capture_time_unavailable',
            'dream_captures_do_not_overlap',
            'dream_common_word',
            'dream_contradictory_spelling',
            'dream_conversation_user_protected',
            'dream_cursor_collection',
            'dream_daily_budget',
            'dream_disabled',
            'dream_edit_cap',
            'dream_frame_evidence',
            'dream_gateway_failure',
            'dream_gateway_rejected',
            'dream_gate_contention',
            'dream_input_token_budget',
            'dream_invalid_arguments',
            'dream_invalid_cache_usage',
            'dream_invalid_conversation_merge',
            'dream_invalid_entity',
            'dream_invalid_entity_summary',
            'dream_invalid_lane',
            'dream_invalid_language_tag',
            'dream_invalid_language_target',
            'dream_invalid_memory',
            'dream_invalid_person',
            'dream_invalid_person_merge',
            'dream_invalid_question_evidence',
            'dream_invalid_spelling',
            'dream_invalid_target',
            'dream_invalid_task',
            'dream_invalid_tool_calls',
            'dream_invalid_usage',
            'dream_invalid_vocabulary',
            'dream_language_changed',
            'dream_language_speech_insufficient',
            'dream_missing_duplicate',
            'dream_person_changed',
            'dream_person_user_protected',
            'dream_proposal_cap',
            'dream_question_kind',
            'dream_reference_cap',
            'dream_response_truncated',
            'dream_search_token_budget',
            'dream_summary_insufficient_speech',
            'dream_summary_nonempty_field',
            'dream_summary_overview_format',
            'dream_summary_placeholder',
            'dream_summary_ref_leak',
            'dream_summary_ungrounded',
            'dream_suppressed',
            'dream_target_unavailable',
            'dream_task_changed',
            'dream_task_evidence',
            'dream_task_merge_metadata_mismatch',
            'dream_task_user_protected',
            'dream_unknown_cursor',
            'dream_unknown_evidence',
            'dream_unknown_person',
            'dream_unknown_tool',
            'dream_unknown_vocabulary',
            'dream_unsupported_edit',
            'dream_unsupported_spelling_target',
            'dream_vocabulary_cap',
            'dream_vocabulary_requires_acceptance',
        ]
    )
)


def record_pass(report):
    status = report.get('status', 'failed')
    status = status if status in {'complete', 'failed', 'deadline', 'not_admitted', 'waiting'} else 'failed'
    error = report.get('error_type')
    PASSES.labels(status, error if error in ERROR_TYPES else 'other' if error else 'none').inc()
    tokens = max(0, int(report.get('tokens', 0)))
    TOKENS.inc(tokens)
    bucket = report.get('size_bucket')
    if bucket in {'empty', 'light', 'medium', 'heavy'}:
        SESSION_TOKENS.labels(bucket).observe(tokens)
    TURNS.inc(max(0, int(report.get('turns', 0))))
    for tool, count in report.get('tool_counts', {}).items():
        if tool in {'search', 'read', 'propose_edit', 'ask', 'learn_term', 'finish', 'unknown'}:
            TOOLS.labels(tool).inc(max(0, int(count)))
    for reason, count in report.get('rejected', {}).items():
        # Exact source-owned reason codes only. Arbitrary exception messages
        # and model-supplied fields can never become metric labels.
        label = (
            reason
            if reason in DREAM_VALUE_ERROR_CODES or reason in {'schema', 'dream_stale_or_unavailable'}
            else 'other'
        )
        REJECTED.labels(label).inc(max(0, int(count)))
    RESUBMITS.inc(max(0, int(report.get('resubmits_succeeded', 0))))
    for decision, count in report.get('verifier_outcomes', {}).items():
        if decision in {'agree', 'split', 'disagree', 'unverified'}:
            DECISIONS.labels(decision).inc(max(0, int(count)))
    for row in report.get('outcomes', []):
        if row.get('status') == 'applied' and row.get('kind') in KNOWN_KINDS:
            APPLIED.labels(row['kind']).inc()
    for key, label in [
        ('cached_tokens', 'cached'),
        ('uncached_tokens', 'uncached'),
        ('cache_unreported_tokens', 'unreported'),
    ]:
        CACHE.labels(label).inc(max(0, int(report.get(key, 0))))
    code = report.get('error_code')
    stop = report.get('stop_reason')
    cost = report.get('cost_usd')
    logger.info(
        'Dream status=%s bucket=%s tokens=%d turns=%d tool_calls=%d verifier_calls=%d applied=%d '
        'error_type=%s error_code=%s stop_reason=%s weighted_tokens=%d cost_usd=%s',
        status,
        bucket if bucket in {'empty', 'light', 'medium', 'heavy'} else 'unknown',
        tokens,
        max(0, int(report.get('turns', 0))),
        sum(max(0, int(count)) for count in report.get('tool_counts', {}).values()),
        max(0, int(report.get('verifier_calls', 0))),
        sum(row.get('status') == 'applied' for row in report.get('outcomes', [])),
        # Source-owned codes only; exception messages never reach the log line.
        error if error in ERROR_TYPES else 'other' if error else 'none',
        code if code in DREAM_VALUE_ERROR_CODES else 'other' if code else 'none',
        (
            stop
            if isinstance(stop, str) and (stop in DREAM_VALUE_ERROR_CODES or stop.isidentifier())
            else 'other' if stop else 'none'
        ),
        max(0, int(report.get('price_weighted_tokens') or 0)),
        f'{cost:.4f}' if isinstance(cost, (int, float)) else 'unknown',
    )


DREAM_VALUE_ERROR_CODES = (
    BASE_VALUE_ERROR_CODES
    | frozenset(code.replace('dream_', 'agent_', 1) for code in BASE_VALUE_ERROR_CODES)
    | {
        'agent_target_term_missing',
        'agent_target_quote_mismatch',
        'agent_fragment_not_supported',
        'agent_unread_ref',
        'agent_question_policy',
    }
)


def record_reclaimed(age_s, size_bucket=None):
    ABANDONED.inc()
    logger.info('Dream lease reclaimed age_s=%d', age_s)


def record_undo(change):
    kind = change.edit_kind or change.kind
    UNDO.labels(kind if kind in KNOWN_KINDS else 'other').inc()


OVERLAY_READ_FAILURES = Counter(
    "agent_overlay_read_failures_total", "Original transcript rendered after projection failure"
)
