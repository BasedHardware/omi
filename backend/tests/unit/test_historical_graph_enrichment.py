from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from models.memory_apply import ApplyStatus, MemoryControlState, memory_content_hash
from models.memory_promotion import PROMOTION_GRAPH_PLAN_V2_VERSION, canonical_graph_entity_id
from models.product_memory import MemoryItemStatus, MemoryTier, ProcessingState, MemoryItem
from utils.memory.graph_enrichment import GraphEnrichmentStatus
from utils.memory.historical_graph_enrichment import plan_historical_graph_enrichment
from scripts import enrich_historical_memory_graph as historical_runner
from scripts.enrich_historical_memory_graph import _is_replan_candidate
from scripts.enrich_historical_memory_graph import run_enrichment


class _Response:
    def __init__(self, payload: dict[str, object]):
        self.content = json.dumps(payload)


class _Planner:
    def __init__(self, payload: dict[str, object]):
        self.payload = payload

    def invoke(self, _messages: object) -> _Response:
        return _Response(self.payload)


class _FailingPlanner:
    def invoke(self, _messages: object) -> _Response:
        raise RuntimeError("transient gateway failure")


class _CursorStore:
    def __init__(self):
        self.cursor = historical_runner.HistoricalGraphEnrichmentCursor()
        self.advances: list[tuple[int, str | None]] = []

    def read(self, _uid: str, **_kwargs: object):
        return self.cursor

    def advance(self, _uid: str, *, expected_generation: int, resume_after: MemoryItem | None, **_kwargs: object):
        if expected_generation != self.cursor.generation:
            return False
        self.advances.append((expected_generation, resume_after.memory_id if resume_after is not None else None))
        self.cursor = historical_runner.HistoricalGraphEnrichmentCursor(
            generation=expected_generation + 1,
            resume_after_updated_at=resume_after.updated_at if resume_after is not None else None,
            resume_after_memory_id=resume_after.memory_id if resume_after is not None else None,
        )
        return True


class _CursorSnapshot:
    def __init__(self, payload: dict[str, object] | None):
        self.exists = payload is not None
        self._payload = payload

    def to_dict(self):
        return self._payload


class _CursorRef:
    def __init__(self, payload: dict[str, object] | None):
        self.payload = payload

    def get(self, *, transaction: object | None = None):
        return _CursorSnapshot(self.payload)


class _CursorTransaction:
    def set(self, ref: _CursorRef, payload: dict[str, object]):
        ref.payload = payload


class _CursorDb:
    def __init__(self, ref: _CursorRef):
        self.ref = ref

    def document(self, _path: str):
        return self.ref


def _item(**overrides: object) -> MemoryItem:
    now = datetime.now(timezone.utc)
    payload: dict[str, object] = {
        "memory_id": "mem_historical",
        "uid": "u1",
        "version": 1,
        "content": "The user prefers concise updates.",
        "tier": MemoryTier.long_term,
        "status": MemoryItemStatus.active,
        "processing_state": ProcessingState.processed,
        "source_state": "active",
        "evidence": [
            {
                "evidence_id": "ev1",
                "source_type": "conversation",
                "source_id": "conv1",
                "source_version": "v1",
                "artifact_preservation": "preserved",
                "source_state": "active",
            }
        ],
        "sensitivity_labels": [],
        "visibility": "private",
        "user_asserted": False,
        "captured_at": now,
        "updated_at": now,
        "ledger_commit_id": "head0",
        "ledger_sequence": 1,
        "item_revision": 1,
        "content_hash": "",
        "account_generation": 1,
    }
    payload.update(overrides)
    if "content_hash" not in overrides:
        payload["content_hash"] = memory_content_hash(
            content=str(payload["content"]),
            evidence_ids=sorted(item["evidence_id"] for item in payload["evidence"]),
        )
    return MemoryItem(**payload)


