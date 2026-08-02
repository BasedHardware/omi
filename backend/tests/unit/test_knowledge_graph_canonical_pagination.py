from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from database.memory_collections import MemoryCollections
from models.memory_promotion import PromotionGraphPlan, build_memory_graph_assertion
from routers import knowledge_graph as kg_router
from utils.memory import canonical_graph as kg

UID = "uid-canonical-graph"
NOW = datetime(2026, 8, 2, 12, 0, tzinfo=timezone.utc)


class _Snapshot:
    def __init__(self, doc_id: str, payload: dict, *, exists: bool = True):
        self.id = doc_id
        self._payload = dict(payload)
        self.exists = exists

    def to_dict(self):
        return dict(self._payload)


class _DocumentRef:
    def __init__(self, doc_id: str):
        self.id = doc_id


class _Query:
    def __init__(self, db: "_FakeDB", docs: list[_Snapshot]):
        self.db = db
        self.docs = docs
        self.filters = []
        self.boundary = None
        self.limit_value = None

    def where(self, *args, **kwargs):
        filt = kwargs.get("filter") or (args[0] if args else None)
        self.filters.append(filt)
        return self

    def order_by(self, *_args, **_kwargs):
        return self

    def start_after(self, boundary):
        self.boundary = boundary
        return self

    def limit(self, value: int):
        self.limit_value = value
        self.db.query_limits.append(value)
        return self

    def stream(self):
        docs = list(self.docs)
        for filt in self.filters:
            field = getattr(filt, "field_path", None)
            value = getattr(filt, "value", None)
            if field is not None:
                docs = [doc for doc in docs if doc.to_dict().get(field) == value]
        docs.sort(
            key=lambda doc: (doc.to_dict()["updated_at"], doc.to_dict()["memory_id"]),
            reverse=True,
        )
        if self.boundary is not None:
            boundary_time = self.boundary["updated_at"]
            boundary_ref = self.boundary["__name__"]
            assert isinstance(boundary_ref, _DocumentRef)
            boundary_id = boundary_ref.id
            docs = [
                doc
                for doc in docs
                if (doc.to_dict()["updated_at"], doc.to_dict()["memory_id"]) < (boundary_time, boundary_id)
            ]
        if self.limit_value is not None:
            docs = docs[: self.limit_value]
        self.db.query_snapshot_ids.append([doc.id for doc in docs])
        return iter(docs)


class _AssertionCollection:
    def document(self, memory_id: str):
        return _DocumentRef(memory_id)


class _UserRef:
    def __init__(self, db: "_FakeDB"):
        self.db = db

    def collection(self, name: str):
        assert name == "memory_graph_assertions"
        return _AssertionCollection()


class _UsersCollection:
    def __init__(self, db: "_FakeDB"):
        self.db = db

    def document(self, uid: str):
        assert uid == UID
        return _UserRef(self.db)


class _ItemsCollection(_Query):
    def __init__(self, db: "_FakeDB"):
        super().__init__(db, db.items)

    def document(self, memory_id: str):
        return _DocumentRef(memory_id)


class _FakeDB:
    def __init__(self, items: list[_Snapshot], assertions: dict[str, dict]):
        self.items = items
        self.assertions = assertions
        self.query_limits: list[int] = []
        self.query_snapshot_ids: list[list[str]] = []
        self.assertion_batch_sizes: list[int] = []
        self.assertion_ref_pages: list[list[str]] = []
        self.state = {
            "schema_version": 1,
            "uid": UID,
            "source": "memory_state_head",
            "account_generation": 4,
            "head_commit_id": "head-4",
            "commit_sequence": 999,
        }

    def collection(self, path: str):
        if path == "users":
            return _UsersCollection(self)
        assert path == MemoryCollections(uid=UID).memory_items
        return _ItemsCollection(self)

    def document(self, path: str):
        assert path == f"users/{UID}/memory_state/head"
        return SimpleNamespace(get=lambda: _Snapshot("head", self.state))

    def get_all(self, refs):
        refs = list(refs)
        self.assertion_batch_sizes.append(len(refs))
        page_index = len(self.query_snapshot_ids) - 1
        while len(self.assertion_ref_pages) <= page_index:
            self.assertion_ref_pages.append([])
        self.assertion_ref_pages[page_index].extend(ref.id for ref in refs)
        return [_Snapshot(ref.id, self.assertions[ref.id]) for ref in refs if ref.id in self.assertions]


