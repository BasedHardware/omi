import copy
from datetime import datetime, timedelta, timezone

import pytest

import database.memory_apply_store as memory_apply_store
from database import document_store
from tests.store_fakes import FakeDocumentStore

from models.memory_evidence import ArtifactPreservationState, MemoryEvidence, SourceState, SourceStateReason
from utils.memory.v3.account_generation_source import read_memory_v3_trusted_account_generation
from models.memory_apply import ApplyStatus, MemoryControlState
from models.memory_contracts import DurablePatchDecision, LifecycleState
from models.memory_operations import MemoryOperation, MemoryOperationType
from models.product_memory import MemoryItemStatus, MemoryTier, ProcessingState, MemoryItem


@pytest.fixture
def store():
    """The real ``database.memory_apply_store`` module.

    After the storage-port migration the module drives ``_store().run_transaction``
    with no injected client, so tests exercise it through a ``FakeDocumentStore``
    installed at the ``_store`` seam (see ``_install``). Firestore transaction
    atomicity is now the adapter's responsibility, covered by the live contract
    test (``tests/contract/test_document_store_contract.py``).
    """
    return memory_apply_store


def _install(monkeypatch, docs):
    """Install one FakeDocumentStore over ``docs`` at every ``_store`` seam this suite reads."""
    fake = FakeDocumentStore(backing=docs)
    monkeypatch.setattr(memory_apply_store, "_store", lambda: fake)
    monkeypatch.setattr(document_store, "_store", lambda: fake)
    return fake


def _evidence(**overrides):
    data = dict(
        evidence_id="ev1",
        source_type="conversation",
        source_id="conv1",
        source_version="v1",
        artifact_preservation=ArtifactPreservationState.preserved,
    )
    data.update(overrides)
    return MemoryEvidence(**data)


