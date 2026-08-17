"""Behavioral tests for the authoritative L2 route/apply boundary."""

from __future__ import annotations

import hashlib
import importlib
import os
import sys
from datetime import datetime, timedelta, timezone
from typing import Optional

import pytest

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)

from tests.unit.memory_import_isolation import (
    CONSOLIDATION_APPLY_STUB_MODULE_NAMES,
    ensure_utils_memory_packages_importable,
    install_consolidation_apply_stubs,
    restore_sys_modules,
    snapshot_sys_modules,
)

canonical_consolidation = None
ConsolidationAgentDecision = None
apply_consolidation_decision = None


@pytest.fixture(scope="module", autouse=True)
def _consolidation_apply_import_isolation():
    saved = snapshot_sys_modules(CONSOLIDATION_APPLY_STUB_MODULE_NAMES)
    touched = install_consolidation_apply_stubs()
    saved.update(snapshot_sys_modules(touched))
    ensure_utils_memory_packages_importable()

    for stale_module in ("database.memory_apply_store", "utils.memory.canonical_consolidation"):
        sys.modules.pop(stale_module, None)

    module = importlib.import_module("utils.memory.canonical_consolidation")
    globals()["canonical_consolidation"] = module
    globals()["ConsolidationAgentDecision"] = module.ConsolidationAgentDecision
    globals()["apply_consolidation_decision"] = module.apply_consolidation_decision
    yield
    restore_sys_modules(saved)


from models.memory_apply import MemoryControlState, memory_content_hash
from models.memory_admission import (
    REQUIRED_PROCESSING_RECEIPT_VERSION,
    REQUIRED_PROCESSOR_ID,
    REQUIRED_PROCESSOR_VERSION,
    valid_required_processing_receipt,
)
from models.memory_evidence import ArtifactPreservationState, MemoryEvidence, SourceState
from models.memory_operations import MemoryOperation, MemoryOperationStatus, MemoryOperationType
from models.product_memory import MemoryItemStatus, MemoryTier, ProcessingState, MemoryItem
from utils.memory.canonical_lineage import canonical_lineage_root
from utils.memory.memory_system import MemorySystem

NOW = datetime(2026, 6, 20, 12, 0, tzinfo=timezone.utc)
UID = "uid-canonical"


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

    def set(self, data, merge=False):
        if merge and self.path in self._db.docs:
            merged = dict(self._db.docs[self.path])
            merged.update(data)
            self._db.docs[self.path] = merged
        else:
            self._db.docs[self.path] = data


class _FakeTransaction:
    def __init__(self, db):
        self._db = db
        self.sets = []
        self.deletes = []
        self.fail_after_sets: Optional[int] = None
        self._id = None
        self._read_only = False
        self._max_attempts = 5

    def set(self, ref, data):
        self.sets.append((ref.path, data))
        if self.fail_after_sets is not None and len(self.sets) > self.fail_after_sets:
            raise RuntimeError("injected transaction set failure")

    def delete(self, ref):
        self.deletes.append(ref.path)

    def _clean_up(self):
        self._id = None

    def _begin(self, retry_id=None):
        self._id = retry_id or "txn-1"
        self.sets = []
        self.deletes = []

    def _commit(self):
        for path, data in self.sets:
            self._db.docs[path] = data
        for path in self.deletes:
            self._db.docs.pop(path, None)

    def _rollback(self):
        self._id = None
        self.sets = []
        self.deletes = []


class _FakeDb:
    def __init__(self, docs):
        self.docs = docs
        self.transaction_obj = _FakeTransaction(self)

    def transaction(self):
        return self.transaction_obj

    def document(self, path):
        return _FakeDocumentRef(path, self)


def _evidence(evidence_id: str, *, source_id: str = "conv-1") -> MemoryEvidence:
    return MemoryEvidence(
        evidence_id=evidence_id,
        source_id=source_id,
        source_type="conversation",
        source_version="v1",
        artifact_preservation=ArtifactPreservationState.preserved,
    )


