from datetime import datetime, timedelta, timezone

import pytest

from models.memory_evidence import ArtifactPreservationState, MemoryEvidence, SourceState, SourceStateReason
from models.memory_apply import (
    ApplyStatus,
    MemoryControlState,
    MemoryOutboxEventType,
    apply_long_term_patch_transaction,
    build_patch_mutation_identity,
    memory_content_hash,
)
from models.memory_contracts import DurablePatchDecision, LifecycleState
from models.memory_operations import MemoryOperation, MemoryOperationStatus, MemoryOperationType
from models.memory_promotion import PromotionGraphPlan, build_promotion_admission_receipt
from models.product_memory import MemoryItemStatus, MemoryTier, ProcessingState, MemoryItem
from utils.memory.graph_enrichment import GraphEnrichmentStatus, prepare_graph_enrichment


def _evidence():
    return MemoryEvidence(
        evidence_id="ev1",
        source_type="conversation",
        source_id="conv1",
        source_version="v1",
        artifact_preservation=ArtifactPreservationState.preserved,
    )


def _logical_payload(**overrides):
    payload = {
        "decision": DurablePatchDecision.add.value,
        "memory_text": "User prefers concise updates.",
        "target_memory_id": None,
        "result_status": LifecycleState.active.value,
        "supersedes": [],
        "subject_entity_id": "user",
        "predicate": None,
        "arguments": {},
        "target_tier": None,
    }
    payload.update(overrides)
    return payload


