"""Conversation deletion feed for agents that keep copies (MCP tool and REST; in-memory Firestore)."""

import os
from datetime import datetime, timedelta, timezone

os.environ.setdefault('OPENAI_API_KEY', 'sk-test-not-real')
os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')

import jsonschema
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from database import conversation_deletion_feed as feed
from routers import mcp as rest
from utils.mcp_server.errors import ToolExecutionError
from utils.mcp_server.handlers import sync
from utils.mcp_server.payloads import tool_result_payload
from utils.mcp_server.registry import TOOLS_BY_NAME

UID = 'synthetic-owner'
T0 = datetime(2026, 11, 1, tzinfo=timezone.utc)


class _Doc:
    def __init__(self, doc_id, data):
        self.id, self._data = doc_id, data

    def to_dict(self):
        return dict(self._data)


class _Ref:
    def __init__(self, doc_id):
        self.id = doc_id


class _Query:
    """Applies the feed's where/order/start_after/limit like Firestore, on (deleted_at, id)."""

    def __init__(self, store, ops=()):
        self.store, self.ops = store, list(ops)

    def _with(self, op):
        return _Query(self.store, self.ops + [op])

    def where(self, filter=None):
        return self._with(('where', filter.field_path, filter.op_string, filter.value))

    def order_by(self, field, direction=None):
        return self._with(('order_by', field))

    def start_after(self, position):
        return self._with(('start_after', position['deleted_at'], position['__name__'].id))

    def select(self, fields):
        self.store['selects'].append(list(fields))
        return self._with(('select',))

    def limit(self, count):
        return self._with(('limit', count))

    def document(self, doc_id):
        return _Ref(doc_id)

    def stream(self):
        # order_by drops absent fields but keeps explicit nulls (sorted first); a range
        # filter matches only values of its own type, so it drops nulls.
        rows = [(d['deleted_at'], i, d) for i, d in self.store['docs'].items() if 'deleted_at' in d]
        rows.sort(key=lambda r: (r[0] is not None, r[0] or T0, r[1]))
        for op in self.ops:
            if op[0] == 'where':
                rows = [r for r in rows if r[0] is not None and r[0] >= op[3]]
            elif op[0] == 'start_after':
                rows = [r for r in rows if (r[0], r[1]) > (op[1], op[2])]
            elif op[0] == 'limit':
                rows = rows[: op[1]]
        return iter(_Doc(i, d) for _, i, d in rows)


class _Client:
    def __init__(self, store):
        self.store = store

    def collection(self, name):
        assert name == 'users'
        return self

    def document(self, uid):
        assert uid == UID
        return _Leaf(self.store)


class _Leaf:
    def __init__(self, store):
        self.store = store

    def collection(self, name):
        assert name == 'deleted_conversations'
        return _Query(self.store)


@pytest.fixture
def tombstones(monkeypatch):
    store = {'docs': {}, 'selects': []}
    real = feed.get_deleted_conversations_page

    def page(uid, **kwargs):
        return real(uid, firestore_client=_Client(store), **kwargs)

    monkeypatch.setattr(feed, 'get_deleted_conversations_page', page)
    return store


def add(store, cid, minutes, **extra):
    store['docs'][cid] = {'conversation_id': cid, 'deleted_at': T0 + timedelta(minutes=minutes), **extra}


def walk(**arguments):
    seen, cursor = [], None
    for _ in range(20):
        page = sync.get_deleted_conversations(UID, {**arguments, **({'cursor': cursor} if cursor else {})})
        wire = tool_result_payload(page)['structuredContent']
        jsonschema.validate(wire, TOOLS_BY_NAME['get_deleted_conversations'].output_schema)
        seen += [row['id'] for row in page['deleted']]
        cursor = page['next_cursor']
        assert page['has_more'] == (cursor is not None)
        if cursor is None:
            return seen
    raise AssertionError('feed did not end')


def test_paging_walks_every_deletion_once_in_order_across_equal_timestamps(tombstones):
    for cid, minutes in (('c', 5), ('a', 5), ('b', 5), ('d', 1), ('e', 9)):
        add(tombstones, cid, minutes)
    assert walk(limit=2) == ['d', 'a', 'b', 'c', 'e']
    assert tombstones['selects'] and all(fields == ['deleted_at'] for fields in tombstones['selects'])


def test_deleted_since_is_inclusive_and_untimed_tombstones_never_appear(tombstones):
    add(tombstones, 'before', 1)
    add(tombstones, 'at', 5)
    add(tombstones, 'after', 6)
    tombstones['docs']['legacy'] = {'deleted': True}
    assert walk(deleted_since=(T0 + timedelta(minutes=5)).isoformat()) == ['at', 'after']


def test_null_timestamps_never_appear_even_without_a_watermark(tombstones):
    add(tombstones, 'timed', 2)
    tombstones['docs']['null'] = {'conversation_id': 'null', 'deleted_at': None}
    assert walk(limit=1) == ['timed']


def test_rest_limit_is_bounded_like_the_tool(tombstones, client):
    for bad in (0, 501):
        assert client.get('/v1/mcp/conversations/deleted', params={'limit': bad}).status_code == 422


def test_rows_carry_only_the_id_and_the_watermark(tombstones):
    add(tombstones, 'x', 3, created_at=T0, client_session_id='secret-session')
    (row,) = sync.get_deleted_conversations(UID, {})['deleted']
    assert row == {'id': 'x', 'deleted_at': T0 + timedelta(minutes=3)}


def test_a_cursor_is_bound_to_its_deleted_since(tombstones):
    for i in range(3):
        add(tombstones, f'c{i}', i)
    first = sync.get_deleted_conversations(UID, {'limit': 1, 'deleted_since': T0.isoformat()})
    with pytest.raises(ToolExecutionError) as error:
        sync.get_deleted_conversations(
            UID, {'limit': 1, 'deleted_since': (T0 + timedelta(minutes=1)).isoformat(), 'cursor': first['next_cursor']}
        )
    assert error.value.code == -32602


@pytest.mark.parametrize('since', ['2026-11-01T00:00:00', 'yesterday', ''])
def test_naive_or_malformed_watermarks_are_rejected(tombstones, since):
    with pytest.raises(ToolExecutionError) as error:
        sync.get_deleted_conversations(UID, {'deleted_since': since})
    assert error.value.code == -32602


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(rest.router)
    app.dependency_overrides[rest.get_uid_with_mcp_conversations_read] = lambda: UID
    return TestClient(app)


def test_rest_feed_is_an_array_with_the_cursor_in_a_header(tombstones, client):
    for i in range(3):
        add(tombstones, f'c{i}', i)
    response = client.get('/v1/mcp/conversations/deleted', params={'limit': 2, 'deleted_since': T0.isoformat()})
    assert response.status_code == 200
    assert [row['id'] for row in response.json()] == ['c0', 'c1']
    cursor = response.headers['X-Next-Cursor']
    rest_page = client.get(
        '/v1/mcp/conversations/deleted', params={'limit': 2, 'deleted_since': T0.isoformat(), 'cursor': cursor}
    )
    assert [row['id'] for row in rest_page.json()] == ['c2'] and 'X-Next-Cursor' not in rest_page.headers
    assert client.get('/v1/mcp/conversations/deleted', params={'deleted_since': 'naive'}).status_code == 400


def test_conversation_updated_since_gate_points_at_the_deletion_feed(client):
    response = client.get('/v1/mcp/conversations', params={'updated_since': T0.isoformat()})
    assert response.status_code == 400 and '/v1/mcp/conversations/deleted' in response.json()['detail']