def test_historical_graph_planner_builds_a_fenced_plan_for_source_grounded_output():
    planned = plan_historical_graph_enrichment(
        item=_item(),
        control=MemoryControlState(uid="u1", head_commit_id="head0", account_generation=1, source_generation=2),
        llm=_Planner(
            {
                "eligible": True,
                "subject_label": "user",
                "subject_node_type": "person",
                "predicate": "prefers_update_style",
                "object_label": "concise updates",
                "object_node_type": "concept",
                "qualifiers": {"style": "concise"},
            }
        ),
    )

    assert planned.status == GraphEnrichmentStatus.ready
    assert planned.operation is not None
    assert planned.patch_payload["expected_content_hash"] == _item().content_hash
    assert planned.patch_payload["evidence_ids"] == ["ev1"]
    assert planned.patch_payload["subject_entity_id"] == "user"
    graph_plan = planned.patch_payload["promotion_audit"]["graph_plan"]
    assert graph_plan["schema_version"] == PROMOTION_GRAPH_PLAN_V2_VERSION
    assert graph_plan["object"] == {
        "entity_id": canonical_graph_entity_id("concise updates"),
        "label": "concise updates",
        "node_type": "concept",
    }
    assert graph_plan["qualifiers"] == {"style": "concise"}


@pytest.mark.parametrize(
    ("content", "subject_label", "object_label"),
    [
        ("I prefer concise updates.", "I", "concise updates"),
        ("I’m a concise communicator.", "I'm", "concise communicator"),
        ("I’ve chosen concise updates.", "I've", "concise updates"),
        ("I’d choose concise updates.", "I'd", "concise updates"),
        ("I’ll choose concise updates.", "I'll", "concise updates"),
        ("I prefer concise updates.", "user", "concise updates"),
    ],
)
def test_historical_graph_planner_normalizes_direct_first_person_subjects_to_user(
    content: str, subject_label: str, object_label: str
):
    planned = plan_historical_graph_enrichment(
        item=_item(content=content),
        control=MemoryControlState(uid="u1", head_commit_id="head0", account_generation=1, source_generation=2),
        llm=_Planner(
            {
                "eligible": True,
                "subject_label": subject_label,
                "subject_node_type": "person",
                "predicate": "prefers_update_style",
                "object_label": object_label,
                "object_node_type": "concept",
            }
        ),
    )

    assert planned.status == GraphEnrichmentStatus.ready
    assert planned.patch_payload["subject_entity_id"] == "user"
    graph_plan = planned.patch_payload["promotion_audit"]["graph_plan"]
    assert graph_plan["subject"] == {"entity_id": "user", "label": "user", "node_type": "person"}


@pytest.mark.parametrize(
    ("content", "subject_label", "object_label"),
    [
        ("The superuser prefers concise updates.", "user", "concise updates"),
        ("Iceland prefers concise updates.", "I", "concise updates"),
        ("The user prefers inconcisely.", "user", "concise"),
    ],
)
def test_historical_graph_planner_rejects_partial_evidence_tokens(content: str, subject_label: str, object_label: str):
    planned = plan_historical_graph_enrichment(
        item=_item(content=content),
        control=MemoryControlState(uid="u1", head_commit_id="head0", account_generation=1, source_generation=2),
        llm=_Planner(
            {
                "eligible": True,
                "subject_label": subject_label,
                "subject_node_type": "person",
                "predicate": "prefers_update_style",
                "object_label": object_label,
                "object_node_type": "concept",
            }
        ),
    )

    assert planned.status == GraphEnrichmentStatus.blocked
    assert planned.block_code == "not_source_grounded"


def test_historical_graph_planner_blocks_an_endpoint_label_not_supported_by_the_memory_text():
    planned = plan_historical_graph_enrichment(
        item=_item(),
        control=MemoryControlState(uid="u1", head_commit_id="head0", account_generation=1, source_generation=2),
        llm=_Planner(
            {
                "eligible": True,
                "subject_label": "user",
                "subject_node_type": "person",
                "predicate": "prefers_update_style",
                "object_label": "weekly updates",
                "object_node_type": "concept",
            }
        ),
    )

    assert planned.status == GraphEnrichmentStatus.blocked
    assert planned.block_code == "not_source_grounded"