def _assertion_and_item(
    memory_id: str,
    sequence: int,
    *,
    updated_at: datetime = NOW,
    sensitivity_labels: list[str] | None = None,
    status: str = "active",
    graph_ready: bool = True,
    assertion_content_hash: str | None = None,
    account_generation: int = 4,
):
    plan = PromotionGraphPlan(
        subject_entity_id=f"subject-{memory_id}",
        predicate="knows",
        arguments={"object": {"entity_id": f"object-{memory_id}"}},
    )
    content_hash = assertion_content_hash or f"hash-{memory_id}"
    evidence_id = f"evidence-{memory_id}"
    assertion = build_memory_graph_assertion(
        uid=UID,
        memory_id=memory_id,
        item_revision=1,
        content_hash=content_hash,
        evidence_ids=[evidence_id],
        graph_plan=plan,
        commit_id=f"commit-{sequence}",
        commit_sequence=max(sequence, 1),
        created_at=updated_at,
    )
    item = {
        "uid": UID,
        "memory_id": memory_id,
        "account_generation": account_generation,
        "status": status,
        "tier": "long_term",
        "processing_state": "processed",
        "source_state": "active",
        "graph_ready": graph_ready,
        "graph_assertion_id": assertion.assertion_id,
        "graph_plan_hash": assertion.graph_plan_hash,
        "item_revision": 1,
        "content_hash": content_hash,
        "ledger_commit_id": assertion.commit_id,
        "ledger_sequence": assertion.commit_sequence,
        "subject_entity_id": assertion.subject_entity_id,
        "predicate": assertion.predicate,
        "arguments": assertion.arguments,
        "evidence": [{"evidence_id": evidence_id}],
        "sensitivity_labels": sensitivity_labels or [],
        "promotion": {"user_review": True},
        "updated_at": updated_at,
    }
    return _Snapshot(memory_id, item), assertion.model_dump(mode="python")


def _fake_db_for(rows):
    items, assertions = zip(*rows) if rows else ([], [])
    return _FakeDB(list(items), {payload["memory_id"]: payload for payload in assertions})


def _page_memory_ids(payload: dict) -> set[str]:
    return {
        memory_id for record in [*payload["nodes"], *payload["edges"]] for memory_id in record.get("memory_ids", [])
    }


def test_canonical_graph_pages_more_than_500_tied_items_without_omissions(monkeypatch):
    monkeypatch.setenv("MEMORY_V3_CURSOR_SECRET", "canonical-graph-test-secret")
    rows = [_assertion_and_item(f"mem-{index:04d}", index + 1) for index in range(650)]
    db = _fake_db_for(rows)

    pages = []
    cursor = None
    while True:
        page = kg.get_canonical_knowledge_graph(
            UID,
            db_client=db,
            limit=500,
            cursor=cursor,
        )
        pages.append(page)
        if not page["has_more"]:
            assert page["next_cursor"] is None
            break
        cursor = page["next_cursor"]
        assert isinstance(cursor, str)

    seen = set().union(*(_page_memory_ids(page) for page in pages))
    assert seen == {f"mem-{index:04d}" for index in range(650)}
    assert len(pages) == 2
    assert db.query_limits == [501, 501]
    assert all(len(snapshot_ids) <= 501 for snapshot_ids in db.query_snapshot_ids)
    consumed_windows = [set(snapshot_ids[:500]) for snapshot_ids in db.query_snapshot_ids]
    assert consumed_windows[0].isdisjoint(consumed_windows[1])
    assert set().union(*consumed_windows) == {f"mem-{index:04d}" for index in range(650)}
    assert all(len(refs) <= 500 for refs in db.assertion_ref_pages)
    assert [len(refs) for refs in db.assertion_ref_pages] == [500, 150]
    assert max(db.assertion_batch_sizes) <= kg.CANONICAL_GRAPH_ASSERTION_BATCH_SIZE
    assertion_ref_ids = [memory_id for page in db.assertion_ref_pages for memory_id in page]
    assert len(assertion_ref_ids) == len(set(assertion_ref_ids)) == 650


def test_canonical_graph_filters_stale_ineligible_and_restricted_assertions(monkeypatch):
    monkeypatch.setenv("MEMORY_V3_CURSOR_SECRET", "canonical-graph-test-secret")
    valid_row = _assertion_and_item("valid", 1, updated_at=NOW.replace(minute=1))
    restricted_row = _assertion_and_item(
        "restricted",
        2,
        updated_at=NOW.replace(minute=4),
        sensitivity_labels=["financial"],
    )
    stale_item, stale_assertion = _assertion_and_item("stale", 3, updated_at=NOW.replace(minute=3))
    stale_item._payload["content_hash"] = "different-item-version"
    stale_generation_row = _assertion_and_item(
        "stale-generation",
        5,
        updated_at=NOW.replace(minute=5),
        account_generation=3,
    )
    ineligible_row = _assertion_and_item(
        "ineligible",
        4,
        updated_at=NOW.replace(minute=2),
        status="superseded",
    )
    db = _fake_db_for([stale_generation_row, restricted_row, (stale_item, stale_assertion), ineligible_row, valid_row])

    page = kg.get_canonical_knowledge_graph(
        UID,
        db_client=db,
        limit=10,
    )

    assert _page_memory_ids(page) == {"valid"}
    assert page["has_more"] is False
    assert page["next_cursor"] is None
    assert "stale-generation" not in {memory_id for refs in db.assertion_ref_pages for memory_id in refs}


def test_assertion_loader_rechecks_account_generation_before_fetch():
    stale_item, stale_assertion = _assertion_and_item("stale-generation", 1, account_generation=3)
    db = _fake_db_for([(stale_item, stale_assertion)])

    accepted = kg._load_assertions_for_canonical_graph_items(
        UID,
        [stale_item.to_dict()],
        db_client=db,
        account_generation=4,
    )

    assert accepted == []
    assert db.assertion_batch_sizes == []


