"""Server-side merge of agent-VM local_kg_* sync into Firestore knowledge graph."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, cast

import pytest
from pydantic import ValidationError

from database import knowledge_graph as kg_db
from routers import knowledge_graph as kg_router
from utils import knowledge_graph_sync as kg_sync

UID = "uid-kg-sync-merge"
SOURCE_NAMESPACE = "macos_test"
NAMESPACE = kg_sync.namespace_for_source(SOURCE_NAMESPACE)
BASE = datetime(2026, 7, 1, 12, 0, tzinfo=timezone.utc)


def _node_path(node_id: str) -> str:
    return f"users/{UID}/knowledge_nodes/{NAMESPACE}_{node_id}"


def _edge_path(edge_id: str) -> str:
    return f"users/{UID}/knowledge_edges/{NAMESPACE}_{edge_id}"


def _node_path_for_namespace(source_namespace: str, node_id: str) -> str:
    return f"users/{UID}/knowledge_nodes/{kg_sync.namespace_for_source(source_namespace)}_{node_id}"


class _Snapshot:
    def __init__(self, db: "_FakeDb", path: str, *, exists: bool):
        self._db = db
        self._path = path
        self.id = path.rsplit("/", 1)[-1]
        self.reference = _DocRef(db, path)
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

    def set(self, data: dict[str, Any], merge: bool = False):
        if merge and self.path in self._db.docs:
            existing = dict(self._db.docs[self.path])
            existing.update(data)
            self._db.docs[self.path] = existing
        else:
            self._db.docs[self.path] = dict(data)

    def delete(self):
        self._db.docs.pop(self.path, None)

    def collection(self, name: str):
        return _CollectionRef(self._db, f"{self.path}/{name}")


class _CollectionRef:
    def __init__(self, db: "_FakeDb", path: str):
        self._db = db
        self.path = path
        self._limit: int | None = None

    def document(self, doc_id: str):
        return _DocRef(self._db, f"{self.path}/{doc_id}")

    def limit(self, count: int):
        self._limit = count
        return self

    def order_by(self, _field_path: str, *_args, **_kwargs):
        return self

    def where(self, *_args, **_kwargs):
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
    def __init__(self, docs: dict[str, Any] | None = None):
        self.docs = dict(docs or {})
        self.batch_commits = 0

    def collection(self, name: str):
        return _CollectionRef(self, name)

    def get_all(self, refs):
        return [ref.get() for ref in refs]

    def batch(self):
        return _Batch(self)


class _Batch:
    def __init__(self, db: _FakeDb):
        self.db = db
        self.operations: list[tuple[str, _DocRef, dict[str, Any] | None]] = []

    def set(self, ref: _DocRef, data: dict[str, Any], merge: bool = False):
        self.operations.append(("set", ref, dict(data)))

    def delete(self, ref: _DocRef):
        self.operations.append(("delete", ref, None))

    def commit(self):
        self.db.batch_commits += 1
        for operation, ref, data in self.operations:
            if operation == "delete":
                ref.delete()
            else:
                ref.set(cast(dict[str, Any], data))


def _node_doc(node_id: str, *, label: str, updated_at: datetime) -> dict[str, Any]:
    return {
        "id": f"{NAMESPACE}_{node_id}",
        "label": label,
        "node_type": "concept",
        "aliases": [],
        "memory_ids": [],
        "created_at": updated_at - timedelta(days=1),
        "updated_at": updated_at,
        "label_lower": label.lower(),
        "aliases_lower": [],
        "sync_namespace": NAMESPACE,
    }


def _edge_doc(edge_id: str, *, source_id: str, target_id: str, created_at: datetime) -> dict[str, Any]:
    return {
        "id": f"{NAMESPACE}_{edge_id}",
        "source_id": f"{NAMESPACE}_{source_id}",
        "target_id": f"{NAMESPACE}_{target_id}",
        "label": "related_to",
        "memory_ids": [],
        "created_at": created_at,
        "sync_namespace": NAMESPACE,
    }


def test_local_kg_node_row_maps_and_merges_aliases(monkeypatch):
    db = _FakeDb()
    row = {
        "nodeId": "node-a",
        "label": "Omi",
        "nodeType": "org",
        "aliasesJson": '["Based Hardware"]',
        "createdAt": "2026-07-01T12:00:00Z",
        "updatedAt": "2026-07-02T12:00:00Z",
    }
    result = kg_sync.merge_synced_local_kg_nodes(UID, [row], SOURCE_NAMESPACE, db_client=db)

    stored = db.docs[_node_path("node-a")]
    assert result == {
        "table": "local_kg_nodes",
        "merged": 1,
        "skipped": 0,
        "quarantined": 0,
        "deleted": 0,
        "nodes_evicted": 0,
        "edges_evicted": 0,
    }
    assert stored["label"] == "Omi"
    assert stored["node_type"] == "org"
    assert stored["aliases"] == ["Based Hardware"]
    assert stored["created_at"] == datetime(2026, 7, 1, 12, 0, tzinfo=timezone.utc)
    assert stored["updated_at"] == datetime(2026, 7, 2, 12, 0, tzinfo=timezone.utc)

    updated = {
        **row,
        "aliasesJson": '["Based Hardware", "Omi Inc"]',
        "updatedAt": "2026-07-03T12:00:00Z",
    }
    kg_sync.merge_synced_local_kg_nodes(UID, [updated], SOURCE_NAMESPACE, db_client=db)
    merged = db.docs[_node_path("node-a")]
    assert sorted(merged["aliases"]) == ["Based Hardware", "Omi Inc"]


def test_local_kg_edge_row_upserts_by_edge_id():
    db = _FakeDb(
        {
            _node_path("node-a"): _node_doc("node-a", label="A", updated_at=BASE),
            _node_path("node-b"): _node_doc("node-b", label="B", updated_at=BASE),
        }
    )
    row = {
        "edgeId": "edge-1",
        "sourceNodeId": "node-a",
        "targetNodeId": "node-b",
        "label": "works_at",
        "createdAt": "2026-07-01T12:00:00Z",
    }
    result = kg_sync.merge_synced_local_kg_edges(UID, [row], SOURCE_NAMESPACE, db_client=db)
    stored = db.docs[_edge_path("edge-1")]

    assert result["merged"] == 1
    assert stored["source_id"] == f"{NAMESPACE}_node-a"
    assert stored["target_id"] == f"{NAMESPACE}_node-b"
    assert stored["label"] == "works_at"


def test_local_ids_are_namespaced_per_source_device():
    db = _FakeDb()
    first = {"nodeId": "same-id", "label": "First"}
    second = {"nodeId": "same-id", "label": "Second"}

    kg_sync.merge_synced_local_kg_nodes(UID, [first], "macos_first", db_client=db)
    kg_sync.merge_synced_local_kg_nodes(UID, [second], "macos_second", db_client=db)

    assert _node_path_for_namespace("macos_first", "same-id") in db.docs
    assert _node_path_for_namespace("macos_second", "same-id") in db.docs
    assert len([path for path in db.docs if "/knowledge_nodes/" in path]) == 2


def test_empty_reconciliation_deletes_only_one_source_namespace():
    db = _FakeDb()
    row = {"nodeId": "node-a", "label": "A"}
    kg_sync.merge_synced_local_kg_nodes(UID, [row], SOURCE_NAMESPACE, db_client=db)
    kg_sync.merge_synced_local_kg_nodes(UID, [row], "macos_other", db_client=db)

    result = kg_sync.merge_synced_local_kg_nodes(
        UID,
        [],
        SOURCE_NAMESPACE,
        reconcile_complete=True,
        db_client=db,
    )

    assert result["deleted"] == 1
    assert _node_path("node-a") not in db.docs
    assert _node_path_for_namespace("macos_other", "node-a") in db.docs


def test_node_batch_merge_commits_one_batch_for_multiple_rows():
    db = _FakeDb()
    rows = [{"nodeId": f"node-{index}", "label": f"Node {index}"} for index in range(3)]

    result = kg_sync.merge_synced_local_kg_nodes(UID, rows, SOURCE_NAMESPACE, db_client=db)

    assert result["merged"] == 3
    assert db.batch_commits == 1


def test_enforce_caps_does_not_delete_nodes_or_edges():
    docs: dict[str, Any] = {}
    for index in range(kg_db.MAX_KNOWLEDGE_GRAPH_NODES):
        node_id = f"keep-{index:03d}"
        docs[_node_path(node_id)] = _node_doc(
            node_id,
            label=node_id,
            updated_at=BASE + timedelta(hours=index),
        )
    docs[_node_path("zzz-excess")] = _node_doc(
        "zzz-excess",
        label="Excess",
        updated_at=BASE + timedelta(days=30),
    )
    docs[_edge_path("stale-edge")] = _edge_doc(
        "stale-edge",
        source_id="zzz-excess",
        target_id="keep-001",
        created_at=BASE,
    )
    docs[_edge_path("keep-edge")] = _edge_doc(
        "keep-edge",
        source_id="keep-000",
        target_id="keep-001",
        created_at=BASE + timedelta(days=30),
    )
    db = _FakeDb(docs)

    eviction = kg_sync.enforce_knowledge_graph_caps(UID, db_client=db)

    assert eviction["nodes_evicted"] == 0
    assert eviction["edges_evicted"] == 0
    assert _node_path("zzz-excess") in db.docs
    assert _node_path("keep-000") in db.docs
    assert _edge_path("stale-edge") in db.docs
    assert _edge_path("keep-edge") in db.docs


def test_enforce_caps_does_not_delete_edges_beyond_get_name_prefix():
    docs: dict[str, Any] = {}
    for index in range(2):
        node_id = f"node-{index}"
        docs[_node_path(node_id)] = _node_doc(
            node_id,
            label=node_id,
            updated_at=BASE,
        )
    for index in range(kg_db.MAX_KNOWLEDGE_GRAPH_EDGES):
        edge_id = f"edge-{index:04d}"
        docs[_edge_path(edge_id)] = _edge_doc(
            edge_id,
            source_id="node-0",
            target_id="node-1",
            created_at=BASE + timedelta(minutes=index),
        )
    docs[_edge_path("zzz-excess")] = _edge_doc(
        "zzz-excess",
        source_id="node-0",
        target_id="node-1",
        created_at=BASE + timedelta(days=30),
    )
    db = _FakeDb(docs)

    eviction = kg_sync.enforce_knowledge_graph_caps(UID, db_client=db)

    assert eviction["edges_evicted"] == 0
    assert _edge_path("zzz-excess") in db.docs
    remaining_edges = [path for path in db.docs if path.startswith(f"users/{UID}/knowledge_edges/")]
    assert len(remaining_edges) == kg_db.MAX_KNOWLEDGE_GRAPH_EDGES + 1
    assert _edge_path("edge-0000") in db.docs


def test_sync_route_delegates_to_merge(monkeypatch):
    captured: dict[str, Any] = {}

    def fake_merge(uid, table, rows, source_namespace, *, reconcile_complete=False):
        captured["uid"] = uid
        captured["table"] = table
        captured["rows"] = rows
        captured["source_namespace"] = source_namespace
        return {
            "table": table,
            "merged": len(rows),
            "skipped": 0,
            "nodes_evicted": 0,
            "edges_evicted": 0,
        }

    monkeypatch.setattr(kg_router.kg_sync, "merge_synced_local_kg", fake_merge)
    monkeypatch.setattr(kg_router, "firestore_db", object())
    monkeypatch.setattr(kg_router, "_require_legacy_graph_mutation", lambda _uid: None)

    rows = [{"nodeId": "n1", "label": "Test"}]
    response = kg_router.sync_local_knowledge_graph(
        payload=kg_router.LocalKgSyncRequest(table="local_kg_nodes", rows=rows, source_namespace=SOURCE_NAMESPACE),
        uid=UID,
    )

    assert captured == {
        "uid": UID,
        "table": "local_kg_nodes",
        "rows": rows,
        "source_namespace": SOURCE_NAMESPACE,
    }
    assert response.merged == 1
    assert response.table == "local_kg_nodes"


def test_sync_request_rejects_oversized_batch():
    with pytest.raises(ValidationError):
        kg_router.LocalKgSyncRequest(
            table="local_kg_nodes",
            rows=[{"nodeId": str(index), "label": "Test"} for index in range(kg_router.LOCAL_KG_SYNC_MAX_ROWS + 1)],
        )


def test_invalid_local_kg_rows_are_skipped():
    db = _FakeDb()
    result = kg_sync.merge_synced_local_kg_nodes(
        UID, [{"nodeId": "", "label": "Bad"}, {"label": "Missing id"}, "not-a-row"], SOURCE_NAMESPACE, db_client=db
    )
    assert result["merged"] == 0
    assert result["skipped"] == 3
    assert db.docs == {}


def test_merge_preserves_stable_node_id_despite_label_collision():
    db = _FakeDb(
        {
            _node_path("existing-omi"): _node_doc(
                "existing-omi",
                label="Omi",
                updated_at=BASE,
            )
        }
    )
    row = {
        "nodeId": "local-omi",
        "label": "Omi",
        "nodeType": "org",
        "aliasesJson": "[]",
        "createdAt": "2026-07-01T12:00:00Z",
        "updatedAt": "2026-07-02T12:00:00Z",
    }
    kg_sync.merge_synced_local_kg_nodes(UID, [row], SOURCE_NAMESPACE, db_client=db)

    assert _node_path("local-omi") in db.docs
    assert db.docs[_node_path("local-omi")]["id"] == f"{NAMESPACE}_local-omi"
    assert _node_path("existing-omi") in db.docs

    edge_row = {
        "edgeId": "edge-local",
        "sourceNodeId": "local-omi",
        "targetNodeId": "existing-omi",
        "label": "related_to",
        "createdAt": "2026-07-01T12:00:00Z",
    }
    result = kg_sync.merge_synced_local_kg_edges(UID, [edge_row], SOURCE_NAMESPACE, db_client=db)
    assert result["merged"] == 1
    assert result["edges_evicted"] == 0
    assert _edge_path("edge-local") in db.docs


def test_merge_preserves_documents_beyond_get_name_prefix():
    db = _FakeDb()
    old_ts = "2026-01-01T00:00:00Z"
    new_ts = "2026-07-01T12:00:00Z"
    keep_rows = [
        {
            "nodeId": f"keep-{index:03d}",
            "label": f"keep-{index:03d}",
            "nodeType": "concept",
            "aliasesJson": "[]",
            "createdAt": old_ts,
            "updatedAt": old_ts,
        }
        for index in range(kg_db.MAX_KNOWLEDGE_GRAPH_NODES)
    ]
    kg_sync.merge_synced_local_kg_nodes(UID, keep_rows, SOURCE_NAMESPACE, db_client=db)
    kg_sync.merge_synced_local_kg_nodes(
        UID,
        [
            {
                "nodeId": "zzz-excess",
                "label": "Excess",
                "nodeType": "concept",
                "aliasesJson": "[]",
                "createdAt": new_ts,
                "updatedAt": new_ts,
            }
        ],
        SOURCE_NAMESPACE,
        db_client=db,
    )

    assert _node_path("zzz-excess") in db.docs
    assert _node_path("keep-000") in db.docs
    keep = db.docs[_node_path("keep-000")]
    assert keep["updated_at"] == datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)
    assert keep["created_at"] == datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)


def test_merge_quarantines_edges_when_endpoints_missing():
    db = _FakeDb(
        {
            _node_path("node-a"): _node_doc("node-a", label="A", updated_at=BASE),
        }
    )
    row = {
        "edgeId": "edge-missing-target",
        "sourceNodeId": "node-a",
        "targetNodeId": "node-missing",
        "label": "related_to",
        "createdAt": "2026-07-01T12:00:00Z",
    }
    result = kg_sync.merge_synced_local_kg_edges(UID, [row], SOURCE_NAMESPACE, db_client=db)
    assert result["merged"] == 0
    assert result["quarantined"] == 1
    assert _edge_path("edge-missing-target") not in db.docs


def test_merge_writes_valid_edges_and_quarantines_missing_edges():
    db = _FakeDb(
        {
            _node_path("node-a"): _node_doc("node-a", label="A", updated_at=BASE),
            _node_path("node-b"): _node_doc("node-b", label="B", updated_at=BASE),
        }
    )
    rows = [
        {
            "edgeId": "edge-valid",
            "sourceNodeId": "node-a",
            "targetNodeId": "node-b",
            "label": "related_to",
        },
        {
            "edgeId": "edge-invalid",
            "sourceNodeId": "node-a",
            "targetNodeId": "node-missing",
            "label": "related_to",
        },
    ]

    result = kg_sync.merge_synced_local_kg_edges(UID, rows, SOURCE_NAMESPACE, db_client=db)
    assert result["merged"] == 1
    assert result["quarantined"] == 1
    assert _edge_path("edge-valid") in db.docs


def test_merge_rejects_firestore_path_separator_in_ids():
    with pytest.raises(kg_db.InvalidKnowledgeGraphDocumentIdError):
        kg_sync.merge_synced_local_kg_nodes(
            UID, [{"nodeId": "folder/node", "label": "Invalid"}], SOURCE_NAMESPACE, db_client=_FakeDb()
        )


@pytest.mark.parametrize("node_id", ["__reserved__", "__name__"])
def test_merge_rejects_firestore_reserved_ids(node_id):
    with pytest.raises(kg_db.InvalidKnowledgeGraphDocumentIdError):
        kg_sync.merge_synced_local_kg_nodes(
            UID, [{"nodeId": node_id, "label": "Invalid"}], SOURCE_NAMESPACE, db_client=_FakeDb()
        )


def test_legacy_edge_label_slash_is_normalized_before_firestore_write():
    db = _FakeDb()
    result = kg_db.upsert_knowledge_edge(
        UID,
        {"source_id": "source", "target_id": "target", "label": "works/with"},
        db_client=db,
    )

    assert result["id"] == "source_works_with_target"
    assert f"users/{UID}/knowledge_edges/source_works_with_target" in db.docs


def test_sync_route_returns_quarantine_count(monkeypatch):
    monkeypatch.setattr(kg_router, "_require_legacy_graph_mutation", lambda _uid: None)

    def fake_merge(uid, table, rows, source_namespace, *, reconcile_complete=False):
        return {
            "table": table,
            "merged": 0,
            "skipped": 0,
            "quarantined": 1,
            "deleted": 0,
            "nodes_evicted": 0,
            "edges_evicted": 0,
        }

    monkeypatch.setattr(kg_router.kg_sync, "merge_synced_local_kg", fake_merge)
    response = kg_router.sync_local_knowledge_graph(
        payload=kg_router.LocalKgSyncRequest(
            table="local_kg_edges",
            rows=[{"edgeId": "e1", "sourceNodeId": "a", "targetNodeId": "b", "label": "related_to"}],
            source_namespace=SOURCE_NAMESPACE,
        ),
        uid=UID,
    )
    assert response.quarantined == 1


def test_merge_keeps_fresher_cloud_updated_at():
    newer = BASE + timedelta(days=2)
    older = BASE
    db = _FakeDb(
        {
            _node_path("node-a"): _node_doc("node-a", label="Omi", updated_at=newer),
        }
    )
    row = {
        "nodeId": "node-a",
        "label": "Omi",
        "nodeType": "org",
        "aliasesJson": '["Based Hardware"]',
        "createdAt": "2026-07-01T12:00:00Z",
        "updatedAt": older.isoformat().replace("+00:00", "Z"),
    }
    kg_sync.merge_synced_local_kg_nodes(UID, [row], SOURCE_NAMESPACE, db_client=db)
    stored = db.docs[_node_path("node-a")]
    assert stored["updated_at"] == newer
    assert sorted(stored["aliases"]) == ["Based Hardware"]


def test_merge_keeps_fresher_cloud_scalar_fields():
    newer = BASE + timedelta(days=2)
    db = _FakeDb(
        {
            _node_path("node-a"): _node_doc("node-a", label="Cloud label", updated_at=newer),
        }
    )
    row = {
        "nodeId": "node-a",
        "label": "Stale local label",
        "nodeType": "stale_type",
        "updatedAt": BASE.isoformat().replace("+00:00", "Z"),
    }

    kg_sync.merge_synced_local_kg_nodes(UID, [row], SOURCE_NAMESPACE, db_client=db)
    stored = db.docs[_node_path("node-a")]
    assert stored["label"] == "Cloud label"
    assert stored["node_type"] == "concept"
    assert stored["label_lower"] == "cloud label"
