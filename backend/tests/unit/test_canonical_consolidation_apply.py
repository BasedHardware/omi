"""WS-O consolidation tests exercising the real durable apply path."""

from __future__ import annotations

import copy
import importlib
import os
import sys
from datetime import datetime, timedelta, timezone
from typing import Optional
from unittest.mock import MagicMock, patch

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
ConsolidationAgentBatch = None
ConsolidationAgentDecision = None
apply_consolidation_decision = None
list_pending_consolidation_items = None
run_canonical_consolidation = None
jobs_mod = None


@pytest.fixture(scope="module", autouse=True)
def _consolidation_apply_import_isolation():
    """Install heavy-import stubs for this module only; restore after to avoid polluting combined runs."""
    saved = snapshot_sys_modules(CONSOLIDATION_APPLY_STUB_MODULE_NAMES)
    touched = install_consolidation_apply_stubs()
    saved.update(snapshot_sys_modules(touched))
    ensure_utils_memory_packages_importable()

    for stale_module in ("database.memory_apply_store", "utils.memory.canonical_consolidation"):
        sys.modules.pop(stale_module, None)

    cc = importlib.import_module("utils.memory.canonical_consolidation")
    g = globals()
    g["canonical_consolidation"] = cc
    g["ConsolidationAgentBatch"] = cc.ConsolidationAgentBatch
    g["ConsolidationAgentDecision"] = cc.ConsolidationAgentDecision
    g["apply_consolidation_decision"] = cc.apply_consolidation_decision
    g["list_pending_consolidation_items"] = cc.list_pending_consolidation_items
    g["run_canonical_consolidation"] = cc.run_canonical_consolidation
    g["jobs_mod"] = importlib.import_module("jobs.short_term_lifecycle_worker")
    g["apply_long_term_patch_firestore"] = importlib.import_module(
        "database.memory_apply_store"
    ).apply_long_term_patch_firestore

    yield

    restore_sys_modules(saved)


apply_long_term_patch_firestore = None
from models.memory_apply import ApplyStatus, MemoryControlState
from models.memory_evidence import ArtifactPreservationState, MemoryEvidence, SourceState
from models.product_memory import MemoryAccessPolicy, MemoryItemStatus, MemoryTier, ProcessingState, MemoryItem
from utils.memory.canonical_visibility_filter import filter_canonical_default_visible_items
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
        self._read_only = False
        self._max_attempts = 5

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


def _db_for_apply(
    *,
    survivor: MemoryItem,
    extra_items: Optional[list[MemoryItem]] = None,
    extra_evidence: Optional[list[MemoryEvidence]] = None,
) -> _FakeDb:
    control = MemoryControlState(uid=UID, head_commit_id="head0", account_generation=1, source_generation=1)
    docs = {
        f"users/{UID}/memory_state/apply_control": _stored(control),
        f"users/{UID}/memory_items/{survivor.memory_id}": _stored(survivor),
    }
    for item in extra_items or []:
        docs[f"users/{UID}/memory_items/{item.memory_id}"] = _stored(item)
        for ev in item.evidence:
            docs[f"users/{UID}/memory_evidence/{ev.evidence_id}"] = _stored(ev)
    for ev in survivor.evidence:
        docs[f"users/{UID}/memory_evidence/{ev.evidence_id}"] = _stored(ev)
    for ev in extra_evidence or []:
        docs[f"users/{UID}/memory_evidence/{ev.evidence_id}"] = _stored(ev)
    return _FakeDb(docs)


def _stored_item(db: _FakeDb, memory_id: str) -> MemoryItem:
    return MemoryItem(**db.docs[f"users/{UID}/memory_items/{memory_id}"])


