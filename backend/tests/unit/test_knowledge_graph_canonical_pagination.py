from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from database import document_store
from database import knowledge_graph as kg_db
from database.memory_collections import MemoryCollections
from models.memory_promotion import PromotionGraphPlan, build_memory_graph_assertion
from routers import knowledge_graph as kg_router
from tests.store_fakes import FakeDocumentStore
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


_STATE_HEAD = {
    "schema_version": 1,
    "uid": UID,
    "source": "memory_state_head",
    "account_generation": 4,
    "head_commit_id": "head-4",
    "commit_sequence": 999,
}


class _RecordingStore(FakeDocumentStore):
    """Neutral store fake recording the canonical-graph access the tests assert on: page limits,
    per-page item ids, and assertion batch sizes grouped by the query page that requested them."""

    def __init__(self, backing):
        super().__init__(backing=backing)
        self.query_limits: list[int] = []
        self.query_snapshot_ids: list[list[str]] = []
        self.assertion_batch_sizes: list[int] = []
        self.assertion_ref_pages: list[list[str]] = []

    def query(self, collection, **kwargs):
        result = super().query(collection, **kwargs)
        if kwargs.get("limit") is not None:
            self.query_limits.append(kwargs["limit"])
            self.query_snapshot_ids.append([doc.id for doc in result])
            self.assertion_ref_pages.append([])
        return result

    def get_many(self, collection, ids):
        ids = list(ids)
        self.assertion_batch_sizes.append(len(ids))
        if self.assertion_ref_pages:
            self.assertion_ref_pages[-1].extend(ids)
        return super().get_many(collection, ids)

    @property
    def state(self) -> dict:
        """The seeded memory-state-head doc; mutating it in place changes the read revision."""
        return self._docs[MemoryCollections(uid=UID).memory_state_head]


_STORE_HOLDER: dict = {}


@pytest.fixture(autouse=True)
def _route_canonical_store(monkeypatch):
    # canonical_graph queries + the v3 revision source read through the document_store facade;
    # the fenced-assertion loader reads through database.knowledge_graph's own store seam. Route
    # both to the per-test recording fake that _fake_db_for installs.
    monkeypatch.setattr(document_store, "_store", lambda: _STORE_HOLDER["store"])
    monkeypatch.setattr(kg_db, "_store", lambda: _STORE_HOLDER["store"])


def _fake_db_for(rows):
    backing: dict = {MemoryCollections(uid=UID).memory_state_head: dict(_STATE_HEAD)}
    items_collection = MemoryCollections(uid=UID).memory_items
    assertions_collection = f"users/{UID}/memory_graph_assertions"
    for item_snapshot, assertion_payload in rows:
        backing[f"{items_collection}/{item_snapshot.id}"] = item_snapshot.to_dict()
        # assertion_payload is None for an unlinked canonical memory (item only, no graph assertion).
        if assertion_payload is not None:
            backing[f"{assertions_collection}/{assertion_payload['memory_id']}"] = assertion_payload
    store = _RecordingStore(backing)
    _STORE_HOLDER["store"] = store
    return store


def _page_memory_ids(payload) -> set[str]:
    return {
        memory_id for record in [*payload.nodes, *payload.edges] for memory_id in record.get("memory_ids", [])
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
            limit=500,
            cursor=cursor,
        )
        pages.append(page)
        if not page.has_more:
            assert page.next_cursor is None
            break
        cursor = page.next_cursor
        assert isinstance(cursor, str)

    seen = set().union(*(_page_memory_ids(page) for page in pages))
    assert seen == {f"mem-{index:04d}" for index in range(650)}
    assert len(pages) == 2
    # Port-level observable: each window queries limit+1 and pages don't overlap or omit items.
    # (Assertion-fetch batch sizes are an adapter concern — covered by the dual-backend contract.)
    assert db.query_limits == [501, 501]
    assert all(len(snapshot_ids) <= 501 for snapshot_ids in db.query_snapshot_ids)
    consumed_windows = [set(snapshot_ids[:500]) for snapshot_ids in db.query_snapshot_ids]
    assert consumed_windows[0].isdisjoint(consumed_windows[1])
    assert set().union(*consumed_windows) == {f"mem-{index:04d}" for index in range(650)}


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
        limit=10,
    )

    assert _page_memory_ids(page) == {"valid"}
    assert page.has_more is False
    assert page.next_cursor is None