def _item(
    memory_id: str,
    content: str,
    *,
    tier: MemoryTier = MemoryTier.short_term,
    evidence_ids: Optional[list[str]] = None,
) -> MemoryItem:
    evidence = [_evidence(evidence_id) for evidence_id in (evidence_ids or [f"ev_{memory_id}"])]
    return MemoryItem(
        memory_id=memory_id,
        uid=UID,
        version=2,
        tier=tier,
        status=MemoryItemStatus.active,
        processing_state=ProcessingState.processed,
        content=content,
        evidence=evidence,
        source_state=SourceState.active,
        sensitivity_labels=[],
        visibility="private",
        user_asserted=False,
        captured_at=NOW - timedelta(hours=2),
        updated_at=NOW - timedelta(hours=1),
        expires_at=NOW + timedelta(days=30) if tier == MemoryTier.short_term else None,
        ledger_commit_id="commit-1",
        ledger_sequence=1,
        item_revision=2,
        source_commit_id="commit-1",
        source_commit_sequence=1,
        content_hash=memory_content_hash(
            content=content,
            evidence_ids=[item.evidence_id for item in evidence],
        ),
        account_generation=1,
    )


def _stored(model) -> dict:
    return model.model_dump(mode="json")


def _db_for_items(source: MemoryItem, *other_items: MemoryItem) -> _FakeDb:
    control = MemoryControlState(uid=UID, head_commit_id="head0", account_generation=1, source_generation=1)
    docs = {
        f"users/{UID}/memory_state/apply_control": _stored(control),
    }
    for item in (source, *other_items):
        docs[f"users/{UID}/memory_items/{item.memory_id}"] = _stored(item)
        for evidence in item.evidence:
            docs[f"users/{UID}/memory_evidence/{evidence.evidence_id}"] = _stored(evidence)
    return _FakeDb(docs)


def _promote_decision(
    source: MemoryItem,
    *,
    supersedes: Optional[list[str]] = None,
    target_memory_id: Optional[str] = None,
):
    return ConsolidationAgentDecision(
        source_memory_id=source.memory_id,
        route="promote",
        reconciliation="replace" if supersedes else "create",
        target_memory_id=target_memory_id,
        supersedes=supersedes or [],
        memory_text="The user enjoys hiking in Seattle.",
        evidence_ids=[evidence.evidence_id for evidence in source.evidence],
        subject_entity_id="user",
        predicate="enjoys_activity",
        arguments={"activity": "hiking", "location": "Seattle"},
        relationship_to_user="self",
        aboutness="primary_user",
        basis_for_memory="explicit",
        confidence="high",
        rationale="Explicit first-person preference.",
    )


@pytest.fixture(autouse=True)
def _canonical_runtime(monkeypatch):
    monkeypatch.setattr(
        "utils.memory.canonical_consolidation.resolve_memory_system",
        lambda uid, db_client=None: MemorySystem.CANONICAL,
    )


def _apply(source: MemoryItem, decision, db: _FakeDb, *, quarantine: bool = False):
    control = MemoryControlState(**db.docs[f"users/{UID}/memory_state/apply_control"])
    return apply_consolidation_decision(
        UID,
        decision=decision,
        pending_by_id={source.memory_id: source},
        control=control,
        run_id="run-route",
        now=NOW,
        db_client=db,
        quarantine=quarantine,
    )


def test_promote_route_atomically_commits_long_term_item_and_graph_assertion():
    source = _item("mem_source", "I enjoy hiking in Seattle.")
    db = _db_for_items(source)

    applied_ids = _apply(source, _promote_decision(source), db)

    stored = MemoryItem(**db.docs[f"users/{UID}/memory_items/{source.memory_id}"])
    assertion = db.docs[f"users/{UID}/memory_graph_assertions/{source.memory_id}"]
    operations = [
        MemoryOperation(**payload)
        for path, payload in db.docs.items()
        if path.startswith(f"users/{UID}/memory_operations/")
    ]
    assert applied_ids == [source.memory_id]
    assert stored.tier == MemoryTier.long_term
    assert stored.graph_ready is True
    assert stored.graph_assertion_id == assertion["assertion_id"]
    assert assertion["item_revision"] == stored.item_revision
    assert assertion["content_hash"] == stored.content_hash
    assert assertion["predicate"] == "enjoys_activity"
    assert len(operations) == 1
    assert operations[0].operation_type == MemoryOperationType.synthesis
    assert operations[0].status == MemoryOperationStatus.committed


