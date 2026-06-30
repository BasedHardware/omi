from datetime import datetime, timedelta, timezone

import pytest

from models.memory_evidence import ArtifactPreservationState, MemoryEvidence, SourceState, SourceStateReason
from models.memory_apply import (
    ApplyStatus,
    MemoryControlState,
    MemoryOutboxEventType,
    apply_long_term_patch_transaction,
)
from models.memory_contracts import DurablePatchDecision, LifecycleState
from models.memory_operations import MemoryOperation, MemoryOperationStatus, MemoryOperationType
from models.product_memory import MemoryItemStatus, MemoryTier, ProcessingState, MemoryItem, new_memory_id


def _evidence():
    return MemoryEvidence(
        evidence_id="ev1",
        source_type="conversation",
        source_id="conv1",
        source_version="v1",
        artifact_preservation=ArtifactPreservationState.preserved,
    )


def _operation(**overrides):
    base = dict(
        uid="u1",
        operation_type=MemoryOperationType.long_term_apply,
        source_packet_id="pkt1",
        target_memory_id=None,
        evidence_ids=["ev1"],
        logical_payload={"decision": "add", "memory_text": "User prefers concise updates.", "result_status": "active"},
        account_generation=1,
        source_generation=2,
        observed_head_commit_id="head0",
    )
    base.update(overrides)
    return MemoryOperation.new(**base)


def _patch(**overrides):
    payload = dict(
        patch_id="patch1",
        packet_id="pkt1",
        run_id="run1",
        observed_head_commit_id="head0",
        idempotency_key="idem1",
        decision=DurablePatchDecision.add,
        result_status=LifecycleState.active,
        evidence_ids=["ev1"],
        memory_text="User prefers concise updates.",
        confidence="medium",
        relationship_to_user="self",
        subject_entity_id="user",
        subject_label="the user",
        aboutness="primary_user",
    )
    payload.update(overrides)
    return payload


def test_atomic_apply_commits_memory_operation_control_head_and_outbox_together():
    control = MemoryControlState(uid="u1", head_commit_id="head0", account_generation=1, source_generation=2)
    operation = _operation()

    result = apply_long_term_patch_transaction(control_state=control, operation=operation, patch_payload=_patch())

    assert result.status == ApplyStatus.committed
    assert result.operation.status == MemoryOperationStatus.committed
    assert result.control_state.head_commit_id == result.operation.committed_head_commit_id
    assert len(result.memory_items) == 1
    assert result.memory_items[0].tier == MemoryTier.long_term
    assert result.outbox_events[0].event_type == MemoryOutboxEventType.projection_sync
    assert result.outbox_events[1].event_type == MemoryOutboxEventType.vector_sync
    assert all(event.commit_id == result.control_state.head_commit_id for event in result.outbox_events)


def test_apply_fails_closed_on_head_or_generation_mismatch_without_outbox():
    control = MemoryControlState(uid="u1", head_commit_id="head-new", account_generation=1, source_generation=2)
    result = apply_long_term_patch_transaction(control_state=control, operation=_operation(), patch_payload=_patch())
    assert result.status == ApplyStatus.retryable_head_mismatch
    assert result.memory_items == []
    assert result.outbox_events == []

    purged = MemoryControlState(uid="u1", head_commit_id="head0", account_generation=2, source_generation=2)
    result = apply_long_term_patch_transaction(control_state=purged, operation=_operation(), patch_payload=_patch())
    assert result.status == ApplyStatus.generation_mismatch
    assert result.operation.status == MemoryOperationStatus.stale_generation


def test_apply_rejects_deleted_or_purged_sources_before_memory_creation():
    control = MemoryControlState(uid="u1", head_commit_id="head0", account_generation=1, source_generation=2)
    tombstoned = _patch(
        evidence=[
            _evidence().model_copy(
                update={
                    "source_state": SourceState.tombstoned,
                    "source_state_reason": SourceStateReason.deleted_by_user,
                    "artifact_preservation": ArtifactPreservationState.deleted_by_user,
                }
            )
        ]
    )

    result = apply_long_term_patch_transaction(control_state=control, operation=_operation(), patch_payload=tombstoned)

    assert result.status == ApplyStatus.source_not_active
    assert result.memory_items == []
    assert result.outbox_events == []


