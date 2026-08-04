from __future__ import annotations

import json
from datetime import datetime, timezone

from models.memory_apply import MemoryControlState
from models.product_memory import MemoryItemStatus, MemoryTier, ProcessingState, MemoryItem
from utils.memory.graph_enrichment import GraphEnrichmentStatus
from utils.memory.historical_graph_enrichment import plan_historical_graph_enrichment


class _Response:
    def __init__(self, payload: dict[str, object]):
        self.content = json.dumps(payload)


class _Planner:
    def __init__(self, payload: dict[str, object]):
        self.payload = payload

    def invoke(self, _messages: object) -> _Response:
        return _Response(self.payload)


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
        "content_hash": "hash1",
        "account_generation": 1,
    }
    payload.update(overrides)
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
                "arguments": {"style": "concise"},
            }
        ),
    )

    assert planned.status == GraphEnrichmentStatus.ready
    assert planned.operation is not None
    assert planned.patch_payload["expected_content_hash"] == "hash1"
    assert planned.patch_payload["evidence_ids"] == ["ev1"]


def test_historical_graph_planner_blocks_when_no_source_grounded_fact_exists():
    planned = plan_historical_graph_enrichment(
        item=_item(),
        control=MemoryControlState(uid="u1", head_commit_id="head0", account_generation=1, source_generation=2),
        llm=_Planner({"eligible": False}),
    )

    assert planned.status == GraphEnrichmentStatus.blocked
    assert planned.block_code == "not_source_grounded"
