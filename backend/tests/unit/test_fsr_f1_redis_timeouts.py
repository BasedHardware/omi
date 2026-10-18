"""Exercise real Redis socket deadlines against a local non-responding listener."""

import socket
import time
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from database import action_items_cache, s5_candidates_cache, staged_promote_cache
from database import fsr_read_cache as s4_read_cache
from routers import action_items as router


@pytest.fixture
def blackhole(monkeypatch):
    # TCP completes in the kernel, but nothing accepts or answers Redis commands.
    # No worker thread, external Redis service, credentials, or sleeps are needed.
    listener = socket.socket()
    listener.bind(('127.0.0.1', 0))
    listener.listen(32)
    monkeypatch.setenv('REDIS_DB_HOST', '127.0.0.1')
    monkeypatch.setenv('REDIS_DB_PORT', str(listener.getsockname()[1]))
    monkeypatch.delenv('REDIS_DB_PASSWORD', raising=False)
    monkeypatch.setenv(
        'FIRESTORE_READ_LEVERS', '{"subscription_cache":100,"candidates_page":100,"action_items_page":100}'
    )
    clients = []
    modules = (s4_read_cache, s5_candidates_cache, action_items_cache, staged_promote_cache)
    accessors = [module._redis for module in modules]
    for module in modules:
        module._redis.cache_clear()
        client = module._redis()
        assert module._redis() is client  # Lazy singleton, not a new pool per operation.
        kwargs = client.connection_pool.connection_kwargs
        assert 0 < kwargs['socket_timeout'] <= 0.25
        assert 0 < kwargs['socket_connect_timeout'] <= 0.25
        clients.append(client)
    try:
        yield
    finally:
        for client in clients:
            client.close()
            client.connection_pool.disconnect()
        for accessor in accessors:
            accessor.cache_clear()
        listener.close()


def bounded(call):
    started = time.monotonic()
    result = call()
    # Wide scheduling headroom; without the socket deadline these calls hang.
    assert time.monotonic() - started < 1.5
    return result


def test_s4_blackhole_reads_fall_back_to_firestore_and_writers_proceed(blackhole):
    firestore = Mock(return_value={'plan': 'basic'})
    assert bounded(lambda: s4_read_cache.cached_read('subscription_cache', 'u', '', firestore)) == {'plan': 'basic'}
    firestore.assert_called_once_with()
    durable_write = Mock()

    def write():
        with s4_read_cache.writing('subscription_cache', 'u'):
            durable_write()

    bounded(write)
    durable_write.assert_called_once_with()


def test_s4_blackhole_fill_preserves_firestore_result(blackhole, monkeypatch):
    client = s4_read_cache._redis()
    calls = []

    def eval(script, *args):
        calls.append(script)
        if script == s4_read_cache._READ:
            return ['v', '', int(time.time() * 1000)]
        return client.eval(script, *args)

    monkeypatch.setattr(s4_read_cache, '_redis', lambda: SimpleNamespace(eval=eval))
    firestore = Mock(return_value={'plan': 'basic'})
    assert bounded(lambda: s4_read_cache.cached_read('subscription_cache', 'u', '', firestore)) == {'plan': 'basic'}
    assert calls == [s4_read_cache._READ, s4_read_cache._PUBLISH]
    firestore.assert_called_once_with()


@pytest.mark.parametrize('phase', ['read', 'fill_check', 'fill', 'invalidate'])
def test_s5_candidates_blackhole_preserves_durable_reads_and_writes(blackhole, monkeypatch, phase):
    client = s5_candidates_cache._redis()
    durable = Mock(return_value=[])
    if phase in ('fill_check', 'fill'):
        # Allow the cold lookup; blackhole either the generation check or SET.
        gets = iter(['v', None] if phase == 'fill_check' else ['v', None, 'v'])
        initialized = False

        def get(key):
            value = next(gets, 'timeout')
            return client.get(key) if value == 'timeout' else value

        def set(key, value, **kwargs):
            nonlocal initialized
            if not initialized:
                initialized = True
                return True
            return client.set(key, value, **kwargs)

        monkeypatch.setattr(s5_candidates_cache, '_redis', lambda: SimpleNamespace(set=set, get=get))
    if phase == 'invalidate':
        assert bounded(lambda: s5_candidates_cache.invalidate_after_write(durable)('u')) == []
        durable.assert_called_once_with('u')
    else:
        assert bounded(lambda: s5_candidates_cache.load_compatibility_candidates('u', 7, durable)) == []
        durable.assert_called_once_with()


@pytest.mark.parametrize('phase', ['version', 'read', 'fill', 'invalidate'])
def test_s5_action_items_blackhole_fails_open(blackhole, phase):
    if phase == 'version':
        assert bounded(lambda: action_items_cache.get_action_items_list_version('u')) is None
    elif phase == 'read':
        assert bounded(lambda: action_items_cache.read_cached_list('page')) is None
    elif phase == 'fill':
        bounded(lambda: action_items_cache.write_cached_list('page', body={'items': []}, etag='etag', ttl=30))
    else:
        bounded(lambda: action_items_cache.bump_action_items_list_version('u'))


def test_s5_action_items_route_blackhole_falls_back_to_firestore(blackhole, monkeypatch):
    firestore = Mock(return_value=[])
    monkeypatch.setattr(router.action_items_db, 'get_action_items', firestore)
    monkeypatch.setattr(router, 'enforce_stale_client_list_refusal', lambda *_: None)
    monkeypatch.setattr(router, 'enforce_hot_client_list_ceiling', lambda *_: None)
    monkeypatch.setattr(
        router,
        'list_read_budget_for_request',
        lambda *a, **kw: SimpleNamespace(truncated=False, observe=lambda *_: None),
    )
    result = bounded(
        lambda: router.get_action_items(
            request=SimpleNamespace(headers={}),
            response=SimpleNamespace(headers={}),
            uid='u',
            limit=2,
            offset=0,
            completed=False,
            conversation_id='c',
            start_date=None,
            end_date=None,
            due_start_date=None,
            due_end_date=None,
        )
    )
    assert result == {'action_items': [], 'has_more': False, 'truncated': False}
    firestore.assert_called_once()


@pytest.mark.parametrize('phase', ['read', 'fill_check', 'fill', 'invalidate'])
def test_staged_negative_cache_blackhole_preserves_reads_and_writes(blackhole, monkeypatch, phase):
    client = staged_promote_cache._redis()
    monkeypatch.delenv('OMI_STAGED_TASK_PROMOTE_EMPTY_CACHE_ENABLED', raising=False)
    durable = Mock(return_value=[])
    if phase in ('fill_check', 'fill'):
        gets = iter([None] if phase == 'fill_check' else [None, 'v'])

        def get(key):
            value = next(gets, 'timeout')
            return client.get(key) if value == 'timeout' else value

        def set(key, value, **kwargs):
            return client.set(key, value, **kwargs) if kwargs.get('pxat') else True

        monkeypatch.setattr(
            staged_promote_cache, '_redis', lambda: SimpleNamespace(set=set, get=get, eval=lambda *a: 'v')
        )
    if phase == 'invalidate':
        assert bounded(lambda: staged_promote_cache.invalidate_around_write(durable)('u')) == []
        durable.assert_called_once_with('u')
    else:
        assert bounded(lambda: staged_promote_cache.load_projection('u', 7, durable)) == []
        durable.assert_called_once_with()
