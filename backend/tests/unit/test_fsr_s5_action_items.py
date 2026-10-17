"""Filtered-poll parity through the real route, bounded stream, and Redis cache."""

import copy
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi.encoders import jsonable_encoder
from redis.exceptions import ConnectionError

from database import action_items as db
from database import action_items_cache as cache
from routers import action_items as router
from utils.other.list_budget import ListReadBudget

NOW = datetime(2026, 10, 16, tzinfo=timezone.utc)


class Redis:
    def __init__(self):
        self.data = {}
        self.expires = {}
        self.now = 0

    def get(self, key):
        if self.expires.get(key, float('inf')) <= self.now:
            self.data.pop(key, None)
        return self.data.get(key)

    def set(self, key, value, ex=None):
        self.data[key] = value
        self.expires[key] = self.now + ex if ex is not None else float('inf')


class Query:
    def __init__(self, rows, reads, size=None):
        self.rows, self.reads, self.size = rows, reads, size

    def where(self, *, filter):
        def match(row):
            if filter.field_path not in row:
                return False
            v, target = row[filter.field_path], filter.value
            return {
                '==': lambda: v == target,
                '>=': lambda: v is not None and v >= target,
                '<=': lambda: v is not None and v <= target,
                'in': lambda: v in target,
            }[filter.op_string]()

        return Query([r for r in self.rows if match(r)], self.reads, self.size)

    def order_by(self, name, direction=None):
        rows = [r for r in self.rows if name in r]
        return Query(sorted(rows, key=lambda r: r[name], reverse=direction == 'DESCENDING'), self.reads, self.size)

    def select(self, fields):
        return self

    def limit(self, n):
        return Query(self.rows, self.reads, n)

    def stream(self, **kwargs):
        rows = self.rows[: self.size]
        self.reads[0] += max(1, len(rows))
        return iter([SimpleNamespace(id=r['id'], to_dict=lambda r=r: copy.deepcopy(r)) for r in rows])

    def count(self):
        def get(**kwargs):
            self.reads[0] += max(1, (len(self.rows) + 999) // 1000)
            return [[SimpleNamespace(value=len(self.rows))]]

        return SimpleNamespace(get=get)


@pytest.fixture
def installed(monkeypatch):
    fake = Redis()
    reads = [0]
    rows = [
        dict(
            id=f't{i}',
            description=f'Task {i}',
            completed=i % 2 == 0,
            deleted=i == 2,
            is_locked=i == 3,
            created_at=NOW - timedelta(days=i),
            due_at=NOW + timedelta(days=i),
            conversation_id='c' if i < 6 else 'other',
        )
        for i in range(8)
    ]
    query = Query(rows, reads)
    monkeypatch.setattr(
        db,
        'db',
        SimpleNamespace(
            collection=lambda _: SimpleNamespace(document=lambda _: SimpleNamespace(collection=lambda _: query))
        ),
    )
    monkeypatch.setattr(cache, '_redis', lambda: fake)
    monkeypatch.setattr(router, 'enforce_stale_client_list_refusal', lambda *_: None)
    monkeypatch.setattr(router, 'enforce_hot_client_list_ceiling', lambda *_: None)
    monkeypatch.setattr(
        router,
        'list_read_budget_for_request',
        lambda *a, **kw: ListReadBudget(deadline_monotonic=1e20, max_documents=10000),
    )
    monkeypatch.setenv('ACTION_ITEMS_LIST_CACHE_TTL_SECONDS', '30')
    monkeypatch.delenv('ACTION_ITEMS_PAGE_CACHE_TTL_SECONDS', raising=False)
    return fake, reads


def call(**kwargs):
    params = dict(
        request=SimpleNamespace(headers={}),
        response=SimpleNamespace(headers={}),
        uid='u',
        limit=2,
        offset=0,
        completed=None,
        conversation_id=None,
        start_date=None,
        end_date=None,
        due_start_date=None,
        due_end_date=None,
    )
    params.update(kwargs)
    result = router.get_action_items(**params)
    return json.loads(result.body) if hasattr(result, 'body') else jsonable_encoder(result)


@pytest.mark.parametrize('completed', [None, False, True])
@pytest.mark.parametrize('offset', [0, 2, 8])
@pytest.mark.parametrize(
    'filters',
    [
        {'conversation_id': 'c'},
        {'start_date': NOW - timedelta(days=5), 'end_date': NOW},
        {'due_start_date': NOW, 'due_end_date': NOW + timedelta(days=5)},
        {'conversation_id': 'empty'},
    ],
)
def test_golden_filters_pages_deleted_last_empty_and_has_more(installed, monkeypatch, completed, offset, filters):
    fake, reads = installed
    monkeypatch.delenv('FIRESTORE_READ_LEVERS', raising=False)
    off = call(completed=completed, offset=offset, **filters)
    monkeypatch.setenv('FIRESTORE_READ_LEVERS', '{"action_items_page":100}')
    cold = call(completed=completed, offset=offset, **filters)
    before = reads[0]
    hit = call(completed=completed, offset=offset, **filters)
    assert off == cold == hit
    assert reads[0] == before
    assert all(r['id'] != 't2' for r in hit['action_items'])


def test_ten_identical_filtered_polls_read_three_instead_of_thirty(installed, monkeypatch):
    _, reads = installed
    monkeypatch.delenv('FIRESTORE_READ_LEVERS', raising=False)
    for _ in range(10):
        call(completed=False, conversation_id='c')
    assert reads[0] == 30
    reads[0] = 0
    monkeypatch.setenv('FIRESTORE_READ_LEVERS', '{"action_items_page":100}')
    for _ in range(10):
        call(completed=False, conversation_id='c')
    assert reads[0] == 3


def test_write_during_fill_cannot_publish_stale_body(installed, monkeypatch):
    fake, reads = installed
    monkeypatch.setenv('FIRESTORE_READ_LEVERS', '{"action_items_page":100}')
    original = db.get_action_items

    def read_and_write(*args, **kwargs):
        result = original(*args, **kwargs)
        fake.set(cache._version_key('u'), str(int(fake.get(cache._version_key('u')) or 0) + 1))
        return result

    monkeypatch.setattr(db, 'get_action_items', read_and_write)
    call(completed=False, conversation_id='c')
    before = reads[0]
    call(completed=False, conversation_id='c')
    assert reads[0] == 2 * before


def test_explicit_invalidation_and_redis_outage(installed, monkeypatch):
    fake, reads = installed
    monkeypatch.setenv('FIRESTORE_READ_LEVERS', '{"action_items_page":100}')
    call(completed=False, conversation_id='c')
    fake.set(cache._version_key('u'), '1')
    call(completed=False, conversation_id='c')
    assert reads[0] == 6
    monkeypatch.setattr(fake, 'get', lambda _: (_ for _ in ()).throw(ConnectionError('down')))
    call(completed=False, conversation_id='c')
    assert reads[0] == 9


def test_304_filters_ttl_and_rollback(installed, monkeypatch):
    monkeypatch.setenv('FIRESTORE_READ_LEVERS', '{"action_items_page":100}')
    monkeypatch.setenv('ACTION_ITEMS_PAGE_CACHE_TTL_SECONDS', '120')
    assert cache.list_cache_ttl_seconds('u') == 120
    assert cache.list_cache_ttl_seconds() == 30
    response = SimpleNamespace(headers={})
    call(completed=False, conversation_id='c', response=response)
    before = installed[1][0]
    result = router._serve_action_items_list_from_cache(
        'u',
        request=SimpleNamespace(headers={'if-none-match': response.headers['ETag']}),
        limit=2,
        offset=0,
        completed=False,
        conversation_id='c',
        start_date=None,
        end_date=None,
        due_start_date=None,
        due_end_date=None,
    )
    assert result.status_code == 304
    assert installed[1][0] == before
    monkeypatch.setenv('ACTION_ITEMS_LIST_CACHE_TTL_SECONDS', '0')
    assert cache.list_cache_ttl_seconds('u') == 0
    call(completed=False, conversation_id='c')
    assert installed[1][0] > before


def test_opt_in_120s_ttl_removes_three_of_four_30s_poll_scans(installed, monkeypatch):
    fake, reads = installed
    monkeypatch.delenv('FIRESTORE_READ_LEVERS', raising=False)
    for i in range(16):
        fake.now = i * 30
        call(completed=False)
    assert reads[0] == 64
    fake.data.clear()
    fake.expires.clear()
    reads[0] = 0
    monkeypatch.setenv('FIRESTORE_READ_LEVERS', '{"action_items_page":100}')
    monkeypatch.setenv('ACTION_ITEMS_PAGE_CACHE_TTL_SECONDS', '120')
    for i in range(16):
        fake.now = i * 30
        call(completed=False)
    assert reads[0] == 16


@pytest.mark.parametrize('disabled', ['0', '00', '-1'])
def test_base_ttl_kill_switch_always_wins(installed, monkeypatch, disabled):
    monkeypatch.setenv('FIRESTORE_READ_LEVERS', '{"action_items_page":100}')
    monkeypatch.setenv('ACTION_ITEMS_PAGE_CACHE_TTL_SECONDS', '120')
    monkeypatch.setenv('ACTION_ITEMS_LIST_CACHE_TTL_SECONDS', disabled)
    assert cache.list_cache_ttl_seconds('u') == 0


def test_filtered_cache_keys_do_not_cross_pages_or_filters(installed, monkeypatch):
    monkeypatch.delenv('FIRESTORE_READ_LEVERS', raising=False)
    expected = [call(completed=False, conversation_id='c', offset=i) for i in (0, 2)]
    expected.append(call(completed=False, conversation_id='other'))
    monkeypatch.setenv('FIRESTORE_READ_LEVERS', '{"action_items_page":100}')
    actual = [call(completed=False, conversation_id='c', offset=i) for i in (0, 2)]
    actual.append(call(completed=False, conversation_id='other'))
    assert actual == expected
    assert actual[0] != actual[1] != actual[2]


def test_truncated_filtered_page_remains_uncached_with_lever_on(installed, monkeypatch):
    fake, reads = installed
    monkeypatch.setattr(
        router,
        'list_read_budget_for_request',
        lambda *a, **kw: ListReadBudget(deadline_monotonic=1e20, max_documents=1),
    )
    monkeypatch.delenv('FIRESTORE_READ_LEVERS', raising=False)
    expected = call(completed=False, conversation_id='c')
    monkeypatch.setenv('FIRESTORE_READ_LEVERS', '{"action_items_page":100}')
    first = call(completed=False, conversation_id='c')
    before = reads[0]
    second = call(completed=False, conversation_id='c')
    assert first == second == expected
    assert first['truncated'] and first['has_more']
    assert reads[0] > before
    assert not any(key.startswith('ail:u:') for key in fake.data)
