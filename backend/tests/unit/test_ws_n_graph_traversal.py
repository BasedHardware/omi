"""WS-N bounded read-only knowledge-graph traversal."""

from __future__ import annotations

import os
import sys
import types
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock, patch

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[2]

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)

_db_client_mod = types.ModuleType("database._client")
_db_client_mod.db = MagicMock()


def _document_id_from_seed(seed: str) -> str:
    import hashlib
    import uuid

    seed_hash = hashlib.sha256(seed.encode("utf-8")).digest()
    return str(uuid.UUID(bytes=seed_hash[:16], version=4))


_db_client_mod.document_id_from_seed = _document_id_from_seed

from tests.unit.memory_import_isolation import (
    ensure_utils_memory_packages_importable,
    install_database_client_stub,
    install_ws_n_heavy_import_stubs,
    restore_sys_modules,
    snapshot_sys_modules,
)


@pytest.fixture(scope="module", autouse=True)
def _ws_n_import_isolation():
    saved = snapshot_sys_modules(["database._client"])
    install_database_client_stub()
    touched = install_ws_n_heavy_import_stubs()
    saved.update(snapshot_sys_modules(touched))
    yield
    restore_sys_modules(saved)


ensure_utils_memory_packages_importable(str(BACKEND_DIR))
from models.memory_evidence import ArtifactPreservationState, MemoryEvidence, SourceState
from models.product_memory import MemoryItemStatus, MemoryTier, ProcessingState, MemoryItem
from utils.memory.kg_graph_traversal import (
    MAX_EDGES_PER_NODE,
    MAX_TRAVERSAL_HOPS,
    MAX_TRIPLES,
    TraversalResult,
    format_traversal_result,
    traverse_knowledge_graph,
    user_allows_kg_traversal,
)
from utils.memory.memory_system import MemorySystem

CANONICAL_UID = "uid-canonical-ws-n"
LEGACY_UID = "uid-legacy-ws-n"
NOW = datetime(2026, 6, 23, tzinfo=timezone.utc)


def _evidence() -> MemoryEvidence:
    return MemoryEvidence(
        evidence_id="ev_ws_n",
        source_id="conv-1",
        source_type="conversation",
        source_version="v1",
        conversation_id="conv-1",
        artifact_preservation=ArtifactPreservationState.preserved,
    )


def _long_term_item(memory_id: str, content: str) -> MemoryItem:
    now = datetime(2026, 6, 1, tzinfo=timezone.utc)
    return MemoryItem(
        memory_id=memory_id,
        uid=CANONICAL_UID,
        version=1,
        tier=MemoryTier.long_term,
        status=MemoryItemStatus.active,
        processing_state=ProcessingState.processed,
        content=content,
        evidence=[_evidence()],
        source_state=SourceState.active,
        sensitivity_labels=[],
        visibility="private",
        user_asserted=False,
        captured_at=now,
        updated_at=now,
        expires_at=None,
        ledger_commit_id="commit_ws_n",
        ledger_sequence=1,
    )


def _sample_graph():
    return {
        "nodes": [
            {"id": "n-alice", "label": "Alice", "aliases": [], "node_type": "person"},
            {"id": "n-omi", "label": "Omi", "aliases": [], "node_type": "organization"},
            {"id": "n-seattle", "label": "Seattle", "aliases": [], "node_type": "place"},
            {"id": "n-bob", "label": "Bob", "aliases": [], "node_type": "person"},
        ],
        "edges": [
            {
                "id": "e-alice-omi",
                "source_id": "n-alice",
                "target_id": "n-omi",
                "label": "works_at",
                "memory_ids": ["mem-alice-omi"],
            },
            {
                "id": "e-omi-seattle",
                "source_id": "n-omi",
                "target_id": "n-seattle",
                "label": "located_in",
                "memory_ids": ["mem-omi-seattle"],
            },
            {
                "id": "e-bob-alice",
                "source_id": "n-bob",
                "target_id": "n-alice",
                "label": "knows",
                "memory_ids": ["mem-bob-alice"],
            },
            {
                "id": "e-alice-far",
                "source_id": "n-alice",
                "target_id": "n-bob",
                "label": "knows",
                "memory_ids": ["mem-hop3-only"],
            },
        ],
    }