def test_underfilled_empty_item_window_advances_without_overlap(monkeypatch):
    monkeypatch.setenv("MEMORY_V3_CURSOR_SECRET", "canonical-graph-test-secret")
    stale_item, stale_assertion = _assertion_and_item(
        "stale",
        3,
        updated_at=NOW.replace(minute=3),
    )
    stale_item._payload["content_hash"] = "different-item-version"
    missing_item, _missing_assertion = _assertion_and_item(
        "missing",
        2,
        updated_at=NOW.replace(minute=2),
    )
    valid_row = _assertion_and_item("valid", 1, updated_at=NOW.replace(minute=1))
    db = _fake_db_for([(stale_item, stale_assertion), valid_row])
    db.items.append(missing_item)

    first = kg.get_canonical_knowledge_graph(UID, db_client=db, limit=2)
    second = kg.get_canonical_knowledge_graph(
        UID,
        db_client=db,
        limit=2,
        cursor=first["next_cursor"],
    )

    assert _page_memory_ids(first) == set()
    assert first["has_more"] is True
    assert isinstance(first["next_cursor"], str)
    assert _page_memory_ids(second) == {"valid"}
    assert second["has_more"] is False
    assert second["next_cursor"] is None
    first_consumed = set(db.query_snapshot_ids[0][:2])
    second_consumed = set(db.query_snapshot_ids[1][:2])
    assert first_consumed == {"stale", "missing"}
    assert second_consumed == {"valid"}
    assert first_consumed.isdisjoint(second_consumed)


def test_invalid_consumed_cursor_boundary_fails_closed(monkeypatch):
    monkeypatch.setenv("MEMORY_V3_CURSOR_SECRET", "canonical-graph-test-secret")
    malformed_row = _assertion_and_item("z-malformed", 2, updated_at=NOW.replace(minute=2))
    malformed_row[0].id = "different-document-id"
    valid_row = _assertion_and_item("a-valid", 1, updated_at=NOW.replace(minute=1))
    db = _fake_db_for([malformed_row, valid_row])

    with pytest.raises(kg.CanonicalGraphReadUnavailable, match="malformed_cursor_boundary"):
        kg.get_canonical_knowledge_graph(UID, db_client=db, limit=1)


def test_canonical_graph_rejects_tampered_and_stale_cursors(monkeypatch):
    monkeypatch.setenv("MEMORY_V3_CURSOR_SECRET", "canonical-graph-test-secret")
    rows = [_assertion_and_item(f"mem-{index}", index + 1) for index in range(3)]
    db = _fake_db_for(rows)
    first = kg.get_canonical_knowledge_graph(UID, db_client=db, limit=1)
    cursor = first["next_cursor"]
    assert cursor
    with pytest.raises(kg.CanonicalGraphCursorError):
        kg.get_canonical_knowledge_graph(UID, db_client=db, limit=1, cursor=f"{cursor}x")

    db.state["commit_sequence"] += 1
    with pytest.raises(kg.CanonicalGraphCursorError):
        kg.get_canonical_knowledge_graph(UID, db_client=db, limit=1, cursor=cursor)


def test_canonical_route_is_additive_and_legacy_route_response_is_unchanged(monkeypatch):
    legacy_payload = {
        "nodes": [{"id": "legacy-node"}],
        "edges": [],
        "truncated": True,
        "node_count": 1,
        "edge_count": 0,
        "node_limit": 500,
        "edge_limit": 1000,
    }
    canonical_payload = {
        "nodes": [{"id": "canonical-node"}],
        "edges": [],
        "has_more": True,
        "next_cursor": "v3.opaque.signed",
    }
    monkeypatch.setattr(kg_router, "get_knowledge_graph_payload", lambda _uid: legacy_payload)
    monkeypatch.setattr(kg_router, "get_canonical_knowledge_graph_payload", lambda *_args, **_kwargs: canonical_payload)
    app = FastAPI()
    app.include_router(kg_router.router)
    app.dependency_overrides[kg_router.auth.get_current_user_uid] = lambda: UID
    client = TestClient(app)

    legacy_response = client.get("/v1/knowledge-graph")
    canonical_response = client.get("/v1/knowledge-graph/canonical?limit=200")

    assert legacy_response.status_code == 200
    assert legacy_response.json() == legacy_payload
    assert canonical_response.status_code == 200
    assert canonical_response.json() == canonical_payload


def test_canonical_route_fails_closed_for_invalid_cursor(monkeypatch):
    monkeypatch.setattr(
        kg_router,
        "get_canonical_knowledge_graph_payload",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(kg.CanonicalGraphCursorError("invalid_signature")),
    )
    app = FastAPI()
    app.include_router(kg_router.router)
    app.dependency_overrides[kg_router.auth.get_current_user_uid] = lambda: UID

    response = TestClient(app).get("/v1/knowledge-graph/canonical?cursor=bad")

    assert response.status_code == 400
    assert response.json()["detail"] == "invalid_or_stale_cursor"
