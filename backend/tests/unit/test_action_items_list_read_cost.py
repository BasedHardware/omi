"""GET /v1/action-items must not read Firestore for a repeat poll.

`action_items_list` was 48.8% of every billable Firestore document read
(~$328/day) before #12258 restored its 12/min per-uid cap by exempting the
policy from RATE_LIMIT_BOOST. That removed ~90% of the volume by cutting the
*frequency* of the stale `omi-windows` hot loop. The residual is fan-out:
documents-per-operation rose 54.5 -> ~223 because the cheap requests are the
ones the cap removed, so each remaining allowed poll re-reads a whole unchanged
backlog.

These tests pin the two properties that make the residual go away:

* a cache hit and a 304 both perform **zero** Firestore reads (asserted as zero
  calls to `action_items_db.get_action_items`, the one function that streams
  documents), and
* a refused hot-loop poll is refused *before* any Firestore call.

A test that only asserted "returns the right body" would pass on a design that
reads Firestore and throws the result away, which is exactly the failure this
change exists to prevent.
"""

import json
import os
from types import SimpleNamespace
from unittest.mock import patch

import pytest

import database.action_items_cache as ai_cache
import routers.action_items as action_items_router
import utils.action_items_list_guard as guard


class _FakeRedis:
    """Minimal Redis stand-in: get/set/incr/expire plus a pipeline."""

    def __init__(self):
        self.store = {}

    def get(self, key):
        value = self.store.get(key)
        return value.encode() if isinstance(value, str) else value

    def set(self, key, value, ex=None):
        self.store[key] = value

    def incr(self, key):
        self.store[key] = str(int(self.store.get(key, 0)) + 1)
        return int(self.store[key])

    def expire(self, key, ttl):
        return True

    def pipeline(self):
        outer = self

        class _Pipe:
            def __init__(self):
                self.ops = []

            def incr(self, key):
                self.ops.append(('incr', key))
                return self

            def expire(self, key, ttl):
                self.ops.append(('expire', key, ttl))
                return self

            def execute(self):
                for op in self.ops:
                    if op[0] == 'incr':
                        outer.incr(op[1])
                self.ops = []

        return _Pipe()


class _Headers(dict):
    def get(self, key, default=None):
        return super().get(key.lower(), default)


def _request(headers=None):
    return SimpleNamespace(headers=_Headers({k.lower(): v for k, v in (headers or {}).items()}))


class _Response:
    def __init__(self):
        self.headers = {}


def _item(item_id: str) -> dict:
    return {'id': item_id, 'description': 'Do a thing', 'completed': False, 'is_locked': False}


def _call(*, request=None, response=None, uid='user-1', limit=50, offset=0, completed=None, **kwargs):
    return action_items_router.get_action_items(
        request=request,
        response=response,
        limit=limit,
        offset=offset,
        completed=completed,
        conversation_id=kwargs.get('conversation_id'),
        start_date=kwargs.get('start_date'),
        end_date=kwargs.get('end_date'),
        due_start_date=kwargs.get('due_start_date'),
        due_end_date=kwargs.get('due_end_date'),
        uid=uid,
    )


@pytest.fixture
def fake_redis(monkeypatch):
    fake = _FakeRedis()
    monkeypatch.setattr(ai_cache.redis_db, 'r', fake)
    monkeypatch.setenv('ACTION_ITEMS_LIST_CACHE_TTL_SECONDS', '30')
    return fake


class _Budget:
    truncated = False

    def observe(self, _outcome):
        return None


@pytest.fixture(autouse=True)
def _stub_budget(monkeypatch):
    monkeypatch.setattr(action_items_router, 'list_read_budget_for_request', lambda *a, **k: _Budget())


def test_repeat_poll_reads_zero_firestore_documents(fake_redis):
    with patch.object(action_items_router.action_items_db, 'get_action_items', return_value=[_item('one')]) as db_call:
        first = _call(request=_request(), response=_Response())
        assert db_call.call_count == 1

        second = _call(request=_request(), response=_Response())
        # The whole point: the second identical poll never reaches Firestore.
        assert db_call.call_count == 1

    assert [i['id'] for i in json.loads(second.body)['action_items']] == ['one']
    assert [i.id for i in first['action_items']] == ['one']


