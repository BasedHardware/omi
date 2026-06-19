import os
import sys
from datetime import datetime, timezone
from unittest.mock import MagicMock

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)

sys.modules["database._client"] = MagicMock()

from database.v17_memory_apply_store import apply_long_term_patch_firestore
from models.memory_evidence import ArtifactPreservationState, MemoryEvidence, SourceState, SourceStateReason
from models.v17_memory_apply import ApplyStatus, MemoryControlState
from models.v17_memory_contracts import DurablePatchDecision, LifecycleState
from models.v17_memory_operations import MemoryOperation, MemoryOperationType


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
    def __init__(self):
        self.sets = []
        self._read_only = False
        self._max_attempts = 1
        self._id = None

    def set(self, ref, data):
        self.sets.append((ref.path, data))

    def _clean_up(self):
        self._id = None

    def _begin(self, retry_id=None):
        self._id = retry_id or "txn-1"

    def _commit(self):
        pass

    def _rollback(self):
        pass


class _FakeDb:
    def __init__(self, docs):
        self.docs = docs
        self.transaction_obj = _FakeTransaction()

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


def _db_with(control=None, operation=None, evidence=None):
    control = control or MemoryControlState(uid="u1", head_commit_id="head0", account_generation=1, source_generation=2)
    operation = operation or _operation()
    evidence = evidence or _evidence()
    return _FakeDb(
        {
            "users/u1/memory_control/state": _stored_model(control),
            f"users/u1/memory_operations/{operation.operation_id}": _stored_model(operation),
            "users/u1/memory_evidence/ev1": _stored_model(evidence),
        }
    )


def test_firestore_apply_reads_authoritative_docs_and_writes_commit_projection_operation_and_outbox_atomically():
    operation = _operation()
    db = _db_with(operation=operation)

    result = apply_long_term_patch_firestore(
        uid="u1",
        operation_id=operation.operation_id,
        patch_payload=_patch(),
        db_client=db,
    )

    assert result.status == ApplyStatus.committed
    written_paths = [path for path, _ in db.transaction_obj.sets]
    assert "users/u1/memory_control/state" in written_paths
    assert f"users/u1/memory_operations/{operation.operation_id}" in written_paths
    assert any(path.startswith("users/u1/memory_items/") for path in written_paths)
    assert any(path.startswith("users/u1/memory_outbox/") for path in written_paths)
    assert any(path.startswith("users/u1/memory_commits/") for path in written_paths)


def test_firestore_apply_uses_stored_evidence_not_caller_payload_and_does_not_write_domain_rows_when_source_purged():
    operation = _operation()
    purged_evidence = _evidence(
        source_state=SourceState.purged,
        source_state_reason=SourceStateReason.account_purged,
        artifact_preservation=ArtifactPreservationState.deleted_by_user,
    )
    db = _db_with(operation=operation, evidence=purged_evidence)
    caller_claims_active = _patch(evidence=[_evidence()])

    result = apply_long_term_patch_firestore(
        uid="u1",
        operation_id=operation.operation_id,
        patch_payload=caller_claims_active,
        db_client=db,
    )

    assert result.status == ApplyStatus.source_not_active
    written_paths = [path for path, _ in db.transaction_obj.sets]
    assert written_paths == [f"users/u1/memory_operations/{operation.operation_id}"]
