"""WS-O consolidation tests exercising the real durable apply path."""

from __future__ import annotations

import copy
import importlib
import os
import sys
import types
from datetime import datetime, timedelta, timezone
from typing import Optional
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)

from tests.unit.memory_import_isolation import (
    AutoMockModule,
    install_database_client_stub,
    install_firestore_transactional_stub,
    install_ws_i_heavy_import_stubs,
    restore_sys_modules,
    snapshot_sys_modules,
)

_saved_modules = snapshot_sys_modules(["database._client"])
install_database_client_stub()
install_firestore_transactional_stub()
_touched = install_ws_i_heavy_import_stubs()

review_queue_mod = AutoMockModule("database.review_queue")
review_queue_mod.create_review_conflict = MagicMock()
review_queue_mod.purge_stale_review_conflicts_for_memories = MagicMock()
review_queue_mod.should_escalate_conflict = MagicMock(return_value=True)
sys.modules["database.review_queue"] = review_queue_mod
_touched.append("database.review_queue")

jobs_mod = AutoMockModule("jobs.short_term_lifecycle_worker")
jobs_mod.fetch_short_term_memory_items_firestore = MagicMock(return_value=[])
sys.modules["jobs.short_term_lifecycle_worker"] = jobs_mod
_touched.append("jobs.short_term_lifecycle_worker")

for module_name in (
    "utils.memory.atom_keyword_index",
    "utils.memory.canonical_memory_adapter",
    "utils.memory.canonical_vector_sync",
):
    sys.modules[module_name] = AutoMockModule(module_name)
    _touched.append(module_name)

canonical_consolidation = importlib.import_module("utils.memory.canonical_consolidation")
ConsolidationAgentBatch = canonical_consolidation.ConsolidationAgentBatch
ConsolidationAgentDecision = canonical_consolidation.ConsolidationAgentDecision
apply_consolidation_decision = canonical_consolidation.apply_consolidation_decision
run_canonical_consolidation = canonical_consolidation.run_canonical_consolidation

from database.memory_apply_store import apply_long_term_patch_firestore
from models.memory_apply import ApplyStatus, MemoryControlState
from models.memory_evidence import ArtifactPreservationState, MemoryEvidence, SourceState
from models.product_memory import MemoryItemStatus, MemoryTier, ProcessingState, MemoryItem
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
        self.fail_after_sets: Optional[int] = None
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
    tier=MemoryTier.short_term,
    evidence_ids: Optional[list[str]] = None,
    corroboration_count: int = 0,
) -> MemoryItem:
    evidence = [_evidence(eid) for eid in (evidence_ids or [f"ev_{memory_id}"])]
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
        expires_at=NOW + timedelta(days=30),
        ledger_commit_id="commit-1",
        ledger_sequence=1,
        item_revision=2,
        source_commit_id="commit-1",
        source_commit_sequence=1,
        content_hash="hash",
        account_generation=1,
        corroboration_count=corroboration_count,
    )


def _stored(model) -> dict:
    return model.model_dump(mode="json")


def _db_for_apply(*, survivor: MemoryItem, extra_evidence: Optional[list[MemoryEvidence]] = None) -> _FakeDb:
    control = MemoryControlState(uid=UID, head_commit_id="head0", account_generation=1, source_generation=1)
    docs = {
        f"users/{UID}/memory_control/state": _stored(control),
        f"users/{UID}/memory_items/{survivor.memory_id}": _stored(survivor),
    }
    for ev in survivor.evidence:
        docs[f"users/{UID}/memory_evidence/{ev.evidence_id}"] = _stored(ev)
    for ev in extra_evidence or []:
        docs[f"users/{UID}/memory_evidence/{ev.evidence_id}"] = _stored(ev)
    return _FakeDb(docs)


def _stored_item(db: _FakeDb, memory_id: str) -> MemoryItem:
    return MemoryItem(**db.docs[f"users/{UID}/memory_items/{memory_id}"])


