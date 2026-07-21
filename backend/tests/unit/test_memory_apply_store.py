import copy
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import ModuleType
from typing import Optional
from unittest.mock import MagicMock

import pytest

from testing.import_isolation import load_module_fresh, stub_modules

from models.memory_evidence import ArtifactPreservationState, MemoryEvidence, SourceState, SourceStateReason
from utils.memory.v3.account_generation_source import read_memory_v3_trusted_account_generation
from models.memory_apply import ApplyStatus, MemoryControlState
from models.memory_contracts import DurablePatchDecision, LifecycleState
from models.memory_operations import MemoryOperation, MemoryOperationType
from models.product_memory import MemoryItemStatus, MemoryTier, ProcessingState, MemoryItem

backend = Path(__file__).resolve().parents[2]


def _fake_transactional():
    def transactional(func):
        def wrapper(transaction, *args, **kwargs):
            if hasattr(transaction, "_begin"):
                transaction._begin()
            try:
                result = func(transaction, *args, **kwargs)
                if hasattr(transaction, "_commit"):
                    transaction._commit()
                return result
            except Exception:
                if hasattr(transaction, "_rollback"):
                    transaction._rollback()
                raise
            finally:
                if hasattr(transaction, "_clean_up"):
                    transaction._clean_up()

        return wrapper

    return transactional


@pytest.fixture(scope="module")
def store():
    """Load database.memory_apply_store fresh against a fake firestore_v1.transactional.

    apply_long_term_patch_firestore decorates its transaction helpers with
    google.cloud.firestore_v1.transactional at import time. The real decorator drives a
    real Firestore transaction lifecycle and is incompatible with the test's
    _FakeTransaction, so a fake-transaction-compatible wrapper must precede the import.
    """
    client_stub = ModuleType("database._client")
    client_stub.db = MagicMock(name="db")

    firestore_v1_stub = ModuleType("google.cloud.firestore_v1")
    firestore_v1_stub.transactional = _fake_transactional()
    google_pkg = ModuleType("google")
    google_pkg.__path__ = []  # type: ignore[attr-defined]
    google_cloud_pkg = ModuleType("google.cloud")
    google_cloud_pkg.__path__ = []  # type: ignore[attr-defined]

    fakes = {
        "database._client": client_stub,
        "google": google_pkg,
        "google.cloud": google_cloud_pkg,
        "google.cloud.firestore_v1": firestore_v1_stub,
    }
    with stub_modules(fakes):
        module = load_module_fresh(
            "database.memory_apply_store",
            os.path.join(str(backend), "database", "memory_apply_store.py"),
        )
        yield module


class _FakeSnapshot:
    def __init__(self, data, exists=True):
        self._data = data
        self.exists = exists

    def to_dict(self):
        return self._data


class _FakeDocumentRef:
    def __init__(self, path, db):
        self.path = path
        self._db = db

    def get(self, transaction=None):
        if self.path not in self._db.docs:
            return _FakeSnapshot(None, exists=False)
        return _FakeSnapshot(self._db.docs[self.path], exists=True)


class _FakeTransaction:
    def __init__(self, db):
        self._db = db
        self.sets = []
        self.fail_after_sets: Optional[int] = None
        self._read_only = False
        self._max_attempts = 1
        self._id = None

    def set(self, ref, data):
        self.sets.append((ref.path, data))
        if self.fail_after_sets is not None and len(self.sets) > self.fail_after_sets:
            raise RuntimeError("injected transaction set failure")

    def _clean_up(self):
        self._id = None

    def _begin(self, retry_id=None):
        self._id = retry_id or "txn-1"
        self.sets = []

    def _commit(self):
        for path, data in self.sets:
            self._db.docs[path] = data

    def _rollback(self):
        self._id = None


class _FakeDb:
    def __init__(self, docs):
        self.docs = docs
        self.transaction_obj = _FakeTransaction(self)

    def transaction(self):
        return self.transaction_obj

    def document(self, path):
        return _FakeDocumentRef(path, self)


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


def _db_with(control=None, operation=None, evidence=None, target_items=None):
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
    return _FakeDb(docs)


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


def test_firestore_apply_reads_authoritative_docs_and_writes_commit_projection_operation_and_outbox_atomically(store):
    operation = _operation()
    db = _db_with(operation=operation)

    result = store.apply_long_term_patch_firestore(
        uid="u1",
        operation_id=operation.operation_id,
        patch_payload=_patch(),
        db_client=db,
    )

    assert result.status == ApplyStatus.committed
    written_paths = [path for path, _ in db.transaction_obj.sets]
    assert "users/u1/memory_state/apply_control" in written_paths
    assert f"users/u1/memory_operations/{operation.operation_id}" in written_paths
    assert any(path.startswith("users/u1/memory_items/") for path in written_paths)
    assert any(path.startswith("users/u1/memory_outbox/") for path in written_paths)
    assert any(path.startswith("users/u1/memory_commits/") for path in written_paths)
    assert "users/u1/memory_state/head" in written_paths

    state_head = db.docs["users/u1/memory_state/head"]
    assert state_head == {
        "schema_version": 1,
        "uid": "u1",
        "source": "memory_state_head",
        "account_generation": result.control_state.account_generation,
        "head_commit_id": result.control_state.head_commit_id,
        "commit_sequence": result.control_state.commit_sequence,
        "updated_at": result.control_state.updated_at,
    }

    trusted = read_memory_v3_trusted_account_generation(uid="u1", db_client=db)
    assert trusted.read_error_reason is None
    assert trusted.account_generation == result.control_state.account_generation
    assert trusted.head_commit_id == result.control_state.head_commit_id
    assert trusted.commit_sequence == result.control_state.commit_sequence


