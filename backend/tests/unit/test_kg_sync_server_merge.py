"""Server-side merge of agent-VM local_kg_* sync into Firestore knowledge graph."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, cast

import pytest

from database import knowledge_graph as kg_db
from routers import knowledge_graph as kg_router

UID = "uid-kg-sync-merge"
BASE = datetime(2026, 7, 1, 12, 0, tzinfo=timezone.utc)


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

    def collection(self, name: str):
        return _CollectionRef(self, name)

    def get_all(self, refs):
        return [ref.get() for ref in refs]


def _node_doc(node_id: str, *, label: str, updated_at: datetime) -> dict[str, Any]:
    return {
        "id": node_id,
        "label": label,
        "node_type": "concept",
        "aliases": [],
        "memory_ids": [],
        "created_at": updated_at - timedelta(days=1),
        "updated_at": updated_at,
        "label_lower": label.lower(),
        "aliases_lower": [],
    }


def _edge_doc(edge_id: str, *, source_id: str, target_id: str, created_at: datetime) -> dict[str, Any]:
    return {
        "id": edge_id,
        "source_id": source_id,
        "target_id": target_id,
        "label": "related_to",
        "memory_ids": [],
        "created_at": created_at,
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
    result = kg_db.merge_synced_local_kg_nodes(UID, [row], db_client=db)

    stored = db.docs[f"users/{UID}/knowledge_nodes/node-a"]
    assert result == {
        "table": "local_kg_nodes",
        "merged": 1,
        "skipped": 0,
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
    kg_db.merge_synced_local_kg_nodes(UID, [updated], db_client=db)
    merged = db.docs[f"users/{UID}/knowledge_nodes/node-a"]
    assert sorted(merged["aliases"]) == ["Based Hardware", "Omi Inc"]


def test_local_kg_edge_row_upserts_by_edge_id():
    db = _FakeDb(
        {
            f"users/{UID}/knowledge_nodes/node-a": _node_doc("node-a", label="A", updated_at=BASE),
            f"users/{UID}/knowledge_nodes/node-b": _node_doc("node-b", label="B", updated_at=BASE),
        }
    )
    row = {
        "edgeId": "edge-1",
        "sourceNodeId": "node-a",
        "targetNodeId": "node-b",
        "label": "works_at",
        "createdAt": "2026-07-01T12:00:00Z",
    }
    result = kg_db.merge_synced_local_kg_edges(UID, [row], db_client=db)
    stored = db.docs[f"users/{UID}/knowledge_edges/edge-1"]

    assert result["merged"] == 1
    assert stored["source_id"] == "node-a"
    assert stored["target_id"] == "node-b"
    assert stored["label"] == "works_at"


def test_enforce_caps_evicts_nodes_beyond_get_name_prefix_and_dangling_edges():
    docs: dict[str, Any] = {}
    for index in range(kg_db.MAX_KNOWLEDGE_GRAPH_NODES):
        node_id = f"keep-{index:03d}"
        docs[f"users/{UID}/knowledge_nodes/{node_id}"] = _node_doc(
            node_id,
            label=node_id,
            updated_at=BASE + timedelta(hours=index),
        )
    docs[f"users/{UID}/knowledge_nodes/zzz-excess"] = _node_doc(
        "zzz-excess",
        label="Excess",
        updated_at=BASE + timedelta(days=30),
    )
    docs[f"users/{UID}/knowledge_edges/stale-edge"] = _edge_doc(
        "stale-edge",
        source_id="zzz-excess",
        target_id="keep-001",
        created_at=BASE,
    )
    docs[f"users/{UID}/knowledge_edges/keep-edge"] = _edge_doc(
        "keep-edge",
        source_id="keep-000",
        target_id="keep-001",
        created_at=BASE + timedelta(days=30),
    )
    db = _FakeDb(docs)

    eviction = kg_db.enforce_knowledge_graph_caps(UID, db_client=db)

    assert eviction["nodes_evicted"] == 1
    assert eviction["edges_evicted"] == 1
    assert f"users/{UID}/knowledge_nodes/zzz-excess" not in db.docs
    assert f"users/{UID}/knowledge_nodes/keep-000" in db.docs
    assert f"users/{UID}/knowledge_edges/stale-edge" not in db.docs
    assert f"users/{UID}/knowledge_edges/keep-edge" in db.docs


def test_enforce_caps_evicts_edges_beyond_get_name_prefix():
    docs: dict[str, Any] = {}
    for index in range(2):
        node_id = f"node-{index}"
        docs[f"users/{UID}/knowledge_nodes/{node_id}"] = _node_doc(
            node_id,
            label=node_id,
            updated_at=BASE,
        )
    for index in range(kg_db.MAX_KNOWLEDGE_GRAPH_EDGES):
        edge_id = f"edge-{index:04d}"
        docs[f"users/{UID}/knowledge_edges/{edge_id}"] = _edge_doc(
            edge_id,
            source_id="node-0",
            target_id="node-1",
            created_at=BASE + timedelta(minutes=index),
        )
    docs[f"users/{UID}/knowledge_edges/zzz-excess"] = _edge_doc(
        "zzz-excess",
        source_id="node-0",
        target_id="node-1",
        created_at=BASE + timedelta(days=30),
    )
    db = _FakeDb(docs)

    eviction = kg_db.enforce_knowledge_graph_caps(UID, db_client=db)

    assert eviction["edges_evicted"] == 1
    assert f"users/{UID}/knowledge_edges/zzz-excess" not in db.docs
    remaining_edges = [path for path in db.docs if path.startswith(f"users/{UID}/knowledge_edges/")]
    assert len(remaining_edges) == kg_db.MAX_KNOWLEDGE_GRAPH_EDGES
    assert f"users/{UID}/knowledge_edges/edge-0000" in db.docs


def test_sync_route_delegates_to_merge(monkeypatch):
    captured: dict[str, Any] = {}

    def fake_merge(uid, table, rows, *, db_client=None):
        captured["uid"] = uid
        captured["table"] = table
        captured["rows"] = rows
        captured["db_client"] = db_client
        return {
            "table": table,
            "merged": len(rows),
            "skipped": 0,
            "nodes_evicted": 0,
            "edges_evicted": 0,
        }

    monkeypatch.setattr(kg_router.kg_db, "merge_synced_local_kg", fake_merge)
    monkeypatch.setattr(kg_router, "firestore_db", object())
    monkeypatch.setattr(kg_router, "_require_legacy_graph_mutation", lambda _uid: None)

    rows = [{"nodeId": "n1", "label": "Test"}]
    response = kg_router.sync_local_knowledge_graph(
        payload=kg_router.LocalKgSyncRequest(table="local_kg_nodes", rows=rows),
        uid=UID,
    )

    assert captured == {"uid": UID, "table": "local_kg_nodes", "rows": rows, "db_client": kg_router.firestore_db}
    assert response.merged == 1
    assert response.table == "local_kg_nodes"


def test_invalid_local_kg_rows_are_skipped():
    db = _FakeDb()
    result = kg_db.merge_synced_local_kg_nodes(
        UID,
        [{"nodeId": "", "label": "Bad"}, {"label": "Missing id"}, "not-a-row"],
        db_client=db,
    )
    assert result["merged"] == 0
    assert result["skipped"] == 3
    assert db.docs == {}


def test_merge_preserves_stable_node_id_despite_label_collision():
    db = _FakeDb(
        {
            f"users/{UID}/knowledge_nodes/existing-omi": _node_doc(
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
    kg_db.merge_synced_local_kg_nodes(UID, [row], db_client=db)

    assert f"users/{UID}/knowledge_nodes/local-omi" in db.docs
    assert db.docs[f"users/{UID}/knowledge_nodes/local-omi"]["id"] == "local-omi"
    assert f"users/{UID}/knowledge_nodes/existing-omi" in db.docs

    edge_row = {
        "edgeId": "edge-local",
        "sourceNodeId": "local-omi",
        "targetNodeId": "existing-omi",
        "label": "related_to",
        "createdAt": "2026-07-01T12:00:00Z",
    }
    result = kg_db.merge_synced_local_kg_edges(UID, [edge_row], db_client=db)
    assert result["merged"] == 1
    assert result["edges_evicted"] == 0
    assert f"users/{UID}/knowledge_edges/edge-local" in db.docs


def test_merge_evicts_by_document_name_not_timestamp():
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
    kg_db.merge_synced_local_kg_nodes(UID, keep_rows, db_client=db)
    kg_db.merge_synced_local_kg_nodes(
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
        db_client=db,
    )

    assert f"users/{UID}/knowledge_nodes/zzz-excess" not in db.docs
    assert f"users/{UID}/knowledge_nodes/keep-000" in db.docs
    keep = db.docs[f"users/{UID}/knowledge_nodes/keep-000"]
    assert keep["updated_at"] == datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)
    assert keep["created_at"] == datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)


def test_merge_fails_edges_when_endpoints_missing():
    db = _FakeDb(
        {
            f"users/{UID}/knowledge_nodes/node-a": _node_doc("node-a", label="A", updated_at=BASE),
        }
    )
    row = {
        "edgeId": "edge-missing-target",
        "sourceNodeId": "node-a",
        "targetNodeId": "node-missing",
        "label": "related_to",
        "createdAt": "2026-07-01T12:00:00Z",
    }
    with pytest.raises(kg_db.MissingKnowledgeGraphEndpointsError):
        kg_db.merge_synced_local_kg_edges(UID, [row], db_client=db)
    assert f"users/{UID}/knowledge_edges/edge-missing-target" not in db.docs


def test_sync_route_returns_422_when_edge_endpoints_missing(monkeypatch):
    monkeypatch.setattr(kg_router, "_require_legacy_graph_mutation", lambda _uid: None)

    def fake_merge(uid, table, rows, *, db_client=None):
        raise kg_db.MissingKnowledgeGraphEndpointsError("1 local_kg edge(s) reference missing endpoint nodes")

    monkeypatch.setattr(kg_router.kg_db, "merge_synced_local_kg", fake_merge)
    with pytest.raises(kg_router.HTTPException) as error:
        kg_router.sync_local_knowledge_graph(
            payload=kg_router.LocalKgSyncRequest(
                table="local_kg_edges",
                rows=[{"edgeId": "e1", "sourceNodeId": "a", "targetNodeId": "b", "label": "related_to"}],
            ),
            uid=UID,
        )
    assert error.value.status_code == 422


def test_merge_keeps_fresher_cloud_updated_at():
    newer = BASE + timedelta(days=2)
    older = BASE
    db = _FakeDb(
        {
            f"users/{UID}/knowledge_nodes/node-a": _node_doc("node-a", label="Omi", updated_at=newer),
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
    kg_db.merge_synced_local_kg_nodes(UID, [row], db_client=db)
    stored = db.docs[f"users/{UID}/knowledge_nodes/node-a"]
    assert stored["updated_at"] == newer
    assert sorted(stored["aliases"]) == ["Based Hardware"]
