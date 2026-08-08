"""Behavioral tests for the authoritative L2 route/apply boundary."""

from __future__ import annotations

import importlib
import os
import sys
from datetime import datetime, timedelta, timezone
from typing import Optional

import pytest

from database import document_store
from tests.store_fakes import FakeDocumentStore

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
from models.memory_evidence import ArtifactPreservationState, MemoryEvidence, SourceState
from models.memory_operations import MemoryOperation, MemoryOperationStatus, MemoryOperationType
from models.product_memory import MemoryItemStatus, MemoryTier, ProcessingState, MemoryItem
from utils.memory.canonical_lineage import canonical_lineage_root
from utils.memory.memory_system import MemorySystem

NOW = datetime(2026, 6, 20, 12, 0, tzinfo=timezone.utc)
UID = "uid-canonical"


class _FakeDb:
    """Holds one test's seeded ``.docs`` dict and tracks the latest instance so the
    ``document_store`` port seam (patched in ``_canonical_runtime``) can resolve the current
    test's backing store lazily. Post-ADR-0028 the apply path takes no injected ``db_client``;
    persistence flows through the neutral store, and sharing this ``.docs`` dict keeps seeded
    data and assertions consistent with what the service writes."""

    _latest: Optional["_FakeDb"] = None

    def __init__(self, docs):
        self.docs = docs
        _FakeDb._latest = self


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
    # Point ``document_store`` (and the module's directly-imported ``get_document_store`` handle) at
    # a ``FakeDocumentStore`` sharing the current test's ``.docs`` dict: post-ADR-0028 the apply path
    # persists through the neutral store, not an injected db_client, so this seam keeps its
    # reads/writes consistent with the dict the assertions inspect.
    monkeypatch.setattr(
        document_store,
        "_store",
        lambda: FakeDocumentStore(backing=_FakeDb._latest.docs),
    )
    monkeypatch.setattr(
        "utils.memory.canonical_consolidation.get_document_store",
        lambda: FakeDocumentStore(backing=_FakeDb._latest.docs),
    )
    # The apply path settles long-term patches through ``apply_long_term_patch_firestore``, which
    # resolves its own ``_store`` seam; point it at the same shared backing dict.
    monkeypatch.setattr(
        "database.memory_apply_store._store",
        lambda: FakeDocumentStore(backing=_FakeDb._latest.docs),
    )
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