def test_firestore_apply_uses_stored_evidence_not_caller_payload_and_does_not_write_domain_rows_when_source_purged(
    store,
):
    operation = _operation()
    purged_evidence = _evidence(
        source_state=SourceState.purged,
        source_state_reason=SourceStateReason.account_purged,
        artifact_preservation=ArtifactPreservationState.deleted_by_user,
    )
    db = _db_with(operation=operation, evidence=purged_evidence)
    caller_claims_active = _patch(evidence=[_evidence()])

    result = store.apply_long_term_patch_firestore(
        uid="u1",
        operation_id=operation.operation_id,
        patch_payload=caller_claims_active,
        db_client=db,
    )

    assert result.status == ApplyStatus.source_not_active
    written_paths = [path for path, _ in db.transaction_obj.sets]
    assert written_paths == [f"users/u1/memory_operations/{operation.operation_id}"]


def test_firestore_apply_reads_target_memory_and_fails_closed_when_target_is_missing(store):
    operation = _operation(
        target_memory_id="mem1",
        logical_payload={
            "decision": "update",
            "target_memory_id": "mem1",
            "memory_text": "Updated.",
            "result_status": "active",
        },
    )
    db = _db_with(operation=operation)
    patch = _patch(decision=DurablePatchDecision.update, target_memory_id="mem1", memory_text="Updated.")

    result = store.apply_long_term_patch_firestore(
        uid="u1",
        operation_id=operation.operation_id,
        patch_payload=patch,
        db_client=db,
    )

    assert result.status == ApplyStatus.target_not_active
    written_paths = [path for path, _ in db.transaction_obj.sets]
    assert written_paths == [f"users/u1/memory_operations/{operation.operation_id}"]


def test_firestore_apply_allows_update_when_target_is_authoritative_active_same_generation(store):
    operation = _operation(
        target_memory_id="mem1",
        logical_payload={
            "decision": "update",
            "target_memory_id": "mem1",
            "memory_text": "Updated.",
            "result_status": "active",
        },
    )
    db = _db_with(operation=operation, target_items=[_target_item()])
    patch = _patch(decision=DurablePatchDecision.update, target_memory_id="mem1", memory_text="Updated.")

    result = store.apply_long_term_patch_firestore(
        uid="u1",
        operation_id=operation.operation_id,
        patch_payload=patch,
        db_client=db,
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
    db = _db_with(operation=operation, target_items=[existing])
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
        db_client=db,
    )

    assert result.status == ApplyStatus.committed
    persisted = db.docs["users/u1/memory_items/mem1"]
    restored = MemoryItem(**persisted)
    assert restored.expires_at == expires_at
    assert restored.updated_at >= captured_at
    assert restored.updated_at >= prior_updated_at


def test_firestore_apply_retries_committed_operation_from_stored_result_without_rereading_mutable_evidence_or_target(
    store,
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
    db = _db_with(control=control, operation=operation, evidence=purged_evidence)
    patch = _patch(decision=DurablePatchDecision.update, target_memory_id="mem1", memory_text="Updated.")

    result = store.apply_long_term_patch_firestore(
        uid="u1",
        operation_id=operation.operation_id,
        patch_payload=patch,
        db_client=db,
    )

    assert result.status == ApplyStatus.idempotent_skip
    assert result.operation.committed_sequence == 5
    assert result.operation.committed_memory_item_ids == ["mem1"]
    assert result.operation.committed_outbox_event_ids == ["evt_projection", "evt_vector"]
    assert db.transaction_obj.sets == []


def test_firestore_transaction_set_failure_leaves_store_unchanged_and_retry_commits_same_ids(store):
    operation = _operation()
    db = _db_with(operation=operation)
    patch = _patch()
    original_docs = copy.deepcopy(db.docs)

    db.transaction_obj.fail_after_sets = 2
    with pytest.raises(RuntimeError, match="injected transaction set failure"):
        store.apply_long_term_patch_firestore(
            uid="u1",
            operation_id=operation.operation_id,
            patch_payload=patch,
            db_client=db,
        )

    assert db.docs == original_docs

    db.transaction_obj.fail_after_sets = None
    retry = store.apply_long_term_patch_firestore(
        uid="u1",
        operation_id=operation.operation_id,
        patch_payload=patch,
        db_client=db,
    )

    assert retry.status == ApplyStatus.committed
    assert (
        db.docs[f"users/u1/memory_operations/{operation.operation_id}"]["committed_head_commit_id"]
        == retry.control_state.head_commit_id
    )
    assert db.docs["users/u1/memory_state/apply_control"]["head_commit_id"] == retry.control_state.head_commit_id
    assert retry.operation.committed_memory_item_ids == [item.memory_id for item in retry.memory_items]
    assert retry.operation.committed_outbox_event_ids == [event.event_id for event in retry.outbox_events]