def _operation(**overrides):
    logical_payload = overrides.pop("logical_payload", None)
    base = dict(
        uid="u1",
        operation_type=MemoryOperationType.long_term_apply,
        source_packet_id="pkt1",
        target_memory_id=None,
        evidence_ids=["ev1"],
        logical_payload=_logical_payload(**(logical_payload or {})),
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


def _promotion_audit(
    existing: MemoryItem,
    *,
    memory_text: str,
    supersedes=None,
    source_item_revision: int | None = None,
):
    superseded_ids = list(supersedes or [])
    graph_plan = PromotionGraphPlan(
        subject_entity_id="user",
        predicate="prefers_update_style",
        arguments={"style": "concise"},
    )
    evidence_ids = [item.evidence_id for item in existing.evidence]
    receipt = build_promotion_admission_receipt(
        memory_id=existing.memory_id,
        source_item_revision=source_item_revision or existing.item_revision,
        output_content_hash=memory_content_hash(content=memory_text, evidence_ids=evidence_ids),
        evidence_ids=evidence_ids,
        graph_plan=graph_plan,
        supersedes=superseded_ids,
    )
    return {
        "graph_plan": graph_plan.model_dump(mode="json"),
        "admission_receipt": receipt.model_dump(mode="json"),
    }


def _promotion_operation(
    existing: MemoryItem,
    *,
    memory_text: str,
    supersedes=None,
    operation_type: MemoryOperationType = MemoryOperationType.synthesis,
):
    superseded_ids = list(supersedes or [])
    return _operation(
        operation_type=operation_type,
        target_memory_id=existing.memory_id,
        logical_payload={
            "decision": DurablePatchDecision.update.value,
            "memory_text": memory_text,
            "target_memory_id": existing.memory_id,
            "result_status": LifecycleState.active.value,
            "supersedes": superseded_ids,
            "subject_entity_id": "user",
            "predicate": "prefers_update_style",
            "arguments": {"style": "concise"},
            "target_tier": MemoryTier.long_term.value,
        },
    )


def _promotion_patch(
    existing: MemoryItem,
    *,
    memory_text: str,
    supersedes=None,
    promotion_audit=None,
):
    payload = _patch(
        decision=DurablePatchDecision.update,
        target_memory_id=existing.memory_id,
        memory_text=memory_text,
        target_tier=MemoryTier.long_term,
        supersedes=list(supersedes or []),
        predicate="prefers_update_style",
        arguments={"style": "concise"},
        promotion_audit=promotion_audit,
    )
    payload["existing_item"] = existing.model_dump(mode="python")
    return payload


def test_atomic_apply_commits_memory_operation_control_head_and_outbox_together():
    control = MemoryControlState(uid="u1", head_commit_id="head0", account_generation=1, source_generation=2)
    operation = _operation()

    result = apply_long_term_patch_transaction(control_state=control, operation=operation, patch_payload=_patch())

    assert result.status == ApplyStatus.committed
    assert result.operation.status == MemoryOperationStatus.committed
    assert result.control_state.head_commit_id == result.operation.committed_head_commit_id
    assert len(result.memory_items) == 1
    assert result.memory_items[0].tier == MemoryTier.short_term
    assert result.graph_assertions == []
    assert result.outbox_events[0].event_type == MemoryOutboxEventType.projection_sync
    assert result.outbox_events[1].event_type == MemoryOutboxEventType.vector_sync
    assert [event.payload["action"] for event in result.outbox_events] == ["upsert", "upsert"]
    assert all(event.commit_id == result.control_state.head_commit_id for event in result.outbox_events)


def test_atomic_apply_emits_delete_intent_for_restricted_memory_projections():
    control = MemoryControlState(uid="u1", head_commit_id="head0", account_generation=1, source_generation=2)

    result = apply_long_term_patch_transaction(
        control_state=control,
        operation=_operation(),
        patch_payload=_patch(sensitivity_labels=["credential"]),
    )

    assert result.status == ApplyStatus.committed
    assert result.memory_items[0].sensitivity_labels == ["credential"]
    actions = {event.event_type: event.payload["action"] for event in result.outbox_events}
    assert actions == {
        MemoryOutboxEventType.projection_sync: "delete",
        MemoryOutboxEventType.vector_sync: "delete",
    }


def test_apply_fails_closed_on_head_or_generation_mismatch_without_outbox():
    control = MemoryControlState(uid="u1", head_commit_id="head-new", account_generation=1, source_generation=2)
    operation = _operation()
    result = apply_long_term_patch_transaction(control_state=control, operation=operation, patch_payload=_patch())
    assert result.status == ApplyStatus.retryable_head_mismatch
    assert result.memory_items == []
    assert result.outbox_events == []
    assert result.operation.observed_head_commit_id == "head-new"
    assert result.operation.attempt_count == operation.attempt_count + 1
    assert result.operation.updated_at >= operation.updated_at

    purged = MemoryControlState(uid="u1", head_commit_id="head0", account_generation=2, source_generation=2)
    result = apply_long_term_patch_transaction(control_state=purged, operation=_operation(), patch_payload=_patch())
    assert result.status == ApplyStatus.generation_mismatch
    assert result.operation.status == MemoryOperationStatus.stale_generation


def test_apply_rejects_explicit_direct_long_term_add():
    control = MemoryControlState(uid="u1", head_commit_id="head0", account_generation=1, source_generation=2)

    result = apply_long_term_patch_transaction(
        control_state=control,
        operation=_operation(),
        patch_payload=_patch(initial_tier=MemoryTier.long_term),
    )

    assert result.status == ApplyStatus.invalid_patch
    assert result.control_state == control
    assert result.memory_items == []
    assert result.graph_assertions == []
    assert result.outbox_events == []


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


def test_patch_evidence_ids_must_exactly_match_operation_identity():
    control = MemoryControlState(uid="u1", head_commit_id="head0", account_generation=1, source_generation=2)
    operation = _operation()

    result = apply_long_term_patch_transaction(
        control_state=control,
        operation=operation,
        patch_payload=_patch(evidence_ids=["ev_other"]),
    )

    assert result.status == ApplyStatus.payload_mismatch
    assert result.reason == "patch evidence_ids do not match operation evidence_ids"
    assert result.memory_items == []


def test_skip_duplicate_advances_audit_head_with_barrier_outbox_but_no_memory_item():
    control = MemoryControlState(uid="u1", head_commit_id="head0", account_generation=1, source_generation=2)
    operation = _operation(
        target_memory_id="mem_existing",
        logical_payload={
            "decision": "skip_duplicate",
            "target_memory_id": "mem_existing",
            "memory_text": None,
            "result_status": "active",
        },
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


def _long_term_graph_item(**overrides):
    data = dict(
        tier=MemoryTier.long_term,
        expires_at=None,
        ledger_commit_id="head0",
        ledger_sequence=1,
        source_commit_id="head0",
        source_commit_sequence=1,
        subject_entity_id="user",
        predicate="prefers_update_style",
        arguments={"style": "concise"},
        graph_ready=False,
        graph_assertion_id=None,
        graph_plan_hash=None,
        kg_extracted=False,
    )
    data.update(overrides)
    return _short_term_existing(**data)


def test_graph_enrichment_commits_one_fenced_assertion_without_changing_long_term_semantics():
    control = MemoryControlState(uid="u1", head_commit_id="head0", account_generation=1, source_generation=2)
    existing = _long_term_graph_item()
    plan = PromotionGraphPlan(
        subject_entity_id="user",
        predicate="prefers_update_style",
        arguments={"style": "concise"},
    )

    planned = prepare_graph_enrichment(
        item=existing,
        plan=plan,
        account_generation=1,
        source_generation=2,
        expected_item_revision=existing.item_revision,
        expected_content_hash=existing.content_hash,
        expected_evidence_ids=["ev1"],
        observed_head_commit_id="head0",
    )

    assert planned.status == GraphEnrichmentStatus.ready
    assert planned.operation is not None
    patch_payload = {**planned.patch_payload, "evidence": existing.evidence}
    result = apply_long_term_patch_transaction(
        control_state=control,
        operation=planned.operation,
        patch_payload=patch_payload,
    )

    assert result.status == ApplyStatus.committed
    assert result.memory_items[0].content == existing.content
    assert result.memory_items[0].evidence == existing.evidence
    assert result.memory_items[0].graph_ready is True
    assert len(result.graph_assertions) == 1
    assert result.graph_assertions[0].memory_id == existing.memory_id


def test_graph_enrichment_rejects_a_plan_that_changes_existing_long_term_semantics():
    control = MemoryControlState(uid="u1", head_commit_id="head0", account_generation=1, source_generation=2)
    existing = _long_term_graph_item()
    planned = prepare_graph_enrichment(
        item=existing,
        plan=PromotionGraphPlan(
            subject_entity_id="user",
            predicate="prefers_update_style",
            arguments={"style": "concise"},
        ),
        account_generation=1,
        source_generation=2,
        observed_head_commit_id="head0",
    )
    assert planned.operation is not None
    tampered = dict(planned.patch_payload)
    tampered["arguments"] = {"style": "verbose"}
    tampered["mutation_metadata"] = build_patch_mutation_identity(tampered)
    operation = MemoryOperation.new(
        uid=planned.operation.uid,
        operation_type=planned.operation.operation_type,
        source_packet_id=planned.operation.source_packet_id,
        target_memory_id=planned.operation.target_memory_id,
        evidence_ids=planned.operation.evidence_ids,
        logical_payload=planned.operation.logical_payload.model_copy(
            update={"arguments": {"style": "verbose"}, "mutation_metadata": tampered["mutation_metadata"]}
        ),
        account_generation=planned.operation.account_generation,
        source_generation=planned.operation.source_generation,
        observed_head_commit_id=planned.operation.observed_head_commit_id,
    )

    result = apply_long_term_patch_transaction(control_state=control, operation=operation, patch_payload=tampered)

    assert result.status == ApplyStatus.invalid_patch
    assert result.graph_assertions == []


def test_short_term_to_long_term_requires_synthesis_and_commits_structured_graph_assertion():
    control = MemoryControlState(uid="u1", head_commit_id="head0", account_generation=1, source_generation=2)
    existing = _short_term_existing()
    memory_text = "User prefers concise updates."
    promotion_audit = _promotion_audit(existing, memory_text=memory_text)

    result = apply_long_term_patch_transaction(
        control_state=control,
        operation=_promotion_operation(existing, memory_text=memory_text),
        patch_payload=_promotion_patch(
            existing,
            memory_text=memory_text,
            promotion_audit=promotion_audit,
        ),
    )

    assert result.status == ApplyStatus.committed
    assert len(result.memory_items) == 1
    promoted = result.memory_items[0]
    assert promoted.tier == MemoryTier.long_term
    assert promoted.graph_ready is True
    assert promoted.kg_extracted is True
    assert len(result.graph_assertions) == 1
    assertion = result.graph_assertions[0]
    assert assertion.assertion_id == promoted.graph_assertion_id
    assert assertion.memory_id == promoted.memory_id
    assert assertion.item_revision == promoted.item_revision
    assert assertion.content_hash == promoted.content_hash
    assert assertion.subject_entity_id == "user"
    assert assertion.predicate == "prefers_update_style"
    assert assertion.arguments == {"style": "concise"}
    assert assertion.graph_plan_hash == promoted.graph_plan_hash
    assert assertion.commit_id == result.control_state.head_commit_id
    graph_records = assertion.graph_records()
    assert graph_records["nodes"]
    assert graph_records["edges"]


def test_long_term_metadata_update_refreshes_graph_assertion_fences():
    first_control = MemoryControlState(uid="u1", head_commit_id="head0", account_generation=1, source_generation=2)
    existing = _short_term_existing()
    memory_text = "User prefers concise updates."
    promoted_result = apply_long_term_patch_transaction(
        control_state=first_control,
        operation=_promotion_operation(existing, memory_text=memory_text),
        patch_payload=_promotion_patch(
            existing,
            memory_text=memory_text,
            promotion_audit=_promotion_audit(existing, memory_text=memory_text),
        ),
    )
    promoted = promoted_result.memory_items[0]
    prior_assertion = promoted_result.graph_assertions[0]
    patch_payload = _patch(
        decision=DurablePatchDecision.update,
        target_memory_id=promoted.memory_id,
        memory_text=None,
        target_visibility="public",
        expected_item_revision=promoted.item_revision,
        expected_content_hash=promoted.content_hash,
        existing_item=promoted.model_dump(mode="python"),
    )
    operation = _operation(
        operation_type=MemoryOperationType.user_mutation,
        target_memory_id=promoted.memory_id,
        observed_head_commit_id=promoted_result.control_state.head_commit_id,
        logical_payload={
            "decision": DurablePatchDecision.update.value,
            "memory_text": None,
            "target_memory_id": promoted.memory_id,
            "result_status": LifecycleState.active.value,
            "subject_entity_id": "user",
            "target_visibility": "public",
        },
    )

    result = apply_long_term_patch_transaction(
        control_state=promoted_result.control_state,
        operation=operation,
        patch_payload=patch_payload,
    )

    assert result.status == ApplyStatus.committed
    updated = result.memory_items[0]
    refreshed = result.graph_assertions[0]
    assert updated.visibility == "public"
    assert updated.item_revision == promoted.item_revision + 1
    assert refreshed.assertion_id != prior_assertion.assertion_id
    assert refreshed.item_revision == updated.item_revision
    assert refreshed.commit_id == updated.ledger_commit_id
    assert refreshed.commit_sequence == updated.ledger_sequence
    assert updated.graph_assertion_id == refreshed.assertion_id


def test_short_term_to_long_term_rejects_non_synthesis_operation_even_with_valid_admission():
    control = MemoryControlState(uid="u1", head_commit_id="head0", account_generation=1, source_generation=2)
    existing = _short_term_existing()
    memory_text = "User prefers concise updates."
    promotion_audit = _promotion_audit(existing, memory_text=memory_text)

    result = apply_long_term_patch_transaction(
        control_state=control,
        operation=_promotion_operation(
            existing,
            memory_text=memory_text,
            operation_type=MemoryOperationType.long_term_apply,
        ),
        patch_payload=_promotion_patch(
            existing,
            memory_text=memory_text,
            promotion_audit=promotion_audit,
        ),
    )

    assert result.status == ApplyStatus.invalid_patch
    assert result.memory_items == []
    assert result.graph_assertions == []


@pytest.mark.parametrize("admission_state", ["missing", "stale"])
def test_short_term_to_long_term_rejects_missing_or_stale_admission(admission_state):
    control = MemoryControlState(uid="u1", head_commit_id="head0", account_generation=1, source_generation=2)
    existing = _short_term_existing()
    memory_text = "User prefers concise updates."
    promotion_audit = None
    if admission_state == "stale":
        promotion_audit = _promotion_audit(
            existing,
            memory_text=memory_text,
            source_item_revision=existing.item_revision + 1,
        )

    result = apply_long_term_patch_transaction(
        control_state=control,
        operation=_promotion_operation(existing, memory_text=memory_text),
        patch_payload=_promotion_patch(
            existing,
            memory_text=memory_text,
            promotion_audit=promotion_audit,
        ),
    )

    assert result.status == ApplyStatus.invalid_patch
    assert result.control_state == control
    assert result.memory_items == []
    assert result.graph_assertions == []
    assert result.outbox_events == []


def test_promoting_with_supersedes_returns_survivor_and_invalidations_in_one_commit():
    control = MemoryControlState(uid="u1", head_commit_id="head0", account_generation=1, source_generation=2)
    existing = _short_term_existing()
    superseded = _short_term_existing(
        memory_id="mem_old",
        tier=MemoryTier.long_term,
        expires_at=None,
        graph_ready=True,
        graph_assertion_id="mga_old",
        graph_plan_hash="plan_old",
        kg_extracted=True,
    )
    memory_text = "User prefers concise updates."
    promotion_audit = _promotion_audit(
        existing,
        memory_text=memory_text,
        supersedes=[superseded.memory_id],
    )
    patch = _promotion_patch(
        existing,
        memory_text=memory_text,
        supersedes=[superseded.memory_id],
        promotion_audit=promotion_audit,
    )
    patch["superseded_items"] = [superseded.model_dump(mode="python")]

    result = apply_long_term_patch_transaction(
        control_state=control,
        operation=_promotion_operation(
            existing,
            memory_text=memory_text,
            supersedes=[superseded.memory_id],
        ),
        patch_payload=patch,
    )

    assert result.status == ApplyStatus.committed
    assert result.operation.committed_memory_item_ids == [existing.memory_id, superseded.memory_id]
    assert {item.memory_id for item in result.memory_items} == {existing.memory_id, superseded.memory_id}
    promoted = next(item for item in result.memory_items if item.memory_id == existing.memory_id)
    invalidated = next(item for item in result.memory_items if item.memory_id == superseded.memory_id)
    assert promoted.tier == MemoryTier.long_term
    assert promoted.status == MemoryItemStatus.active
    assert invalidated.status == MemoryItemStatus.superseded
    assert invalidated.superseded_by == promoted.memory_id
    assert invalidated.graph_ready is False
    assert invalidated.graph_assertion_id is None
    assert {event.payload["action"] for event in result.outbox_events} == {"upsert", "delete"}


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


def test_user_content_edit_demotes_and_clears_graph_assertion_in_same_apply():
    control = MemoryControlState(uid="u1", head_commit_id="head0", account_generation=1, source_generation=2)
    existing = _short_term_existing(
        tier=MemoryTier.long_term,
        expires_at=None,
        subject_entity_id="user",
        predicate="prefers",
        arguments={"style": "concise"},
        graph_ready=True,
        graph_assertion_id="mga_existing",
        graph_plan_hash="plan_existing",
        kg_extracted=True,
    )
    expires_at = existing.updated_at + timedelta(days=30)
    promotion_audit = {
        "required": True,
        "status": "pending",
        "processing_status": "pending_processing",
    }
    patch_payload = _patch(
        decision=DurablePatchDecision.update,
        target_memory_id=existing.memory_id,
        memory_text="User now prefers detailed updates.",
        subject_entity_id=None,
        predicate=None,
        arguments={},
        target_tier=MemoryTier.short_term,
        target_user_asserted=True,
        clear_graph_assertion=True,
    )
    patch_payload.update(
        {
            "existing_item": existing.model_dump(mode="python"),
            "expected_item_revision": existing.item_revision,
            "expected_content_hash": existing.content_hash,
            "promotion_audit": promotion_audit,
            "expires_at": expires_at,
            "kg_extracted": False,
        }
    )
    mutation_identity = build_patch_mutation_identity(patch_payload)
    patch_payload["mutation_metadata"] = mutation_identity
    operation = _operation(
        operation_type=MemoryOperationType.user_mutation,
        target_memory_id=existing.memory_id,
        logical_payload={
            "decision": DurablePatchDecision.update.value,
            "memory_text": "User now prefers detailed updates.",
            "target_memory_id": existing.memory_id,
            "result_status": LifecycleState.active.value,
            "subject_entity_id": None,
            "predicate": None,
            "arguments": {},
            "target_tier": MemoryTier.short_term.value,
            "target_user_asserted": True,
            "clear_graph_assertion": True,
            "mutation_metadata": mutation_identity,
        },
    )

    result = apply_long_term_patch_transaction(
        control_state=control,
        operation=operation,
        patch_payload=patch_payload,
    )

    assert result.status == ApplyStatus.committed
    updated = result.memory_items[0]
    assert updated.tier == MemoryTier.short_term
    assert updated.processing_state == ProcessingState.pending
    assert updated.expires_at == expires_at
    assert updated.user_asserted is True
    assert updated.subject_entity_id is None
    assert updated.predicate is None
    assert updated.arguments == {}
    assert updated.graph_ready is False
    assert updated.graph_assertion_id is None
    assert updated.graph_plan_hash is None
    assert updated.kg_extracted is False
    assert [event.payload["action"] for event in result.outbox_events] == ["delete", "delete"]
    assert all(event.payload["item_revision"] == updated.item_revision for event in result.outbox_events)
    assert all(event.payload["content_hash"] == updated.content_hash for event in result.outbox_events)


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