def test_if_none_match_returns_304_without_reading_firestore(fake_redis):
    resp = _Response()
    with patch.object(action_items_router.action_items_db, 'get_action_items', return_value=[_item('one')]) as db_call:
        _call(request=_request(), response=resp)
        etag = resp.headers['ETag']
        not_modified = _call(request=_request({'If-None-Match': etag}), response=_Response())
        assert db_call.call_count == 1

    assert not_modified.status_code == 304
    assert not_modified.headers['etag'] == etag


def test_a_write_invalidates_the_cached_page(fake_redis):
    with patch.object(action_items_router.action_items_db, 'get_action_items', return_value=[_item('one')]) as db_call:
        _call(request=_request(), response=_Response())
        ai_cache.bump_action_items_list_version('user-1')
        _call(request=_request(), response=_Response())

    assert db_call.call_count == 2


def test_date_filtered_reads_are_not_cached(fake_redis):
    from datetime import datetime, timezone

    start = datetime(2026, 9, 1, tzinfo=timezone.utc)
    with patch.object(action_items_router.action_items_db, 'get_action_items', return_value=[_item('one')]) as db_call:
        _call(request=_request(), response=_Response(), start_date=start)
        _call(request=_request(), response=_Response(), start_date=start)

    assert db_call.call_count == 2


def test_truncated_pages_are_never_cached(fake_redis):
    class _Truncated(_Budget):
        truncated = True

    with patch.object(action_items_router, 'list_read_budget_for_request', lambda *a, **k: _Truncated()):
        with patch.object(
            action_items_router.action_items_db, 'get_action_items', return_value=[_item('one')]
        ) as db_call:
            _call(request=_request(), response=_Response())
            _call(request=_request(), response=_Response())

    assert db_call.call_count == 2


def test_redis_outage_falls_open_to_a_real_read(monkeypatch):
    import redis as redis_pkg

    class _Broken:
        def get(self, *_a, **_k):
            raise redis_pkg.exceptions.ConnectionError('down')

        def set(self, *_a, **_k):
            raise redis_pkg.exceptions.ConnectionError('down')

    monkeypatch.setattr(ai_cache.redis_db, 'r', _Broken())
    monkeypatch.setenv('ACTION_ITEMS_LIST_CACHE_TTL_SECONDS', '30')
    with patch.object(action_items_router.action_items_db, 'get_action_items', return_value=[_item('one')]) as db_call:
        result = _call(request=_request(), response=_Response())
    assert db_call.call_count == 1
    assert [i.id for i in result['action_items']] == ['one']


def test_ttl_zero_disables_the_cache(monkeypatch, fake_redis):
    monkeypatch.setenv('ACTION_ITEMS_LIST_CACHE_TTL_SECONDS', '0')
    with patch.object(action_items_router.action_items_db, 'get_action_items', return_value=[_item('one')]) as db_call:
        _call(request=_request(), response=_Response())
        _call(request=_request(), response=_Response())
    assert db_call.call_count == 2


def test_ttl_is_clamped_and_typo_tolerant(monkeypatch):
    monkeypatch.setenv('ACTION_ITEMS_LIST_CACHE_TTL_SECONDS', '99999')
    assert ai_cache.list_cache_ttl_seconds() == 300
    monkeypatch.setenv('ACTION_ITEMS_LIST_CACHE_TTL_SECONDS', 'thirty')
    assert ai_cache.list_cache_ttl_seconds() == 30


@pytest.mark.parametrize(
    ('user_agent', 'expected'),
    [
        (
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 omi-windows/1.0.0 '
            'Chrome/142.0.7444.265 Electron/39.8.10 Safari/537.36',
            'stale_windows',
        ),
        ('Mozilla/5.0 omi-windows/1.0.36 Electron/39.8.10', 'windows'),
        ('Omi/12264 CFNetwork/3826.500.111.2.2 Darwin/24.6.0', 'other'),
        ('Dart/3.11 (dart:io)', 'other'),
        (None, 'other'),
        # A UA that merely mentions windows is not the hot-loop build.
        ('Mozilla/5.0 (Windows NT 10.0) Chrome/142', 'other'),
    ],
)
def test_client_classification(user_agent, expected):
    assert guard.classify_list_client(user_agent) == expected