def test_canonical_graph_includes_unlinked_canonical_memory_as_an_atlas_node(monkeypatch):
    # Atlas product change (#11081): a durable canonical memory with no graph assertion (graph_ready
    # False, unlinked) is still surfaced as an isolated catalog node. Exercised on the neutral store
    # seam — the item is seeded without an assertion (row second element None).
    monkeypatch.setenv("MEMORY_V3_CURSOR_SECRET", "canonical-graph-test-secret")
    item, _assertion = _assertion_and_item("unlinked", 1, graph_ready=False)
    item._payload["content"] = "A durable canonical memory that has no inferred relationship yet."
    _fake_db_for([(item, None)])

    page = kg.get_canonical_knowledge_graph(UID, limit=10)

    assert page.edges == []
    assert page.nodes == [
        {
            "id": "memory:unlinked",
            "label": "A durable canonical memory that has no inferred relationship yet.",
            "node_type": "concept",
            "aliases": [],
            "memory_ids": ["unlinked"],
            "created_at": NOW,
            "updated_at": NOW,
        }
    ]


def test_assertion_loader_rechecks_account_generation_before_fetch():
    # Kept from upstream, re-expressed on the neutral seam (the loader reads through kg_db._store(),
    # which the autouse _route_canonical_store fixture routes; the port dropped the db_client arg).
    # Same recheck as test_load_fenced_assertions_excludes_wrong_account_generation, exercised via the
    # canonical-graph fixtures.
    stale_item, stale_assertion = _assertion_and_item("stale-generation", 1, account_generation=3)
    _fake_db_for([(stale_item, stale_assertion)])

    loaded = kg_db.load_fenced_assertions_for_memory_items(
        UID,
        ["stale-generation"],
        account_generation=4,
    )

    assert loaded == []


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
    # An item present in the query window but with no matching assertion must be dropped.
    db.set(f"{MemoryCollections(uid=UID).memory_items}/{missing_item.id}", missing_item.to_dict())

    page = kg.get_canonical_knowledge_graph(UID, limit=2)

    # Hardened behaviour: an underfilled window (stale + assertion-less items dropped) advances within
    # the same read rather than returning an empty page, so `valid` surfaces on the first page.
    assert _page_memory_ids(page) == {"valid"}
    assert page.has_more is False
    assert page.next_cursor is None
    assert db.query_snapshot_ids[0] == ["stale", "missing", "valid"]


def test_invalid_consumed_cursor_boundary_fails_closed(monkeypatch):
    monkeypatch.setenv("MEMORY_V3_CURSOR_SECRET", "canonical-graph-test-secret")
    malformed_row = _assertion_and_item("z-malformed", 2, updated_at=NOW.replace(minute=2))
    malformed_row[0].id = "different-document-id"
    valid_row = _assertion_and_item("a-valid", 1, updated_at=NOW.replace(minute=1))
    db = _fake_db_for([malformed_row, valid_row])

    page = kg.get_canonical_knowledge_graph(UID, limit=1)

    assert _page_memory_ids(page) == {"a-valid"}
    with pytest.raises(kg.CanonicalGraphReadUnavailable, match="malformed_cursor_boundary"):
        kg._canonical_graph_cursor_boundary_from_snapshot(malformed_row[0])


