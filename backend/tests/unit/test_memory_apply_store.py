import copy
import hashlib
import os
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import ModuleType
from typing import Optional
from unittest.mock import MagicMock

import pytest

from database.read_boundary import MalformedDocError
from testing.import_isolation import load_module_fresh, stub_modules

from models.memory_evidence import (
    ArtifactPreservationState,
    MemoryEvidence,
    ProvenanceVisibility,
    RedactionStatus,
    SourceState,
    SourceStateReason,
)
from utils.memory.v3.account_generation_source import read_memory_v3_trusted_account_generation
from models.memory_apply import (
    ApplyStatus,
    MemoryControlState,
    build_patch_mutation_identity,
    memory_content_hash,
)
from models.memory_contracts import DurablePatchDecision, LifecycleState
from models.memory_operations import (
    MemoryLedgerReopenReceipt,
    MemoryOperation,
    MemoryOperationStatus,
    MemoryOperationType,
)
from models.jit_trigger_feedback import JITTriggerFeedbackReceipt
from models.jit_proactivity import JITProactivityEventReceipt
from models.memory_promotion import PromotionGraphPlan, build_promotion_admission_receipt
from models.product_memory import (
    LedgerWriteReason,
    MemoryAccessPolicy,
    MemoryItem,
    MemoryItemStatus,
    MemoryKind,
    MemorySubjectScope,
    MemoryTier,
    ProcessingState,
    is_default_access_eligible,
)

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
    client_stub.get_firestore_client = MagicMock(return_value=client_stub.db)
    # memory_apply_store imports the data-plane seam's lazy proxy (aliased to
    # `db` at its own import site) rather than the shared `db` above — see
    # database/_client.py's get_data_plane_firestore_client().
    client_stub.data_plane_db = MagicMock(name="data_plane_db")
    client_stub.get_data_plane_firestore_client = MagicMock(return_value=client_stub.data_plane_db)

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
        module.assert_destructive_operation_transaction = MagicMock()

        @contextmanager
        def permitted_cleanup_gate(*_args, **_kwargs):
            yield "retention-cleanup-token"

        module.destructive_operation_gate = permitted_cleanup_gate
        yield module


def test_global_intake_pause_is_enforced_inside_apply_boundary(store, monkeypatch):
    monkeypatch.setenv("MEMORY_MODE", "off")
    db_client = MagicMock()

    with pytest.raises(store.CanonicalMemoryIntakePausedError, match="globally paused"):
        store.apply_long_term_patch_firestore(
            uid="uid-paused",
            operation_id="op-paused",
            patch_payload={},
            db_client=db_client,
        )

    db_client.transaction.assert_not_called()


def test_global_intake_pause_is_enforced_inside_source_replacement_boundary(store, monkeypatch):
    monkeypatch.setenv("MEMORY_MODE", "shadow")
    db_client = MagicMock()

    with pytest.raises(store.CanonicalMemoryIntakePausedError, match="globally paused"):
        store.replace_conversation_source_firestore(
            uid="uid-paused",
            conversation_id="conversation-paused",
            replacement_id="replacement-paused",
            replacement_digest="digest-paused",
            replacement_operation=None,
            observed_control=None,
            expected_source_items=[],
            expected_reactivation_items=[],
            writes=[],
            deletion_gate_token="gate-token",
            db_client=db_client,
        )

    db_client.transaction.assert_not_called()


class _FakeSnapshot:
    def __init__(self, data, exists=True, reference=None):
        self._data = data
        self.exists = exists
        self.reference = reference
        self.id = reference.path.rsplit("/", 1)[-1] if reference is not None else None

    def to_dict(self):
        return self._data


class _FakeDocumentRef:
    def __init__(self, path, db):
        self.path = path
        self._db = db

    def get(self, transaction=None):
        if self.path not in self._db.docs:
            return _FakeSnapshot(None, exists=False, reference=self)
        return _FakeSnapshot(self._db.docs[self.path], exists=True, reference=self)

    def delete(self):
        self._db.docs.pop(self.path, None)


class _FakeReceiptQuery:
    def __init__(self, db, path):
        self._db = db
        self._path = path
        self._cutoff = None
        self._limit = 128

    def where(self, field, operator, value):
        assert field == "expires_at" and operator == "<="
        self._cutoff = value
        return self

    def limit(self, value):
        self._limit = value
        return self

    def stream(self):
        prefix = self._path + "/"
        rows = []
        for path, payload in self._db.docs.items():
            if not path.startswith(prefix) or payload.get("expires_at") > self._cutoff:
                continue
            rows.append(_FakeSnapshot(payload, exists=True, reference=_FakeDocumentRef(path, self._db)))
        return iter(rows[: self._limit])


class _FakeTransaction:
    def __init__(self, db):
        self._db = db
        self.sets = []
        self.deletes = []
        self.mutations = []
        self.fail_after_sets: Optional[int] = None
        self.fail_delete_paths: set[str] = set()
        self._read_only = False
        self._max_attempts = 1
        self._id = None

    def set(self, ref, data):
        self.sets.append((ref.path, data))
        self.mutations.append(("set", ref.path, data))
        if self.fail_after_sets is not None and len(self.sets) > self.fail_after_sets:
            raise RuntimeError("injected transaction set failure")

    def delete(self, ref):
        self.deletes.append(ref.path)
        self.mutations.append(("delete", ref.path, None))
        if ref.path in self.fail_delete_paths:
            raise RuntimeError("injected transaction delete failure")

    def _clean_up(self):
        self._id = None

    def _begin(self, retry_id=None):
        self._id = retry_id or "txn-1"
        self.sets = []
        self.deletes = []
        self.mutations = []

    def _commit(self):
        for operation, path, data in self.mutations:
            if operation == "set":
                self._db.docs[path] = data
            else:
                self._db.docs.pop(path, None)

    def _rollback(self):
        self._id = None
        self.sets = []
        self.deletes = []
        self.mutations = []


class _FakeDb:
    def __init__(self, docs):
        self.docs = docs
        self.transaction_obj = _FakeTransaction(self)

    def transaction(self):
        return self.transaction_obj

    def document(self, path):
        return _FakeDocumentRef(path, self)

    def collection(self, path):
        return _FakeReceiptQuery(self, path)


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


