"""Bounded Firestore list reads for prod GET 504s (action-items / memories / KG).

Regression coverage for Closes #10746: list paths must not full-collection stream.
"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any, Dict, List, Optional

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
        self.data = {k: v for k, v in data.items() if k != 'id'}

    def to_dict(self):
        return dict(self.data)


class _FakeAggregation:
    def __init__(self, count: int, error: Exception | None):
        self.count = count
        self.error = error

    def get(self, **kwargs):
        del kwargs
        if self.error is not None:
            raise self.error
        return [[SimpleNamespace(value=self.count)]]


class _FakeQuery:
    def __init__(self, docs: List[_FakeDoc], filters: Optional[List] = None, *, count_error: Any = None):
        self._docs = docs
        self._filters = list(filters or [])
        self._count_error = count_error
        self._limit = None
        self._offset = 0
        self._select: Optional[List[str]] = None

    last_select: Optional[List[str]] = None

    def where(self, *args, **kwargs):
        filt = kwargs.get('filter') or (args[0] if args else None)
        q = _FakeQuery(self._docs, self._filters + [filt], count_error=self._count_error)
        q._limit = self._limit
        q._offset = self._offset
        q._select = self._select
        return q

    def order_by(self, *args, **kwargs):
        return self

    def select(self, fields):
        q = _FakeQuery(self._docs, self._filters, count_error=self._count_error)
        q._limit = self._limit
        q._offset = self._offset
        q._select = list(fields)
        _FakeQuery.last_select = list(fields)
        return q

    def offset(self, n: int):
        q = _FakeQuery(self._docs, self._filters, count_error=self._count_error)
        q._limit = self._limit
        q._offset = n
        q._select = self._select
        return q

    def limit(self, n: int):
        q = _FakeQuery(self._docs, self._filters, count_error=self._count_error)
        q._limit = n
        q._offset = self._offset
        q._select = self._select
        return q

    def _filtered_docs(self):
        docs = self._docs
        for filt in self._filters:
            # FieldFilter duck: .field_path / .op_string / .value
            field = getattr(filt, 'field_path', None) or getattr(filt, 'field', None)
            op = getattr(filt, 'op_string', None) or getattr(filt, 'op', '==')
            value = getattr(filt, 'value', None)
            if field == 'completed' and op == '==':
                docs = [d for d in docs if 'completed' in d.data and d.data.get('completed') is value]
            elif field == 'completed' and op == 'in' and isinstance(value, (list, tuple, set, frozenset)):
                docs = [d for d in docs if 'completed' in d.data and d.data.get('completed') in value]
            elif field == 'conversation_id' and op == '==':
                docs = [d for d in docs if d.data.get('conversation_id') == value]
        return docs

    def count(self):
        error = self._count_error(self) if callable(self._count_error) else self._count_error
        return _FakeAggregation(len(self._filtered_docs()), error)

    def stream(self):
        docs = self._filtered_docs()
        if self._offset:
            docs = docs[self._offset :]
        if self._limit is not None:
            docs = docs[: self._limit]
        # yield copies so callers can mutate safely
        for d in docs:
            yield _FakeDoc({'id': d.id, **d.data})


class _FakeCollection:
    def __init__(self, docs: List[_FakeDoc], *, count_error: Any = None):
        self._docs = docs
        self._count_error = count_error

    def document(self, uid: str):
        return SimpleNamespace(collection=lambda name: _FakeQuery(self._docs, count_error=self._count_error))


class _FakeDB:
    def __init__(self, docs: List[_FakeDoc], *, count_error: Any = None):
        self._coll = _FakeCollection(docs, count_error=count_error)

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
    budget = ai.ListReadBudget(deadline_monotonic=10, max_documents=100, clock=lambda: 0, started_monotonic=0)

    page = ai.get_action_items('uid', limit=10, offset=0, budget=budget)
    assert [x['id'] for x in page[:5]] == ['a0', 'a1', 'a2', 'a3', 'a4']
    assert all(not x['completed'] for x in page[:5])
    # Completed only after actives fill
    assert all(x['completed'] for x in page[5:])
    assert recorded
    assert recorded[0][1] == metrics.FirestoreReadMode.BOUNDED
    # Two one-read count aggregations prove there are no missing/null completion
    # fields, so the old 128-document compatibility scan over this 305-row
    # collection is skipped.
    assert recorded[0][2] <= 5 + ai._list_scan_budget(5) + 2
    assert budget.docs_scanned == recorded[0][2]


def test_get_action_items_keeps_legacy_rows_when_probe_finds_them(ai_mod, monkeypatch):
    ai, recorded, _metrics = ai_mod
    missing = _item('missing')
    missing.pop('completed')
    null = _item('null')
    null['completed'] = None
    docs = [
        _FakeDoc(_item('active', completed=False)),
        _FakeDoc(missing),
        _FakeDoc(null),
        _FakeDoc(_item('done', completed=True)),
    ]
    monkeypatch.setattr(ai, 'db', _FakeDB(docs))

    page = ai.get_action_items('uid', limit=4)

    assert [item['id'] for item in page] == ['active', 'missing', 'null', 'done']
    assert all(isinstance(item['completed'], bool) for item in page)
    # The compatibility scan remains charged when the aggregation detects a
    # missing/null completion field.
    assert recorded[0][2] == 8


def test_get_action_items_aggregation_failure_recovers_with_legacy_scan(ai_mod, monkeypatch):
    ai, _recorded, _metrics = ai_mod
    legacy = _item('legacy')
    legacy.pop('completed')
    fallbacks = []
    monkeypatch.setattr(ai, 'db', _FakeDB([_FakeDoc(legacy)], count_error=TypeError('aggregation unavailable')))
    monkeypatch.setattr(ai, 'record_fallback', lambda **kwargs: fallbacks.append(kwargs))

    page = ai.get_action_items('uid', limit=3)

    assert [item['id'] for item in page] == ['legacy']
    assert fallbacks == [
        {
            'component': 'firestore_read',
            'from_mode': 'legacy_completion_probe',
            'to_mode': 'bounded_legacy_scan',
            'reason': 'other',
            'outcome': 'recovered',
            'log': ai.logger,
        }
    ]


def test_get_action_items_unbudgeted_aggregation_timeout_recovers_with_legacy_scan(ai_mod, monkeypatch):
    ai, recorded, _metrics = ai_mod
    legacy = _item('legacy')
    legacy.pop('completed')
    fallbacks = []

    def _fail_collection_total(query):
        if not query._filters:
            return ai.FirestoreDeadlineExceeded('aggregation timeout')
        return None

    monkeypatch.setattr(ai, 'db', _FakeDB([_FakeDoc(legacy)], count_error=_fail_collection_total))
    monkeypatch.setattr(ai, 'record_fallback', lambda **kwargs: fallbacks.append(kwargs))

    page = ai.get_action_items('uid', limit=3)

    assert [item['id'] for item in page] == ['legacy']
    assert recorded[0][2] == 2  # successful canonical count + compatibility scan
    assert fallbacks == [
        {
            'component': 'firestore_read',
            'from_mode': 'legacy_completion_probe',
            'to_mode': 'bounded_legacy_scan',
            'reason': 'timeout',
            'outcome': 'recovered',
            'log': ai.logger,
        }
    ]


def test_get_action_items_attributes_partial_probe_billing_before_fallback(ai_mod, monkeypatch):
    ai, recorded, _metrics = ai_mod
    legacy = _item('legacy')
    legacy.pop('completed')

    def _fail_collection_total(query):
        if not query._filters:
            return TypeError('second aggregation unavailable')
        return None

    monkeypatch.setattr(ai, 'db', _FakeDB([_FakeDoc(legacy)], count_error=_fail_collection_total))

    page = ai.get_action_items('uid', limit=3)

    assert [item['id'] for item in page] == ['legacy']
    assert recorded[0][2] == 2  # successful canonical count + compatibility scan


def test_get_action_items_attributes_partial_probe_billing_before_budget_truncation(ai_mod, monkeypatch):
    ai, recorded, _metrics = ai_mod
    legacy = _item('legacy')
    legacy.pop('completed')

    def _timeout_collection_total(query):
        if not query._filters:
            return ai.FirestoreDeadlineExceeded('request-derived timeout')
        return None

    monkeypatch.setattr(ai, 'db', _FakeDB([_FakeDoc(legacy)], count_error=_timeout_collection_total))
    budget = ai.ListReadBudget(deadline_monotonic=10, max_documents=10, clock=lambda: 0, started_monotonic=0)

    page = ai.get_action_items('uid', limit=3, budget=budget)

    assert page == []
    assert budget.truncated is True
    assert budget.exhaustion_reason == 'deadline'
    assert recorded[0][2] == 1  # successful canonical count before the timed-out total


def test_legacy_probe_charges_firestore_aggregation_batches(ai_mod):
    ai, _recorded, _metrics = ai_mod
    docs = [_FakeDoc(_item(f'item-{index}', completed=False)) for index in range(1001)]
    budget = ai.ListReadBudget(deadline_monotonic=10, max_documents=10, clock=lambda: 0, started_monotonic=0)

    probe = ai._probe_legacy_completion_rows(_FakeQuery(docs), budget=budget)

    assert probe.has_legacy_rows is False
    # Each count crosses the 1,000-entry billing boundary: two reads for the
    # canonical count plus two for the collection total.
    assert probe.billed_reads == 4
    assert budget.docs_scanned == 4


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


def test_completed_filter_scans_page_plus_slack_not_double(ai_mod, monkeypatch):
    """Windows sends completed= + limit=500; the old 2× overscan pulled ~1000 full docs."""
    ai, recorded, metrics = ai_mod
    docs = [_FakeDoc(_item(f'c{i}', completed=True)) for i in range(2000)]
    monkeypatch.setattr(ai, 'db', _FakeDB(docs))

    page = ai.get_action_items('uid', completed=True, limit=500, offset=0)
    assert len(page) == 500
    assert recorded[0][1] == metrics.FirestoreReadMode.BOUNDED
    assert recorded[0][2] <= 500 + ai._ACTION_ITEMS_LIST_DELETED_SLACK
    assert recorded[0][2] < 1000


def test_completed_offset_is_a_live_item_slice_not_a_firestore_offset(ai_mod, monkeypatch):
    """Client offset counts returned rows. Firestore offset would also skip deleted docs.

    High offset still reads offset+limit+slack (capped at HARD_MAX), not 2×.
    """
    ai, recorded, metrics = ai_mod
    docs = [_FakeDoc(_item(f'c{i}', completed=True)) for i in range(2000)]
    monkeypatch.setattr(ai, 'db', _FakeDB(docs))

    page = ai.get_action_items('uid', completed=True, limit=500, offset=1500)
    assert [x['id'] for x in page[:2]] == ['c1500', 'c1501']
    assert len(page) == 500
    assert recorded[0][1] == metrics.FirestoreReadMode.BOUNDED
    assert recorded[0][2] <= ai._ACTION_ITEMS_LIST_HARD_MAX
    assert recorded[0][2] < 2 * (1500 + 500)


def test_list_projects_lean_fields_and_omits_provenance(ai_mod, monkeypatch):
    ai, recorded, _metrics = ai_mod
    _FakeQuery.last_select = None
    docs = [_FakeDoc(_item('a1', completed=False))]
    monkeypatch.setattr(ai, 'db', _FakeDB(docs))

    ai.get_action_items('uid', completed=False, limit=10, offset=0)
    assert _FakeQuery.last_select is not None
    assert 'description' in _FakeQuery.last_select
    assert 'completed' in _FakeQuery.last_select
    assert 'deleted' in _FakeQuery.last_select
    assert 'provenance' not in _FakeQuery.last_select
    assert recorded[0][2] <= 10 + ai._ACTION_ITEMS_LIST_DELETED_SLACK


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
    page = SimpleNamespace(
        nodes=payload['nodes'],
        edges=payload['edges'],
        has_more=payload['truncated'],
        next_cursor='next',
    )
    monkeypatch.setattr(
        kg_router.canonical_graph_service, 'get_canonical_knowledge_graph', lambda *args, **kwargs: page
    )
    app = FastAPI()
    app.include_router(kg_router.router)
    app.dependency_overrides[kg_router.auth.get_current_user_uid] = lambda: 'u'

    response = TestClient(app).get('/v1/knowledge-graph')

    assert response.status_code == 200
    assert response.json() == {**payload, 'node_limit': 500, 'edge_limit': 500}


def test_knowledge_graph_route_keeps_firebase_auth_dependency():
    from routers import knowledge_graph as kg_router

    route = next(route for route in kg_router.router.routes if route.path == '/v1/knowledge-graph')
    assert [dependency.call for dependency in route.dependant.dependencies] == [kg_router.auth.get_current_user_uid]
