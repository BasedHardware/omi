from datetime import datetime, timedelta, timezone

from models.memory_evidence import ArtifactPreservationState, MemoryEvidence, SourceState, SourceStateReason
from models.product_memory import MemoryItemStatus, MemoryTier, ProcessingState, MemoryItem
from utils.memory.short_term_lifecycle import (
    DEFAULT_SHORT_TERM_TTL_DAYS,
    ShortTermDisposition,
    ShortTermLifecycleOutcome,
    evaluate_short_term_lifecycle,
)

NOW = datetime(2026, 6, 19, 12, 0, tzinfo=timezone.utc)
CAPTURED_AT = NOW - timedelta(days=1)


def _evidence(source_state: SourceState = SourceState.active) -> MemoryEvidence:
    data = {
        'evidence_id': 'ev_1',
        'source_type': 'conversation',
        'source_id': 'conversation_1',
        'source_version': '1',
        'conversation_id': 'conversation_1',
        'artifact_preservation': ArtifactPreservationState.preserved,
        'source_state': source_state,
    }
    if source_state != SourceState.active:
        data.update(
            {
                'source_version': None,
                'source_state_reason': SourceStateReason.deleted_by_user,
            }
        )
    return MemoryEvidence(**data)


def _short_term_item(**overrides) -> MemoryItem:
    captured_at = overrides.pop('captured_at', CAPTURED_AT)
    source_state = overrides.get('source_state', SourceState.active)
    data = {
        'memory_id': 'mem_short_1',
        'uid': 'user_1',
        'version': 1,
        'tier': MemoryTier.short_term,
        'status': MemoryItemStatus.active,
        'processing_state': ProcessingState.pending,
        'content': 'User is evaluating the lifecycle policy.',
        'evidence': [_evidence(source_state)],
        'source_state': source_state,
        'sensitivity_labels': [],
        'visibility': 'private',
        'user_asserted': False,
        'captured_at': captured_at,
        'updated_at': captured_at,
        'expires_at': captured_at + timedelta(days=DEFAULT_SHORT_TERM_TTL_DAYS),
    }
    data.update(overrides)
    return MemoryItem(**data)


def test_fresh_short_term_remains_default_accessible_until_expiry():
    item = _short_term_item()

    decision = evaluate_short_term_lifecycle(item, now=NOW)

    assert decision.outcome == ShortTermLifecycleOutcome.remain_short_term
    assert decision.default_access_allowed is True
    assert decision.requires_lifecycle_decision is False
    assert decision.audit_metadata['memory_id'] == item.memory_id
    assert decision.audit_metadata['decision_reason'] == 'short_term_fresh'


def test_stale_short_term_is_default_excluded_and_requires_lifecycle_decision():
    item = _short_term_item(captured_at=NOW - timedelta(days=31))

    decision = evaluate_short_term_lifecycle(item, now=NOW)

    assert decision.outcome == ShortTermLifecycleOutcome.remain_short_term
    assert decision.default_access_allowed is False
    assert decision.requires_lifecycle_decision is True
    assert decision.audit_metadata['decision_reason'] == 'short_term_expired_requires_lifecycle_decision'


def test_l2_processed_item_routes_to_provided_disposition():
    item = _short_term_item(processing_state=ProcessingState.processed)

    promote = evaluate_short_term_lifecycle(item, now=NOW, disposition=ShortTermDisposition.promote_to_long_term)
    archive = evaluate_short_term_lifecycle(item, now=NOW, disposition=ShortTermDisposition.archive)
    hidden = evaluate_short_term_lifecycle(item, now=NOW, disposition=ShortTermDisposition.reject_or_hide)

    assert promote.outcome == ShortTermLifecycleOutcome.promote_to_long_term
    assert promote.default_access_allowed is False
    assert archive.outcome == ShortTermLifecycleOutcome.archive
    assert archive.default_access_allowed is False
    assert hidden.outcome == ShortTermLifecycleOutcome.reject_or_hide
    assert hidden.default_access_allowed is False
    assert promote.audit_metadata['decision_reason'] == 'l2_processed_promote_to_long_term'


def test_source_tombstoned_item_routes_to_tombstone_and_default_excluded():
    item = _short_term_item(source_state=SourceState.tombstoned)

    decision = evaluate_short_term_lifecycle(item, now=NOW)

    assert decision.outcome == ShortTermLifecycleOutcome.source_tombstoned
    assert decision.default_access_allowed is False
    assert decision.requires_lifecycle_decision is False
    assert decision.audit_metadata['decision_reason'] == 'source_tombstoned'


def test_lifecycle_decisions_are_idempotent_and_deterministic():
    item = _short_term_item(processing_state=ProcessingState.processed)

    first = evaluate_short_term_lifecycle(item, now=NOW, disposition='archive')
    second = evaluate_short_term_lifecycle(item, now=NOW, disposition=ShortTermDisposition.archive)

    assert first == second
    assert first.audit_metadata == second.audit_metadata
    assert first.audit_metadata['policy_version'] == 'short_term_lifecycle.v1'