def test_historical_graph_planner_blocks_when_no_source_grounded_fact_exists():
    planned = plan_historical_graph_enrichment(
        item=_item(),
        control=MemoryControlState(uid="u1", head_commit_id="head0", account_generation=1, source_generation=2),
        llm=_Planner({"eligible": False}),
    )

    assert planned.status == GraphEnrichmentStatus.blocked
    assert planned.block_code == "not_source_grounded"


def test_historical_graph_planner_blocks_a_stale_content_hash_before_calling_the_model():
    planned = plan_historical_graph_enrichment(
        item=_item(content_hash="stale"),
        control=MemoryControlState(uid="u1", head_commit_id="head0", account_generation=1, source_generation=2),
        llm=_Planner({"eligible": True}),
    )

    assert planned.status == GraphEnrichmentStatus.blocked
    assert planned.block_code == "content_hash_invalid"


def test_replan_candidates_exclude_current_planner_version():
    current = _item(
        graph_ready=True,
        promotion={
            "graph_enrichment": True,
            "graph_enrichment_planner_version": "canonical_historical_graph_enrichment.v3",
        },
    )
    legacy = _item(
        memory_id="mem_legacy",
        graph_ready=True,
        promotion={
            "graph_enrichment": True,
            "graph_enrichment_planner_version": "canonical_historical_graph_enrichment.v1",
        },
    )

    assert _is_replan_candidate(current) is False
    assert _is_replan_candidate(legacy) is True


def test_historical_runner_allows_a_bounded_scan_for_unenriched_candidates():
    """A recent graph-ready head must not hide older non-graph candidates."""
    with pytest.raises(AttributeError, match="document"):
        run_enrichment(
            uid="u1",
            firestore_project="test",
            limit=1,
            scan_limit=2,
            apply=False,
            confirm_uid=None,
            structured_only=False,
            db_client=object(),
            llm=object(),
        )


def test_historical_runner_skips_a_transient_planner_error_and_commits_a_later_candidate(
    monkeypatch: pytest.MonkeyPatch,
):
    control = MemoryControlState(uid="u1", head_commit_id="head0", account_generation=1, source_generation=2)
    failing = _item(memory_id="mem_failing")
    ready = _item(memory_id="mem_ready")
    cursor_store = _CursorStore()
    planner = _Planner(
        {
            "eligible": True,
            "subject_label": "user",
            "subject_node_type": "person",
            "predicate": "prefers_update_style",
            "object_label": "concise updates",
            "object_node_type": "concept",
        }
    )

    monkeypatch.setattr(historical_runner, "_control", lambda *_args, **_kwargs: control)
    monkeypatch.setattr(
        historical_runner,
        "_candidate_page",
        lambda *_args, **_kwargs: historical_runner.HistoricalGraphCandidatePage(
            items=[failing, ready], last_scanned=ready, exhausted=False
        ),
    )

    def plan(item: MemoryItem, **_kwargs: object):
        if item.memory_id == failing.memory_id:
            return plan_historical_graph_enrichment(item=item, control=control, llm=_FailingPlanner())
        return plan_historical_graph_enrichment(item=item, control=control, llm=planner)

    monkeypatch.setattr(historical_runner, "plan_historical_graph_enrichment", plan)
    monkeypatch.setattr(
        historical_runner,
        "apply_long_term_patch_firestore",
        lambda **_kwargs: SimpleNamespace(status=ApplyStatus.committed),
    )

    report = run_enrichment(
        uid="u1",
        firestore_project="test",
        limit=1,
        scan_limit=2,
        apply=True,
        confirm_uid="u1",
        structured_only=False,
        apply_limit=1,
        db_client=object(),
        llm=object(),
        cursor_store=cursor_store,
    )

    assert report["outcomes"] == {"committed": 1, "cursor_advanced": 1, "planner_error": 1}
    assert cursor_store.advances == [(0, "mem_ready")]