@pytest.mark.parametrize("agent_decision", ["merge", "add_evidence"])
def test_merge_and_add_evidence_update_survivor_in_place(agent_decision: str):
    survivor = _item("mem_survivor", "Enjoys hiking in Seattle")
    duplicate_ev = _evidence("ev_pending", source_id="conv-2")
    db = _db_for_apply(survivor=survivor, extra_evidence=[duplicate_ev])
    control = MemoryControlState(**db.docs[f"users/{UID}/memory_control/state"])
    pending = _item("mem_pending", "Enjoys hiking in Seattle", evidence_ids=["ev_pending"])

    decision = ConsolidationAgentDecision(
        decision=agent_decision,
        survivor_memory_id="mem_survivor",
        memory_text="Enjoys hiking in Seattle",
        evidence_ids=["ev_pending"],
        corroboration_increment=True,
        rationale="cross-source duplicate",
    )

    apply_consolidation_decision(
        UID,
        decision=decision,
        pending_by_id={survivor.memory_id: survivor, pending.memory_id: pending},
        control=control,
        run_id="run-merge",
        now=NOW,
        db_client=db,
    )

    updated = _stored_item(db, "mem_survivor")
    assert updated.memory_id == "mem_survivor"
    assert updated.version == survivor.version + 1
    assert updated.tier == survivor.tier
    assert updated.captured_at == survivor.captured_at
    assert updated.corroboration_count == 1
    evidence_ids = {ev.evidence_id for ev in updated.evidence}
    assert evidence_ids == {"ev_mem_survivor", "ev_pending"}


def test_skip_duplicate_with_corroboration_increments_survivor():
    survivor = _item("mem_existing", "Likes coffee", corroboration_count=2)
    db = _db_for_apply(survivor=survivor)
    control = MemoryControlState(**db.docs[f"users/{UID}/memory_control/state"])

    decision = ConsolidationAgentDecision(
        decision="skip_duplicate",
        survivor_memory_id="mem_existing",
        corroboration_increment=True,
        rationale="duplicate pending item",
    )

    apply_consolidation_decision(
        UID,
        decision=decision,
        pending_by_id={},
        control=control,
        run_id="run-skip",
        now=NOW,
        db_client=db,
    )

    updated = _stored_item(db, "mem_existing")
    assert updated.memory_id == "mem_existing"
    assert updated.version == survivor.version + 1
    assert updated.corroboration_count == 3
    assert updated.last_corroborated_at is not None


def test_consolidation_apply_is_idempotent_on_operation_retry():
    survivor = _item("mem_survivor", "Enjoys hiking")
    db = _db_for_apply(survivor=survivor)
    control = MemoryControlState(**db.docs[f"users/{UID}/memory_control/state"])
    decision = ConsolidationAgentDecision(
        decision="merge",
        survivor_memory_id="mem_survivor",
        memory_text="Enjoys hiking",
        evidence_ids=["ev_mem_survivor"],
        corroboration_increment=True,
    )

    apply_consolidation_decision(
        UID,
        decision=decision,
        pending_by_id={survivor.memory_id: survivor},
        control=control,
        run_id="run-idem",
        now=NOW,
        db_client=db,
    )
    after_first = copy.deepcopy(db.docs[f"users/{UID}/memory_items/mem_survivor"])

    op_paths = [path for path in db.docs if "/memory_operations/" in path]
    assert len(op_paths) == 1
    operation_id = op_paths[0].split("/")[-1]
    operation_doc = db.docs[op_paths[0]]
    patch_payload = {
        "patch_id": operation_doc.get("patch_id", "patch_retry"),
        "packet_id": "consolidation_run-idem",
        "run_id": "run-idem",
        "observed_head_commit_id": control.head_commit_id,
        "idempotency_key": "retry-key",
        "decision": "update",
        "result_status": "active",
        "target_memory_id": "mem_survivor",
        "memory_text": "Enjoys hiking",
        "evidence_ids": ["ev_mem_survivor"],
        "corroboration_count": 1,
        "last_corroborated_at": NOW.isoformat(),
    }

    retry = apply_long_term_patch_firestore(
        uid=UID,
        operation_id=operation_id,
        patch_payload=patch_payload,
        db_client=db,
    )
    assert retry.status == ApplyStatus.idempotent_skip
    after_retry = db.docs[f"users/{UID}/memory_items/mem_survivor"]
    assert after_retry["version"] == after_first["version"]
    assert after_retry["corroboration_count"] == after_first["corroboration_count"]