def test_canonical_graph_rejects_tampered_and_stale_cursors(monkeypatch):
    monkeypatch.setenv("MEMORY_V3_CURSOR_SECRET", "canonical-graph-test-secret")
    rows = [_assertion_and_item(f"mem-{index}", index + 1) for index in range(3)]
    db = _fake_db_for(rows)
    first = kg.get_canonical_knowledge_graph(UID, limit=1)
    cursor = first.next_cursor
    assert cursor
    with pytest.raises(kg.CanonicalGraphCursorError):
        kg.get_canonical_knowledge_graph(UID, limit=1, cursor=f"{cursor}x")

    db.state["commit_sequence"] += 1
    with pytest.raises(kg.CanonicalGraphCursorError):
        kg.get_canonical_knowledge_graph(UID, limit=1, cursor=cursor)


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
    monkeypatch.setattr(
        kg_router.canonical_graph_service,
        "get_canonical_knowledge_graph",
        lambda *_args, **_kwargs: SimpleNamespace(**canonical_payload),
    )
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
        kg_router.canonical_graph_service,
        "get_canonical_knowledge_graph",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(kg.CanonicalGraphCursorError("invalid_signature")),
    )
    app = FastAPI()
    app.include_router(kg_router.router)
    app.dependency_overrides[kg_router.auth.get_current_user_uid] = lambda: UID

    response = TestClient(app).get("/v1/knowledge-graph/canonical?cursor=bad")

    assert response.status_code == 400
    assert response.json()["detail"] == "invalid_or_stale_cursor"


def test_canonical_route_maps_read_unavailable_to_503(monkeypatch):
    monkeypatch.setattr(
        kg_router.canonical_graph_service,
        "get_canonical_knowledge_graph",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            kg.CanonicalGraphReadUnavailable("malformed_memory_state_head")
        ),
    )
    app = FastAPI()
    app.include_router(kg_router.router)
    app.dependency_overrides[kg_router.auth.get_current_user_uid] = lambda: UID

    response = TestClient(app).get("/v1/knowledge-graph/canonical")

    assert response.status_code == 503
    assert response.json()["detail"] == "canonical_graph_unavailable"


def test_canonical_graph_retries_once_when_revision_changes_during_read(monkeypatch):
    monkeypatch.setenv("MEMORY_V3_CURSOR_SECRET", "canonical-graph-test-secret")
    valid_row = _assertion_and_item("valid", 1)
    db = _fake_db_for([valid_row])
    original_read = kg._read_canonical_graph_revision
    revision_reads = 0

    def flaky_read(uid: str):
        nonlocal revision_reads
        revision_reads += 1
        revision = original_read(uid)
        if revision_reads == 2:
            return kg._CanonicalGraphRevision(
                account_generation=revision.account_generation,
                commit_sequence=revision.commit_sequence + 1,
                head_commit_id="head-changed",
            )
        return revision

    monkeypatch.setattr(kg, "_read_canonical_graph_revision", flaky_read)

    page = kg.get_canonical_knowledge_graph(UID, limit=10)

    assert _page_memory_ids(page) == {"valid"}
    assert revision_reads == 4


def test_canonical_graph_fails_after_bounded_revision_retry_exhausted(monkeypatch):
    monkeypatch.setenv("MEMORY_V3_CURSOR_SECRET", "canonical-graph-test-secret")
    valid_row = _assertion_and_item("valid", 1)
    db = _fake_db_for([valid_row])
    original_read = kg._read_canonical_graph_revision
    revision_reads = 0

    def always_changing_ending_read(uid: str):
        nonlocal revision_reads
        revision_reads += 1
        revision = original_read(uid)
        if revision_reads % 2 == 0:
            return kg._CanonicalGraphRevision(
                account_generation=revision.account_generation,
                commit_sequence=revision.commit_sequence + revision_reads,
                head_commit_id=f"head-{revision_reads}",
            )
        return revision

    monkeypatch.setattr(kg, "_read_canonical_graph_revision", always_changing_ending_read)

    with pytest.raises(kg.CanonicalGraphReadUnavailable, match="canonical_revision_changed_during_read"):
        kg.get_canonical_knowledge_graph(UID, limit=10)

    assert revision_reads == 4