def test_historical_runner_rotates_cursor_past_a_bounded_scan_window(monkeypatch: pytest.MonkeyPatch):
    control = MemoryControlState(uid="u1", head_commit_id="head0", account_generation=1, source_generation=2)
    pages = {
        None: _item(memory_id="mem_head"),
        "mem_head": _item(memory_id="mem_middle"),
        "mem_middle": _item(memory_id="mem_tail"),
    }
    seen: list[str] = []
    cursor_store = _CursorStore()

    monkeypatch.setattr(historical_runner, "_control", lambda *_args, **_kwargs: control)

    def candidate_page(*_args: object, cursor: historical_runner.HistoricalGraphEnrichmentCursor, **_kwargs: object):
        item = pages[cursor.resume_after_memory_id]
        return historical_runner.HistoricalGraphCandidatePage(
            items=[item], last_scanned=item, exhausted=item.memory_id == "mem_tail"
        )

    monkeypatch.setattr(historical_runner, "_candidate_page", candidate_page)
    monkeypatch.setattr(
        historical_runner,
        "_plan_with_deadline",
        lambda *, item, **_kwargs: (
            seen.append(item.memory_id)
            or SimpleNamespace(
                status=GraphEnrichmentStatus.ready,
                operation=SimpleNamespace(operation_id=item.memory_id),
                patch_payload={},
            )
        ),
    )
    monkeypatch.setattr(
        historical_runner,
        "apply_long_term_patch_firestore",
        lambda **_kwargs: SimpleNamespace(status=ApplyStatus.committed),
    )

    for _ in range(3):
        run_enrichment(
            uid="u1",
            firestore_project="test",
            limit=1,
            scan_limit=1,
            apply=True,
            confirm_uid="u1",
            structured_only=False,
            db_client=object(),
            llm=object(),
            cursor_store=cursor_store,
        )

    assert seen == ["mem_head", "mem_middle", "mem_tail"]
    assert cursor_store.advances == [(0, "mem_head"), (1, "mem_middle"), (2, None)]


def test_historical_graph_cursor_cas_rejects_a_stale_writer():
    control = MemoryControlState(uid="u1", head_commit_id="head0", account_generation=1, source_generation=2)
    ref = _CursorRef({"generation": 2, "resume_after_memory_id": "newer"})
    transaction = _CursorTransaction()

    stale = historical_runner._advance_historical_graph_cursor_txn(
        transaction, ref, control, False, 1, _item(memory_id="stale"), datetime.now(timezone.utc)
    )
    current = historical_runner._advance_historical_graph_cursor_txn(
        transaction, ref, control, False, 2, _item(memory_id="current"), datetime.now(timezone.utc)
    )

    assert stale is False
    assert current is True
    assert ref.payload is not None
    assert ref.payload["generation"] == 3
    assert ref.payload["resume_after_memory_id"] == "current"


def test_historical_graph_cursor_resets_boundary_when_the_account_generation_changes():
    item = _item(memory_id="old_boundary")
    ref = _CursorRef(
        {
            "generation": 4,
            "account_generation": 1,
            "planner_version": historical_runner.HISTORICAL_GRAPH_PLANNER_VERSION,
            "replan_existing": False,
            "resume_after_updated_at": item.updated_at,
            "resume_after_memory_id": item.memory_id,
        }
    )

    cursor = historical_runner.FirestoreHistoricalGraphCursorStore(_CursorDb(ref)).read(
        "u1",
        control=MemoryControlState(uid="u1", head_commit_id="head0", account_generation=2, source_generation=2),
        replan_existing=False,
    )

    assert cursor == historical_runner.HistoricalGraphEnrichmentCursor(generation=4)


def test_historical_planner_deadline_interrupts_a_stuck_sync_call(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(historical_runner, "HISTORICAL_GRAPH_PLANNER_TIMEOUT_SECONDS", 0.01)
    monkeypatch.setattr(
        historical_runner,
        "plan_historical_graph_enrichment",
        lambda **_kwargs: time.sleep(1),
    )

    with pytest.raises(historical_runner.HistoricalGraphPlannerTimeout):
        historical_runner._plan_with_deadline(
            item=_item(),
            control=MemoryControlState(uid="u1", head_commit_id="head0", account_generation=1, source_generation=2),
            llm=object(),
        )
