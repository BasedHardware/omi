"""Canonical per-memory graph assertions are merged into the read-side graph."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pytest

from database import knowledge_graph as kg_db
from models.memory_promotion import (
    MemoryGraphAssertion,
    PromotionGraphPlan,
    build_memory_graph_assertion,
)
from utils.memory import kg_graph_traversal

UID = "uid-memory-graph-read"
NOW = datetime(2026, 7, 27, 12, 0, tzinfo=timezone.utc)


class _Snapshot:
    def __init__(self, db: "_FakeDb", path: str, *, exists: bool):
        self._db = db
        self._path = path
        self.id = path.rsplit("/", 1)[-1]
        self.exists = exists

    def to_dict(self):
        return self._db.docs.get(self._path)


class _DocRef:
    def __init__(self, db: "_FakeDb", path: str):
        self._db = db
        self.path = path
        self.id = path.rsplit("/", 1)[-1]

    def get(self):
        return _Snapshot(self._db, self.path, exists=self.path in self._db.docs)

    def collection(self, name: str):
        return _CollectionRef(self._db, f"{self.path}/{name}")


class _CollectionRef:
    def __init__(self, db: "_FakeDb", path: str):
        self._db = db
        self.path = path
        self._limit = None

    def document(self, doc_id: str):
        return _DocRef(self._db, f"{self.path}/{doc_id}")

    def limit(self, count: int):
        self._db.limit_calls.append((self.path, count))
        self._limit = count
        return self

    def order_by(self, _field_path: str, *_args, **_kwargs):
        return self

    def stream(self):
        prefix = f"{self.path}/"
        depth = self.path.count("/")
        emitted = 0
        for path in sorted(self._db.docs):
            if path.startswith(prefix) and path.count("/") == depth + 1:
                yield _Snapshot(self._db, path, exists=True)
                emitted += 1
                if self._limit is not None and emitted >= self._limit:
                    break


class _FakeDb:
    def __init__(self, docs=None):
        self.docs = dict(docs or {})
        self.limit_calls: list[tuple[str, int]] = []
        self.get_all_batch_sizes: list[int] = []

    def collection(self, name: str):
        return _CollectionRef(self, name)

    def get_all(self, refs):
        refs = list(refs)
        self.get_all_batch_sizes.append(len(refs))
        return [ref.get() for ref in refs]


def _assertion(
    memory_id: str = "mem-canonical",
    *,
    commit_sequence: int = 7,
    subject_entity_id: str = "legacy-user",
    location: str = "Seattle",
) -> MemoryGraphAssertion:
    graph_plan = PromotionGraphPlan(
        subject_entity_id=subject_entity_id,
        predicate="resides_in",
        arguments={"location": location},
    )
    return build_memory_graph_assertion(
        uid=UID,
        memory_id=memory_id,
        item_revision=2,
        content_hash=f"hash-{memory_id}",
        evidence_ids=[f"ev-{memory_id}"],
        graph_plan=graph_plan,
        commit_id=f"commit-{memory_id}",
        commit_sequence=commit_sequence,
        created_at=NOW,
    )


def _active_item(assertion: MemoryGraphAssertion, **overrides: Any) -> dict[str, Any]:
    item = {
        "uid": UID,
        "memory_id": assertion.memory_id,
        "account_generation": 4,
        "status": "active",
        "tier": "long_term",
        "processing_state": "processed",
        "source_state": "active",
        "graph_ready": True,
        "graph_assertion_id": assertion.assertion_id,
        "graph_plan_hash": assertion.graph_plan_hash,
        "item_revision": assertion.item_revision,
        "content_hash": assertion.content_hash,
        "ledger_commit_id": assertion.commit_id,
        "ledger_sequence": assertion.commit_sequence,
        "subject_entity_id": assertion.subject_entity_id,
        "predicate": assertion.predicate,
        "arguments": assertion.arguments,
        "evidence": [{"evidence_id": evidence_id} for evidence_id in assertion.evidence_ids],
        "promotion": {},
    }
    item.update(overrides)
    return item


def _docs_for(assertion: MemoryGraphAssertion, item: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        f"users/{UID}/memory_graph_assertions/{assertion.memory_id}": assertion.model_dump(mode="json"),
        f"users/{UID}/memory_items/{assertion.memory_id}": item,
    }


def _legacy_graph_docs() -> dict[str, dict[str, Any]]:
    return {
        f"users/{UID}/knowledge_nodes/legacy-user": {
            "id": "legacy-user",
            "label": "User",
            "node_type": "person",
            "aliases": ["Me"],
            "memory_ids": ["mem-legacy"],
        },
        f"users/{UID}/knowledge_nodes/legacy-seattle": {
            "id": "legacy-seattle",
            "label": "Seattle",
            "node_type": "place",
            "aliases": [],
            "memory_ids": ["mem-canonical", "mem-legacy"],
        },
        f"users/{UID}/knowledge_nodes/stale-portland": {
            "id": "stale-portland",
            "label": "Portland",
            "node_type": "place",
            "aliases": [],
            "memory_ids": ["mem-canonical"],
        },
        f"users/{UID}/knowledge_edges/legacy-current": {
            "id": "legacy-current",
            "source_id": "legacy-user",
            "target_id": "legacy-seattle",
            "label": "resides_in",
            "memory_ids": ["mem-canonical", "mem-legacy"],
        },
        f"users/{UID}/knowledge_edges/legacy-stale": {
            "id": "legacy-stale",
            "source_id": "legacy-user",
            "target_id": "stale-portland",
            "label": "resides_in",
            "memory_ids": ["mem-canonical"],
        },
    }


def test_get_knowledge_graph_merges_current_assertion_and_replaces_its_stale_legacy_records():
    assertion = _assertion()
    db = _FakeDb({**_legacy_graph_docs(), **_docs_for(assertion, _active_item(assertion))})

    graph = kg_db.get_knowledge_graph(UID, db_client=db)

    assert graph["truncated"] is False
    nodes = {node["id"]: node for node in graph["nodes"]}
    assert set(nodes) == {"legacy-seattle", "legacy-user"}
    assert nodes["legacy-seattle"]["memory_ids"] == ["mem-canonical", "mem-legacy"]

    assert len(graph["edges"]) == 1
    edge = graph["edges"][0]
    assert edge["source_id"] == "legacy-user"
    assert edge["target_id"] == "legacy-seattle"
    assert edge["label"] == "resides_in"
    assert edge["memory_ids"] == ["mem-canonical", "mem-legacy"]
    assert edge["id"].startswith("edge_")


@pytest.mark.parametrize(
    "item_override",
    [
        {"status": "superseded", "graph_ready": False, "graph_assertion_id": None},
        {"source_state": "tombstoned"},
        {"graph_assertion_id": "mga-stale"},
        {"item_revision": 3},
        {"promotion": {"user_review": False}},
        {"sensitivity_labels": ["HeAlTh"]},
    ],
)
def test_loader_excludes_assertions_not_fenced_to_an_active_current_item(item_override):
    assertion = _assertion()
    db = _FakeDb(_docs_for(assertion, _active_item(assertion, **item_override)))

    assert kg_db.get_active_memory_graph_assertions(UID, db_client=db) == []
    assert kg_db.get_knowledge_graph(UID, db_client=db) == {
        "nodes": [],
        "edges": [],
        "truncated": False,
        "node_count": 0,
        "edge_count": 0,
        "node_limit": kg_db.MAX_KNOWLEDGE_GRAPH_NODES,
        "edge_limit": kg_db.MAX_KNOWLEDGE_GRAPH_EDGES,
    }


def test_loader_keeps_active_item_when_original_source_is_missing_but_evidence_was_preserved():
    assertion = _assertion()
    db = _FakeDb(_docs_for(assertion, _active_item(assertion, source_state="missing")))

    assert kg_db.get_active_memory_graph_assertions(UID, db_client=db) == [assertion]


def test_tombstoned_canonical_item_fences_legacy_graph_before_projection_prune():
    memory_id = "mem-deleted-before-kg-prune"
    db = _FakeDb(
        {
            f"users/{UID}/memory_state/apply_control": {
                "uid": UID,
                "head_commit_id": "commit-delete",
                "account_generation": 1,
                "source_generation": 1,
                "commit_sequence": 9,
            },
            f"users/{UID}/memory_items/{memory_id}": {
                "uid": UID,
                "memory_id": memory_id,
                "status": "tombstoned",
            },
            f"users/{UID}/knowledge_nodes/private-deleted-node": {
                "id": "private-deleted-node",
                "label": "Deleted private fact",
                "node_type": "concept",
                "memory_ids": [memory_id],
            },
        }
    )

    assert kg_db.get_knowledge_graph(UID, db_client=db) == {
        "nodes": [],
        "edges": [],
        "truncated": False,
        "node_count": 0,
        "edge_count": 0,
        "node_limit": kg_db.MAX_KNOWLEDGE_GRAPH_NODES,
        "edge_limit": kg_db.MAX_KNOWLEDGE_GRAPH_EDGES,
    }


def test_stored_assertion_presence_probe_is_bounded_and_does_not_require_a_valid_assertion():
    assertions_path = f"users/{UID}/memory_graph_assertions"
    db = _FakeDb(
        {
            f"{assertions_path}/retained-malformed": {"unexpected": "payload"},
            f"{assertions_path}/retained-second": {"unexpected": "payload"},
        }
    )

    assert kg_db.has_stored_memory_graph_assertions(UID, db_client=db) is True
    assert db.limit_calls == [(assertions_path, 1)]


def test_loader_ignores_malformed_assertion_without_exposing_partial_graph(monkeypatch):
    assertion = _assertion()
    malformed = assertion.model_dump(mode="json")
    malformed["graph_plan_hash"] = "wrong"
    recorded_fallbacks: list[dict[str, Any]] = []
    monkeypatch.setattr(
        "database.read_boundary.record_fallback",
        lambda **fields: recorded_fallbacks.append(fields),
    )
    db = _FakeDb(
        {
            f"users/{UID}/memory_graph_assertions/{assertion.memory_id}": malformed,
            f"users/{UID}/memory_items/{assertion.memory_id}": _active_item(assertion),
        }
    )

    assert kg_db.get_active_memory_graph_assertions(UID, db_client=db) == []
    expected_fallback = {
        "component": "firestore_read",
        "from_mode": "firestore_document",
        "to_mode": "skip_malformed_document",
        "reason": "malformed_doc",
        "outcome": "degraded",
    }
    assert len(recorded_fallbacks) == 1
    assert {key: recorded_fallbacks[0][key] for key in expected_fallback} == expected_fallback


def test_merge_is_deterministic_and_structurally_deduplicates_assertion_edges():
    first = _assertion("mem-a", commit_sequence=9)
    second = _assertion("mem-b", commit_sequence=4)
    legacy_graph = {
        "nodes": list(reversed([value for key, value in _legacy_graph_docs().items() if "/knowledge_nodes/" in key])),
        "edges": list(reversed([value for key, value in _legacy_graph_docs().items() if "/knowledge_edges/" in key])),
    }

    forward = kg_db.merge_knowledge_graph_records(legacy_graph, [first, second])
    reverse = kg_db.merge_knowledge_graph_records(
        {
            "nodes": list(reversed(legacy_graph["nodes"])),
            "edges": list(reversed(legacy_graph["edges"])),
        },
        [second, first],
    )

    assert forward == reverse
    current_edges = [edge for edge in forward["edges"] if edge["target_id"] == "legacy-seattle"]
    assert len(current_edges) == 1
    assert current_edges[0]["memory_ids"] == ["mem-a", "mem-b", "mem-canonical", "mem-legacy"]


def test_bounded_graph_read_returns_only_edges_closed_over_the_node_page(monkeypatch):
    monkeypatch.setattr(kg_db, "MAX_KNOWLEDGE_GRAPH_NODES", 4)
    monkeypatch.setattr(kg_db, "MAX_KNOWLEDGE_GRAPH_EDGES", 10)
    monkeypatch.setattr(kg_db, "MAX_KNOWLEDGE_GRAPH_ASSERTIONS", 3)
    assertions = [
        _assertion(
            f"mem-{index}",
            commit_sequence=index + 1,
            subject_entity_id=f"subject-{index}",
            location=f"Location {index}",
        )
        for index in range(3)
    ]
    docs: dict[str, dict[str, Any]] = {}
    for assertion in assertions:
        docs.update(_docs_for(assertion, _active_item(assertion)))

    graph = kg_db.get_knowledge_graph(UID, db_client=_FakeDb(docs))

    node_ids = {node["id"] for node in graph["nodes"]}
    assert len(node_ids) == 4
    assert len(graph["edges"]) == 1
    assert all(edge["source_id"] in node_ids and edge["target_id"] in node_ids for edge in graph["edges"])
    assert graph["truncated"] is True


def test_existing_graph_traversal_sees_atomic_assertion_without_an_llm_call(monkeypatch):
    assertion = _assertion()
    graph = kg_db.merge_knowledge_graph_records({"nodes": [], "edges": []}, [assertion])
    monkeypatch.setattr(kg_graph_traversal, "user_allows_kg_traversal", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(
        kg_graph_traversal,
        "_long_term_memory_ids",
        lambda *_args, **_kwargs: {assertion.memory_id},
    )
    monkeypatch.setattr(
        kg_graph_traversal,
        "fetch_authoritative_product_memory_items",
        lambda **_kwargs: [],
    )

    result = kg_graph_traversal.traverse_knowledge_graph(
        UID,
        assertion.subject_entity_id,
        hops=1,
        graph=graph,
    )

    assert [
        (triple.source_id, triple.relation, triple.target_label, triple.memory_ids) for triple in result.triples
    ] == [
        (
            assertion.subject_entity_id,
            assertion.predicate,
            "Seattle",
            (assertion.memory_id,),
        )
    ]


def test_load_fenced_assertions_preserves_caller_order_and_skips_missing():
    first = _assertion("mem-first", commit_sequence=2)
    second = _assertion("mem-second", commit_sequence=3)
    third = _assertion("mem-third", commit_sequence=4)
    docs = {
        **_docs_for(first, _active_item(first)),
        **_docs_for(third, _active_item(third)),
    }
    db = _FakeDb(docs)

    loaded = kg_db.load_fenced_assertions_for_memory_items(
        UID,
        ["mem-second", "mem-first", "mem-missing", "mem-third"],
        account_generation=4,
        db_client=db,
    )

    assert [assertion.memory_id for assertion in loaded] == ["mem-first", "mem-third"]


def test_load_fenced_assertions_batches_assertion_and_item_reads():
    assertions = [_assertion(f"mem-{index:03d}", commit_sequence=index + 1) for index in range(205)]
    docs: dict[str, dict[str, Any]] = {}
    for assertion in assertions:
        docs.update(_docs_for(assertion, _active_item(assertion)))
    db = _FakeDb(docs)
    memory_ids = [assertion.memory_id for assertion in assertions]

    loaded = kg_db.load_fenced_assertions_for_memory_items(
        UID,
        memory_ids,
        account_generation=4,
        db_client=db,
    )

    assert len(loaded) == 205
    assert max(db.get_all_batch_sizes) <= kg_db.MEMORY_GRAPH_ASSERTION_BATCH_SIZE
    assert db.get_all_batch_sizes == [100, 100, 5, 100, 100, 5]


def test_load_fenced_assertions_excludes_wrong_account_generation():
    assertion = _assertion("mem-stale-generation")
    db = _FakeDb(_docs_for(assertion, _active_item(assertion, account_generation=3)))

    assert (
        kg_db.load_fenced_assertions_for_memory_items(
            UID,
            [assertion.memory_id],
            account_generation=4,
            db_client=db,
        )
        == []
    )


def test_load_fenced_assertions_excludes_restricted_sensitivity_labels():
    assertion = _assertion("mem-restricted")
    db = _FakeDb(_docs_for(assertion, _active_item(assertion, sensitivity_labels=["HeAlTh"])))

    assert (
        kg_db.load_fenced_assertions_for_memory_items(
            UID,
            [assertion.memory_id],
            account_generation=4,
            db_client=db,
        )
        == []
    )


def test_load_fenced_assertions_ignores_miskeyed_memory_item_documents():
    assertion = _assertion("mem-authoritative")
    docs = _docs_for(assertion, _active_item(assertion))
    item_path = f"users/{UID}/memory_items/{assertion.memory_id}"
    miskeyed_item = dict(docs[item_path])
    miskeyed_item["memory_id"] = "mem-payload-alias"
    docs[item_path] = miskeyed_item
    db = _FakeDb(docs)

    assert (
        kg_db.load_fenced_assertions_for_memory_items(
            UID,
            [assertion.memory_id],
            account_generation=4,
            db_client=db,
        )
        == []
    )
