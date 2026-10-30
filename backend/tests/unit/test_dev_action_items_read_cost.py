"""Real ASGI route + list reader with strict query semantics and modeled SDK charges.

No credentials/network: the query fake implements Firestore missing-field, bool,
projection, ordering, limit and count behavior. It reports modeled charges through
SDK probe _record; these are local savings fixtures, not production measurements.
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.testclient import TestClient

from database import action_items as items
from database.firestore_document_probe import _record
from dependencies import ApiKeyAuth
from routers import developer
from tests.unit.test_external_list_cache import FakeRedis, immediate_population
from utils import external_list_reads as cache
from utils.observability import external_lists as metrics
from utils.other.list_budget import ListReadBudget

PATH = '/v1/dev/user/action-items'
NOW = datetime(2026, 10, 19, tzinfo=timezone.utc)


class Snapshot:
    __slots__ = ('id', '_row', '_fields')

    def __init__(self, row, fields):
        self.id, self._row, self._fields = row['id'], row, fields

    def to_dict(self):
        return {key: value for key, value in self._row.items() if self._fields is None or key in self._fields}


class Query:
    def __init__(self, rows, ledger, filters=(), order=None, fields=None, size=None):
        self.rows, self.ledger = rows, ledger
        self.filters, self.order, self.fields, self.size = filters, order, fields, size

    def copy(self, **changes):
        args = dict(filters=self.filters, order=self.order, fields=self.fields, size=self.size)
        return Query(self.rows, self.ledger, **(args | changes))

    def where(self, *, filter):
        return self.copy(filters=(*self.filters, filter))

    def order_by(self, name, direction=None):
        return self.copy(order=(name, direction))

    def select(self, fields):
        return self.copy(fields=frozenset(fields))

    def limit(self, size):
        return self.copy(size=size)

    def matching(self, *, ordered=True):
        rows = self.rows
        for f in self.filters:

            def match(row):
                if f.field_path not in row:
                    return False
                value, target = row[f.field_path], f.value
                if f.op_string == 'in':
                    return any(type(value) is type(v) and value == v for v in target)
                if f.op_string == '==':
                    return type(value) is type(target) and value == target
                if value is None:
                    return False
                return value >= target if f.op_string == '>=' else value <= target

            rows = [row for row in rows if match(row)]
        if self.order:
            field, direction = self.order
            rows = [row for row in rows if field in row]
            if ordered:
                rows = sorted(rows, key=lambda row: (row[field], row['id']), reverse=direction == 'DESCENDING')
        elif ordered:
            rows = sorted(rows, key=lambda row: row['id'])
        return rows

    def charge(self, amount, kind):
        self.ledger.append((kind, amount))
        _record(('users', 'fixture', 'action_items'), True, amount, kind=kind)

    def stream(self, **kwargs):
        rows = self.matching()[: self.size]
        self.charge(max(1, len(rows)), 'query')
        return (Snapshot(row, self.fields) for row in rows)

    def count(self):
        def get(**kwargs):
            # Counts retain filter/order-field existence semantics, but do not
            # need the stream's document ordering or projected snapshots.
            size = len(self.matching(ordered=False))
            self.charge(max(1, (size + 999) // 1000), 'aggregation')
            return [[SimpleNamespace(value=size)]]

        return SimpleNamespace(get=get)


def row(i, **changes):
    return (
        dict(
            id=f'{i:05}',
            description=f'Task {i}',
            completed=True,
            created_at=NOW - timedelta(minutes=i),
            due_at=NOW + timedelta(days=i % 17),
            conversation_id='conversation',
        )
        | changes
    )


@pytest.fixture
def endpoint(monkeypatch):
    state = SimpleNamespace(rows=[], ledger=[], status=200, uid='fixture')
    db = SimpleNamespace(
        collection=lambda _: SimpleNamespace(
            document=lambda _: SimpleNamespace(collection=lambda _: Query(state.rows, state.ledger))
        )
    )
    monkeypatch.setattr(items, 'db', db)
    monkeypatch.setattr(cache, '_client', FakeRedis())
    monkeypatch.setattr(cache, 'submit_with_context', immediate_population)
    monkeypatch.setattr(cache.action_item_versions, 'version', lambda uid: 'version-' + uid)
    app = FastAPI()
    app.include_router(developer.router)
    app.add_middleware(metrics.ExternalListMetricsMiddleware)

    async def auth(request: Request):
        _record(('users', state.uid), True, 2, kind='lookup')
        if state.status != 200:
            raise HTTPException(state.status)
        return ApiKeyAuth(state.uid, ['action_items:read'], app_id='app', key_id='key')

    async def owner(context=Depends(auth)):
        return context.uid

    app.dependency_overrides[developer.get_api_key_auth] = auth
    app.dependency_overrides[developer.get_uid_with_action_items_read] = owner
    return TestClient(app), state


def read_count(state):
    return sum(amount for _, amount in state.ledger)


def sample(collector, name, labels=None):
    return sum(
        s.value
        for metric in collector.collect()
        for s in metric.samples
        if s.name == name and (labels is None or s.labels == labels)
    )


@pytest.mark.parametrize(
    'filters',
    [
        {'conversation_id': 'conversation'},
        {'start_date': (NOW - timedelta(days=2)).isoformat()},
        {'end_date': NOW.isoformat()},
        {'conversation_id': 'conversation', 'start_date': (NOW - timedelta(days=2)).isoformat()},
    ],
)
def test_filtered_canonical_miss_avoids_amplified_legacy_scan(endpoint, monkeypatch, filters):
    client, state = endpoint
    state.rows = [row(i) for i in range(1000)]
    monkeypatch.setenv('OMI_EXTERNAL_LIST_CACHE_ENABLED', 'false')
    monkeypatch.setenv('OMI_DEV_ACTION_ITEMS_FILTERED_LEGACY_PROBE_ENABLED', 'false')
    old = client.get(PATH, params=filters)
    old_reads = read_count(state)
    state.ledger.clear()
    monkeypatch.delenv('OMI_DEV_ACTION_ITEMS_FILTERED_LEGACY_PROBE_ENABLED')
    new = client.get(PATH, params=filters)
    assert old.status_code == new.status_code == 200
    assert old.content == new.content and old.headers == new.headers
    assert old_reads == 933  # empty active floor + 800 legacy + 132 completed
    assert read_count(state) == 135  # same prefix, two one-read counts, no scan


@pytest.mark.parametrize('completed', [None, False, True])
@pytest.mark.parametrize('offset,limit', [(0, 5), (20, 10), (0, 1000), (1500, 100)])
@pytest.mark.parametrize('legacy', [False, True])
def test_response_parity_legacy_deleted_locked_missing_fields_offsets_and_cache(
    endpoint, monkeypatch, completed, offset, limit, legacy
):
    client, state = endpoint
    state.rows = [row(i, completed=i % 3 == 0) for i in range(80)]
    for i, value in [(2, True), (3, None), (4, False)]:
        state.rows[i]['deleted'] = value
        state.rows[i + 6]['is_locked'] = value
    if legacy:
        state.rows[11].pop('completed')
        state.rows[12]['completed'] = None
        state.rows[13].update(completed=None, status='completed')
    params = dict(offset=offset, limit=limit, conversation_id='conversation')
    if completed is not None:
        params['completed'] = str(completed).lower()
    monkeypatch.setenv('OMI_DEV_ACTION_ITEMS_FILTERED_LEGACY_PROBE_ENABLED', 'false')
    monkeypatch.setenv('OMI_EXTERNAL_LIST_CACHE_ENABLED', 'false')
    old = client.get(PATH, params=params)
    monkeypatch.delenv('OMI_DEV_ACTION_ITEMS_FILTERED_LEGACY_PROBE_ENABLED')
    monkeypatch.delenv('OMI_EXTERNAL_LIST_CACHE_ENABLED')
    new = client.get(PATH, params=params)
    before = read_count(state)
    warm = client.get(PATH, params=params)
    assert old.status_code == new.status_code == warm.status_code == 200
    assert old.content == new.content == warm.content
    assert old.headers == new.headers == warm.headers
    assert read_count(state) == before  # auth is tracked separately, no list reads
    state.status = 403
    assert client.get(PATH, params=params).status_code == 403


def test_global_probe_never_hides_legacy_in_filtered_subset(endpoint, monkeypatch):
    client, state = endpoint
    state.rows = [row(i) for i in range(1000)]
    state.rows[10].pop('completed')
    state.rows[20]['completed'] = None
    state.rows[30]['completed'] = 0  # noncanonical values also require compatibility
    monkeypatch.setenv('OMI_EXTERNAL_LIST_CACHE_ENABLED', 'false')
    result = client.get(PATH, params={'conversation_id': 'conversation'})
    assert {'00010', '00020', '00030'} <= {item['id'] for item in result.json()}
    # Global proof is intentionally conservative: legacy rows in another
    # conversation also retain the old scan, rather than excluding old data.
    state.rows[10]['conversation_id'] = 'other'
    state.ledger.clear()
    client.get(PATH, params={'conversation_id': 'conversation'})
    assert sum(amount for kind, amount in state.ledger if kind == 'query') > 800


def test_components_partition_sdk_total_and_page_rows_expose_overfetch(endpoint, monkeypatch):
    client, state = endpoint
    state.rows = [row(i, completed=i < 10, deleted=i == 0, is_locked=i == 11) for i in range(80)]
    monkeypatch.setenv('OMI_EXTERNAL_LIST_CACHE_ENABLED', 'false')
    components = {
        c: sample(
            metrics.ACTION_ITEMS_READ_COMPONENTS,
            'omi_dev_action_items_firestore_reads_by_component_sum',
            {'component': c},
        )
        for c in ('auth', 'incomplete', 'completed', 'legacy', 'count', 'other')
    }
    before = sample(metrics.EXTERNAL_LIST_READS, 'omi_external_list_firestore_reads_per_request_sum', {'route': PATH})
    response = client.get(PATH, params={'limit': 100, 'offset': 5, 'conversation_id': 'conversation'})
    delta = {
        c: sample(
            metrics.ACTION_ITEMS_READ_COMPONENTS,
            'omi_dev_action_items_firestore_reads_by_component_sum',
            {'component': c},
        )
        - v
        for c, v in components.items()
    }
    assert response.status_code == 200
    assert delta == dict(auth=4, incomplete=70, completed=10, legacy=0, count=2, other=0)
    assert (
        sum(delta.values())
        == sample(metrics.EXTERNAL_LIST_READS, 'omi_external_list_firestore_reads_per_request_sum', {'route': PATH})
        - before
        == 86
    )
    assert metrics.ACTION_ITEMS_READ_COMPONENTS._labelnames == ('component',)
    assert metrics.ACTION_ITEMS_PAGE_PARAMETERS._labelnames == ('parameter',)
    assert metrics.ACTION_ITEMS_PAGE_ROWS._labelnames == ('stage',)
    assert metrics.ACTION_ITEMS_REQUEST_SHAPES._labelnames == ('filters', 'completion', 'cache')


def test_probe_failure_falls_back_and_budget_exhaustion_remains_truncated(endpoint, monkeypatch):
    client, state = endpoint
    state.rows = [row(i) for i in range(1000)]
    monkeypatch.setenv('OMI_EXTERNAL_LIST_CACHE_ENABLED', 'false')
    monkeypatch.setattr(items, '_probe_legacy_completion_rows', Mock(side_effect=ValueError('synthetic')))
    response = client.get(PATH, params={'conversation_id': 'conversation'})
    assert response.status_code == 200 and read_count(state) == 933
    monkeypatch.setenv('OMI_LIST_READ_MAX_DOCUMENTS', '2')
    response = client.get(PATH, params={'conversation_id': 'conversation'})
    assert response.status_code == 200 and response.headers['X-Omi-List-Truncated'] == 'true'


def test_equivalent_date_params_share_cache_only_when_normalization_enabled(endpoint, monkeypatch):
    client, state = endpoint
    state.rows = [row(i) for i in range(50)]
    first = client.get(PATH, params={'end_date': NOW.isoformat()})
    before = read_count(state)
    offset_time = NOW.astimezone(timezone(timedelta(hours=7)))
    second = client.get(PATH, params={'end_date': offset_time.isoformat()})
    assert first.content == second.content and read_count(state) == before
    naive = client.get(PATH, params={'end_date': NOW.replace(tzinfo=None).isoformat()})
    assert naive.content == first.content and read_count(state) == before
    monkeypatch.setenv('OMI_DEV_ACTION_ITEMS_CACHE_NORMALIZE_ENABLED', 'false')
    client.get(PATH, params={'end_date': offset_time.isoformat()})
    assert read_count(state) > before


@pytest.mark.parametrize(
    'limit,offset,old_reads,new_reads',
    [
        (100, 0, 933, 139),
        (1000, 0, 3033, 1039),
        (100, 500, 2633, 639),
    ],
)
def test_modeled_filtered_large_and_offset_misses(endpoint, limit, offset, old_reads, new_reads):
    _client, state = endpoint
    state.rows = [row(i) for i in range(3000)]

    def read(probe):
        budget = ListReadBudget.for_request(None, route='developer-action-items')
        result = items.get_action_items(
            'fixture',
            limit=limit,
            offset=offset,
            conversation_id='conversation',
            budget=budget,
            probe_filtered_legacy=probe,
        )
        assert not budget.truncated
        return result

    # Large cost models exercise the real reader directly. Real ASGI/cache/
    # response-model parity is covered above without repeating HTTP machinery
    # around every large scan under the fast-unit CPU budget.
    old = read(False)
    assert read_count(state) == old_reads
    state.ledger.clear()
    new = read(True)
    assert new == old
    assert read_count(state) == new_reads


def test_large_canonical_owner_tiny_filtered_subset_exposes_count_overhead(endpoint):
    _client, state = endpoint
    state.rows = [row(i, conversation_id='conversation' if i == 0 else 'other') for i in range(2001)]

    def read(probe):
        budget = ListReadBudget.for_request(None, route='developer-action-items')
        result = items.get_action_items(
            'fixture',
            limit=100,
            conversation_id='conversation',
            budget=budget,
            probe_filtered_legacy=probe,
        )
        assert not budget.truncated
        return result

    old = read(False)
    assert [item['id'] for item in old] == ['00000']
    assert state.ledger == [('query', 1), ('query', 1), ('query', 1)]
    assert read_count(state) == 3
    state.ledger.clear()
    new = read(True)
    assert new == old
    # Both proof counts bill all 2,001 owner rows, not the one matching row.
    assert state.ledger == [('query', 1), ('aggregation', 3), ('aggregation', 3), ('query', 1)]
    assert read_count(state) == 8


def test_deleted_saturated_active_prefix_keeps_canonical_refill(endpoint, monkeypatch):
    client, state = endpoint
    state.rows = [row(i, completed=False, deleted=i < 100) for i in range(250)]
    monkeypatch.setenv('OMI_EXTERNAL_LIST_CACHE_ENABLED', 'false')
    monkeypatch.setenv('OMI_DEV_ACTION_ITEMS_FILTERED_LEGACY_PROBE_ENABLED', 'false')
    old = client.get(PATH, params={'conversation_id': 'conversation'})
    old_reads = read_count(state)
    state.ledger.clear()
    monkeypatch.delenv('OMI_DEV_ACTION_ITEMS_FILTERED_LEGACY_PROBE_ENABLED')
    new = client.get(PATH, params={'conversation_id': 'conversation'})
    assert new.content == old.content and len(new.json()) == 100
    assert read_count(state) == old_reads  # scan also refills canonical active rows


def test_details_switch_keeps_existing_total_accounting(endpoint, monkeypatch):
    client, state = endpoint
    state.rows = [row(i) for i in range(10)]
    monkeypatch.setenv('OMI_EXTERNAL_LIST_CACHE_ENABLED', 'false')
    monkeypatch.setenv('OMI_DEV_ACTION_ITEMS_READ_DETAILS_ENABLED', 'false')
    before = sample(metrics.ACTION_ITEMS_READ_COMPONENTS, 'omi_dev_action_items_firestore_reads_by_component_count')
    params = sample(metrics.ACTION_ITEMS_PAGE_PARAMETERS, 'omi_dev_action_items_page_parameter_count')
    total = sample(metrics.EXTERNAL_LIST_READS, 'omi_external_list_firestore_reads_per_request_count', {'route': PATH})
    assert client.get(PATH).status_code == 200
    assert (
        sample(metrics.ACTION_ITEMS_READ_COMPONENTS, 'omi_dev_action_items_firestore_reads_by_component_count')
        == before
    )
    assert sample(metrics.ACTION_ITEMS_PAGE_PARAMETERS, 'omi_dev_action_items_page_parameter_count') == params
    assert (
        sample(metrics.EXTERNAL_LIST_READS, 'omi_external_list_firestore_reads_per_request_count', {'route': PATH})
        == total + 1
    )


def test_arbitrary_large_accepted_offset_cannot_overflow_telemetry(endpoint):
    client, state = endpoint
    state.rows = [row(1)]
    before = sample(
        metrics.ACTION_ITEMS_PAGE_PARAMETERS, 'omi_dev_action_items_page_parameter_sum', {'parameter': 'offset'}
    )
    result = client.get(PATH, params={'offset': str(10**400)})
    assert result.status_code == 200 and result.json() == []
    assert (
        sample(metrics.ACTION_ITEMS_PAGE_PARAMETERS, 'omi_dev_action_items_page_parameter_sum', {'parameter': 'offset'})
        - before
        == 25001
    )