def test_new_commit_persists_replay_metadata_on_committed_operation():
    control = MemoryControlState(uid="u1", head_commit_id="head0", account_generation=1, source_generation=2)
    operation = _operation()

    result = apply_long_term_patch_transaction(control_state=control, operation=operation, patch_payload=_patch())

    assert result.status == ApplyStatus.committed
    assert result.operation.committed_sequence == result.control_state.commit_sequence
    assert result.operation.committed_memory_item_ids == [result.memory_items[0].memory_id]
    assert result.operation.committed_outbox_event_ids == [event.event_id for event in result.outbox_events]


def test_materialized_memory_item_carries_control_account_generation_for_future_fence_checks():
    control = MemoryControlState(uid="u1", head_commit_id="head0", account_generation=7, source_generation=2)
    operation = _operation(account_generation=7)

    result = apply_long_term_patch_transaction(control_state=control, operation=operation, patch_payload=_patch())

    assert result.status == ApplyStatus.committed
    assert result.memory_items[0].account_generation == 7


def test_apply_is_idempotent_when_operation_already_committed():
    control = MemoryControlState(uid="u1", head_commit_id="head1", account_generation=1, source_generation=2)
    committed = _operation().mark_committed(
        "head1",
        committed_sequence=7,
        committed_memory_item_ids=["mem_existing"],
        committed_outbox_event_ids=["evt_projection", "evt_vector"],
    )

    result = apply_long_term_patch_transaction(control_state=control, operation=committed, patch_payload=_patch())

    assert result.status == ApplyStatus.idempotent_skip
    assert result.operation.committed_sequence == 7
    assert result.operation.committed_memory_item_ids == ["mem_existing"]
    assert result.operation.committed_outbox_event_ids == ["evt_projection", "evt_vector"]
    assert result.memory_items == []
    assert result.outbox_events == []


def test_control_state_rejects_blank_gap_or_backwards_projection_watermark():
    control = MemoryControlState(uid="u1", head_commit_id="head0", account_generation=1, source_generation=2)
    result = apply_long_term_patch_transaction(control_state=control, operation=_operation(), patch_payload=_patch())
    event = result.outbox_events[0]
    advanced = control.advance_projection_watermark(event)
    assert advanced.projection_watermark_commit_id == event.commit_id

    blank_event = event.model_copy(update={"commit_id": ""})
    with pytest.raises(ValueError, match="blank"):
        control.advance_projection_watermark(blank_event)
    gap_event = event.model_copy(update={"commit_sequence": 2})
    with pytest.raises(ValueError, match="skip|backwards"):
        control.advance_projection_watermark(gap_event)


def test_committed_operation_with_different_patch_payload_is_payload_mismatch_not_idempotent():
    control = MemoryControlState(uid="u1", head_commit_id="head1", account_generation=1, source_generation=2)
    committed = _operation().mark_committed("head1", committed_sequence=1)
    different_patch = _patch(memory_text="User prefers verbose updates.")

    result = apply_long_term_patch_transaction(
        control_state=control, operation=committed, patch_payload=different_patch
    )

    assert result.status == ApplyStatus.payload_mismatch


def test_skip_duplicate_advances_audit_head_with_barrier_outbox_but_no_memory_item():
    control = MemoryControlState(uid="u1", head_commit_id="head0", account_generation=1, source_generation=2)
    operation = _operation(
        target_memory_id="mem_existing",
        logical_payload={"decision": "skip_duplicate", "target_memory_id": "mem_existing", "result_status": "active"},
    )
    patch = _patch(
        decision=DurablePatchDecision.skip_duplicate,
        target_memory_id="mem_existing",
        memory_text=None,
    )

    result = apply_long_term_patch_transaction(control_state=control, operation=operation, patch_payload=patch)

    assert result.status == ApplyStatus.committed
    assert result.memory_items == []
    assert [event.payload["action"] for event in result.outbox_events] == ["barrier", "barrier"]