def test_promotion_and_supersession_share_one_commit_and_remove_old_assertion():
    source = _item("mem_new", "I now live in Seattle.")
    old = _item("mem_old", "The user lives in Portland.", tier=MemoryTier.long_term)
    old = old.model_copy(
        update={
            "graph_ready": True,
            "graph_assertion_id": "mga_old",
            "graph_plan_hash": "old-plan",
            "kg_extracted": True,
        }
    )
    db = _db_for_items(source, old)
    db.docs[f"users/{UID}/memory_graph_assertions/{old.memory_id}"] = {
        "assertion_id": "mga_old",
    }
    decision = _promote_decision(
        source,
        supersedes=[old.memory_id],
        target_memory_id=old.memory_id,
    )

    applied_ids = _apply(source, decision, db)

    promoted = MemoryItem(**db.docs[f"users/{UID}/memory_items/{source.memory_id}"])
    superseded = MemoryItem(**db.docs[f"users/{UID}/memory_items/{old.memory_id}"])
    assert applied_ids == [source.memory_id, old.memory_id]
    assert promoted.tier == MemoryTier.long_term
    assert superseded.status == MemoryItemStatus.superseded
    assert superseded.superseded_by == source.memory_id
    assert superseded.canonical_memory_id == source.memory_id
    items_by_id = {item.memory_id: item for item in (promoted, superseded)}
    assert canonical_lineage_root(promoted, items_by_id=items_by_id) == source.memory_id
    assert canonical_lineage_root(superseded, items_by_id=items_by_id) == source.memory_id
    assert promoted.ledger_commit_id == superseded.ledger_commit_id
    assert f"users/{UID}/memory_graph_assertions/{old.memory_id}" not in db.docs


@pytest.mark.parametrize(
    ("route", "expected_status"),
    [
        ("archive", MemoryItemStatus.active),
        ("review", MemoryItemStatus.active),
        ("reject", MemoryItemStatus.hidden),
    ],
)
def test_nonpromote_routes_are_terminal_archive_outcomes(route: str, expected_status: MemoryItemStatus):
    source = _item(f"mem_{route}", "A broad but non-durable observation.")
    db = _db_for_items(source)
    decision = ConsolidationAgentDecision(
        source_memory_id=source.memory_id,
        route=route,
        evidence_ids=[],
        relationship_to_user="unclear",
        basis_for_memory="weak_or_none",
        rationale="Not safe or useful enough for durable memory.",
    )

    _apply(source, decision, db)

    stored = MemoryItem(**db.docs[f"users/{UID}/memory_items/{source.memory_id}"])
    assert stored.tier == MemoryTier.archive
    assert stored.status == expected_status
    review_path = f"users/{UID}/memory_review_queue/review:{source.memory_id}:r{stored.item_revision}:"
    if route == "review":
        assert db.docs[review_path]["source_commit_id"] == stored.ledger_commit_id
        assert db.docs[review_path]["status"] == "pending"
        assert db.docs[review_path]["authority"] == "canonical_memory"
    else:
        assert review_path not in db.docs
    assert stored.graph_ready is False
    assert f"users/{UID}/memory_graph_assertions/{source.memory_id}" not in db.docs


def test_quarantine_review_is_a_canonical_blocked_commit_with_projection_deletes():
    source = _item("mem_quarantine", "A source that exhausted automatic consolidation.")
    db = _db_for_items(source)
    decision = ConsolidationAgentDecision(
        source_memory_id=source.memory_id,
        route="review",
        relationship_to_user="unclear",
        basis_for_memory="weak_or_none",
        rationale="Automatic consolidation exhausted its bounded retry budget.",
    )

    _apply(source, decision, db, quarantine=True)

    stored = MemoryItem(**db.docs[f"users/{UID}/memory_items/{source.memory_id}"])
    assert stored.tier == MemoryTier.short_term
    assert stored.processing_state == ProcessingState.blocked
    assert stored.promotion is not None
    assert stored.promotion["route"] == "review"
    assert stored.promotion["processing_status"] == "processing_blocked"
    review_path = f"users/{UID}/memory_review_queue/review:{source.memory_id}:r{stored.item_revision}:"
    assert db.docs[review_path]["status"] == "pending"
    outbox = [payload for path, payload in db.docs.items() if path.startswith(f"users/{UID}/memory_outbox/")]
    assert len(outbox) == 2
    assert {event["payload"]["action"] for event in outbox} == {"delete"}


