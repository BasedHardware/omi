"""Smart-merge telemetry: fold decisions, refresh, audit, and ancestor flatten.

Split out of ``utils.metrics`` so that module stays under its size budget;
``utils.metrics`` re-exports every public name, so existing imports keep
working. Same convention: bounded label vocabularies, never labeled by uid,
and ``record_*`` helpers never raise.
"""

from __future__ import annotations

from collections.abc import Mapping

from prometheus_client import REGISTRY, Counter, Histogram


def _reuse_or_create(factory, name: str, documentation: str, labelnames: list[str], **kwargs):
    """Module-reload-safe collector: reuse only an identical registration, else raise."""
    registered = getattr(REGISTRY, '_names_to_collectors', {})
    existing = registered.get(name) if isinstance(registered, Mapping) else None
    if existing is not None:
        if type(existing) is not factory or list(getattr(existing, '_labelnames', ())) != list(labelnames):
            raise ValueError(f'metric {name} already registered with a different shape')
        return existing
    return factory(name, documentation, labelnames, **kwargs)


# Folding a finished pendant conversation into its predecessor
# (utils/conversations/smart_merge.py, CONVERSATION_SMART_MERGE_MODE). `decision`
# is merge/keep for a Jev answer and skip when the pair never reached Jev;
# `reason` is a bounded rule or outcome id; `gap_bucket` is the recorded gap.
CONVERSATION_SMART_MERGE_LABELS = {
    'mode': frozenset({'shadow', 'merge'}),
    'decision': frozenset({'merge', 'keep', 'skip'}),
    'gap_bucket': frozenset({'2_5m', '5_15m', '15_30m', '30_60m', 'none'}),
}
CONVERSATION_SMART_MERGE_REASONS = frozenset(
    {
        'uid_not_allowed',
        'not_eligible_source',
        'not_capture_end',
        'conversation_not_eligible',
        'user_managed',
        'wake_word',
        'no_predecessor',
        'predecessor_not_completed',
        'predecessor_user_ended',
        'predecessor_refresh_pending',
        'refresh_unavailable',
        'gap_out_of_window',
        'too_few_words',
        'span_cap',
        'segment_cap',
        'fragment_cap',
        'jev_unavailable',
        'jev_same',
        'jev_different',
        'absorbed',
        'survivor_changed',
        'error',
        'flatten_ancestor_invalid',
        'flatten_ancestor_user_managed',
        'flatten_ancestor_cap',
        'flatten_content_changed',
        'wallclock_gap_negative',
        'wallclock_time_invalid',
    }
)
CONVERSATION_SMART_MERGE_REFRESH_OUTCOMES = frozenset({'refreshed', 'fenced', 'lease_busy', 'failed'})

CONVERSATION_SMART_MERGE_DECISION_TOTAL = _reuse_or_create(
    Counter,
    'omi_conversation_smart_merge_decision_total',
    'Smart-merge decisions for finished conversations by mode, decision, bounded reason and recorded-gap bucket. '
    'Never labeled by uid. Per-pod; sum() across jobs.',
    ['mode', 'decision', 'reason', 'gap_bucket'],
)
CONVERSATION_SMART_MERGE_SCORE = _reuse_or_create(
    Histogram,
    'omi_conversation_smart_merge_score',
    'Jev P(same occasion) for smart-merge candidate pairs, by mode (threshold 0.35).',
    ['mode'],
    buckets=(0.05, 0.1, 0.2, 0.25, 0.3, 0.325, 0.35, 0.375, 0.4, 0.5, 0.7, 1),
)
CONVERSATION_SMART_MERGE_REFRESH_TOTAL = _reuse_or_create(
    Counter,
    'omi_conversation_smart_merge_refresh_total',
    'Survivor refreshes after a smart merge by outcome. Never labeled by uid.',
    ['outcome'],
)


def _smart_merge_gap_bucket(gap_seconds: float | None) -> str:
    if gap_seconds is None or gap_seconds < 120 or gap_seconds > 3600:
        return 'none'
    for limit, bucket in ((300, '2_5m'), (900, '5_15m'), (1800, '15_30m')):
        if gap_seconds < limit:
            return bucket
    return '30_60m'


def record_conversation_smart_merge(
    *, mode: str, decision: str, reason: str, gap_seconds: float | None = None, p_same: float | None = None
) -> None:
    """Never raises: observability must not change a finalization outcome."""
    try:
        labels = {
            name: value if value in CONVERSATION_SMART_MERGE_LABELS[name] else 'other'
            for name, value in (('mode', mode), ('decision', decision))
        }
        labels['reason'] = reason if reason in CONVERSATION_SMART_MERGE_REASONS else 'other'
        labels['gap_bucket'] = _smart_merge_gap_bucket(gap_seconds)
        CONVERSATION_SMART_MERGE_DECISION_TOTAL.labels(**labels).inc()
        if p_same is not None:
            CONVERSATION_SMART_MERGE_SCORE.labels(mode=labels['mode']).observe(p_same)
    except Exception:
        pass


