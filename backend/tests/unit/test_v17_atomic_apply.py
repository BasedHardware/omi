from datetime import datetime, timedelta, timezone

import pytest

from models.memory_evidence import ArtifactPreservationState, MemoryEvidence, SourceState, SourceStateReason
from models.v17_memory_apply import (
    ApplyStatus,
    MemoryControlState,
    MemoryOutboxEventType,
    apply_long_term_patch_transaction,
)
from models.v17_memory_contracts import DurablePatchDecision, LifecycleState
from models.v17_memory_operations import MemoryOperation, MemoryOperationStatus, MemoryOperationType
from models.v17_product_memory import MemoryItemStatus, MemoryTier, V17MemoryItem, new_memory_id


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
    assert result.status == ApplyStatus.head_mismatch
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


def test_apply_is_idempotent_when_operation_already_committed():
    control = MemoryControlState(uid="u1", head_commit_id="head1", account_generation=1, source_generation=2)
    committed = _operation().mark_committed("head1")

    result = apply_long_term_patch_transaction(control_state=control, operation=committed, patch_payload=_patch())

    assert result.status == ApplyStatus.idempotent_skip
    assert result.memory_items == []
    assert result.outbox_events == []


def test_control_state_rejects_blank_or_backwards_projection_watermark():
    control = MemoryControlState(uid="u1", head_commit_id="head0", account_generation=1, source_generation=2)
    advanced = control.advance_projection_watermark("head0", projection_sequence=1)
    assert advanced.projection_watermark_commit_id == "head0"

    with pytest.raises(ValueError, match="blank"):
        control.advance_projection_watermark("", projection_sequence=1)
    with pytest.raises(ValueError, match="backwards"):
        advanced.advance_projection_watermark("head0", projection_sequence=0)
