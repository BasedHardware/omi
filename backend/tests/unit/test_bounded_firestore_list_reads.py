"""Bounded list reads for prod GET 504s (action-items / memories / KG).

Regression coverage for Closes #10746: list paths must not full-collection stream.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from tests.store_fakes import FakeDocumentStore


def _item(
    id: str,
    *,
    completed: bool = False,
    deleted: bool = False,
    due_at: Optional[datetime] = None,
    created_at: Optional[datetime] = None,
) -> Dict[str, Any]:
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return {
        'id': id,
        'description': id,
        'completed': completed,
        'status': 'completed' if completed else 'active',
        'deleted': deleted,
        'due_at': due_at,
        'created_at': created_at or now,
        'owner': 'user',
        'source': 'test',
        'provenance': [],
        'sort_order': 0,
        'indent_level': 0,
    }


def _seed(store: FakeDocumentStore, uid: str, items) -> None:
    for item in items:
        store._docs[f'users/{uid}/action_items/{item["id"]}'] = {k: v for k, v in item.items() if k != 'id'}


@pytest.fixture
def ai_mod(monkeypatch):
    import database.action_items as ai
    import database.firestore_read_metrics as metrics

    recorded = []

    def _record(family, mode, documents):
        recorded.append((family, mode, documents))

    monkeypatch.setattr(ai, 'record_firestore_read', _record)
    return ai, recorded, metrics


def _bind_store(ai, monkeypatch) -> FakeDocumentStore:
    store = FakeDocumentStore()
    monkeypatch.setattr(ai, '_store', lambda: store)
    return store


def test_get_action_items_active_first_without_full_scan(ai_mod, monkeypatch):
    ai, recorded, metrics = ai_mod
    store = _bind_store(ai, monkeypatch)
    # Many completed docs first in storage order; actives must still lead the page.
    items = []
    for i in range(300):
        items.append(_item(f'c{i}', completed=True, created_at=datetime(2026, 1, 2, tzinfo=timezone.utc)))
    for i in range(5):
        items.append(_item(f'a{i}', completed=False, created_at=datetime(2026, 1, 3, tzinfo=timezone.utc)))
    _seed(store, 'uid', items)

    page = ai.get_action_items('uid', limit=10, offset=0)
    assert [x['id'] for x in page[:5]] == ['a0', 'a1', 'a2', 'a3', 'a4']
    assert all(not x['completed'] for x in page[:5])
    # Completed only after actives fill
    assert all(x['completed'] for x in page[5:])
    assert recorded
    assert recorded[0][1] == metrics.FirestoreReadMode.BOUNDED
    # Must not stream the entire 305-doc collection for a 10-row page
    assert recorded[0][2] < 400  # two-bucket + legacy harvest, still << full 305+ stream


def test_get_action_items_hard_caps_document_iteration(ai_mod, monkeypatch):
    ai, recorded, metrics = ai_mod
    store = _bind_store(ai, monkeypatch)
    _seed(store, 'uid', [_item(f'x{i}', completed=False) for i in range(5000)])

    page = ai.get_action_items('uid', limit=50, offset=0)
    assert len(page) == 50
    assert recorded[0][1] == metrics.FirestoreReadMode.BOUNDED
    assert recorded[0][2] <= ai._ACTION_ITEMS_LIST_HARD_MAX


def test_get_action_items_skips_deleted_in_active_bucket(ai_mod, monkeypatch):
    ai, recorded, metrics = ai_mod
    store = _bind_store(ai, monkeypatch)
    _seed(
        store,
        'uid',
        [
            _item('del1', completed=False, deleted=True),
            _item('a1', completed=False),
            _item('c1', completed=True),
        ],
    )
    page = ai.get_action_items('uid', limit=10, offset=0)
    ids = [x['id'] for x in page]
    assert 'del1' not in ids
    assert ids[0] == 'a1'


def test_knowledge_graph_get_is_bounded(monkeypatch):
    import database.knowledge_graph as kg
    from tests.store_fakes import FakeDocumentStore

    # Small caps make the bounded-scan behavior independent of the production constants.
    monkeypatch.setattr(kg, 'MAX_KNOWLEDGE_GRAPH_NODES', 2)
    monkeypatch.setattr(kg, 'MAX_KNOWLEDGE_GRAPH_EDGES', 3)
    monkeypatch.setattr(kg, 'MAX_KNOWLEDGE_GRAPH_ASSERTIONS', 4)

    captured: dict = {}

    class _RecordingStore(FakeDocumentStore):
        def query(self, collection, **kwargs):
            captured[collection.rsplit('/', 1)[-1]] = kwargs.get('limit')
            return super().query(collection, **kwargs)

    fake = _RecordingStore()
    # More nodes than the cap so the reader must bound the scan and mark the graph truncated.
    for node_id in ('a', 'b', 'c'):
        fake._docs[f'users/uid/knowledge_nodes/{node_id}'] = {'id': node_id, 'label': f'L{node_id}'}
    # Distinct-key edges whose endpoints stay inside the bounded node page, so referential
    # closure keeps them and the edge page fills to the cap.
    fake._docs['users/uid/knowledge_edges/e0'] = {'id': 'e0', 'source_id': 'a', 'target_id': 'b', 'label': 'r0'}
    fake._docs['users/uid/knowledge_edges/e1'] = {'id': 'e1', 'source_id': 'a', 'target_id': 'b', 'label': 'r1'}
    fake._docs['users/uid/knowledge_edges/e2'] = {'id': 'e2', 'source_id': 'b', 'target_id': 'a', 'label': 'r0'}
    monkeypatch.setattr(kg, '_store', lambda: fake)

    graph = kg.get_knowledge_graph('uid')
    assert len(graph['nodes']) == kg.MAX_KNOWLEDGE_GRAPH_NODES
    assert len(graph['edges']) == kg.MAX_KNOWLEDGE_GRAPH_EDGES
    assert graph['truncated'] is True
    # The reader fetches exactly one past each cap to detect truncation without a count().
    assert captured['knowledge_nodes'] == kg.MAX_KNOWLEDGE_GRAPH_NODES + 1
    assert captured['knowledge_edges'] == kg.MAX_KNOWLEDGE_GRAPH_EDGES + 1
    assert captured['memory_graph_assertions'] == kg.MAX_KNOWLEDGE_GRAPH_ASSERTIONS + 1


@pytest.mark.parametrize(
    ('node_total', 'edge_total', 'expected_nodes', 'expected_edges', 'expected_truncated'),
    (
        (0, 0, 0, 0, False),
        (3, 2, 3, 2, False),
        (20_000, 20_000, 500, 1000, True),
    ),
)
def test_knowledge_graph_get_is_deterministic_and_bounded_for_large_fixtures(
    monkeypatch,
    node_total,
    edge_total,
    expected_nodes,
    expected_edges,
    expected_truncated,
):
    import database.knowledge_graph as kg
    from tests.store_fakes import FakeDocumentStore

    # Migrated to the neutral storage port: the module now orders reads by document name
    # (`_store().query(coll, order_by='__name__', limit=...)`) instead of a Firestore
    # `.order_by(...).stream()` chain, and the FakeDocumentStore honors '__name__' as
    # document-id order. Seeding N docs and asserting the bounded page + truncated flag against
    # the store's ordered result is the behavioral equivalent of the retired stream-count and
    # order_by-field assertions.
    captured: dict = {}

    class _RecordingStore(FakeDocumentStore):
        def query(self, collection, **kwargs):
            captured[collection.rsplit('/', 1)[-1]] = kwargs.get('limit')
            return super().query(collection, **kwargs)

    fake = _RecordingStore()
    # Deterministic document-id order ('n0','n1',...) keeps the two edge endpoints ('n0','n1')
    # inside the bounded node page so referential closure fills the edge page to the cap.
    for i in range(node_total):
        fake._docs[f'users/uid/knowledge_nodes/n{i}'] = {'id': f'n{i}', 'label': f'L{i}'}
    for i in range(edge_total):
        fake._docs[f'users/uid/knowledge_edges/e{i}'] = {
            'id': f'e{i}',
            'source_id': 'n0',
            'target_id': 'n1',
            'label': f'L{i}',
        }
    monkeypatch.setattr(kg, '_store', lambda: fake)

    graph = kg.get_knowledge_graph('uid')
    assert len(graph['nodes']) == expected_nodes
    assert len(graph['edges']) == expected_edges
    assert graph['node_count'] == expected_nodes
    assert graph['edge_count'] == expected_edges
    assert graph['truncated'] is expected_truncated
    # Bounded reads: the reader fetches at most one row past each public cap, never the full
    # collection (replaces the retired `limit_n == cap + 1` / stream-count call mechanics).
    if node_total:
        assert captured['knowledge_nodes'] == kg.MAX_KNOWLEDGE_GRAPH_NODES + 1
    if edge_total:
        assert captured['knowledge_edges'] == kg.MAX_KNOWLEDGE_GRAPH_EDGES + 1


def test_legacy_get_memories_no_first_page_5000_force():
    import routers.memories as mem

    calls = []

    def fake_get(uid, limit, offset):
        calls.append((uid, limit, offset))
        return []

    with patch.object(mem.memories_db, 'get_memories', side_effect=fake_get):
        mem._legacy_get_memories('u', limit=100, offset=0)
    assert calls == [('u', 100, 0)]

    with patch.object(mem.memories_db, 'get_memories', side_effect=fake_get):
        mem._legacy_get_memories('u', limit=9999, offset=0)
    assert calls[-1] == ('u', 500, 0)


def test_knowledge_graph_route_exposes_truncation(monkeypatch):
    import routers.knowledge_graph as kg_router

    payload = {
        'nodes': [{'id': 'n1'}],
        'edges': [],
        'truncated': True,
        'node_count': 1,
        'edge_count': 0,
        'node_limit': 500,
        'edge_limit': 1000,
    }
    monkeypatch.setattr(kg_router, 'get_knowledge_graph_payload', lambda uid: payload)
    app = FastAPI()
    app.include_router(kg_router.router)
    app.dependency_overrides[kg_router.auth.get_current_user_uid] = lambda: 'u'

    response = TestClient(app).get('/v1/knowledge-graph')

    assert response.status_code == 200
    assert response.json() == payload


def test_knowledge_graph_route_keeps_firebase_auth_dependency():
    from routers import knowledge_graph as kg_router

    route = next(route for route in kg_router.router.routes if route.path == '/v1/knowledge-graph')
    assert [dependency.call for dependency in route.dependant.dependencies] == [kg_router.auth.get_current_user_uid]
