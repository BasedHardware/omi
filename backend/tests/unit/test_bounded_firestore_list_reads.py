"""Bounded Firestore list reads for prod GET 504s (action-items / memories / KG).

Regression coverage for Closes #10746: list paths must not full-collection stream.
"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any, Dict, List, Optional
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest


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


class _FakeDoc:
    def __init__(self, data: Dict[str, Any]):
        self.id = data['id']
        self._data = {k: v for k, v in data.items() if k != 'id'}

    def to_dict(self):
        return dict(self._data)


class _FakeQuery:
    def __init__(self, docs: List[_FakeDoc], filters: Optional[List] = None):
        self._docs = docs
        self._filters = list(filters or [])
        self._limit = None

    def where(self, *args, **kwargs):
        filt = kwargs.get('filter') or (args[0] if args else None)
        return _FakeQuery(self._docs, self._filters + [filt])

    def order_by(self, *args, **kwargs):
        return self

    def limit(self, n: int):
        q = _FakeQuery(self._docs, self._filters)
        q._limit = n
        return q

    def stream(self):
        docs = self._docs
        for filt in self._filters:
            # FieldFilter duck: .field_path / .op_string / .value
            field = getattr(filt, 'field_path', None) or getattr(filt, 'field', None)
            op = getattr(filt, 'op_string', None) or getattr(filt, 'op', '==')
            value = getattr(filt, 'value', None)
            if field == 'completed' and op == '==':
                docs = [d for d in docs if bool(d._data.get('completed')) is bool(value)]
            elif field == 'conversation_id' and op == '==':
                docs = [d for d in docs if d._data.get('conversation_id') == value]
        if self._limit is not None:
            docs = docs[: self._limit]
        # yield copies so callers can mutate safely
        for d in docs:
            yield _FakeDoc({'id': d.id, **d._data})


class _FakeCollection:
    def __init__(self, docs: List[_FakeDoc]):
        self._docs = docs

    def document(self, uid: str):
        return SimpleNamespace(collection=lambda name: _FakeQuery(self._docs))


class _FakeDB:
    def __init__(self, docs: List[_FakeDoc]):
        self._coll = _FakeCollection(docs)

    def collection(self, name: str):
        assert name == 'users'
        return self._coll


@pytest.fixture
def ai_mod(monkeypatch):
    import database.action_items as ai
    import database.firestore_read_metrics as metrics

    recorded = []

    def _record(family, mode, documents):
        recorded.append((family, mode, documents))

    monkeypatch.setattr(ai, 'record_firestore_read', _record)
    return ai, recorded, metrics


@pytest.fixture
def kg_module():
    import database.knowledge_graph as kg

    return kg


def test_get_action_items_active_first_without_full_scan(ai_mod, monkeypatch):
    ai, recorded, metrics = ai_mod
    # Many completed docs first in storage order; actives must still lead the page.
    docs = []
    for i in range(300):
        docs.append(
            _FakeDoc(
                _item(
                    f'c{i}',
                    completed=True,
                    created_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
                )
            )
        )
    for i in range(5):
        docs.append(
            _FakeDoc(
                _item(
                    f'a{i}',
                    completed=False,
                    created_at=datetime(2026, 1, 3, tzinfo=timezone.utc),
                )
            )
        )
    monkeypatch.setattr(ai, 'db', _FakeDB(docs))

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
    docs = [_FakeDoc(_item(f'x{i}', completed=False)) for i in range(5000)]
    monkeypatch.setattr(ai, 'db', _FakeDB(docs))

    page = ai.get_action_items('uid', limit=50, offset=0)
    assert len(page) == 50
    assert recorded[0][1] == metrics.FirestoreReadMode.BOUNDED
    assert recorded[0][2] <= ai._ACTION_ITEMS_LIST_HARD_MAX


def test_get_action_items_skips_deleted_in_active_bucket(ai_mod, monkeypatch):
    ai, recorded, metrics = ai_mod
    docs = [
        _FakeDoc(_item('del1', completed=False, deleted=True)),
        _FakeDoc(_item('a1', completed=False)),
        _FakeDoc(_item('c1', completed=True)),
    ]
    monkeypatch.setattr(ai, 'db', _FakeDB(docs))
    page = ai.get_action_items('uid', limit=10, offset=0)
    ids = [x['id'] for x in page]
    assert 'del1' not in ids
    assert ids[0] == 'a1'


@pytest.mark.parametrize(
    ('node_total', 'edge_total', 'expected_nodes', 'expected_edges', 'expected_truncated'),
    (
        (0, 0, 0, 0, False),
        (3, 2, 3, 2, False),
        (20_000, 20_000, 500, 1000, True),
    ),
)
def test_knowledge_graph_get_is_deterministic_and_bounded_for_large_fixtures(
    kg_module,
    node_total,
    edge_total,
    expected_nodes,
    expected_edges,
    expected_truncated,
):
    kg = kg_module

    class _StreamColl:
        def __init__(self, n, *, edge=False):
            self.n = n
            self.edge = edge
            self.limit_n = None
            self.order_fields = []
            self.streamed = 0

        def order_by(self, field_path, *args, **kwargs):
            self.order_fields.append(field_path)
            return self

        def limit(self, n):
            self.limit_n = n
            return self

        def stream(self):
            count = min(self.n, self.limit_n) if self.limit_n is not None else self.n
            for i in range(count):
                payload = (
                    {
                        'id': f'e{i}',
                        'source_id': 'n0',
                        'target_id': 'n1',
                        'label': f'L{i}',
                    }
                    if self.edge
                    else {'id': f'n{i}', 'label': f'L{i}'}
                )
                self.streamed += 1
                yield SimpleNamespace(to_dict=lambda payload=payload: payload)

    nodes = _StreamColl(node_total)
    edges = _StreamColl(edge_total, edge=True)
    assertions = _StreamColl(0)

    collections = {
        kg.knowledge_nodes_collection: nodes,
        kg.knowledge_edges_collection: edges,
        kg.memory_graph_assertions_collection: assertions,
    }
    user_ref = SimpleNamespace(collection=lambda name: collections[name])
    client = SimpleNamespace(collection=lambda name: SimpleNamespace(document=lambda uid: user_ref))

    graph = kg.get_knowledge_graph('uid', db_client=client)
    assert len(graph['nodes']) == expected_nodes
    assert len(graph['edges']) == expected_edges
    assert graph['node_count'] == expected_nodes
    assert graph['edge_count'] == expected_edges
    assert graph['truncated'] is expected_truncated
    assert nodes.limit_n == kg.MAX_KNOWLEDGE_GRAPH_NODES + 1
    assert edges.limit_n == kg.MAX_KNOWLEDGE_GRAPH_EDGES + 1
    assert assertions.limit_n == kg.MAX_KNOWLEDGE_GRAPH_ASSERTIONS + 1
    assert nodes.streamed <= kg.MAX_KNOWLEDGE_GRAPH_NODES + 1
    assert edges.streamed <= kg.MAX_KNOWLEDGE_GRAPH_EDGES + 1
    assert nodes.order_fields == [kg.KNOWLEDGE_GRAPH_DOCUMENT_ORDER]
    assert edges.order_fields == [kg.KNOWLEDGE_GRAPH_DOCUMENT_ORDER]
    assert assertions.order_fields == [kg.KNOWLEDGE_GRAPH_DOCUMENT_ORDER]


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