@pytest.fixture(autouse=True)
def _canonical_cohort_for_apply(monkeypatch):
    monkeypatch.setattr(
        "utils.memory.canonical_consolidation.resolve_memory_system",
        lambda uid, db_client=None: MemorySystem.CANONICAL,
    )
    monkeypatch.setattr("utils.memory.canonical_consolidation.delete_atom_keyword_doc", MagicMock())
    monkeypatch.setattr("utils.memory.canonical_consolidation.delete_canonical_memory_vector", MagicMock())
    monkeypatch.setattr("utils.memory.canonical_consolidation.invalidate_kg_for_memory_retraction", MagicMock())
    monkeypatch.setattr("utils.memory.canonical_consolidation.purge_stale_review_conflicts_for_memories", MagicMock())


@pytest.mark.parametrize("agent_decision", ["merge", "add_evidence"])
def test_merge_and_add_evidence_update_survivor_in_place(agent_decision: str):
    survivor = _item("mem_survivor", "Enjoys hiking in Seattle")
    duplicate_ev = _evidence("ev_pending", source_id="conv-2")
    db = _db_for_apply(survivor=survivor, extra_evidence=[duplicate_ev])
    control = MemoryControlState(**db.docs[f"users/{UID}/memory_state/apply_control"])
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
    control = MemoryControlState(**db.docs[f"users/{UID}/memory_state/apply_control"])

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
    control = MemoryControlState(**db.docs[f"users/{UID}/memory_state/apply_control"])
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


def test_update_with_supersede_real_apply_excludes_superseded_from_reads():
    old = _item("mem_old", "Loves ice cream")
    new = _item("mem_new", "Hates ice cream")
    db = _db_for_apply(survivor=new, extra_items=[old])
    control = MemoryControlState(**db.docs[f"users/{UID}/memory_state/apply_control"])

    apply_consolidation_decision(
        UID,
        decision=ConsolidationAgentDecision(
            decision="update",
            survivor_memory_id="mem_new",
            supersedes=["mem_old"],
            memory_text="Hates ice cream",
            evidence_ids=["ev_mem_new"],
            rationale="preference flipped",
        ),
        pending_by_id={new.memory_id: new, old.memory_id: old},
        control=control,
        run_id="run-supersede-real",
        now=NOW,
        db_client=db,
    )

    old_stored = _stored_item(db, "mem_old")
    new_stored = _stored_item(db, "mem_new")
    assert old_stored.status == MemoryItemStatus.superseded
    assert old_stored.superseded_by == "mem_new"
    assert new_stored.content == "Hates ice cream"
    assert new_stored.version == new.version + 1

    policy = MemoryAccessPolicy.for_omi_chat(archive_capability=False)
    visible = filter_canonical_default_visible_items([old_stored, new_stored], policy=policy, now=NOW)
    assert [item.memory_id for item in visible] == ["mem_new"]


def test_partial_supersede_after_survivor_blocks_watermark():
    uid = UID
    survivor = _item("mem_new", "Hates ice cream")
    old = _item("mem_old", "Loves ice cream")
    control = MemoryControlState(
        uid=uid,
        head_commit_id="head0",
        account_generation=1,
        source_generation=1,
        last_consolidation_run_at=NOW - timedelta(days=2),
    )
    db = _db_for_apply(survivor=survivor, extra_items=[old])
    db.docs[f"users/{uid}/memory_state/apply_control"] = _stored(control)
    pending = [old, survivor]

    agent_response = ConsolidationAgentBatch(
        decisions=[
            ConsolidationAgentDecision(
                decision="update",
                survivor_memory_id="mem_new",
                supersedes=["mem_old"],
                memory_text="Hates ice cream",
                evidence_ids=["ev_mem_new"],
            )
        ]
    )

    with (
        patch("utils.memory.canonical_consolidation.resolve_memory_system", return_value=MemorySystem.CANONICAL),
        patch("utils.memory.canonical_consolidation.list_pending_consolidation_items", return_value=pending),
        patch("utils.memory.canonical_consolidation.gather_consolidation_candidates") as mock_gather,
        patch("utils.memory.canonical_consolidation.invoke_consolidation_agent", return_value=agent_response),
        patch(
            "utils.memory.canonical_consolidation._apply_superseded_item",
            side_effect=canonical_consolidation.ConsolidationApplySkipped("target memory is not active"),
        ),
    ):
        mock_gather.return_value = MagicMock(uid=uid, pending_items=pending, candidates_by_anchor={})
        report = run_canonical_consolidation(uid, db_client=db, run_id="run-partial", now=NOW, batch_threshold=2)

    assert report.decisions_partial == 1
    assert report.watermark_blocked is True
    assert report.last_consolidation_run_at == control.last_consolidation_run_at
    updated_survivor = _stored_item(db, "mem_new")
    assert updated_survivor.version == survivor.version + 1
    assert _stored_item(db, "mem_old").status == MemoryItemStatus.active