def test_watermark_not_advanced_on_parse_failure():
    uid = UID
    control = MemoryControlState(
        uid=uid,
        head_commit_id="head0",
        account_generation=1,
        source_generation=1,
        last_consolidation_run_at=NOW - timedelta(days=2),
    )
    db = _FakeDb({f"users/{uid}/memory_control/state": _stored(control)})
    pending = [_item(f"mem_{idx}", f"fact {idx}") for idx in range(2)]

    with (
        patch("utils.memory.canonical_consolidation.resolve_memory_system", return_value=MemorySystem.CANONICAL),
        patch("utils.memory.canonical_consolidation.list_pending_consolidation_items", return_value=pending),
        patch("utils.memory.canonical_consolidation.gather_consolidation_candidates") as mock_gather,
        patch("utils.memory.canonical_consolidation.invoke_consolidation_agent") as mock_agent,
    ):
        mock_gather.return_value = MagicMock(uid=uid, pending_items=pending, candidates_by_anchor={})
        mock_agent.return_value = ConsolidationAgentBatch(decisions=[], reasoning="parse_failed:JSONDecodeError")
        report = run_canonical_consolidation(uid, db_client=db, run_id="run-parse-fail", now=NOW, batch_threshold=2)

    assert report.decisions_applied == 0
    assert report.last_consolidation_run_at == control.last_consolidation_run_at


def test_watermark_not_advanced_when_zero_decisions_applied():
    uid = UID
    control = MemoryControlState(
        uid=uid,
        head_commit_id="head0",
        account_generation=1,
        source_generation=1,
        last_consolidation_run_at=NOW - timedelta(days=2),
    )
    db = _FakeDb({f"users/{uid}/memory_control/state": _stored(control)})
    pending = [_item(f"mem_{idx}", f"fact {idx}") for idx in range(2)]

    with (
        patch("utils.memory.canonical_consolidation.resolve_memory_system", return_value=MemorySystem.CANONICAL),
        patch("utils.memory.canonical_consolidation.list_pending_consolidation_items", return_value=pending),
        patch("utils.memory.canonical_consolidation.gather_consolidation_candidates") as mock_gather,
        patch("utils.memory.canonical_consolidation.invoke_consolidation_agent") as mock_agent,
    ):
        mock_gather.return_value = MagicMock(uid=uid, pending_items=pending[:10], candidates_by_anchor={})
        mock_agent.return_value = ConsolidationAgentBatch(decisions=[], reasoning="no_changes")
        report = run_canonical_consolidation(uid, db_client=db, run_id="run-zero", now=NOW, batch_threshold=2)

    assert report.decisions_applied == 0
    assert report.last_consolidation_run_at == control.last_consolidation_run_at


def test_batch_cap_limits_pending_items_sent_to_llm():
    uid = UID
    control = MemoryControlState(uid=uid, head_commit_id="head0", account_generation=1, source_generation=1)
    db = _FakeDb({f"users/{uid}/memory_control/state": _stored(control)})
    pending = [_item(f"mem_{idx}", f"fact {idx}") for idx in range(15)]

    with (
        patch("utils.memory.canonical_consolidation.resolve_memory_system", return_value=MemorySystem.CANONICAL),
        patch("utils.memory.canonical_consolidation.list_pending_consolidation_items", return_value=pending),
        patch("utils.memory.canonical_consolidation.consolidation_batch_cap", return_value=10),
        patch("utils.memory.canonical_consolidation.gather_consolidation_candidates") as mock_gather,
        patch("utils.memory.canonical_consolidation.invoke_consolidation_agent") as mock_agent,
    ):
        mock_gather.return_value = MagicMock(uid=uid, pending_items=pending[:10], candidates_by_anchor={})
        mock_agent.return_value = ConsolidationAgentBatch(decisions=[])
        run_canonical_consolidation(uid, db_client=db, run_id="run-cap", now=NOW, batch_threshold=10)

    assert len(mock_gather.call_args[0][1]) == 10