def _canonical_items():
    return [
        _long_term_item("mem-alice-omi", "Alice works at Omi."),
        _long_term_item("mem-omi-seattle", "Omi is located in Seattle."),
        _long_term_item("mem-bob-alice", "Bob knows Alice."),
        _long_term_item("mem-hop3-only", "Alice knows Bob."),
    ]


@pytest.fixture
def canonical_graph_context():
    graph = _sample_graph()
    items = _canonical_items()
    with (
        patch(
            "utils.memory.kg_graph_traversal.resolve_memory_system",
            side_effect=lambda uid, **_: (MemorySystem.CANONICAL if uid == CANONICAL_UID else MemorySystem.LEGACY),
        ),
        patch(
            "utils.memory.kg_graph_traversal.fetch_authoritative_product_memory_items",
            return_value=items,
        ),
        patch("database.knowledge_graph.get_knowledge_graph", return_value=graph),
        patch("database.knowledge_graph.upsert_knowledge_node") as upsert_node,
        patch("database.knowledge_graph.upsert_knowledge_edge") as upsert_edge,
        patch("database.knowledge_graph.delete_knowledge_graph") as delete_graph,
    ):
        yield {
            "graph": graph,
            "upsert_node": upsert_node,
            "upsert_edge": upsert_edge,
            "delete_graph": delete_graph,
        }


def test_user_allows_kg_traversal_canonical_only(canonical_graph_context):
    assert user_allows_kg_traversal(CANONICAL_UID) is True
    assert user_allows_kg_traversal(LEGACY_UID) is False


def test_legacy_cohort_skips_traversal(canonical_graph_context):
    result = traverse_knowledge_graph(LEGACY_UID, "Alice", hops=1, graph=canonical_graph_context["graph"])
    assert result.skipped_reason == "not_canonical_cohort"
    assert result.triples == []


def test_one_hop_from_alice_returns_direct_neighbors(canonical_graph_context):
    result = traverse_knowledge_graph(CANONICAL_UID, "Alice", hops=1, graph=canonical_graph_context["graph"])
    relations = {(t.source_label, t.relation, t.target_label) for t in result.triples}
    assert ("Alice", "works_at", "Omi") in relations
    assert ("Alice", "knows", "Bob") in relations
    assert all(t.hop_distance == 1 for t in result.triples)
    assert not any(t.target_label == "Seattle" for t in result.triples)


def test_two_hop_from_alice_reaches_seattle(canonical_graph_context):
    result = traverse_knowledge_graph(CANONICAL_UID, "Alice", hops=2, graph=canonical_graph_context["graph"])
    relations = {(t.source_label, t.relation, t.target_label) for t in result.triples}
    assert ("Alice", "works_at", "Omi") in relations
    assert ("Omi", "located_in", "Seattle") in relations
    hop_distances = {t.hop_distance for t in result.triples}
    assert hop_distances <= {1, 2}


def test_user_rejected_memory_cannot_reappear_through_graph_traversal(canonical_graph_context):
    rejected_items = [
        item.model_copy(update={"promotion": {"user_review": False}}) if item.memory_id == "mem-alice-omi" else item
        for item in _canonical_items()
    ]
    with patch(
        "utils.memory.kg_graph_traversal.fetch_authoritative_product_memory_items",
        return_value=rejected_items,
    ):
        result = traverse_knowledge_graph(
            CANONICAL_UID,
            "Alice",
            hops=1,
            graph=canonical_graph_context["graph"],
        )

    assert all("mem-alice-omi" not in triple.memory_ids for triple in result.triples)
    assert all(citation["memory_id"] != "mem-alice-omi" for citation in result.memory_citations)