def test_hot_client_ceiling_refuses_before_any_firestore_call(fake_redis, monkeypatch):
    from fastapi import HTTPException

    monkeypatch.setattr(guard, 'ACTION_ITEMS_LIST_HOT_CLIENT_MAX', 2)
    monkeypatch.setattr(guard, 'get_effective_limit', lambda _p: (2, 60))
    calls = {'n': 0}

    def _check(key, policy, max_requests, window):
        calls['n'] += 1
        return (calls['n'] <= max_requests, 0, 17)

    monkeypatch.setattr(guard, 'check_rate_limit', _check)
    hot = _request({'User-Agent': 'omi-windows/1.0.0 Electron/39.8.10'})

    with patch.object(action_items_router.action_items_db, 'get_action_items', return_value=[_item('one')]) as db_call:
        _call(request=hot, response=_Response())
        _call(request=hot, response=_Response(), uid='user-2')
        with pytest.raises(HTTPException) as excinfo:
            _call(request=hot, response=_Response(), uid='user-3')
        refused_at = db_call.call_count

    assert excinfo.value.status_code == 429
    assert excinfo.value.headers['Retry-After'] == '17'
    # The refusal happened before the database call for that request.
    assert refused_at == 2


def test_hot_client_ceiling_ignores_other_clients(fake_redis, monkeypatch):
    monkeypatch.setattr(guard, 'ACTION_ITEMS_LIST_HOT_CLIENT_MAX', 1)

    def _never_allowed(*_a, **_k):
        raise AssertionError('non-hot clients must not touch the second bucket')

    monkeypatch.setattr(guard, 'check_rate_limit', _never_allowed)
    mac = _request({'User-Agent': 'Omi/12264 CFNetwork/3826.500.111.2.2 Darwin/24.6.0'})

    with patch.object(action_items_router.action_items_db, 'get_action_items', return_value=[_item('one')]):
        _call(request=mac, response=_Response())


def test_hot_client_ceiling_is_disabled_at_zero(fake_redis, monkeypatch):
    monkeypatch.setattr(guard, 'ACTION_ITEMS_LIST_HOT_CLIENT_MAX', 0)

    def _never_allowed(*_a, **_k):
        raise AssertionError('the ceiling must be inert when the env knob is 0')

    monkeypatch.setattr(guard, 'check_rate_limit', _never_allowed)
    hot = _request({'User-Agent': 'omi-windows/1.0.0'})
    with patch.object(action_items_router.action_items_db, 'get_action_items', return_value=[_item('one')]):
        _call(request=hot, response=_Response())


def test_hot_client_ceiling_fails_open_when_redis_is_down(fake_redis, monkeypatch):
    import redis as redis_pkg

    monkeypatch.setattr(guard, 'ACTION_ITEMS_LIST_HOT_CLIENT_MAX', 1)

    def _down(*_a, **_k):
        raise redis_pkg.exceptions.ConnectionError('down')

    monkeypatch.setattr(guard, 'check_rate_limit', _down)
    hot = _request({'User-Agent': 'omi-windows/1.0.0'})
    with patch.object(action_items_router.action_items_db, 'get_action_items', return_value=[_item('one')]) as db_call:
        _call(request=hot, response=_Response())
    assert db_call.call_count == 1


@pytest.mark.parametrize(
    ('header', 'etag', 'expected'),
    [
        ('W/"abc"', 'W/"abc"', True),
        ('"abc"', 'W/"abc"', True),
        ('*', 'W/"abc"', True),
        ('W/"abc", W/"def"', 'W/"def"', True),
        ('W/"zzz"', 'W/"abc"', False),
        (None, 'W/"abc"', False),
        ('', 'W/"abc"', False),
    ],
)
def test_if_none_match_matching(header, etag, expected):
    assert ai_cache.if_none_match_matches(header, etag) is expected