def test_watermark_not_advanced_on_parse_failure():
    uid = UID
    control = MemoryControlState(
        uid=uid,
        head_commit_id="head0",
        account_generation=1,
        source_generation=1,
        last_consolidation_run_at=NOW - timedelta(days=2),
    )
    db = _FakeDb({f"users/{uid}/memory_state/apply_control": _stored(control)})
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


def test_watermark_advanced_on_clean_empty_run():
    uid = UID
    control = MemoryControlState(
        uid=uid,
        head_commit_id="head0",
        account_generation=1,
        source_generation=1,
        last_consolidation_run_at=NOW - timedelta(days=2),
    )
    db = _FakeDb({f"users/{uid}/memory_state/apply_control": _stored(control)})
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
    assert report.last_consolidation_run_at == NOW
    stored_control = MemoryControlState(**db.docs[f"users/{uid}/memory_state/apply_control"])
    assert stored_control.last_consolidation_run_at == NOW


def test_consolidation_watermark_persist_preserves_apply_head_fields():
    uid = UID
    control = MemoryControlState(
        uid=uid,
        head_commit_id="head0",
        commit_sequence=0,
        account_generation=1,
        source_generation=1,
        last_consolidation_run_at=NOW - timedelta(days=2),
    )
    db = _FakeDb({f"users/{uid}/memory_state/apply_control": _stored(control)})
    pending = [_item(f"mem_{idx}", f"fact {idx}") for idx in range(2)]

    original_set = _FakeDocumentRef.set

    def concurrent_apply_before_watermark(self, data, merge=False):
        if merge:
            current = dict(self._db.docs[self.path])
            current.update({"head_commit_id": "head-concurrent", "commit_sequence": 42})
            self._db.docs[self.path] = current
        return original_set(self, data, merge=merge)

    with (
        patch("utils.memory.canonical_consolidation.resolve_memory_system", return_value=MemorySystem.CANONICAL),
        patch("utils.memory.canonical_consolidation.list_pending_consolidation_items", return_value=pending),
        patch("utils.memory.canonical_consolidation.gather_consolidation_candidates") as mock_gather,
        patch("utils.memory.canonical_consolidation.invoke_consolidation_agent") as mock_agent,
        patch.object(_FakeDocumentRef, "set", concurrent_apply_before_watermark),
    ):
        mock_gather.return_value = MagicMock(uid=uid, pending_items=pending[:10], candidates_by_anchor={})
        mock_agent.return_value = ConsolidationAgentBatch(decisions=[], reasoning="no_changes")
        report = run_canonical_consolidation(uid, db_client=db, run_id="run-zero", now=NOW, batch_threshold=2)

    assert report.last_consolidation_run_at == NOW
    stored_control = MemoryControlState(**db.docs[f"users/{uid}/memory_state/apply_control"])
    assert stored_control.head_commit_id == "head-concurrent"
    assert stored_control.commit_sequence == 42
    assert stored_control.last_consolidation_run_at == NOW


