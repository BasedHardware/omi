"""Real local Redis Lua/compatibility-cache acceptance; no configured services."""

import shutil
import subprocess
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from unittest.mock import Mock

import pytest
import redis

from database import s5_candidates_cache as compat, staged_promote_cache as cache
from routers import staged_tasks as route
from tests.unit.test_staged_promote_empty_cache import EMPTY, STAGED_PROMOTE_ROUTE, candidate, serving
from tests.unit.test_staged_promote_coupled_cache import create_pending

pytestmark = pytest.mark.integration


@pytest.fixture
def local_redis():
    binary = shutil.which('redis-server')
    assert binary, 'local redis-server required'
    with tempfile.TemporaryDirectory(prefix='staged-fence-') as directory:
        socket = directory + '/r.sock'
        process = subprocess.Popen(
            [binary, '--port', '0', '--unixsocket', socket, '--save', '', '--appendonly', 'no'],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        client = redis.Redis(unix_socket_path=socket, socket_timeout=0.2, socket_connect_timeout=0.2)
        try:
            deadline = time.monotonic() + 5
            while True:
                try:
                    if client.ping():
                        break
                except redis.ConnectionError:
                    if time.monotonic() >= deadline:
                        raise
                    time.sleep(0.02)
            yield client
        finally:
            client.close()
            process.terminate()
            process.wait(timeout=5)


class Faults:
    def __init__(self, client):
        self.client = client
        self.compat_failure = False
        self.final_failure = False
        self.final_publication_failure = False
        self.compat_reply_lost = False

    def __getattr__(self, name):
        return getattr(self.client, name)

    def set(self, key, value, **kwargs):
        if key == compat._version_key('owner') and not kwargs.get('nx'):
            if self.compat_reply_lost:
                self.client.set(key, value, **kwargs)
                raise redis.ConnectionError('applied compatibility SET; reply lost')
            if self.compat_failure:
                raise redis.ConnectionError('synthetic compatibility SET failure')
        return self.client.set(key, value, **kwargs)

    def eval(self, script, *args):
        if script == cache._END_WRITE and self.final_failure:
            raise redis.ConnectionError('synthetic final fence failure')
        if script == cache._END_WRITE and self.final_publication_failure:
            # Redis scripts do not roll back earlier commands after an error.
            # Expiry zero fails only the last SET EX, after busy + token removal.
            return self.client.eval(script, *args[:-1], 0)
        return self.client.eval(script, *args)


@pytest.fixture
def coupled_local(local_redis, monkeypatch):
    proxy = Faults(local_redis)
    monkeypatch.setattr(cache, '_redis', lambda: proxy)
    monkeypatch.setattr(compat, '_redis', lambda: proxy)
    monkeypatch.delenv('OMI_STAGED_TASK_PROMOTE_EMPTY_CACHE_ENABLED', raising=False)
    monkeypatch.setenv('FIRESTORE_READ_LEVERS', '{"candidates_page":100}')
    monkeypatch.setenv('CANDIDATES_COMPATIBILITY_CACHE_TTL_SECONDS', '30')
    routes = serving.__wrapped__(monkeypatch, (None, proxy))
    monkeypatch.setattr(route, 'load_compatibility_candidates', compat.load_compatibility_candidates)
    return routes, proxy


def expire_compatibility_entry(client):
    entries = list(client.scan_iter('fsr:s5:candidates:owner:7:*'))
    assert entries
    for key in entries:
        assert 0 < client.pttl(key) <= 30000
        client.pexpire(key, 1)
    deadline = time.monotonic() + 2
    while any(client.exists(key) for key in entries):
        assert time.monotonic() < deadline
        time.sleep(0.002)


def test_real_lua_90_second_expiry_owner_generation_and_write_seam(coupled_local):
    _, proxy = coupled_local
    rows, calls = [], []

    def origin():
        calls.append(1)
        return rows[:]

    assert cache.load_projection('owner', 7, origin) == []
    entries = list(proxy.scan_iter(cache._version_key('owner') + ':*'))
    assert len(entries) == 1
    ttl = proxy.pttl(entries[0])
    assert 0 < ttl <= 90000
    assert cache.load_projection('owner', 7, origin) == [] and len(calls) == 1
    cache.load_projection('owner', 8, origin)
    cache.load_projection('other', 7, origin)
    assert len(calls) == 3

    @cache.invalidate_around_write
    def mutation(uid):
        rows.append({'id': 'new'})
        return 'committed'

    assert mutation('owner') == 'committed'
    assert cache.load_projection('owner', 7, origin) == rows and len(calls) == 4
    print(
        {
            'redis_version': proxy.info('server')['redis_version'],
            'empty_pttl_ms': ttl,
            'owner_generation_isolation': True,
            'write_invalidated': True,
        }
    )


def test_actual_compatibility_set_failure_cannot_gain_a_90_second_negative(coupled_local, monkeypatch):
    (client, store, selected, _), proxy = coupled_local
    assert client.post(STAGED_PROMOTE_ROUTE).content == EMPTY
    old = proxy.get(compat._version_key('owner'))
    before = cache.OPERATIONS.labels(outcome='stored')._value.get()
    proxy.compat_failure = True
    created = create_pending(monkeypatch, store)
    assert proxy.get(compat._version_key('owner')) == old
    for _ in range(3):
        assert client.post(STAGED_PROMOTE_ROUTE).content == EMPTY
    assert cache.OPERATIONS.labels(outcome='stored')._value.get() == before
    assert proxy.get(cache._version_key('owner')) == cache.BUSY.encode()
    expire_compatibility_entry(proxy)
    assert client.post(STAGED_PROMOTE_ROUTE).json()['promoted'] is True
    selected.assert_called_once_with(created.candidate_id, uid='owner')
    assert cache.OPERATIONS.labels(outcome='stored')._value.get() == before


@pytest.mark.parametrize('dependency_fails', [False, True])
def test_real_redis_partial_commit_finally_preserves_error_and_rotates_dependency(coupled_local, dependency_fails):
    (client, store, selected, _), proxy = coupled_local
    assert client.post(STAGED_PROMOTE_ROUTE).content == EMPTY
    old = proxy.get(compat._version_key('owner'))
    proxy.compat_failure = dependency_fails
    error = RuntimeError('synthetic committed prefix')
    count = []

    @compat.invalidate_after_write
    def mutation(uid):
        count.append(uid)
        store.rows['users/owner/candidates/canonical'] = candidate()
        raise error

    with pytest.raises(RuntimeError) as raised:
        mutation('owner')
    assert raised.value is error and count == ['owner']
    if dependency_fails:
        assert proxy.get(compat._version_key('owner')) == old
        assert client.post(STAGED_PROMOTE_ROUTE).content == EMPTY
        expire_compatibility_entry(proxy)
    else:
        assert proxy.get(compat._version_key('owner')) != old
    assert client.post(STAGED_PROMOTE_ROUTE).json()['promoted'] is True
    selected.assert_called_once_with('canonical', uid='owner')


@pytest.mark.parametrize('second_fails', [False, True])
def test_real_lua_overlapping_writers_do_not_lock_or_release_each_other(coupled_local, second_fails):
    _, proxy = coupled_local
    started, release = Event(), Event()
    calls = []

    @compat.invalidate_after_write
    def first(uid):
        calls.append('first')
        started.set()
        assert release.wait(5)
        return 'first'

    @compat.invalidate_after_write
    def second(uid):
        calls.append('second')
        return 'second'

    origin = Mock(return_value=[])
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(first, 'owner')
        try:
            assert started.wait(5)
            proxy.compat_failure = second_fails
            assert second('owner') == 'second'  # Completes while first remains in flight.
            proxy.compat_failure = False
            assert not future.done()
            assert cache.load_projection('owner', 7, origin) == []
            assert proxy.get(cache._version_key('owner')) == cache.BUSY.encode()
        finally:
            release.set()
        assert future.result(timeout=5) == 'first'
    assert calls == ['first', 'second']
    cache.load_projection('owner', 7, origin)
    cache.load_projection('owner', 7, origin)
    assert origin.call_count == (3 if second_fails else 2)


def test_real_lua_read_during_write_failed_final_fence_cannot_store(coupled_local):
    (client, store, selected, _), proxy = coupled_local
    assert client.post(STAGED_PROMOTE_ROUTE).content == EMPTY
    before = cache.OPERATIONS.labels(outcome='stored')._value.get()

    @compat.invalidate_after_write
    def mutation(uid):
        assert client.post(STAGED_PROMOTE_ROUTE).content == EMPTY
        assert cache.OPERATIONS.labels(outcome='stored')._value.get() == before
        store.rows['users/owner/candidates/canonical'] = candidate()
        proxy.final_failure = True
        return 'committed'

    assert mutation('owner') == 'committed'
    assert client.post(STAGED_PROMOTE_ROUTE).json()['promoted'] is True
    selected.assert_called_once_with('canonical', uid='owner')
    assert proxy.get(cache._version_key('owner')) == cache.BUSY.encode()
    assert cache.OPERATIONS.labels(outcome='stored')._value.get() == before


def test_real_lua_version_eviction_cannot_release_inflight_writer(coupled_local):
    _, proxy = coupled_local
    origin = Mock(return_value=[])

    @cache.invalidate_around_write
    def mutation(uid):
        proxy.delete(cache._version_key(uid))
        cache.load_projection(uid, 7, origin)
        assert not list(proxy.scan_iter(cache._version_key(uid) + ':7:*'))

    mutation('owner')
    cache.load_projection('owner', 7, origin)
    cache.load_projection('owner', 7, origin)
    assert origin.call_count == 2


def test_real_redis_uncertain_compatibility_reply_stays_bypassed(coupled_local, monkeypatch):
    (client, store, _, _), proxy = coupled_local
    assert client.post(STAGED_PROMOTE_ROUTE).content == EMPTY
    proxy.compat_reply_lost = True
    create_pending(monkeypatch, store)
    assert client.post(STAGED_PROMOTE_ROUTE).json()['promoted'] is True
    assert proxy.get(cache._version_key('owner')) == cache.BUSY.encode()


def test_real_lua_failed_final_publication_preserves_busy_without_writer_hash(coupled_local):
    (client, store, selected, _), proxy = coupled_local
    assert client.post(STAGED_PROMOTE_ROUTE).content == EMPTY
    before = cache.OPERATIONS.labels(outcome='stored')._value.get()

    @compat.invalidate_after_write
    def mutation(uid):
        assert client.post(STAGED_PROMOTE_ROUTE).content == EMPTY
        store.rows['users/owner/candidates/canonical'] = candidate()
        proxy.final_publication_failure = True
        return 'committed'

    assert mutation('owner') == 'committed'
    assert proxy.get(cache._version_key('owner')) == cache.BUSY.encode()
    assert not proxy.exists(cache._version_key('owner') + ':writers')
    assert client.post(STAGED_PROMOTE_ROUTE).json()['promoted'] is True
    selected.assert_called_once_with('canonical', uid='owner')
    assert cache.OPERATIONS.labels(outcome='stored')._value.get() == before