def test_firestore_transaction_retry_produces_identical_memory_commit_and_outbox_ids():
    control = MemoryControlState(uid="u1", head_commit_id="head0", account_generation=1, source_generation=2)
    operation = _operation()
    patch = _patch()

    first = apply_long_term_patch_transaction(control_state=control, operation=operation, patch_payload=patch)
    retry = apply_long_term_patch_transaction(control_state=control, operation=operation, patch_payload=patch)

    assert first.status == ApplyStatus.committed
    assert retry.status == ApplyStatus.committed
    assert first.control_state.head_commit_id == retry.control_state.head_commit_id
    assert [item.memory_id for item in first.memory_items] == [item.memory_id for item in retry.memory_items]
    assert [event.event_id for event in first.outbox_events] == [event.event_id for event in retry.outbox_events]
    assert first.operation.committed_memory_item_ids == retry.operation.committed_memory_item_ids
    assert first.operation.committed_outbox_event_ids == retry.operation.committed_outbox_event_ids


def _short_term_existing(**overrides):
    now = datetime.now(timezone.utc)
    data = dict(
        memory_id="mem_st",
        uid="u1",
        version=1,
        tier=MemoryTier.short_term,
        status=MemoryItemStatus.active,
        processing_state=ProcessingState.processed,
        content="Short term fact.",
        evidence=[_evidence()],
        source_state=SourceState.active,
        sensitivity_labels=[],
        visibility="private",
        user_asserted=False,
        captured_at=now,
        updated_at=now,
        expires_at=now + timedelta(days=30),
        ledger_commit_id="head0",
        ledger_sequence=1,
        source_commit_id="head0",
        source_commit_sequence=1,
        content_hash="hash1",
        account_generation=1,
    )
    data.update(overrides)
    return MemoryItem(**data)


def test_update_without_target_tier_preserves_existing_short_term_tier():
    control = MemoryControlState(uid="u1", head_commit_id="head0", account_generation=1, source_generation=2)
    existing = _short_term_existing()
    operation = _operation(
        target_memory_id="mem_st",
        logical_payload={
            "decision": "update",
            "target_memory_id": "mem_st",
            "memory_text": "Updated text only.",
            "result_status": "active",
        },
    )
    patch_payload = _patch(
        decision=DurablePatchDecision.update,
        target_memory_id="mem_st",
        memory_text="Updated text only.",
    )
    patch_payload["existing_item"] = existing.model_dump(mode="python")

    result = apply_long_term_patch_transaction(control_state=control, operation=operation, patch_payload=patch_payload)

    assert result.status == ApplyStatus.committed
    assert result.memory_items[0].tier == MemoryTier.short_term
    assert result.memory_items[0].content == "Updated text only."
    assert result.memory_items[0].expires_at is not None


def test_update_with_blank_memory_text_preserves_existing_content():
    control = MemoryControlState(uid="u1", head_commit_id="head0", account_generation=1, source_generation=2)
    existing = _short_term_existing()
    operation = _operation(
        target_memory_id="mem_st",
        logical_payload={
            "decision": "update",
            "target_memory_id": "mem_st",
            "memory_text": "",
            "result_status": "active",
        },
    )
    patch_payload = _patch(
        decision=DurablePatchDecision.update,
        target_memory_id="mem_st",
        memory_text="",
    )
    patch_payload["existing_item"] = existing.model_dump(mode="python")

    result = apply_long_term_patch_transaction(control_state=control, operation=operation, patch_payload=patch_payload)

    assert result.status == ApplyStatus.committed
    assert result.memory_items[0].content == existing.content