def record_conversation_smart_merge_refresh(outcome: str) -> None:
    """Never raises: observability must not change a finalization outcome."""
    try:
        CONVERSATION_SMART_MERGE_REFRESH_TOTAL.labels(
            outcome=outcome if outcome in CONVERSATION_SMART_MERGE_REFRESH_OUTCOMES else 'other'
        ).inc()
    except Exception:
        pass


# False-merge measurement (database/smart_merge_audit.py, utils/conversations/smart_merge_audit.py).
CONVERSATION_SMART_MERGE_AUDIT_OUTCOMES = frozenset(
    {'written', 'disabled', 'skipped_gate', 'skipped_invalid', 'skipped_error', 'unknown'}
)
CONVERSATION_SMART_MERGE_SURVIVOR_AGE_BUCKETS = frozenset({'lt_1h', 'lt_24h', 'lt_7d', 'gte_7d', 'unknown'})
CONVERSATION_SMART_MERGE_AUDIT_TOTAL = _reuse_or_create(
    Counter,
    'omi_conversation_smart_merge_audit_total',
    'Audit siblings for committed smart-merge absorbs by outcome. Never labeled by uid.',
    ['outcome'],
)
CONVERSATION_SMART_MERGE_SURVIVOR_DELETED_TOTAL = _reuse_or_create(
    Counter,
    'omi_conversation_smart_merge_survivor_deleted_total',
    'Purged smart-merge survivors by age since their last merge. Never labeled by uid.',
    ['age_bucket'],
)


def record_conversation_smart_merge_audit(outcome: str) -> None:
    """Never raises: observability must not change a finalization outcome."""
    try:
        CONVERSATION_SMART_MERGE_AUDIT_TOTAL.labels(
            outcome=outcome if outcome in CONVERSATION_SMART_MERGE_AUDIT_OUTCOMES else 'other'
        ).inc()
    except Exception:
        pass


def record_conversation_smart_merge_survivor_deleted(age_bucket: str) -> None:
    """Never raises: observability must not change a deletion outcome."""
    try:
        CONVERSATION_SMART_MERGE_SURVIVOR_DELETED_TOTAL.labels(
            age_bucket=age_bucket if age_bucket in CONVERSATION_SMART_MERGE_SURVIVOR_AGE_BUCKETS else 'other'
        ).inc()
    except Exception:
        pass


SMART_MERGE_FLATTEN_OUTCOMES = frozenset({'absorbed', 'rejected'})
SMART_MERGE_FLATTEN_REASONS = frozenset(
    {
        'none',
        'flatten_ancestor_invalid',
        'flatten_ancestor_user_managed',
        'flatten_ancestor_cap',
        'flatten_content_changed',
        'other',
    }
)
OMI_CONVERSATION_SMART_MERGE_FLATTEN_TOTAL = _reuse_or_create(
    Counter,
    'omi_conversation_smart_merge_flatten_total',
    'Smart-merge ancestor flatten outcomes by bounded reason. Never labeled by uid. Per-pod; sum() across jobs.',
    ['outcome', 'reason'],
)


def record_smart_merge_flatten(outcome: str, reason: str) -> None:
    """Never raises: observability must not change a merge outcome."""
    try:
        OMI_CONVERSATION_SMART_MERGE_FLATTEN_TOTAL.labels(
            outcome=outcome if outcome in SMART_MERGE_FLATTEN_OUTCOMES else 'other',
            reason=reason if reason in SMART_MERGE_FLATTEN_REASONS else 'other',
        ).inc()
    except Exception:
        pass


CONVERSATION_SMART_MERGE_WALLCLOCK_SHADOW_WOULDS = frozenset({'merge', 'kept', 'skip'})
CONVERSATION_SMART_MERGE_WALLCLOCK_SHADOW_TOTAL = _reuse_or_create(
    Counter,
    'omi_conversation_smart_merge_wallclock_shadow_total',
    'Smart-merge wall-clock shadow verdicts for proven same-recording pairs the legacy gate skipped. '
    'Never labeled by uid. Per-pod; sum() across jobs.',
    ['would', 'reason'],
)


def record_conversation_smart_merge_wallclock_shadow(would: str, reason: str) -> None:
    """Never raises: observability must not change a finalization outcome."""
    try:
        CONVERSATION_SMART_MERGE_WALLCLOCK_SHADOW_TOTAL.labels(
            would=would if would in CONVERSATION_SMART_MERGE_WALLCLOCK_SHADOW_WOULDS else 'other',
            reason=reason if reason in CONVERSATION_SMART_MERGE_REASONS else 'other',
        ).inc()
    except Exception:
        pass