def _operation(**overrides):
    data = dict(
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
    data.update(overrides)
    return MemoryOperation.new(**data)


def _patch(**overrides):
    data = dict(
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
    data.update(overrides)
    return data


def _stored_model(model):
    return model.model_dump(mode="json")


def _docs_with(control=None, operation=None, evidence=None, target_items=None):
    control = control or MemoryControlState(uid="u1", head_commit_id="head0", account_generation=1, source_generation=2)
    operation = operation or _operation()
    evidence = evidence or _evidence()
    docs = {
        "users/u1/memory_state/apply_control": _stored_model(control),
        f"users/u1/memory_operations/{operation.operation_id}": _stored_model(operation),
        "users/u1/memory_evidence/ev1": _stored_model(evidence),
    }
    for target_item in target_items or []:
        docs[f"users/u1/memory_items/{target_item.memory_id}"] = _stored_model(target_item)
    return docs


def _target_item(**overrides):
    now = datetime.now(timezone.utc)
    data = dict(
        memory_id="mem1",
        uid="u1",
        version=1,
        tier=MemoryTier.long_term,
        status=MemoryItemStatus.active,
        processing_state=ProcessingState.processed,
        content="User prefers concise updates.",
        evidence=[_evidence()],
        source_state=SourceState.active,
        sensitivity_labels=[],
        visibility="private",
        user_asserted=False,
        captured_at=now,
        updated_at=now,
        ledger_commit_id="head0",
        ledger_sequence=1,
        source_commit_id="head0",
        source_commit_sequence=1,
        content_hash="hash1",
        account_generation=1,
    )
    data.update(overrides)
    return MemoryItem(**data)


def test_firestore_apply_reads_authoritative_docs_and_writes_commit_projection_operation_and_outbox_atomically(
    store, monkeypatch
):
    operation = _operation()
    docs = _docs_with(operation=operation)
    fake = _install(monkeypatch, docs)

    result = store.apply_long_term_patch_firestore(
        uid="u1",
        operation_id=operation.operation_id,
        patch_payload=_patch(),
    )

    assert result.status == ApplyStatus.committed
    written_paths = set(fake._docs)
    assert "users/u1/memory_state/apply_control" in written_paths
    assert f"users/u1/memory_operations/{operation.operation_id}" in written_paths
    assert any(path.startswith("users/u1/memory_items/") for path in written_paths)
    assert any(path.startswith("users/u1/memory_outbox/") for path in written_paths)
    assert any(path.startswith("users/u1/memory_commits/") for path in written_paths)
    assert "users/u1/memory_state/head" in written_paths

    state_head = fake._docs["users/u1/memory_state/head"]
    assert state_head == {
        "schema_version": 1,
        "uid": "u1",
        "source": "memory_state_head",
        "account_generation": result.control_state.account_generation,
        "head_commit_id": result.control_state.head_commit_id,
        "commit_sequence": result.control_state.commit_sequence,
        "updated_at": result.control_state.updated_at,
    }

    trusted = read_memory_v3_trusted_account_generation(uid="u1", db_client=None)
    assert trusted.read_error_reason is None
    assert trusted.account_generation == result.control_state.account_generation
    assert trusted.head_commit_id == result.control_state.head_commit_id
    assert trusted.commit_sequence == result.control_state.commit_sequence


def test_firestore_apply_uses_stored_evidence_not_caller_payload_and_does_not_write_domain_rows_when_source_purged(
    store, monkeypatch
):
    operation = _operation()
    purged_evidence = _evidence(
        source_state=SourceState.purged,
        source_state_reason=SourceStateReason.account_purged,
        artifact_preservation=ArtifactPreservationState.deleted_by_user,
    )
    docs = _docs_with(operation=operation, evidence=purged_evidence)
    fake = _install(monkeypatch, docs)
    caller_claims_active = _patch(evidence=[_evidence()])

    result = store.apply_long_term_patch_firestore(
        uid="u1",
        operation_id=operation.operation_id,
        patch_payload=caller_claims_active,
    )

    assert result.status == ApplyStatus.source_not_active
    # Only the operation row is written back; no domain rows / commit / state-head.
    assert "users/u1/memory_state/head" not in fake._docs
    assert not any(p.startswith("users/u1/memory_commits/") for p in fake._docs)
    assert not any(p.startswith("users/u1/memory_outbox/") for p in fake._docs)
    assert not any(p.startswith("users/u1/memory_items/") for p in fake._docs)


def test_firestore_apply_reads_target_memory_and_fails_closed_when_target_is_missing(store, monkeypatch):
    operation = _operation(
        target_memory_id="mem1",
        logical_payload={
            "decision": "update",
            "target_memory_id": "mem1",
            "memory_text": "Updated.",
            "result_status": "active",
        },
    )
    docs = _docs_with(operation=operation)
    fake = _install(monkeypatch, docs)
    patch = _patch(decision=DurablePatchDecision.update, target_memory_id="mem1", memory_text="Updated.")

    result = store.apply_long_term_patch_firestore(
        uid="u1",
        operation_id=operation.operation_id,
        patch_payload=patch,
    )

    assert result.status == ApplyStatus.target_not_active
    assert "users/u1/memory_state/head" not in fake._docs
    assert not any(p.startswith("users/u1/memory_commits/") for p in fake._docs)
    assert not any(p.startswith("users/u1/memory_outbox/") for p in fake._docs)
    assert not any(p.startswith("users/u1/memory_items/") for p in fake._docs)


def test_firestore_apply_allows_update_when_target_is_authoritative_active_same_generation(store, monkeypatch):
    operation = _operation(
        target_memory_id="mem1",
        logical_payload={
            "decision": "update",
            "target_memory_id": "mem1",
            "memory_text": "Updated.",
            "result_status": "active",
        },
    )
    docs = _docs_with(operation=operation, target_items=[_target_item()])
    _install(monkeypatch, docs)
    patch = _patch(decision=DurablePatchDecision.update, target_memory_id="mem1", memory_text="Updated.")

    result = store.apply_long_term_patch_firestore(
        uid="u1",
        operation_id=operation.operation_id,
        patch_payload=patch,
    )

    assert result.status == ApplyStatus.committed


def test_firestore_apply_update_keeps_persisted_timestamps_monotonic_when_apply_clock_is_behind(store, monkeypatch):
    captured_at = datetime(2026, 8, 21, 1, 24, 2, 685960, tzinfo=timezone(timedelta(hours=5, minutes=30)))
    prior_updated_at = captured_at + timedelta(minutes=1)
    expires_at = captured_at + timedelta(days=30)
    operation = _operation(
        target_memory_id="mem1",
        logical_payload={
            "decision": "update",
            "target_memory_id": "mem1",
            "memory_text": "Updated.",
            "result_status": "active",
        },
    )
    existing = _target_item(
        tier=MemoryTier.short_term,
        captured_at=captured_at,
        updated_at=prior_updated_at,
        expires_at=expires_at,
    )
    docs = _docs_with(operation=operation, target_items=[existing])
    fake = _install(monkeypatch, docs)
    patch = _patch(decision=DurablePatchDecision.update, target_memory_id="mem1", memory_text="Updated.")

    import models.memory_apply as memory_apply

    class _EarlierApplyClock(datetime):
        @classmethod
        def now(cls, tz=None):
            assert tz is timezone.utc
            return captured_at.astimezone(timezone.utc) - timedelta(days=1)

    monkeypatch.setattr(memory_apply, "datetime", _EarlierApplyClock)

    result = store.apply_long_term_patch_firestore(
        uid="u1",
        operation_id=operation.operation_id,
        patch_payload=patch,
    )

    assert result.status == ApplyStatus.committed
    persisted = fake._docs["users/u1/memory_items/mem1"]
    restored = MemoryItem(**persisted)
    assert restored.expires_at == expires_at
    assert restored.updated_at >= captured_at
    assert restored.updated_at >= prior_updated_at


def test_firestore_apply_retries_committed_operation_from_stored_result_without_rereading_mutable_evidence_or_target(
    store, monkeypatch
):
    operation = _operation(
        target_memory_id="mem1",
        logical_payload={
            "decision": "update",
            "target_memory_id": "mem1",
            "memory_text": "Updated.",
            "result_status": "active",
        },
    ).mark_committed(
        "head1",
        committed_sequence=5,
        committed_memory_item_ids=["mem1"],
        committed_outbox_event_ids=["evt_projection", "evt_vector"],
    )
    purged_evidence = _evidence(
        source_state=SourceState.purged,
        source_state_reason=SourceStateReason.account_purged,
        artifact_preservation=ArtifactPreservationState.deleted_by_user,
    )
    control = MemoryControlState(uid="u1", head_commit_id="head1", account_generation=1, source_generation=2)
    docs = _docs_with(control=control, operation=operation, evidence=purged_evidence)
    fake = _install(monkeypatch, docs)
    before = copy.deepcopy(fake._docs)
    patch = _patch(decision=DurablePatchDecision.update, target_memory_id="mem1", memory_text="Updated.")

    result = store.apply_long_term_patch_firestore(
        uid="u1",
        operation_id=operation.operation_id,
        patch_payload=patch,
    )

    assert result.status == ApplyStatus.idempotent_skip
    assert result.operation.committed_sequence == 5
    assert result.operation.committed_memory_item_ids == ["mem1"]
    assert result.operation.committed_outbox_event_ids == ["evt_projection", "evt_vector"]
    # An idempotent replay re-reads only control + operation and writes nothing.
    assert fake._docs == before