def test_batch_cap_limits_pending_items_per_llm_call_and_loops_all_pending():
    uid = UID
    control = MemoryControlState(uid=uid, head_commit_id="head0", account_generation=1, source_generation=1)
    db = _FakeDb({f"users/{uid}/memory_state/apply_control": _stored(control)})
    pending = [_item(f"mem_{idx}", f"fact {idx}") for idx in range(15)]

    with (
        patch("utils.memory.canonical_consolidation.resolve_memory_system", return_value=MemorySystem.CANONICAL),
        patch("utils.memory.canonical_consolidation.list_pending_consolidation_items", return_value=pending),
        patch("utils.memory.canonical_consolidation.consolidation_batch_cap", return_value=10),
        patch("utils.memory.canonical_consolidation.gather_consolidation_candidates") as mock_gather,
        patch("utils.memory.canonical_consolidation.invoke_consolidation_agent") as mock_agent,
    ):
        mock_gather.side_effect = lambda _uid, batch, **kwargs: MagicMock(
            uid=uid, pending_items=batch, candidates_by_anchor={}
        )
        mock_agent.return_value = ConsolidationAgentBatch(decisions=[], reasoning="no_changes")
        report = run_canonical_consolidation(uid, db_client=db, run_id="run-cap", now=NOW, batch_threshold=10)

    assert mock_gather.call_count == 2
    assert all(len(call.args[1]) <= 10 for call in mock_gather.call_args_list)
    assert len(report.batched_memory_ids) == 15


def test_missing_survivor_skips_decision_without_corruption():
    survivor = _item("mem_survivor", "Enjoys hiking")
    db = _db_for_apply(survivor=survivor)
    control = MemoryControlState(**db.docs[f"users/{UID}/memory_state/apply_control"])
    initial_item = copy.deepcopy(db.docs[f"users/{UID}/memory_items/mem_survivor"])

    decision = ConsolidationAgentDecision(
        decision="merge",
        survivor_memory_id="mem_hallucinated",
        memory_text="Enjoys hiking",
        evidence_ids=["ev_mem_survivor"],
        corroboration_increment=True,
    )

    with pytest.raises(canonical_consolidation.ConsolidationApplySkipped):
        apply_consolidation_decision(
            UID,
            decision=decision,
            pending_by_id={},
            control=control,
            run_id="run-missing-survivor",
            now=NOW,
            db_client=db,
        )

    assert db.docs[f"users/{UID}/memory_items/mem_survivor"] == initial_item
    assert "mem_hallucinated" not in db.docs


def test_superseded_survivor_skips_decision():
    survivor = _item("mem_survivor", "Old fact")
    survivor.status = MemoryItemStatus.superseded
    db = _db_for_apply(survivor=survivor)
    control = MemoryControlState(**db.docs[f"users/{UID}/memory_state/apply_control"])
    initial_item = copy.deepcopy(db.docs[f"users/{UID}/memory_items/mem_survivor"])

    decision = ConsolidationAgentDecision(
        decision="update",
        survivor_memory_id="mem_survivor",
        memory_text="Updated fact",
        evidence_ids=["ev_mem_survivor"],
    )

    with pytest.raises(canonical_consolidation.ConsolidationApplySkipped):
        apply_consolidation_decision(
            UID,
            decision=decision,
            pending_by_id={},
            control=control,
            run_id="run-superseded-survivor",
            now=NOW,
            db_client=db,
        )

    assert db.docs[f"users/{UID}/memory_items/mem_survivor"] == initial_item


def test_merged_survivor_stays_short_term_and_reappears_in_pending():
    survivor = _item("mem_survivor", "Enjoys hiking in Seattle", tier=MemoryTier.short_term)
    duplicate_ev = _evidence("ev_pending", source_id="conv-2")
    db = _db_for_apply(survivor=survivor, extra_evidence=[duplicate_ev])
    control = MemoryControlState(**db.docs[f"users/{UID}/memory_state/apply_control"])
    pending = _item("mem_pending", "Enjoys hiking in Seattle", evidence_ids=["ev_pending"])

    apply_consolidation_decision(
        UID,
        decision=ConsolidationAgentDecision(
            decision="merge",
            survivor_memory_id="mem_survivor",
            memory_text="Enjoys hiking in Seattle",
            evidence_ids=["ev_pending"],
            corroboration_increment=True,
        ),
        pending_by_id={survivor.memory_id: survivor, pending.memory_id: pending},
        control=control,
        run_id="run-merge-tier",
        now=NOW,
        db_client=db,
    )

    updated = _stored_item(db, "mem_survivor")
    assert updated.tier == MemoryTier.short_term

    jobs_mod.fetch_short_term_memory_items_firestore.return_value = [updated]
    pending_items = list_pending_consolidation_items(UID, db_client=db, now=NOW)
    assert [item.memory_id for item in pending_items] == ["mem_survivor"]


