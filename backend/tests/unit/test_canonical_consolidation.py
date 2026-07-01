"""WS-O canonical batched consolidation tests."""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)

from models.memory_apply import ApplyStatus, MemoryControlState
from models.memory_evidence import ArtifactPreservationState, MemoryEvidence, SourceState
from models.product_memory import MemoryItemStatus, MemoryTier, ProcessingState, MemoryItem
from utils.memory.canonical_consolidation import (
    ConsolidationAgentBatch,
    ConsolidationAgentDecision,
    ConsolidationContext,
    consolidation_trigger_reason,
    format_consolidation_llm_context,
    gather_consolidation_candidates,
    run_canonical_consolidation,
)
from utils.memory.memory_system import MemorySystem

NOW = datetime(2026, 6, 20, 12, 0, tzinfo=timezone.utc)


def _item(memory_id: str, content: str, *, tier=MemoryTier.short_term) -> MemoryItem:
    return MemoryItem(
        memory_id=memory_id,
        uid="uid-canonical",
        version=1,
        tier=tier,
        status=MemoryItemStatus.active,
        processing_state=ProcessingState.processed,
        content=content,
        evidence=[
            MemoryEvidence(
                evidence_id=f"ev_{memory_id}",
                source_id="conv-1",
                source_type="conversation",
                source_version="v1",
                artifact_preservation=ArtifactPreservationState.preserved,
            )
        ],
        source_state=SourceState.active,
        sensitivity_labels=[],
        visibility="private",
        user_asserted=False,
        captured_at=NOW - timedelta(hours=1),
        updated_at=NOW,
        expires_at=NOW + timedelta(days=30),
        ledger_commit_id="commit-1",
        ledger_sequence=1,
        item_revision=1,
        source_commit_id="commit-1",
        content_hash="hash",
        account_generation=1,
    )


class _Snapshot:
    def __init__(self, data=None, *, exists=True):
        self._data = data
        self.exists = exists

    def to_dict(self):
        return self._data


class _DocRef:
    def __init__(self, db, path):
        self._db = db
        self.path = path

    def get(self, transaction=None):
        if self.path not in self._db.docs:
            return _Snapshot(None, exists=False)
        return _Snapshot(self._db.docs[self.path], exists=True)

    def set(self, data, merge=False):
        if merge and self.path in self._db.docs:
            merged = dict(self._db.docs[self.path])
            merged.update(data)
            self._db.docs[self.path] = merged
        else:
            self._db.docs[self.path] = data


class _CollectionRef:
    def __init__(self, db, path, filters=None, limit_count=None):
        self._db = db
        self.path = path
        self._filters = list(filters or [])
        self._limit_count = limit_count

    def where(self, field_path, op_string, value):
        return _CollectionRef(self._db, self.path, [*self._filters, (field_path, op_string, value)], self._limit_count)

    def limit(self, limit_count):
        return _CollectionRef(self._db, self.path, self._filters, limit_count)

    def stream(self):
        prefix = self.path + "/"
        for path, data in sorted(self._db.docs.items()):
            if not path.startswith(prefix):
                continue
            doc_id = path[len(prefix) :]
            if doc_id.count("/") > 0:
                continue
            matched = True
            for field, op, value in self._filters:
                if op == "==" and data.get(field) != value:
                    matched = False
                    break
            if matched:
                yield _Snapshot(data, exists=True)

    def document(self, doc_id):
        return _DocRef(self._db, f"{self.path}/{doc_id}")


class _FakeDb:
    def __init__(self, docs=None):
        self.docs = dict(docs or {})

    def document(self, path):
        return _DocRef(self, path)

    def collection(self, path):
        return _CollectionRef(self, path)


def test_consolidation_trigger_batch_and_daily():
    assert consolidation_trigger_reason(pending_count=10, last_consolidation_run_at=None, now=NOW) == "batch_threshold"
    assert (
        consolidation_trigger_reason(
            pending_count=2,
            last_consolidation_run_at=NOW - timedelta(hours=25),
            now=NOW,
        )
        == "daily_elapsed"
    )
    assert (
        consolidation_trigger_reason(
            pending_count=1,
            last_consolidation_run_at=NOW - timedelta(hours=25),
            now=NOW,
        )
        is None
    )


def test_gather_excludes_superseded_candidates():
    uid = "uid-canonical"
    active = _item("mem_a", "Lives in Seattle")
    superseded = _item("mem_old", "Lives in NYC")
    superseded.status = MemoryItemStatus.superseded
    db = _FakeDb(
        {
            f"users/{uid}/memory_items/mem_a": active.model_dump(mode="python"),
            f"users/{uid}/memory_items/mem_old": superseded.model_dump(mode="python"),
        }
    )

    hit = MagicMock()
    hit.memory_id = "mem_old"
    hit.score = 0.95
    query_result = MagicMock(hits=[hit], rejected_count=0)

    with patch("utils.memory.canonical_consolidation.query_memory_vector_candidates", return_value=query_result):
        context = gather_consolidation_candidates(uid, [active], db_client=db)

    assert context.candidates_by_anchor["mem_a"] == []