def _privacy_sensitive_evidence(**overrides):
    data = dict(
        conversation_id="conv1",
        artifact_refs=[
            {
                "artifact_id": "artifact-private-audio",
                "uri": "gs://private-memory/audio.wav",
                "checksum": "sha256-private-audio",
                "size_bytes": 321,
                "preservation": ArtifactPreservationState.preserved,
            }
        ],
        quote_refs=[{"text": "Private verbatim source text.", "start_ms": 100, "end_ms": 900}],
        content_hash="evidence-private-content-hash",
        lineage_id="evidence-lineage-1",
        patch_id="patch-private-source",
        commit_id="commit-private-source",
        client_device_id="device-private-source",
    )
    data.update(overrides)
    return _evidence(**data)


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
    data = dict(
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


def _assert_privacy_scrubbed_evidence(raw, *, original: MemoryEvidence, source_identity_scrubbed: bool = True):
    assert raw["artifact_refs"] == []
    assert raw["artifact_preservation"] == ArtifactPreservationState.deleted_by_user.value
    assert raw["quote_refs"] == []
    assert raw["content_hash"] is None
    assert raw["source_state"] == SourceState.tombstoned.value
    assert raw["source_state_reason"] == SourceStateReason.deleted_by_user.value
    assert raw["provenance_visibility"] == ProvenanceVisibility.hidden.value
    assert raw["redaction_status"] == RedactionStatus.tombstoned.value
    assert raw["encryption_or_redaction_status"] == RedactionStatus.tombstoned.value
    assert raw["patch_id"] is None
    assert raw["commit_id"] is None
    assert raw["client_device_id"] is None
    assert {
        "evidence_id": raw["evidence_id"],
        "source_type": raw["source_type"],
        "source_id": raw["source_id"],
        "source_version": raw["source_version"],
        "conversation_id": raw["conversation_id"],
        "lineage_id": raw["lineage_id"],
    } == {
        "evidence_id": original.evidence_id,
        "source_type": original.source_type,
        "source_id": None if source_identity_scrubbed else original.source_id,
        "source_version": None if source_identity_scrubbed else original.source_version,
        "conversation_id": None if source_identity_scrubbed else original.conversation_id,
        "lineage_id": None if source_identity_scrubbed else original.lineage_id,
    }


def _assert_privacy_scrubbed_item_semantics(raw):
    assert raw["status"] == MemoryItemStatus.tombstoned.value
    assert raw["source_state"] == SourceState.tombstoned.value
    assert raw["content"] is None
    assert raw["content_hash"] is None
    assert raw["normalized_content_key"] is None
    assert raw["sensitivity_labels"] == []
    assert raw["promotion"] is None
    assert raw["capture_device_ids"] == []
    assert raw["primary_capture_device"] is None
    assert raw["corroboration_count"] == 0
    assert raw["last_corroborated_at"] is None
    assert raw["confidence"] is None
    assert raw["subject_entity_id"] is None
    assert raw["predicate"] is None
    assert raw["arguments"] == {}
    assert raw["ledger_schema_version"] is None
    assert raw["kind"] == MemoryKind.fact.value
    assert raw["subject_scope"] == MemorySubjectScope.primary_user.value
    assert raw["slot"] is None
    assert raw["body"] is None
    assert raw["valid_from"] is None
    assert raw["valid_to"] is None
    assert raw["curation_weight"] == 0
    assert raw["trigger_condition"] == {}
    assert raw["intent_backed"] is False
    assert raw["write_reason"] is None


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


def _short_term_target(**overrides):
    now = datetime.now(timezone.utc)
    data = {
        "tier": MemoryTier.short_term,
        "captured_at": now,
        "updated_at": now,
        "expires_at": now + timedelta(days=30),
        "graph_ready": False,
        "graph_assertion_id": None,
        "graph_plan_hash": None,
        "kg_extracted": False,
    }
    data.update(overrides)
    return _target_item(**data)


def _privacy_sensitive_target(*, memory_id: str, evidence: MemoryEvidence, **overrides):
    now = datetime.now(timezone.utc)
    data = dict(
        memory_id=memory_id,
        canonical_memory_id=f"lineage-root-{memory_id}",
        content="User shared private health and location details.",
        evidence=[evidence],
        content_hash=f"private-item-hash-{memory_id}",
        sensitivity_labels=["health", "location"],
        promotion={
            "route": "review",
            "rationale": "Private source-derived rationale.",
            "source_attribution": {"quote": "Private verbatim source text."},
        },
        capture_device_ids=["device-private-source"],
        primary_capture_device="device-private-source",
        corroboration_count=3,
        last_corroborated_at=now,
        confidence=0.91,
        subject_entity_id="person:private-user",
        predicate="has_private_preference",
        arguments={"private_detail": "sensitive value"},
    )
    data.update(overrides)
    return _short_term_target(**data)


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


def _promotion_operation(existing: MemoryItem, *, memory_text: str, supersedes=None):
    superseded_ids = list(supersedes or [])
    return _operation(
        operation_type=MemoryOperationType.synthesis,
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


def _promotion_patch(existing: MemoryItem, *, memory_text: str, supersedes=None):
    superseded_ids = list(supersedes or [])
    return _patch(
        decision=DurablePatchDecision.update,
        target_memory_id=existing.memory_id,
        memory_text=memory_text,
        target_tier=MemoryTier.long_term,
        supersedes=superseded_ids,
        predicate="prefers_update_style",
        arguments={"style": "concise"},
        promotion_audit=_promotion_audit(
            existing,
            memory_text=memory_text,
            supersedes=superseded_ids,
        ),
    )


def _replacement_operation_and_write(
    store,
    control: MemoryControlState,
    *,
    memory_id: str = "mem2",
    include_new: bool = True,
    replacement_id: str = "replace_digest-conv1-v2",
    replacement_digest: str = "digest-conv1-v2",
    evidence_id: str = "ev2",
):
    next_generation = control.source_generation + 1
    bumped = control.model_copy(update={"source_generation": next_generation})
    replacement_operation = MemoryOperation.new(
        uid="u1",
        operation_type=MemoryOperationType.source_replacement,
        source_packet_id="conv1",
        target_memory_id=None,
        evidence_ids=[],
        logical_payload={
            "decision": "source_replace",
            "replacement_id": replacement_id,
            "replacement_digest": replacement_digest,
            "conversation_id": "conv1",
            "new_memory_ids": [memory_id] if include_new else [],
        },
        account_generation=control.account_generation,
        source_generation=next_generation,
        observed_head_commit_id=control.head_commit_id,
    )
    replacement_commit_id = bumped.next_commit_id(replacement_operation.operation_id)
    write_control = bumped.advance_head(replacement_commit_id)
    evidence = _evidence(
        evidence_id=evidence_id,
        source_id="conv1",
        source_version=f"source_generation:{next_generation}",
        conversation_id="conv1",
    )
    patch = _patch(
        patch_id=f"patch-replacement-{memory_id}-{next_generation}",
        packet_id="conv1",
        run_id="replace-conv1",
        observed_head_commit_id=write_control.head_commit_id,
        idempotency_key=f"replace-conv1-{memory_id}-{next_generation}",
        evidence_ids=[evidence.evidence_id],
        new_memory_id=memory_id,
        initial_tier=MemoryTier.short_term,
    )
    mutation_identity = build_patch_mutation_identity(patch)
    patch["mutation_metadata"] = mutation_identity
    operation = MemoryOperation.new(
        uid="u1",
        operation_type=MemoryOperationType.source_candidate,
        source_packet_id="conv1",
        target_memory_id=None,
        evidence_ids=[evidence.evidence_id],
        logical_payload={
            "decision": DurablePatchDecision.add.value,
            "memory_text": patch["memory_text"],
            "result_status": LifecycleState.active.value,
            "subject_entity_id": "user",
            "predicate": None,
            "arguments": {},
            "mutation_metadata": mutation_identity,
        },
        account_generation=control.account_generation,
        source_generation=next_generation,
        observed_head_commit_id=write_control.head_commit_id,
    )
    return (
        replacement_id,
        replacement_digest,
        replacement_operation,
        store.CanonicalApplyWrite(
            operation=operation,
            patch_payload=patch,
            evidence=[evidence],
        ),
    )


def test_firestore_privacy_tombstone_advances_ledger_and_journals_delete_events(store):
    control = MemoryControlState(
        uid="u1",
        head_commit_id="head0",
        account_generation=1,
        source_generation=2,
        commit_sequence=4,
    )
    item = _short_term_target(memory_id="mem1")
    db = _db_with(control=control, target_items=[item])

    result = store.tombstone_memory_items_firestore(
        uid="u1",
        reason="canonical_memory_delete",
        observed_control=control,
        expected_items=[item],
        preserved_evidence_ids=[],
        deletion_gate_token="gate-token",
        db_client=db,
    )

    assert result.control_state.head_commit_id != control.head_commit_id
    assert result.control_state.commit_sequence == 5
    tombstoned = db.docs["users/u1/memory_items/mem1"]
    assert tombstoned["status"] == MemoryItemStatus.tombstoned.value
    assert tombstoned["ledger_commit_id"] == result.control_state.head_commit_id
    assert tombstoned["ledger_sequence"] == 5
    assert db.docs["users/u1/memory_evidence/ev1"]["source_state"] == SourceState.tombstoned.value

    operations = [
        payload
        for path, payload in db.docs.items()
        if path.startswith("users/u1/memory_operations/")
        and payload.get("operation_type") == MemoryOperationType.deletion.value
    ]
    assert len(operations) == 1
    operation = operations[0]
    assert operation["status"] == MemoryOperationStatus.committed.value
    assert operation["evidence_ids"] == []
    assert "hash1" not in repr(operation)
    receipt_id = store.privacy_deletion_receipt_id("u1", "mem1")
    receipt = db.docs[f"users/u1/memory_deletion_receipts/{receipt_id}"]
    assert receipt["schema_version"] == "memory_deletion_receipt.v2"
    assert receipt["receipt_id"] == receipt_id
    assert "mem1" not in repr(receipt)
    assert receipt["expires_at"] - receipt["deleted_at"] == timedelta(days=30)
    commit = db.docs[f"users/u1/memory_commits/{result.control_state.head_commit_id}"]
    assert commit["operation_id"] == operation["operation_id"]
    assert set(commit["outbox_event_ids"]) == set(operation["committed_outbox_event_ids"])

    events = [
        payload
        for path, payload in db.docs.items()
        if path.startswith("users/u1/memory_outbox/") and payload["operation_id"] == operation["operation_id"]
    ]
    assert {event["event_type"] for event in events} == {"projection_sync", "vector_sync"}
    assert all(event["commit_id"] == result.control_state.head_commit_id for event in events)
    assert all(event["parent_commit_id"] == result.control_state.head_commit_id for event in events)
    assert all(event["commit_sequence"] == 5 for event in events)
    assert "users/u1/memory_graph_assertions/mem1" not in db.transaction_obj.deletes


def test_firestore_privacy_tombstone_accepts_exact_ninety_nine_item_batch(store):
    control = MemoryControlState(
        uid="u1",
        head_commit_id="head0",
        account_generation=1,
        source_generation=2,
        commit_sequence=4,
    )
    items = []
    for index in range(99):
        evidence = _evidence(
            evidence_id=f"ev-{index}",
            source_id=f"conv-{index}",
            conversation_id=f"conv-{index}",
        )
        items.append(
            _short_term_target(
                memory_id=f"mem-{index}",
                evidence=[evidence],
                content=f"Canonical memory {index}.",
                content_hash=f"hash-{index}",
            )
        )
    db = _db_with(control=control, target_items=items)
    for item in items:
        evidence = item.evidence[0]
        db.docs[f"users/u1/memory_evidence/{evidence.evidence_id}"] = _stored_model(evidence)

    result = store.tombstone_memory_items_firestore(
        uid="u1",
        reason="canonical_memory_delete",
        observed_control=control,
        expected_items=items,
        preserved_evidence_ids=[],
        deletion_gate_token="gate-token",
        db_client=db,
    )

    assert len(result.memory_items) == 99
    assert len(db.transaction_obj.mutations) == 499


def test_content_free_deletion_receipt_expires_after_thirty_days(store, monkeypatch):
    control = MemoryControlState(
        uid="u1",
        head_commit_id="head0",
        account_generation=1,
        source_generation=2,
        commit_sequence=4,
    )
    evidence = _privacy_sensitive_evidence()
    item = _privacy_sensitive_target(memory_id="mem-expiring-receipt", evidence=evidence)
    db = _db_with(control=control, evidence=evidence, target_items=[item])

    result = store.tombstone_memory_items_firestore(
        uid="u1",
        reason="canonical_memory_delete",
        observed_control=control,
        expected_items=[item],
        preserved_evidence_ids=[],
        deletion_gate_token="gate-token",
        db_client=db,
    )
    receipt_path = next(path for path in db.docs if path.startswith("users/u1/memory_deletion_receipts/"))
    receipt = db.docs[receipt_path]
    assert receipt["schema_version"] == "memory_deletion_receipt.v2"
    assert receipt["receipt_id"] == store.privacy_deletion_receipt_id("u1", item.memory_id)
    assert item.memory_id not in repr(receipt)
    assert item.content_hash not in repr(receipt)
    assert evidence.source_id not in repr(receipt)

    assert (
        store.cleanup_expired_memory_deletion_receipts(
            "u1", db_client=db, now=receipt["expires_at"] - timedelta(microseconds=1)
        )
        == 0
    )
    assert receipt_path in db.docs
    with monkeypatch.context() as hold_context:

        @contextmanager
        def blocked_cleanup_gate(*_args, **_kwargs):
            raise RuntimeError("active legal hold")
            yield  # pragma: no cover

        hold_context.setattr(store, "destructive_operation_gate", blocked_cleanup_gate)
        assert store.cleanup_expired_memory_deletion_receipts("u1", db_client=db, now=receipt["expires_at"]) == 0
        assert receipt_path in db.docs
    assert store.cleanup_expired_memory_deletion_receipts("u1", db_client=db, now=receipt["expires_at"]) == 1
    assert receipt_path not in db.docs
    # Transaction-layer tombstones remain pending until provider cleanup; the
    # higher-level finalizer removes these content-derived paths on success.
    tombstone = db.docs["users/u1/memory_items/mem-expiring-receipt"]
    assert tombstone["content"] is None
    assert not any(path.startswith("users/u1/memory_graph_assertions/") for path in db.transaction_obj.deletes)


def test_deletion_receipt_identity_is_server_keyed_and_contains_no_raw_lookup_material(store):
    memory_id = "mem-secret-project-codename"
    receipt_id = store.privacy_deletion_receipt_id("u1", memory_id)
    public_dictionary_guesses = {
        hashlib.sha256(memory_id.encode()).hexdigest(),
        hashlib.sha256(f"u1:{memory_id}".encode()).hexdigest(),
        hashlib.sha256(f"u1/{memory_id}".encode()).hexdigest(),
    }

    assert receipt_id.startswith("receipt_")
    assert receipt_id.removeprefix("receipt_") not in public_dictionary_guesses
    assert "u1" not in receipt_id
    assert memory_id not in receipt_id


def test_firestore_privacy_tombstone_preserves_shared_standalone_evidence_for_editable_sibling(store):
    control = MemoryControlState(
        uid="u1",
        head_commit_id="head0",
        account_generation=1,
        source_generation=2,
        commit_sequence=4,
    )
    shared_evidence = _privacy_sensitive_evidence()
    deleted = _privacy_sensitive_target(memory_id="mem-deleted", evidence=shared_evidence)
    sibling = _short_term_target(
        memory_id="mem-sibling",
        canonical_memory_id=None,
        content="Unrelated sibling memory backed by the same source.",
        evidence=[shared_evidence],
        content_hash="sibling-private-content-hash",
    )
    db = _db_with(
        control=control,
        evidence=shared_evidence,
        target_items=[deleted, sibling],
    )
    standalone_before = copy.deepcopy(db.docs["users/u1/memory_evidence/ev1"])
    sibling_before = copy.deepcopy(db.docs["users/u1/memory_items/mem-sibling"])

    deletion = store.tombstone_memory_items_firestore(
        uid="u1",
        reason="canonical_memory_delete",
        observed_control=control,
        expected_items=[deleted],
        preserved_evidence_ids=[shared_evidence.evidence_id],
        deletion_gate_token="gate-token",
        db_client=db,
    )

    assert deletion.tombstoned_evidence_ids == []
    assert db.docs["users/u1/memory_evidence/ev1"] == standalone_before
    assert db.docs["users/u1/memory_items/mem-sibling"] == sibling_before
    deleted_raw = db.docs["users/u1/memory_items/mem-deleted"]
    _assert_privacy_scrubbed_item_semantics(deleted_raw)
    _assert_privacy_scrubbed_evidence(deleted_raw["evidence"][0], original=shared_evidence)

    updated_text = "The unrelated sibling remains independently editable."
    update_operation = _operation(
        source_packet_id="pkt-sibling-edit",
        target_memory_id=sibling.memory_id,
        evidence_ids=[shared_evidence.evidence_id],
        logical_payload={
            "decision": DurablePatchDecision.update.value,
            "memory_text": updated_text,
            "target_memory_id": sibling.memory_id,
            "result_status": LifecycleState.active.value,
        },
        account_generation=deletion.control_state.account_generation,
        source_generation=deletion.control_state.source_generation,
        observed_head_commit_id=deletion.control_state.head_commit_id,
    )
    update_patch = _patch(
        patch_id="patch-sibling-edit",
        packet_id="pkt-sibling-edit",
        run_id="run-sibling-edit",
        observed_head_commit_id=deletion.control_state.head_commit_id,
        idempotency_key="idem-sibling-edit",
        decision=DurablePatchDecision.update,
        target_memory_id=sibling.memory_id,
        evidence_ids=[shared_evidence.evidence_id],
        memory_text=updated_text,
        expected_item_revision=sibling.item_revision,
        expected_content_hash=sibling.content_hash,
    )

    update = store.apply_long_term_patch_firestore(
        uid="u1",
        operation_id=update_operation.operation_id,
        patch_payload=update_patch,
        proposed_operation=update_operation,
        db_client=db,
    )

    assert update.status == ApplyStatus.committed
    updated_sibling = MemoryItem(**db.docs["users/u1/memory_items/mem-sibling"])
    assert updated_sibling.status == MemoryItemStatus.active
    assert updated_sibling.source_state == SourceState.active
    assert updated_sibling.content == updated_text
    assert updated_sibling.item_revision == sibling.item_revision + 1
    assert updated_sibling.evidence == [shared_evidence]
    assert db.docs["users/u1/memory_evidence/ev1"] == standalone_before


def test_firestore_privacy_tombstone_scrubs_semantics_and_keeps_lineage_outbox_fences(store):
    control = MemoryControlState(
        uid="u1",
        head_commit_id="head0",
        account_generation=1,
        source_generation=2,
        commit_sequence=6,
    )
    evidence = _privacy_sensitive_evidence()
    item = _privacy_sensitive_target(memory_id="mem-private-delete", evidence=evidence)
    db = _db_with(control=control, evidence=evidence, target_items=[item])

    result = store.tombstone_memory_items_firestore(
        uid="u1",
        reason="canonical_memory_delete",
        observed_control=control,
        expected_items=[item],
        preserved_evidence_ids=[],
        deletion_gate_token="gate-token",
        db_client=db,
    )

    tombstoned = db.docs["users/u1/memory_items/mem-private-delete"]
    _assert_privacy_scrubbed_item_semantics(tombstoned)
    _assert_privacy_scrubbed_evidence(tombstoned["evidence"][0], original=evidence)
    _assert_privacy_scrubbed_evidence(db.docs["users/u1/memory_evidence/ev1"], original=evidence)
    assert result.tombstoned_evidence_ids == [evidence.evidence_id]
    assert tombstoned["canonical_memory_id"] == item.canonical_memory_id
    assert tombstoned["superseded_by"] == item.superseded_by
    assert tombstoned["version"] == item.version + 1
    assert tombstoned["item_revision"] == item.item_revision + 1
    assert tombstoned["content_hash"] is None
    assert tombstoned["ledger_commit_id"] == result.control_state.head_commit_id
    assert tombstoned["ledger_sequence"] == result.control_state.commit_sequence
    assert tombstoned["source_commit_id"] == result.control_state.head_commit_id
    assert tombstoned["source_commit_sequence"] == result.control_state.commit_sequence

    delete_events = [
        raw
        for path, raw in db.docs.items()
        if path.startswith("users/u1/memory_outbox/")
        and raw["memory_id"] == item.memory_id
        and raw["payload"]["action"] == "delete"
    ]
    assert {raw["event_type"] for raw in delete_events} == {"projection_sync", "vector_sync"}
    assert len(delete_events) == 2
    assert all(raw["commit_id"] == result.control_state.head_commit_id for raw in delete_events)
    assert all(raw["parent_commit_id"] == result.control_state.head_commit_id for raw in delete_events)
    assert all(raw["commit_sequence"] == result.control_state.commit_sequence for raw in delete_events)
    assert all(raw["account_generation"] == control.account_generation for raw in delete_events)
    assert all(raw["source_generation"] == control.source_generation for raw in delete_events)
    assert all(
        raw["payload"]
        == {
            "memory_id": item.memory_id,
            "tier": item.tier.value,
            "action": "delete",
            "item_revision": tombstoned["item_revision"],
            "content_hash": tombstoned["content_hash"],
            "reason": "canonical_memory_delete",
        }
        for raw in delete_events
    )


def test_firestore_conversation_replacement_commits_old_and_new_generation_atomically(store):
    control = MemoryControlState(
        uid="u1",
        head_commit_id="head0",
        account_generation=1,
        source_generation=2,
    )
    old = _short_term_target(memory_id="mem1")
    db = _db_with(control=control, target_items=[old])
    replacement_id, replacement_digest, replacement_operation, write = _replacement_operation_and_write(store, control)

    result = store.replace_conversation_source_firestore(
        uid="u1",
        conversation_id="conv1",
        replacement_id=replacement_id,
        replacement_digest=replacement_digest,
        replacement_operation=replacement_operation,
        observed_control=control,
        expected_source_items=[old],
        expected_reactivation_items=[],
        writes=[write],
        db_client=db,
    )

    assert result.control_state.source_generation == 3
    assert result.retracted_memory_ids == ["mem1"]
    assert result.committed_memory_ids == ["mem2"]
    assert db.docs["users/u1/memory_items/mem1"]["status"] == MemoryItemStatus.tombstoned.value
    assert db.docs["users/u1/memory_evidence/ev1"]["source_state"] == SourceState.tombstoned.value
    assert db.docs["users/u1/memory_items/mem2"]["status"] == MemoryItemStatus.active.value
    assert db.docs["users/u1/memory_evidence/ev2"]["source_state"] == SourceState.active.value
    receipt = db.docs[f"users/u1/memory_source_replacements/{replacement_id}"]
    assert receipt["operation_id"] == replacement_operation.operation_id
    assert receipt["control_state"]["source_generation"] == 3
    replacement_outbox = [
        raw
        for path, raw in db.docs.items()
        if path.startswith("users/u1/memory_outbox/") and raw["operation_id"] == replacement_operation.operation_id
    ]
    assert {raw["payload"]["action"] for raw in replacement_outbox} == {"barrier", "delete"}
    assert all(raw["parent_commit_id"] == "head0" for raw in replacement_outbox)
    assert all(raw["commit_sequence"] == 1 for raw in replacement_outbox)


def test_firestore_conversation_replacement_cannot_bypass_writer_transition(store):
    control = MemoryControlState(
        uid="u1",
        head_commit_id="head0",
        account_generation=1,
        source_generation=2,
        writer_mode="transitioning_to_ledger",
        writer_epoch=1,
        writer_transition_owner="migration-owner",
    )
    old = _short_term_target(memory_id="mem1")
    db = _db_with(control=control, target_items=[old])
    replacement_id, replacement_digest, replacement_operation, write = _replacement_operation_and_write(store, control)

    with pytest.raises(store.ConversationSourceReplacementConflict, match="not admitted"):
        store.replace_conversation_source_firestore(
            uid="u1",
            conversation_id="conv1",
            replacement_id=replacement_id,
            replacement_digest=replacement_digest,
            replacement_operation=replacement_operation,
            observed_control=control,
            expected_source_items=[old],
            expected_reactivation_items=[],
            writes=[write],
            db_client=db,
        )

    assert db.docs["users/u1/memory_items/mem1"]["status"] == MemoryItemStatus.active.value
    assert "users/u1/memory_items/mem2" not in db.docs


def test_firestore_conversation_replacement_scrubs_semantics_and_keeps_lineage_outbox_fences(store):
    control = MemoryControlState(
        uid="u1",
        head_commit_id="head0",
        account_generation=1,
        source_generation=2,
        commit_sequence=3,
    )
    evidence = _privacy_sensitive_evidence()
    old = _privacy_sensitive_target(memory_id="mem-private-replacement", evidence=evidence)
    db = _db_with(control=control, evidence=evidence, target_items=[old])
    replacement_id, replacement_digest, replacement_operation, _ = _replacement_operation_and_write(
        store,
        control,
        include_new=False,
    )

    result = store.replace_conversation_source_firestore(
        uid="u1",
        conversation_id="conv1",
        replacement_id=replacement_id,
        replacement_digest=replacement_digest,
        replacement_operation=replacement_operation,
        observed_control=control,
        expected_source_items=[old],
        expected_reactivation_items=[],
        writes=[],
        deletion_gate_token="gate-token",
        db_client=db,
    )

    tombstoned = db.docs["users/u1/memory_items/mem-private-replacement"]
    _assert_privacy_scrubbed_item_semantics(tombstoned)
    _assert_privacy_scrubbed_evidence(tombstoned["evidence"][0], original=evidence, source_identity_scrubbed=True)
    _assert_privacy_scrubbed_evidence(
        db.docs["users/u1/memory_evidence/ev1"], original=evidence, source_identity_scrubbed=True
    )
    assert result.tombstoned_evidence_ids == [evidence.evidence_id]
    assert tombstoned["canonical_memory_id"] == old.canonical_memory_id
    assert tombstoned["superseded_by"] == old.superseded_by
    assert tombstoned["version"] == old.version + 1
    assert tombstoned["item_revision"] == old.item_revision + 1
    assert tombstoned["content_hash"] is None
    assert tombstoned["ledger_commit_id"] == result.control_state.head_commit_id
    assert tombstoned["ledger_sequence"] == result.control_state.commit_sequence
    assert tombstoned["source_commit_id"] == result.control_state.head_commit_id
    assert tombstoned["source_commit_sequence"] == result.control_state.commit_sequence

    delete_events = [
        raw
        for path, raw in db.docs.items()
        if path.startswith("users/u1/memory_outbox/")
        and raw["memory_id"] == old.memory_id
        and raw["payload"]["action"] == "delete"
    ]
    assert {raw["event_type"] for raw in delete_events} == {"projection_sync", "vector_sync"}
    assert len(delete_events) == 2
    assert all(raw["commit_id"] == result.control_state.head_commit_id for raw in delete_events)
    assert all(raw["parent_commit_id"] == control.head_commit_id for raw in delete_events)
    assert all(raw["commit_sequence"] == result.control_state.commit_sequence for raw in delete_events)
    assert all(raw["account_generation"] == control.account_generation for raw in delete_events)
    assert all(raw["source_generation"] == result.control_state.source_generation for raw in delete_events)
    assert all(
        raw["payload"]
        == {
            "memory_id": old.memory_id,
            "tier": old.tier.value,
            "action": "delete",
            "item_revision": tombstoned["item_revision"],
            "content_hash": tombstoned["content_hash"],
            "reason": "conversation_reprocess_retract",
        }
        for raw in delete_events
    )


def test_firestore_source_withdrawal_reactivates_independently_sourced_long_term_lineage(store):
    control = MemoryControlState(
        uid="u1",
        head_commit_id="head0",
        account_generation=1,
        source_generation=2,
        commit_sequence=3,
    )
    source_evidence = _evidence(
        evidence_id="ev-source-a",
        source_id="conv1",
        conversation_id="conv1",
    )
    source_survivor = _target_item(
        memory_id="mem-source-a",
        content="The user prefers concise written updates.",
        evidence=[source_evidence],
        content_hash=memory_content_hash(
            content="The user prefers concise written updates.",
            evidence_ids=[source_evidence.evidence_id],
        ),
    )
    independent_evidence = _evidence(
        evidence_id="ev-source-b",
        source_id="conv-independent-b",
        conversation_id="conv-independent-b",
    )
    independent_content = "The user prefers direct written updates."
    independent = _target_item(
        memory_id="mem-independent-b",
        content=independent_content,
        evidence=[independent_evidence],
        content_hash=memory_content_hash(
            content=independent_content,
            evidence_ids=[independent_evidence.evidence_id],
        ),
    )
    independent = independent.model_copy(
        update={
            "canonical_memory_id": source_survivor.memory_id,
            "status": MemoryItemStatus.superseded,
            "superseded_by": source_survivor.memory_id,
            "promotion": _promotion_audit(independent, memory_text=independent_content),
            "graph_ready": False,
            "graph_assertion_id": None,
            "graph_plan_hash": None,
            "kg_extracted": False,
        }
    )
    db = _db_with(control=control, target_items=[source_survivor, independent])
    for evidence in (source_evidence, independent_evidence):
        db.docs[f"users/u1/memory_evidence/{evidence.evidence_id}"] = _stored_model(evidence)
    replacement_id, replacement_digest, replacement_operation, _ = _replacement_operation_and_write(
        store,
        control,
        include_new=False,
    )

    result = store.replace_conversation_source_firestore(
        uid="u1",
        conversation_id="conv1",
        replacement_id=replacement_id,
        replacement_digest=replacement_digest,
        replacement_operation=replacement_operation,
        observed_control=control,
        expected_source_items=[source_survivor],
        expected_reactivation_items=[independent],
        writes=[],
        deletion_gate_token="gate-token",
        db_client=db,
    )

    assert result.reactivated_memory_ids == [independent.memory_id]
    assert db.docs[f"users/u1/memory_items/{source_survivor.memory_id}"]["status"] == (
        MemoryItemStatus.tombstoned.value
    )
    reactivated = MemoryItem(**db.docs[f"users/u1/memory_items/{independent.memory_id}"])
    assert reactivated.status == MemoryItemStatus.active
    assert reactivated.canonical_memory_id is None
    assert reactivated.superseded_by is None
    assert reactivated.item_revision == independent.item_revision + 1
    assert reactivated.graph_ready is True
    assert reactivated.graph_assertion_id
    assert is_default_access_eligible(reactivated, MemoryAccessPolicy.for_omi_chat()).allowed is True
    assertion = db.docs[f"users/u1/memory_graph_assertions/{independent.memory_id}"]
    assert assertion["assertion_id"] == reactivated.graph_assertion_id
    assert assertion["item_revision"] == reactivated.item_revision
    assert assertion["content_hash"] == reactivated.content_hash
    reactivation_events = [
        raw
        for path, raw in db.docs.items()
        if path.startswith("users/u1/memory_outbox/") and raw["memory_id"] == independent.memory_id
    ]
    assert len(reactivation_events) == 2
    assert {raw["payload"]["action"] for raw in reactivation_events} == {"upsert"}


def test_firestore_source_withdrawal_preserves_conflict_semantics_for_malformed_graph_plan(store, caplog):
    control = MemoryControlState(
        uid="u1",
        head_commit_id="head0",
        account_generation=1,
        source_generation=2,
        commit_sequence=3,
    )
    source_evidence = _evidence(
        evidence_id="ev-source-a",
        source_id="conv1",
        conversation_id="conv1",
    )
    source_survivor = _target_item(
        memory_id="mem-source-a",
        content="The user prefers concise written updates.",
        evidence=[source_evidence],
        content_hash=memory_content_hash(
            content="The user prefers concise written updates.",
            evidence_ids=[source_evidence.evidence_id],
        ),
    )
    secret = "private independent preference must not appear in malformed-document logs"
    independent_evidence = _evidence(
        evidence_id="ev-source-b",
        source_id="conv-independent-b",
        conversation_id="conv-independent-b",
    )
    independent = _target_item(
        memory_id="mem-independent-b",
        content=secret,
        evidence=[independent_evidence],
        content_hash=memory_content_hash(
            content=secret,
            evidence_ids=[independent_evidence.evidence_id],
        ),
    )
    independent = independent.model_copy(
        update={
            "canonical_memory_id": source_survivor.memory_id,
            "status": MemoryItemStatus.superseded,
            "superseded_by": source_survivor.memory_id,
            "promotion": _promotion_audit(independent, memory_text=secret),
            "graph_ready": False,
            "graph_assertion_id": None,
            "graph_plan_hash": None,
            "kg_extracted": False,
        }
    )
    db = _db_with(control=control, target_items=[source_survivor, independent])
    for evidence in (source_evidence, independent_evidence):
        db.docs[f"users/u1/memory_evidence/{evidence.evidence_id}"] = _stored_model(evidence)
    item_path = f"users/u1/memory_items/{independent.memory_id}"
    db.docs[item_path]["promotion"]["graph_plan"]["subject_entity_id"] = ""
    original_docs = copy.deepcopy(db.docs)
    replacement_id, replacement_digest, replacement_operation, _ = _replacement_operation_and_write(
        store,
        control,
        include_new=False,
    )

    with pytest.raises(
        store.ConversationSourceReplacementConflict,
        match=f"superseded lineage item has an invalid graph plan: {independent.memory_id}",
    ) as error:
        store.replace_conversation_source_firestore(
            uid="u1",
            conversation_id="conv1",
            replacement_id=replacement_id,
            replacement_digest=replacement_digest,
            replacement_operation=replacement_operation,
            observed_control=control,
            expected_source_items=[source_survivor],
            expected_reactivation_items=[independent],
            writes=[],
            deletion_gate_token="gate-token",
            db_client=db,
        )

    assert isinstance(error.value.__cause__, MalformedDocError)
    assert error.value.__cause__.document_path == item_path
    assert error.value.__cause__.error_fields == ("subject_entity_id",)
    assert db.docs == original_docs
    assert db.transaction_obj.mutations == []
    assert item_path in caplog.text
    assert secret not in caplog.text


def test_firestore_empty_conversation_replacement_is_journaled_and_idempotent(store):
    control = MemoryControlState(
        uid="u1",
        head_commit_id="head0",
        account_generation=1,
        source_generation=2,
    )
    old = _short_term_target(memory_id="mem1")
    db = _db_with(control=control, target_items=[old])
    replacement_id, replacement_digest, replacement_operation, _ = _replacement_operation_and_write(
        store, control, include_new=False
    )

    first = store.replace_conversation_source_firestore(
        uid="u1",
        conversation_id="conv1",
        replacement_id=replacement_id,
        replacement_digest=replacement_digest,
        replacement_operation=replacement_operation,
        observed_control=control,
        expected_source_items=[old],
        expected_reactivation_items=[],
        writes=[],
        deletion_gate_token="gate-token",
        db_client=db,
    )
    docs_after_first = copy.deepcopy(db.docs)
    replay = store.replace_conversation_source_firestore(
        uid="u1",
        conversation_id="conv1",
        replacement_id=replacement_id,
        replacement_digest=replacement_digest,
        replacement_operation=replacement_operation,
        observed_control=control,
        expected_source_items=[old],
        expected_reactivation_items=[],
        writes=[],
        deletion_gate_token="gate-token",
        db_client=db,
    )

    assert first.committed_memory_ids == []
    assert first.control_state.source_generation == 3
    assert first.control_state.commit_sequence == 1
    assert replay == first
    assert db.docs == docs_after_first
    assert db.docs[f"users/u1/memory_operations/{replacement_operation.operation_id}"]["status"] == (
        MemoryOperationStatus.committed.value
    )


def test_firestore_conversation_replacement_does_not_replay_stale_a_b_a_receipt(store):
    control = MemoryControlState(
        uid="u1",
        head_commit_id="head0",
        account_generation=1,
        source_generation=2,
    )
    original = _short_term_target(memory_id="mem-original")
    db = _db_with(control=control, target_items=[original])

    a_id, a_digest, a_operation, a_write = _replacement_operation_and_write(
        store,
        control,
        memory_id="mem-a",
        replacement_id="replace-a",
        replacement_digest="digest-a",
        evidence_id="ev-a-generation-3",
    )
    first_a = store.replace_conversation_source_firestore(
        uid="u1",
        conversation_id="conv1",
        replacement_id=a_id,
        replacement_digest=a_digest,
        replacement_operation=a_operation,
        observed_control=control,
        expected_source_items=[original],
        expected_reactivation_items=[],
        writes=[a_write],
        db_client=db,
    )
    docs_after_first_a = copy.deepcopy(db.docs)
    immediate_replay = store.replace_conversation_source_firestore(
        uid="u1",
        conversation_id="conv1",
        replacement_id=a_id,
        replacement_digest=a_digest,
        replacement_operation=a_operation,
        observed_control=control,
        expected_source_items=[original],
        expected_reactivation_items=[],
        writes=[a_write],
        db_client=db,
    )
    assert immediate_replay == first_a
    assert db.docs == docs_after_first_a

    current_a = MemoryItem(**db.docs["users/u1/memory_items/mem-a"])
    b_id, b_digest, b_operation, b_write = _replacement_operation_and_write(
        store,
        first_a.control_state,
        memory_id="mem-b",
        replacement_id="replace-b",
        replacement_digest="digest-b",
        evidence_id="ev-b-generation-4",
    )
    b_result = store.replace_conversation_source_firestore(
        uid="u1",
        conversation_id="conv1",
        replacement_id=b_id,
        replacement_digest=b_digest,
        replacement_operation=b_operation,
        observed_control=first_a.control_state,
        expected_source_items=[current_a],
        expected_reactivation_items=[],
        writes=[b_write],
        db_client=db,
    )

    current_b = MemoryItem(**db.docs["users/u1/memory_items/mem-b"])
    a_id, a_digest, next_a_operation, next_a_write = _replacement_operation_and_write(
        store,
        b_result.control_state,
        memory_id="mem-a",
        replacement_id="replace-a",
        replacement_digest="digest-a",
        evidence_id="ev-a-generation-5",
    )
    next_a = store.replace_conversation_source_firestore(
        uid="u1",
        conversation_id="conv1",
        replacement_id=a_id,
        replacement_digest=a_digest,
        replacement_operation=next_a_operation,
        observed_control=b_result.control_state,
        expected_source_items=[current_b],
        expected_reactivation_items=[],
        writes=[next_a_write],
        db_client=db,
    )

    assert next_a.control_state.source_generation == 5
    assert next_a.control_state.source_generation > first_a.control_state.source_generation
    assert next_a.committed_memory_ids == ["mem-a"]
    assert db.docs["users/u1/memory_items/mem-a"]["status"] == MemoryItemStatus.active.value
    assert db.docs["users/u1/memory_items/mem-b"]["status"] == MemoryItemStatus.tombstoned.value
    assert db.docs["users/u1/memory_source_replacements/replace-a"]["control_state"]["source_generation"] == 5


def test_firestore_conversation_replacement_write_failure_rolls_back_everything(store):
    control = MemoryControlState(
        uid="u1",
        head_commit_id="head0",
        account_generation=1,
        source_generation=2,
    )
    old = _short_term_target(memory_id="mem1")
    db = _db_with(control=control, target_items=[old])
    replacement_id, replacement_digest, replacement_operation, write = _replacement_operation_and_write(store, control)
    original_docs = copy.deepcopy(db.docs)
    db.transaction_obj.fail_after_sets = 2

    with pytest.raises(RuntimeError, match="injected transaction set failure"):
        store.replace_conversation_source_firestore(
            uid="u1",
            conversation_id="conv1",
            replacement_id=replacement_id,
            replacement_digest=replacement_digest,
            replacement_operation=replacement_operation,
            observed_control=control,
            expected_source_items=[old],
            expected_reactivation_items=[],
            writes=[write],
            db_client=db,
        )

    assert db.docs == original_docs
    assert db.transaction_obj.sets == []
    assert db.transaction_obj.deletes == []
    assert db.transaction_obj.mutations == []


def test_firestore_conversation_replacement_rejects_unrelated_existing_target(store):
    control = MemoryControlState(
        uid="u1",
        head_commit_id="head0",
        account_generation=1,
        source_generation=2,
    )
    old = _short_term_target(memory_id="mem1")
    unrelated = _short_term_target(
        memory_id="mem2",
        evidence=[
            _evidence(
                evidence_id="ev-unrelated",
                source_id="other-conversation",
                conversation_id="other-conversation",
            )
        ],
    )
    db = _db_with(control=control, target_items=[old, unrelated])
    replacement_id, replacement_digest, replacement_operation, write = _replacement_operation_and_write(store, control)
    original_docs = copy.deepcopy(db.docs)

    with pytest.raises(
        store.ConversationSourceReplacementConflict,
        match="replacement target belongs to unrelated state",
    ):
        store.replace_conversation_source_firestore(
            uid="u1",
            conversation_id="conv1",
            replacement_id=replacement_id,
            replacement_digest=replacement_digest,
            replacement_operation=replacement_operation,
            observed_control=control,
            expected_source_items=[old],
            expected_reactivation_items=[],
            writes=[write],
            db_client=db,
        )

    assert db.docs == original_docs
    assert db.transaction_obj.mutations == []


def test_firestore_conversation_replacement_preflights_transaction_limit_before_writes(store):
    control = MemoryControlState(
        uid="u1",
        head_commit_id="head0",
        account_generation=1,
        source_generation=2,
    )
    old_items = []
    old_evidence = []
    for index in range(100):
        evidence = _evidence(
            evidence_id=f"ev-old-{index}",
            source_id="conv1",
            conversation_id="conv1",
        )
        old_evidence.append(evidence)
        old_items.append(
            _short_term_target(
                memory_id=f"mem-old-{index}",
                evidence=[evidence],
            )
        )
    db = _db_with(control=control, target_items=old_items)
    for evidence in old_evidence:
        db.docs[f"users/u1/memory_evidence/{evidence.evidence_id}"] = _stored_model(evidence)
    replacement_id, replacement_digest, replacement_operation, _ = _replacement_operation_and_write(
        store, control, include_new=False
    )
    original_docs = copy.deepcopy(db.docs)

    with pytest.raises(
        store.ConversationSourceReplacementLimitError,
        match="exceeds Firestore's 500-mutation transaction limit",
    ):
        store.replace_conversation_source_firestore(
            uid="u1",
            conversation_id="conv1",
            replacement_id=replacement_id,
            replacement_digest=replacement_digest,
            replacement_operation=replacement_operation,
            observed_control=control,
            expected_source_items=old_items,
            expected_reactivation_items=[],
            writes=[],
            deletion_gate_token="gate-token",
            db_client=db,
        )

    assert db.docs == original_docs
    assert db.transaction_obj.mutations == []


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
    assert result.memory_items[0].tier == MemoryTier.short_term
    assert result.graph_assertions == []
    graph_assertion_path = f"users/u1/memory_graph_assertions/{result.memory_items[0].memory_id}"
    assert graph_assertion_path in db.transaction_obj.deletes
    assert graph_assertion_path not in db.docs

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


def test_firestore_apply_creates_operation_inside_transaction_and_never_overwrites_committed_replay(store):
    operation = _operation()
    db = _db_with(operation=operation)
    operation_path = f"users/u1/memory_operations/{operation.operation_id}"
    db.docs.pop(operation_path)

    first = store.apply_long_term_patch_firestore(
        uid="u1",
        operation_id=operation.operation_id,
        patch_payload=_patch(),
        proposed_operation=operation,
        db_client=db,
    )
    first_sequence = first.control_state.commit_sequence
    assert first.status == ApplyStatus.committed
    assert db.docs[operation_path]["status"] == MemoryOperationStatus.committed.value

    replay = store.apply_long_term_patch_firestore(
        uid="u1",
        operation_id=operation.operation_id,
        patch_payload=_patch(),
        proposed_operation=operation,
        db_client=db,
    )

    assert replay.status == ApplyStatus.idempotent_skip
    assert replay.control_state.commit_sequence == first_sequence
    assert db.docs[operation_path]["status"] == MemoryOperationStatus.committed.value


def test_firestore_standalone_reopen_receipt_blocks_duplicate_current_tail(store):
    now = datetime.now(timezone.utc)
    source_evidence = _evidence(evidence_id="ev-closed-source", source_id="source", source_version="v1")
    reopen_evidence = _evidence(
        evidence_id="ev-reopen",
        source_id="source",
        source_type="explicit_user_reopen",
        source_version="item_revision:1",
    )
    source = _target_item(
        memory_id="source",
        content="User lives in Boston.",
        evidence=[source_evidence],
        content_hash="source-content-hash",
        status=MemoryItemStatus.superseded,
        valid_from=now - timedelta(days=1),
        valid_to=now,
        canonical_memory_id=None,
        superseded_by=None,
        ledger_schema_version="knowledge_ledger.v1",
        kind=MemoryKind.fact,
        subject_scope=MemorySubjectScope.primary_user,
        slot="home_city",
        intent_backed=True,
        write_reason=LedgerWriteReason.daily_reconciliation,
        user_asserted=True,
    )
    control = MemoryControlState(uid="u1", head_commit_id="head0", account_generation=1, source_generation=2)
    patch = _patch(
        patch_id="patch-reopen",
        packet_id="source",
        run_id="reopen-source",
        idempotency_key="reopen-source",
        evidence_ids=[source_evidence.evidence_id, reopen_evidence.evidence_id],
        new_memory_id="replacement",
        memory_text=source.content,
        initial_tier=MemoryTier.long_term,
        ledger_schema_version="knowledge_ledger.v1",
        kind=MemoryKind.fact,
        subject_scope=MemorySubjectScope.primary_user,
        slot="home_city",
        intent_backed=True,
        write_reason=LedgerWriteReason.direct_user_statement,
        user_asserted=True,
        visibility="private",
    )
    mutation_identity = build_patch_mutation_identity(patch)
    patch["mutation_metadata"] = mutation_identity
    operation = _operation(
        operation_type=MemoryOperationType.ledger_mutation,
        source_packet_id="source",
        evidence_ids=patch["evidence_ids"],
        logical_payload={
            "decision": DurablePatchDecision.add.value,
            "memory_text": source.content,
            "supersedes": [],
            "result_status": LifecycleState.active.value,
            "mutation_metadata": mutation_identity,
        },
    )
    db = _db_with(control=control, operation=operation, evidence=source_evidence, target_items=[source])
    db.docs.pop("users/u1/memory_evidence/ev1", None)
    db.docs[f"users/u1/memory_evidence/{source_evidence.evidence_id}"] = _stored_model(source_evidence)
    db.docs[f"users/u1/memory_evidence/{reopen_evidence.evidence_id}"] = _stored_model(reopen_evidence)
    receipt = MemoryLedgerReopenReceipt(
        uid="u1",
        source_memory_id="source",
        replacement_memory_id="replacement",
        operation_id="client-op-1",
        account_generation=1,
        source_generation=2,
        source_item_revision=source.item_revision,
        source_content_hash=source.content_hash or "",
    )

    first = store.apply_direct_user_long_term_patch_firestore(
        uid="u1",
        operation_id=operation.operation_id,
        patch_payload=patch,
        proposed_operation=operation,
        proposed_evidence=[source_evidence, reopen_evidence],
        required_source_item=source,
        ledger_reopen_receipt=receipt,
        db_client=db,
    )
    assert first.status == ApplyStatus.committed, first.reason
    assert db.docs["users/u1/memory_ledger_reopens/source"]["replacement_memory_id"] == "replacement"

    replay = store.apply_direct_user_long_term_patch_firestore(
        uid="u1",
        operation_id=operation.operation_id,
        patch_payload=patch,
        proposed_operation=operation,
        proposed_evidence=[source_evidence, reopen_evidence],
        required_source_item=source,
        ledger_reopen_receipt=receipt,
        db_client=db,
    )
    assert replay.status == ApplyStatus.idempotent_skip
    assert len([path for path in db.docs if path.startswith("users/u1/memory_items/")]) == 2

    competing = _operation(
        operation_type=MemoryOperationType.ledger_mutation,
        source_packet_id="source:competing",
        evidence_ids=patch["evidence_ids"],
        observed_head_commit_id=first.control_state.head_commit_id,
        logical_payload={
            "decision": DurablePatchDecision.add.value,
            "memory_text": source.content,
            "supersedes": [],
            "result_status": LifecycleState.active.value,
            "mutation_metadata": mutation_identity,
        },
    )
    competing_result = store.apply_direct_user_long_term_patch_firestore(
        uid="u1",
        operation_id=competing.operation_id,
        patch_payload=patch,
        proposed_operation=competing,
        proposed_evidence=[source_evidence, reopen_evidence],
        required_source_item=source,
        ledger_reopen_receipt=receipt.model_copy(update={"operation_id": "client-op-2"}),
        db_client=db,
    )
    assert competing_result.status == ApplyStatus.source_not_active
    assert len([path for path in db.docs if path.startswith("users/u1/memory_items/")]) == 2


def test_firestore_apply_stages_new_evidence_in_the_same_commit(store):
    operation = _operation()
    evidence = _evidence()
    db = _db_with(operation=operation)
    evidence_path = "users/u1/memory_evidence/ev1"
    db.docs.pop(evidence_path)

    result = store.apply_long_term_patch_firestore(
        uid="u1",
        operation_id=operation.operation_id,
        patch_payload=_patch(),
        proposed_operation=operation,
        proposed_evidence=[evidence],
        db_client=db,
    )

    assert result.status == ApplyStatus.committed
    assert db.docs[evidence_path]["evidence_id"] == evidence.evidence_id
    assert evidence_path in [path for path, _ in db.transaction_obj.sets]


def test_firestore_apply_does_not_orphan_proposed_evidence_when_patch_fails(store):
    evidence = _evidence(evidence_id="ev-ledger-failed", source_version="v2")
    operation = _operation(
        operation_type=MemoryOperationType.long_term_apply,
        evidence_ids=[evidence.evidence_id],
    )
    patch = _patch(
        evidence_ids=[evidence.evidence_id],
        ledger_schema_version="knowledge_ledger.v1",
        initial_tier=MemoryTier.long_term,
        intent_backed=True,
        write_reason="agent_reusable_conclusion",
    )
    db = _db_with(operation=operation)
    evidence_path = f"users/u1/memory_evidence/{evidence.evidence_id}"

    result = store.apply_long_term_patch_firestore(
        uid="u1",
        operation_id=operation.operation_id,
        patch_payload=patch,
        proposed_operation=operation,
        proposed_evidence=[evidence],
        db_client=db,
    )

    assert result.status == ApplyStatus.invalid_patch
    assert evidence_path not in db.docs
    assert evidence_path not in [path for path, _ in db.transaction_obj.sets]


def test_firestore_apply_rejects_changed_source_version_for_existing_evidence_identity(store):
    operation = _operation()
    db = _db_with(operation=operation, evidence=_evidence(source_version="v1"))

    with pytest.raises(store.MemoryFirestoreApplyError, match="conflicts with existing evidence identity"):
        store.apply_long_term_patch_firestore(
            uid="u1",
            operation_id=operation.operation_id,
            patch_payload=_patch(),
            proposed_operation=operation,
            proposed_evidence=[_evidence(source_version="v2")],
            db_client=db,
        )

    assert db.docs["users/u1/memory_evidence/ev1"]["source_version"] == "v1"
    assert db.transaction_obj.mutations == []


@pytest.mark.parametrize("source_state", [SourceState.tombstoned, SourceState.purged])
def test_firestore_apply_never_resurrects_inactive_proposed_evidence(store, source_state):
    operation = _operation()
    db = _db_with(operation=operation)
    evidence_path = "users/u1/memory_evidence/ev1"
    db.docs.pop(evidence_path)

    with pytest.raises(store.MemoryFirestoreApplyError, match="proposed evidence must be active"):
        store.apply_long_term_patch_firestore(
            uid="u1",
            operation_id=operation.operation_id,
            patch_payload=_patch(),
            proposed_operation=operation,
            proposed_evidence=[
                _evidence(
                    source_state=source_state,
                    source_state_reason=(
                        SourceStateReason.deleted_by_user
                        if source_state == SourceState.tombstoned
                        else SourceStateReason.account_purged
                    ),
                )
            ],
            db_client=db,
        )

    assert evidence_path not in db.docs
    assert db.transaction_obj.mutations == []


def test_firestore_add_rejects_new_operation_that_collides_with_existing_ledger_row_id(store):
    first_evidence = _evidence(evidence_id="ev-ledger-v1", source_version="v1")
    first_operation = _operation(
        operation_type=MemoryOperationType.ledger_mutation,
        evidence_ids=[first_evidence.evidence_id],
    )
    patch = _patch(
        new_memory_id="mem-ledger-stable-action",
        evidence_ids=[first_evidence.evidence_id],
        ledger_schema_version="knowledge_ledger.v1",
        initial_tier=MemoryTier.long_term,
        intent_backed=True,
        write_reason=LedgerWriteReason.agent_reusable_conclusion,
    )
    db = _db_with(operation=first_operation)
    db.docs.pop("users/u1/memory_evidence/ev1")
    db.docs["users/u1/memory_state/apply_control"].update({"writer_mode": "ledger", "writer_epoch": 1})

    first = store.apply_long_term_patch_firestore(
        uid="u1",
        operation_id=first_operation.operation_id,
        patch_payload=patch,
        proposed_operation=first_operation,
        proposed_evidence=[first_evidence],
        db_client=db,
    )
    assert first.status == ApplyStatus.committed
    original = copy.deepcopy(db.docs["users/u1/memory_items/mem-ledger-stable-action"])

    second_evidence = _evidence(evidence_id="ev-ledger-v2", source_version="v2")
    second_operation = _operation(
        operation_type=MemoryOperationType.ledger_mutation,
        evidence_ids=[second_evidence.evidence_id],
        observed_head_commit_id=first.control_state.head_commit_id,
    )
    second_patch = {
        **patch,
        "observed_head_commit_id": first.control_state.head_commit_id,
        "evidence_ids": [second_evidence.evidence_id],
    }

    collision = store.apply_long_term_patch_firestore(
        uid="u1",
        operation_id=second_operation.operation_id,
        patch_payload=second_patch,
        proposed_operation=second_operation,
        proposed_evidence=[second_evidence],
        db_client=db,
    )

    assert collision.status == ApplyStatus.invalid_patch
    assert collision.reason == "add patch new_memory_id already exists"
    assert db.docs["users/u1/memory_items/mem-ledger-stable-action"] == original
    assert "users/u1/memory_evidence/ev-ledger-v2" not in db.docs


@pytest.mark.parametrize(
    ("writer_mode", "writer_epoch", "transition_owner"),
    [
        ("transitioning_to_ledger", 1, "migration-owner"),
        ("transitioning_to_compatibility", 2, "rollback-owner"),
    ],
)
def test_firestore_apply_boundary_blocks_ordinary_writers_during_mode_transitions(
    store, writer_mode, writer_epoch, transition_owner
):
    control = MemoryControlState(
        uid="u1",
        head_commit_id="head0",
        account_generation=1,
        source_generation=2,
        writer_mode=writer_mode,
        writer_epoch=writer_epoch,
        writer_transition_owner=transition_owner,
    )
    operation = _operation()
    db = _db_with(control=control, operation=operation)

    result = store.apply_long_term_patch_firestore(
        uid="u1",
        operation_id=operation.operation_id,
        patch_payload=_patch(),
        proposed_operation=operation,
        db_client=db,
    )

    assert result.status == ApplyStatus.invalid_patch
    assert "not admitted" in (result.reason or "")
    assert not any(path.startswith("users/u1/memory_items/") for path in db.docs)


def test_firestore_apply_boundary_blocks_legacy_schema_writer_in_ledger_mode(store):
    control = MemoryControlState(
        uid="u1",
        head_commit_id="head0",
        account_generation=1,
        source_generation=2,
        writer_mode="ledger",
        writer_epoch=1,
    )
    operation = _operation()
    db = _db_with(control=control, operation=operation)

    result = store.apply_long_term_patch_firestore(
        uid="u1",
        operation_id=operation.operation_id,
        patch_payload=_patch(),
        proposed_operation=operation,
        db_client=db,
    )

    assert result.status == ApplyStatus.invalid_patch
    assert "compatibility writer is not admitted" in (result.reason or "")
    assert not any(path.startswith("users/u1/memory_items/") for path in db.docs)


def test_firestore_apply_rejects_user_mutation_disguised_as_ledger_migration(store):
    existing = _target_item()
    control = MemoryControlState(
        uid="u1",
        head_commit_id="head0",
        account_generation=1,
        source_generation=2,
        writer_mode="transitioning_to_ledger",
        writer_epoch=1,
        writer_transition_owner="migration-owner",
    )
    operation = _operation(
        operation_type=MemoryOperationType.user_mutation,
        source_packet_id="user_mutation:content_edit:mem1:r1:attack",
        target_memory_id="mem1",
        logical_payload={
            "decision": "update",
            "target_memory_id": "mem1",
            "memory_text": "Unauthorized edit.",
            "result_status": "active",
        },
    )
    db = _db_with(control=control, operation=operation, target_items=[existing])
    patch = _patch(
        decision=DurablePatchDecision.update,
        target_memory_id="mem1",
        memory_text="Unauthorized edit.",
        ledger_schema_version="knowledge_ledger.v1",
    )

    result = store.apply_long_term_patch_firestore(
        uid="u1",
        operation_id=operation.operation_id,
        patch_payload=patch,
        proposed_operation=operation,
        allow_ledger_migration=True,
        db_client=db,
    )

    assert result.status == ApplyStatus.invalid_patch
    assert "allowlisted pre-ledger schema adaptation" in (result.reason or "")
    assert db.docs["users/u1/memory_items/mem1"]["content"] == existing.content


def test_firestore_apply_rejects_spoofed_user_prefix_for_ledger_append_in_compatibility(store):
    operation = _operation(
        operation_type=MemoryOperationType.ledger_mutation,
        source_packet_id="user_mutation:spoofed-ledger-add",
    )
    db = _db_with(operation=operation)
    patch = _patch(
        ledger_schema_version="knowledge_ledger.v1",
        initial_tier=MemoryTier.long_term,
        intent_backed=True,
        write_reason=LedgerWriteReason.direct_user_statement,
        user_asserted=True,
    )

    result = store.apply_long_term_patch_firestore(
        uid="u1",
        operation_id=operation.operation_id,
        patch_payload=patch,
        proposed_operation=operation,
        db_client=db,
    )

    assert result.status == ApplyStatus.invalid_patch
    assert "ledger writer is not admitted" in (result.reason or "")


def test_firestore_apply_rejects_spoofed_user_update_that_clears_ledger_schema_in_compatibility(store):
    existing = _target_item(
        ledger_schema_version="knowledge_ledger.v1",
        kind=MemoryKind.fact,
        subject_scope=MemorySubjectScope.primary_user,
        intent_backed=True,
        write_reason=LedgerWriteReason.direct_user_statement,
        user_asserted=True,
    )
    operation = _operation(
        operation_type=MemoryOperationType.user_mutation,
        source_packet_id="user_mutation:spoofed-ledger-update",
        target_memory_id=existing.memory_id,
        logical_payload={
            "decision": DurablePatchDecision.update.value,
            "target_memory_id": existing.memory_id,
            "memory_text": "Spoofed downgrade.",
            "result_status": LifecycleState.active.value,
        },
    )
    db = _db_with(operation=operation, target_items=[existing])
    patch = _patch(
        decision=DurablePatchDecision.update,
        target_memory_id=existing.memory_id,
        memory_text="Spoofed downgrade.",
        ledger_schema_version=None,
        expected_item_revision=existing.item_revision,
        expected_content_hash=existing.content_hash,
    )

    result = store.apply_long_term_patch_firestore(
        uid="u1",
        operation_id=operation.operation_id,
        patch_payload=patch,
        proposed_operation=operation,
        db_client=db,
    )

    assert result.status == ApplyStatus.invalid_patch
    assert "ledger writer is not admitted" in (result.reason or "")
    stored = db.docs[f"users/u1/memory_items/{existing.memory_id}"]
    assert stored["ledger_schema_version"] == "knowledge_ledger.v1"
    assert stored["content"] == existing.content


def test_firestore_promotion_persists_long_term_item_and_structured_graph_assertion_atomically(store):
    existing = _short_term_target()
    memory_text = "User prefers concise updates."
    operation = _promotion_operation(existing, memory_text=memory_text)
    db = _db_with(operation=operation, target_items=[existing])

    result = store.apply_long_term_patch_firestore(
        uid="u1",
        operation_id=operation.operation_id,
        patch_payload=_promotion_patch(existing, memory_text=memory_text),
        db_client=db,
    )

    assert result.status == ApplyStatus.committed
    assert len(result.graph_assertions) == 1
    promoted_path = f"users/u1/memory_items/{existing.memory_id}"
    assertion_path = f"users/u1/memory_graph_assertions/{existing.memory_id}"
    promoted = MemoryItem(**db.docs[promoted_path])
    assertion = db.docs[assertion_path]
    assert promoted.tier == MemoryTier.long_term
    assert promoted.graph_ready is True
    assert promoted.graph_assertion_id == assertion["assertion_id"]
    assert promoted.graph_plan_hash == assertion["graph_plan_hash"]
    assert assertion["memory_id"] == existing.memory_id
    assert assertion["item_revision"] == promoted.item_revision
    assert assertion["commit_id"] == result.control_state.head_commit_id
    assert assertion_path not in db.transaction_obj.deletes


def test_firestore_superseding_promotion_writes_new_assertion_and_deletes_old_assertion_in_one_commit(store):
    existing = _short_term_target()
    superseded = _target_item(
        memory_id="mem_old",
        graph_ready=True,
        graph_assertion_id="mga_old",
        graph_plan_hash="plan_old",
        kg_extracted=True,
    )
    memory_text = "User prefers concise updates."
    operation = _promotion_operation(existing, memory_text=memory_text, supersedes=[superseded.memory_id])
    db = _db_with(operation=operation, target_items=[existing, superseded])
    old_assertion_path = f"users/u1/memory_graph_assertions/{superseded.memory_id}"
    new_assertion_path = f"users/u1/memory_graph_assertions/{existing.memory_id}"
    db.docs[old_assertion_path] = {"assertion_id": "mga_old", "memory_id": superseded.memory_id}

    result = store.apply_long_term_patch_firestore(
        uid="u1",
        operation_id=operation.operation_id,
        patch_payload=_promotion_patch(
            existing,
            memory_text=memory_text,
            supersedes=[superseded.memory_id],
        ),
        db_client=db,
    )

    assert result.status == ApplyStatus.committed
    assert new_assertion_path in db.docs
    assert old_assertion_path not in db.docs
    assert old_assertion_path in db.transaction_obj.deletes
    promoted = MemoryItem(**db.docs[f"users/u1/memory_items/{existing.memory_id}"])
    invalidated = MemoryItem(**db.docs[f"users/u1/memory_items/{superseded.memory_id}"])
    assert promoted.graph_assertion_id == db.docs[new_assertion_path]["assertion_id"]
    assert invalidated.status == MemoryItemStatus.superseded
    assert invalidated.superseded_by == promoted.memory_id
    assert invalidated.graph_ready is False
    assert result.operation.committed_memory_item_ids == [existing.memory_id, superseded.memory_id]


def test_firestore_graph_delete_failure_rolls_back_promotion_items_assertion_and_head(store):
    existing = _short_term_target()
    superseded = _target_item(
        memory_id="mem_old",
        graph_ready=True,
        graph_assertion_id="mga_old",
        graph_plan_hash="plan_old",
        kg_extracted=True,
    )
    memory_text = "User prefers concise updates."
    operation = _promotion_operation(existing, memory_text=memory_text, supersedes=[superseded.memory_id])
    db = _db_with(operation=operation, target_items=[existing, superseded])
    old_assertion_path = f"users/u1/memory_graph_assertions/{superseded.memory_id}"
    db.docs[old_assertion_path] = {"assertion_id": "mga_old", "memory_id": superseded.memory_id}
    original_docs = copy.deepcopy(db.docs)
    db.transaction_obj.fail_delete_paths.add(old_assertion_path)

    with pytest.raises(RuntimeError, match="injected transaction delete failure"):
        store.apply_long_term_patch_firestore(
            uid="u1",
            operation_id=operation.operation_id,
            patch_payload=_promotion_patch(
                existing,
                memory_text=memory_text,
                supersedes=[superseded.memory_id],
            ),
            db_client=db,
        )

    assert db.docs == original_docs
    assert db.transaction_obj.sets == []
    assert db.transaction_obj.deletes == []
    assert db.transaction_obj.mutations == []


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


def test_firestore_apply_allows_short_term_update_when_target_is_authoritative_active_same_generation(store):
    operation = _operation(
        target_memory_id="mem1",
        logical_payload={
            "decision": "update",
            "target_memory_id": "mem1",
            "memory_text": "Updated.",
            "result_status": "active",
        },
    )
    db = _db_with(operation=operation, target_items=[_short_term_target()])
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


@pytest.mark.parametrize(
    ("writer_mode", "operation_type"),
    [
        ("transitioning_to_ledger", MemoryOperationType.long_term_apply),
        ("transitioning_to_compatibility", MemoryOperationType.ledger_mutation),
    ],
)
def test_firestore_apply_retries_committed_operation_from_stored_result_without_rereading_mutable_evidence_or_target(
    store, writer_mode, operation_type
):
    operation = _operation(
        operation_type=operation_type,
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
    control = MemoryControlState(
        uid="u1",
        head_commit_id="head1",
        account_generation=1,
        source_generation=2,
        writer_mode=writer_mode,
        writer_epoch=1,
        writer_transition_owner="transition-owner",
    )
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


def test_firestore_apply_settles_generation_and_head_mismatch_before_dependent_reads(store):
    operation = _operation()
    generation_control = MemoryControlState(
        uid="u1",
        head_commit_id="head0",
        account_generation=1,
        source_generation=3,
    )
    generation_db = _db_with(control=generation_control, operation=operation)
    generation_db.docs.pop("users/u1/memory_evidence/ev1")

    stale = store.apply_long_term_patch_firestore(
        uid="u1",
        operation_id=operation.operation_id,
        patch_payload=_patch(),
        db_client=generation_db,
    )

    assert stale.status == ApplyStatus.generation_mismatch
    assert generation_db.docs[f"users/u1/memory_operations/{operation.operation_id}"]["status"] == (
        MemoryOperationStatus.stale_generation.value
    )

    head_control = MemoryControlState(
        uid="u1",
        head_commit_id="head-new",
        account_generation=1,
        source_generation=2,
    )
    head_db = _db_with(control=head_control, operation=operation)
    head_db.docs.pop("users/u1/memory_evidence/ev1")

    rebased = store.apply_long_term_patch_firestore(
        uid="u1",
        operation_id=operation.operation_id,
        patch_payload=_patch(),
        db_client=head_db,
    )

    assert rebased.status == ApplyStatus.retryable_head_mismatch
    assert head_db.docs[f"users/u1/memory_operations/{operation.operation_id}"]["observed_head_commit_id"] == "head-new"


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


def test_explicit_trigger_feedback_receipt_commits_and_replays_with_the_canonical_revision(store):
    feedback_id = "f" * 64
    trigger = _target_item(
        memory_id="trigger-1",
        user_asserted=True,
        ledger_schema_version="knowledge_ledger.v1",
        kind=MemoryKind.trigger,
        subject_scope=MemorySubjectScope.primary_user,
        slot=None,
        trigger_condition={
            "keywords": ["release"],
            "action": {"type": "agent_prompt", "prompt": "Give the next release step."},
        },
        intent_backed=True,
        write_reason=LedgerWriteReason.standing_trigger,
    )
    source_packet_id = f"user_mutation:jit_trigger_feedback:{feedback_id}:trigger-1:r1:receipt"
    patch = {
        "patch_id": f"patch-{feedback_id}",
        "packet_id": feedback_id,
        "run_id": feedback_id,
        "observed_head_commit_id": "head0",
        "idempotency_key": feedback_id,
        "decision": DurablePatchDecision.update.value,
        "target_memory_id": trigger.memory_id,
        "result_status": LifecycleState.active.value,
        "evidence_ids": ["ev1"],
        "expected_item_revision": trigger.item_revision,
        "expected_content_hash": trigger.content_hash,
        "arguments": {
            "jit_trigger_feedback": {
                "applied_feedback_ids": [feedback_id],
                "last_action": "useful",
                "feedback_count": 1,
            }
        },
        "curation_weight": 1,
    }
    mutation_identity = build_patch_mutation_identity(patch)
    patch["mutation_metadata"] = mutation_identity
    operation = MemoryOperation.new(
        uid="u1",
        operation_type=MemoryOperationType.ledger_mutation,
        source_packet_id=source_packet_id,
        target_memory_id=trigger.memory_id,
        evidence_ids=["ev1"],
        logical_payload={
            "decision": DurablePatchDecision.update.value,
            "memory_text": None,
            "target_memory_id": trigger.memory_id,
            "result_status": LifecycleState.active.value,
            "supersedes": [],
            "arguments": patch["arguments"],
            "mutation_metadata": mutation_identity,
        },
        account_generation=1,
        source_generation=2,
        observed_head_commit_id="head0",
    )
    receipt = JITTriggerFeedbackReceipt(
        uid="u1",
        feedback_id=feedback_id,
        event_id="e" * 64,
        trigger_memory_id=trigger.memory_id,
        account_generation=1,
        expected_trigger_revision=trigger.item_revision,
        action="useful",
        recorded_at=datetime.now(timezone.utc),
        request_hash="a" * 64,
    )
    db = _db_with(operation=operation, target_items=[trigger])
    db.docs[f"users/u1/jit_proactivity_events/{'e' * 64}"] = _stored_model(
        JITProactivityEventReceipt(
            uid="u1",
            event_id="e" * 64,
            candidate_id="c" * 64,
            operation="planned_notification",
            account_generation=1,
            trigger_memory_id=trigger.memory_id,
            trigger_revision=trigger.item_revision,
            budget_day="2026-08-24",
            device_id="d" * 64,
            created_at=datetime.now(timezone.utc),
            request_hash="c" * 64,
        )
    )

    first = store.apply_direct_user_long_term_patch_firestore(
        uid="u1",
        operation_id=operation.operation_id,
        patch_payload=patch,
        proposed_operation=operation,
        trigger_feedback_receipt=receipt,
        db_client=db,
    )

    assert first.status == ApplyStatus.committed, first.reason
    persisted = db.docs[f"users/u1/jit_trigger_feedback/{feedback_id}"]
    assert persisted["request_hash"] == "a" * 64
    assert persisted["applied_trigger_revision"] == trigger.item_revision + 1
    assert db.docs["users/u1/memory_items/trigger-1"]["curation_weight"] == 1

    replay = store.apply_direct_user_long_term_patch_firestore(
        uid="u1",
        operation_id=operation.operation_id,
        patch_payload=patch,
        proposed_operation=operation,
        trigger_feedback_receipt=receipt,
        db_client=db,
    )
    assert replay.status == ApplyStatus.idempotent_skip

    with pytest.raises(store.MemoryFirestoreApplyError, match="different payload"):
        store.apply_direct_user_long_term_patch_firestore(
            uid="u1",
            operation_id=operation.operation_id,
            patch_payload=patch,
            proposed_operation=operation,
            trigger_feedback_receipt=receipt.model_copy(update={"request_hash": "b" * 64}),
            db_client=db,
        )
