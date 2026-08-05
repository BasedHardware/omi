from __future__ import annotations

import json
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from models.memory_apply import ApplyStatus, MemoryControlState, memory_content_hash
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
                "subject_entity_id": "user",
                "predicate": "prefers_update_style",
                "object_label": "concise updates",
                "arguments": {"style": "concise"},
            }
        ),
    )

    assert planned.status == GraphEnrichmentStatus.ready
    assert planned.operation is not None
    assert planned.patch_payload["expected_content_hash"] == _item().content_hash
    assert planned.patch_payload["evidence_ids"] == ["ev1"]
    assert planned.patch_payload["subject_entity_id"] == "user"
    assert planned.patch_payload["arguments"]["object"]["label"] == "concise updates"


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
            "graph_enrichment_planner_version": "canonical_historical_graph_enrichment.v2",
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
    planner = _Planner(
        {
            "eligible": True,
            "subject_entity_id": "user",
            "predicate": "prefers_update_style",
            "object_label": "concise updates",
        }
    )

    monkeypatch.setattr(historical_runner, "_control", lambda *_args, **_kwargs: control)
    monkeypatch.setattr(
        historical_runner,
        "_candidates",
        lambda *_args, **_kwargs: [failing, ready],
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
    )

    assert report["outcomes"] == {"committed": 1, "planner_error": 1}