def test_batch_skips_hallucinated_evidence_and_applies_valid_decision():
    uid = UID
    survivor = _item("mem_valid", "Likes coffee")
    control = MemoryControlState(
        uid=uid,
        head_commit_id="head0",
        account_generation=1,
        source_generation=1,
        last_consolidation_run_at=NOW - timedelta(days=2),
    )
    db = _FakeDb(
        {
            f"users/{uid}/memory_state/apply_control": _stored(control),
            f"users/{uid}/memory_items/mem_valid": _stored(survivor),
            f"users/{uid}/memory_evidence/ev_mem_valid": _stored(survivor.evidence[0]),
        }
    )
    pending = [survivor, _item("mem_pending", "Duplicate coffee", evidence_ids=["ev_pending"])]

    agent_response = ConsolidationAgentBatch(
        decisions=[
            ConsolidationAgentDecision(
                decision="merge",
                survivor_memory_id="mem_valid",
                memory_text="Likes coffee",
                evidence_ids=["ev_hallucinated"],
                corroboration_increment=True,
            ),
            ConsolidationAgentDecision(
                decision="skip_duplicate",
                survivor_memory_id="mem_valid",
                corroboration_increment=True,
            ),
        ]
    )

    with (
        patch("utils.memory.canonical_consolidation.resolve_memory_system", return_value=MemorySystem.CANONICAL),
        patch("utils.memory.canonical_consolidation.list_pending_consolidation_items", return_value=pending),
        patch("utils.memory.canonical_consolidation.gather_consolidation_candidates") as mock_gather,
        patch("utils.memory.canonical_consolidation.invoke_consolidation_agent", return_value=agent_response),
    ):
        mock_gather.return_value = MagicMock(uid=uid, pending_items=pending, candidates_by_anchor={})
        report = run_canonical_consolidation(
            uid,
            db_client=db,
            run_id="run-mixed-batch",
            now=NOW,
            batch_threshold=2,
        )

    assert report.decisions_applied == 1
    assert report.decisions_skipped == 1
    assert report.last_consolidation_run_at == NOW
    updated = _stored_item(db, "mem_valid")
    assert updated.corroboration_count == 1


def test_partial_apply_halts_subsequent_batches():
    """After partial apply, no further LLM batches run in the same pass."""
    uid = UID
    control = MemoryControlState(uid=uid, head_commit_id="head0", account_generation=1, source_generation=1)
    db = _FakeDb({f"users/{uid}/memory_state/apply_control": _stored(control)})
    pending = [_item(f"mem_{idx}", f"fact {idx}") for idx in range(15)]

    first_batch_response = ConsolidationAgentBatch(
        decisions=[
            ConsolidationAgentDecision(
                decision="update",
                survivor_memory_id="mem_0",
                supersedes=["mem_1"],
                memory_text="fact 0 updated",
                evidence_ids=["ev_mem_0"],
            )
        ]
    )

    with (
        patch("utils.memory.canonical_consolidation.resolve_memory_system", return_value=MemorySystem.CANONICAL),
        patch("utils.memory.canonical_consolidation.list_pending_consolidation_items", return_value=pending),
        patch("utils.memory.canonical_consolidation.consolidation_batch_cap", return_value=10),
        patch("utils.memory.canonical_consolidation.gather_consolidation_candidates") as mock_gather,
        patch("utils.memory.canonical_consolidation.invoke_consolidation_agent") as mock_agent,
        patch(
            "utils.memory.canonical_consolidation.apply_consolidation_decision",
            side_effect=canonical_consolidation.ConsolidationPartialApply("supersede failed"),
        ),
    ):
        mock_gather.side_effect = lambda _uid, batch, **kwargs: MagicMock(
            uid=uid, pending_items=batch, candidates_by_anchor={}
        )
        mock_agent.return_value = first_batch_response
        report = run_canonical_consolidation(uid, db_client=db, run_id="run-partial-halt", now=NOW, batch_threshold=10)

    assert mock_agent.call_count == 1
    assert report.decisions_partial == 1
    assert report.watermark_blocked is True
    assert len(report.batched_memory_ids) == 0