def test_three_hop_request_is_capped(canonical_graph_context):
    result = traverse_knowledge_graph(CANONICAL_UID, "Alice", hops=3, graph=canonical_graph_context["graph"])
    assert result.requested_hops == 3
    assert result.effective_hops == MAX_TRAVERSAL_HOPS
    assert result.hops_capped is True
    assert all(t.hop_distance <= MAX_TRAVERSAL_HOPS for t in result.triples)


def test_read_only_never_writes_graph(canonical_graph_context):
    traverse_knowledge_graph(CANONICAL_UID, "Alice", hops=2, graph=canonical_graph_context["graph"])
    canonical_graph_context["upsert_node"].assert_not_called()
    canonical_graph_context["upsert_edge"].assert_not_called()
    canonical_graph_context["delete_graph"].assert_not_called()


def test_per_node_edge_cap_enforced(canonical_graph_context):
    graph = canonical_graph_context["graph"]
    hub_id = "n-hub"
    graph["nodes"].append({"id": hub_id, "label": "Hub", "aliases": [], "node_type": "concept"})
    for index in range(MAX_EDGES_PER_NODE + 5):
        target_id = f"n-spoke-{index}"
        graph["nodes"].append({"id": target_id, "label": f"Spoke{index}", "aliases": [], "node_type": "concept"})
        graph["edges"].append(
            {
                "id": f"e-hub-{index}",
                "source_id": hub_id,
                "target_id": target_id,
                "label": "links",
                "memory_ids": ["mem-alice-omi"],
            }
        )

    result = traverse_knowledge_graph(CANONICAL_UID, "Hub", hops=1, graph=graph)
    assert len(result.triples) == MAX_EDGES_PER_NODE


def test_global_triple_cap_enforced(canonical_graph_context):
    graph = canonical_graph_context["graph"]
    hub_id = "n-hub"
    graph["nodes"].append({"id": hub_id, "label": "Hub", "aliases": [], "node_type": "concept"})
    for index in range(MAX_TRIPLES + 5):
        target_id = f"n-spoke-{index}"
        graph["nodes"].append({"id": target_id, "label": f"Spoke{index}", "aliases": [], "node_type": "concept"})
        graph["edges"].append(
            {
                "id": f"e-hub-{index}",
                "source_id": hub_id,
                "target_id": target_id,
                "label": "links",
                "memory_ids": ["mem-alice-omi"],
            }
        )

    with patch("utils.memory.kg_graph_traversal.MAX_EDGES_PER_NODE", MAX_TRIPLES + 10):
        result = traverse_knowledge_graph(CANONICAL_UID, "Hub", hops=1, graph=graph)
    assert len(result.triples) == MAX_TRIPLES


def test_memory_citations_include_long_term_content(canonical_graph_context):
    result = traverse_knowledge_graph(CANONICAL_UID, "Alice", hops=1, graph=canonical_graph_context["graph"])
    cited = {row["memory_id"]: row["content"] for row in result.memory_citations}
    assert cited["mem-alice-omi"] == "Alice works at Omi."


def test_traverse_knowledge_graph_tool_registered_in_core_tools():
    agentic_source = (BACKEND_DIR / "utils" / "retrieval" / "agentic.py").read_text(encoding="utf-8")
    assert "traverse_knowledge_graph_tool" in agentic_source
    tools_init = (BACKEND_DIR / "utils" / "retrieval" / "tools" / "__init__.py").read_text(encoding="utf-8")
    assert "traverse_knowledge_graph_tool" in tools_init


def test_legacy_formatted_message(canonical_graph_context):
    result = TraversalResult(
        entity_query="Alice",
        requested_hops=1,
        effective_hops=1,
        hops_capped=False,
        skipped_reason="not_canonical_cohort",
    )
    output = format_traversal_result(result)
    assert "unavailable" in output.lower()


def test_canonical_formatted_neighbors(canonical_graph_context):
    result = traverse_knowledge_graph(CANONICAL_UID, "Alice", hops=2, graph=canonical_graph_context["graph"])
    output = format_traversal_result(result)
    assert "works_at" in output
    assert "located_in" in output
    assert "Seattle" in output