def test_format_llm_context_includes_batch():
    active = _item("mem_a", "Enjoys hiking")
    ctx = ConsolidationContext(uid="uid-canonical", pending_items=[active], candidates_by_anchor={"mem_a": []})
    payload = json.loads(format_consolidation_llm_context(ctx))
    assert payload["memories"][0]["memory_id"] == "mem_a"


def test_legacy_cohort_is_noop():
    uid = "uid-legacy"
    with patch("utils.memory.canonical_consolidation.resolve_memory_system", return_value=MemorySystem.LEGACY):
        report = run_canonical_consolidation(uid, run_id="test-run", now=NOW)
    assert report.skipped_reason == "not_canonical_cohort"


def test_supersede_golden_path_with_mock_agent():
    uid = "uid-canonical"
    old = _item("mem_old", "Loves ice cream")
    new = _item("mem_new", "Hates ice cream")
    control = MemoryControlState(uid=uid, head_commit_id="head0", account_generation=1, source_generation=1)
    db = _FakeDb(
        {
            f"users/{uid}/memory_state/apply_control": control.model_dump(mode="python"),
            f"users/{uid}/memory_items/mem_old": old.model_dump(mode="python"),
            f"users/{uid}/memory_items/mem_new": new.model_dump(mode="python"),
        }
    )

    agent_response = ConsolidationAgentBatch(
        decisions=[
            ConsolidationAgentDecision(
                decision="update",
                survivor_memory_id="mem_new",
                supersedes=["mem_old"],
                memory_text="Hates ice cream",
                evidence_ids=["ev_mem_new"],
                rationale="preference flipped",
            )
        ]
    )

    def fake_apply(**kwargs):
        result = MagicMock()
        result.status = ApplyStatus.committed
        result.memory_items = [new]
        result.reason = None
        return result

    with (
        patch("utils.memory.canonical_consolidation.resolve_memory_system", return_value=MemorySystem.CANONICAL),
        patch("utils.memory.canonical_consolidation.list_pending_consolidation_items", return_value=[old, new]),
        patch("utils.memory.canonical_consolidation.gather_consolidation_candidates") as mock_gather,
        patch("utils.memory.canonical_consolidation.apply_long_term_patch_firestore", side_effect=fake_apply),
        patch("utils.memory.canonical_consolidation.delete_canonical_memory_vector"),
        patch("utils.memory.canonical_consolidation.invalidate_kg_for_memory_retraction"),
        patch("utils.memory.canonical_consolidation.delete_atom_keyword_doc"),
        patch("utils.memory.canonical_consolidation.purge_stale_review_conflicts_for_memories"),
    ):
        mock_gather.return_value = ConsolidationContext(uid=uid, pending_items=[old, new], candidates_by_anchor={})
        report = run_canonical_consolidation(
            uid,
            db_client=db,
            run_id="run-1",
            now=NOW,
            llm_invoke=lambda _p: agent_response.model_dump_json(),
            batch_threshold=2,
        )

    assert report.trigger_reason == "batch_threshold"
    assert report.decisions_applied == 1
    assert "mem_old" in report.superseded_memory_ids


def test_ambiguous_contradiction_escalates_to_review_queue():
    uid = "uid-canonical"
    survivor = _item("mem_new", "Maybe lives in LA")
    existing = _item("mem_old", "Lives in NYC")
    control = MemoryControlState(uid=uid, head_commit_id="head0", account_generation=1, source_generation=1)
    db = _FakeDb({f"users/{uid}/memory_state/apply_control": control.model_dump(mode="python")})

    agent_response = ConsolidationAgentBatch(
        decisions=[
            ConsolidationAgentDecision(
                decision="review",
                survivor_memory_id="mem_new",
                conflict_with=["mem_old"],
                review_required=True,
                rationale="ambiguous relocation",
            )
        ]
    )

    with (
        patch("utils.memory.canonical_consolidation.resolve_memory_system", return_value=MemorySystem.CANONICAL),
        patch(
            "utils.memory.canonical_consolidation.list_pending_consolidation_items", return_value=[survivor, existing]
        ),
        patch("utils.memory.canonical_consolidation.gather_consolidation_candidates") as mock_gather,
        patch("utils.memory.canonical_consolidation.create_review_conflict") as mock_review,
    ):
        mock_gather.return_value = ConsolidationContext(
            uid=uid, pending_items=[survivor, existing], candidates_by_anchor={}
        )
        report = run_canonical_consolidation(
            uid,
            db_client=db,
            run_id="run-review",
            now=NOW,
            llm_invoke=lambda _p: agent_response.model_dump_json(),
            batch_threshold=2,
        )

    assert report.review_escalations == 1
    mock_review.assert_called_once()