def test_invoke_failure_blocks_watermark_and_defers_promotion_gate():
    uid = UID
    control = MemoryControlState(
        uid=uid,
        head_commit_id="head0",
        account_generation=1,
        source_generation=1,
        last_consolidation_run_at=NOW - timedelta(days=2),
    )
    db = _FakeDb({f"users/{uid}/memory_state/apply_control": _stored(control)})
    pending = [_item(f"mem_{idx}", f"fact {idx}") for idx in range(2)]

    def _raise_invoke(_prompt: str) -> str:
        raise RuntimeError("llm unavailable")

    with (
        patch("utils.memory.canonical_consolidation.resolve_memory_system", return_value=MemorySystem.CANONICAL),
        patch("utils.memory.canonical_consolidation.list_pending_consolidation_items", return_value=pending),
        patch("utils.memory.canonical_consolidation.gather_consolidation_candidates") as mock_gather,
    ):
        mock_gather.return_value = MagicMock(uid=uid, pending_items=pending, candidates_by_anchor={})
        report = run_canonical_consolidation(
            uid,
            db_client=db,
            run_id="run-invoke-fail",
            now=NOW,
            batch_threshold=2,
            llm_invoke=_raise_invoke,
        )

    assert report.watermark_blocked is True
    assert report.last_consolidation_run_at == control.last_consolidation_run_at

    from utils.memory.short_term_promotion import run_canonical_short_term_promotion

    with (
        patch("utils.memory.short_term_promotion.resolve_memory_system", return_value=MemorySystem.CANONICAL),
        patch("utils.memory.short_term_promotion.list_promotable_short_term_items", return_value=pending),
        patch("utils.memory.short_term_promotion.list_fast_track_promotable_items", return_value=[]),
        patch("utils.memory.short_term_promotion._read_control_state", return_value=control),
        patch("utils.memory.short_term_promotion.promote_short_term_item_via_apply") as mock_promote,
    ):
        promo = run_canonical_short_term_promotion(
            uid,
            db_client=db,
            run_id="run-invoke-fail-promo",
            now=NOW,
            consolidation_batched_ids=set(),
        )

    assert promo.skipped_reason == "consolidation_watermark_blocked"
    mock_promote.assert_not_called()


def _read_control_state_from_db(db: _FakeDb) -> MemoryControlState:
    return MemoryControlState(**db.docs[f"users/{UID}/memory_state/apply_control"])


def test_corroboration_increment_idempotent_across_runs():
    survivor = _item("mem_survivor", "Enjoys hiking", corroboration_count=0)
    db = _db_for_apply(survivor=survivor)
    control = MemoryControlState(**db.docs[f"users/{UID}/memory_state/apply_control"])
    decision = ConsolidationAgentDecision(
        decision="skip_duplicate",
        survivor_memory_id="mem_survivor",
        corroboration_increment=True,
        rationale="duplicate pending item",
    )

    apply_consolidation_decision(
        UID,
        decision=decision,
        pending_by_id={survivor.memory_id: survivor},
        control=control,
        run_id="run-first",
        now=NOW,
        db_client=db,
    )
    after_first = _stored_item(db, "mem_survivor")
    assert after_first.corroboration_count == 1

    apply_consolidation_decision(
        UID,
        decision=decision,
        pending_by_id={after_first.memory_id: after_first},
        control=_read_control_state_from_db(db),
        run_id="run-retry",
        now=NOW + timedelta(hours=1),
        db_client=db,
    )
    after_second = _stored_item(db, "mem_survivor")
    assert after_second.corroboration_count == 1
    assert after_second.version == after_first.version