def test_same_route_retry_is_idempotent_and_does_not_increment_revision_twice():
    source = _item("mem_idempotent", "I enjoy hiking.")
    db = _db_for_items(source)
    decision = _promote_decision(source)

    _apply(source, decision, db)
    first = MemoryItem(**db.docs[f"users/{UID}/memory_items/{source.memory_id}"])
    _apply(source, decision, db)
    second = MemoryItem(**db.docs[f"users/{UID}/memory_items/{source.memory_id}"])

    assert second.item_revision == first.item_revision
    assert second.ledger_commit_id == first.ledger_commit_id


def test_pending_required_promote_stamps_processing_receipt_then_routes():
    content = "Remember I enjoy hiking in Seattle."
    source = _item("mem_required", content)
    source = source.model_copy(
        update={
            "processing_state": ProcessingState.pending,
            "user_asserted": True,
            "promotion": {
                "required": True,
                "status": "pending",
                "processing_status": "pending_processing",
                "processor_id": REQUIRED_PROCESSOR_ID,
                "processor_version": REQUIRED_PROCESSOR_VERSION,
                "submission": {
                    "submission_id": source.memory_id,
                    "content_hash": hashlib.sha256(content.encode("utf-8")).hexdigest(),
                },
                "source_attribution": {
                    "subject_entity_id": "user",
                    "subject_attribution": "user",
                },
            },
        }
    )
    db = _db_for_items(source)

    applied_ids = _apply(source, _promote_decision(source), db)

    stored = MemoryItem(**db.docs[f"users/{UID}/memory_items/{source.memory_id}"])
    operations = [
        MemoryOperation(**payload)
        for path, payload in db.docs.items()
        if path.startswith(f"users/{UID}/memory_operations/")
    ]
    assert applied_ids == [source.memory_id]
    assert stored.tier == MemoryTier.long_term
    assert stored.content == "The user enjoys hiking in Seattle."
    assert stored.processing_state == ProcessingState.processed
    assert stored.promotion is not None
    assert stored.promotion.get("required") is True
    assert valid_required_processing_receipt(
        content=stored.content,
        item_revision=stored.item_revision,
        promotion=stored.promotion,
    )
    assert (
        stored.promotion["processing_receipt"]["output_hash"]
        == hashlib.sha256(stored.content.encode("utf-8")).hexdigest()
    )
    assert len(operations) == 2
    assert {op.operation_type for op in operations} == {MemoryOperationType.synthesis}


def test_already_processed_required_promote_rebinds_memory_text_to_l2_content():
    l2_content = "The user enjoys hiking in Seattle."
    raw = "Remember I enjoy hiking in Seattle."
    source = _item("mem_required_processed", l2_content)
    source = source.model_copy(
        update={
            "user_asserted": True,
            "promotion": {
                "required": True,
                "status": "pending",
                "processing_status": "processed",
                "processor_id": REQUIRED_PROCESSOR_ID,
                "processor_version": REQUIRED_PROCESSOR_VERSION,
                "submission": {
                    "submission_id": source.memory_id,
                    "content_hash": hashlib.sha256(raw.encode("utf-8")).hexdigest(),
                },
                "processing_receipt": {
                    "receipt_version": REQUIRED_PROCESSING_RECEIPT_VERSION,
                    "processor_id": REQUIRED_PROCESSOR_ID,
                    "processor_version": REQUIRED_PROCESSOR_VERSION,
                    "decision": "durable_required",
                    "processed_at": NOW.isoformat(),
                    "input_hash": hashlib.sha256(raw.encode("utf-8")).hexdigest(),
                    "output_hash": hashlib.sha256(l2_content.encode("utf-8")).hexdigest(),
                    "input_item_revision": source.item_revision - 1,
                    "output_item_revision": source.item_revision,
                    "source_submission_id": source.memory_id,
                    "rationale": "normalized during consolidation",
                },
                "source_attribution": {
                    "subject_entity_id": "user",
                    "subject_attribution": "user",
                },
            },
        }
    )
    db = _db_for_items(source)
    decision = _promote_decision(source).model_copy(update={"memory_text": "The user loves backpacking instead."})

    applied_ids = _apply(source, decision, db)

    stored = MemoryItem(**db.docs[f"users/{UID}/memory_items/{source.memory_id}"])
    assert applied_ids == [source.memory_id]
    assert stored.tier == MemoryTier.long_term
    assert stored.content == l2_content
    assert valid_required_processing_receipt(
        content=stored.content,
        item_revision=stored.item_revision,
        promotion=stored.promotion or {},
    )
