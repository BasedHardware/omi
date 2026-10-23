"""Shared catalog read counts, concurrent fill, TTL, empty results and isolation."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event

import pytest

from database import apps
from database.cache_manager import InMemoryCacheManager
from database import cache as shared_cache
from redis.exceptions import ConnectionError


@pytest.fixture
def catalog(monkeypatch):
    memory = InMemoryCacheManager()
    monkeypatch.setattr(apps, 'get_memory_cache', lambda: memory)
    monkeypatch.setattr(apps, 'get_generic_cache', lambda key: None)
    monkeypatch.setattr(apps, 'set_generic_cache', lambda *args: None)
    calls = []

    def read():
        calls.append(1)
        return [{'id': 'public', 'name': 'Public', 'description': 'catalog', 'capabilities': ['chat']}]

    monkeypatch.setattr(apps, 'get_public_approved_apps_db', read)
    return memory, calls


def test_reuses_catalog_and_returns_independent_records(catalog):
    memory, calls = catalog
    first = apps.get_public_approved_apps_cached_db()
    first[0]['capabilities'].append('mutated')
    assert apps.get_public_approved_apps_cached_db()[0]['capabilities'] == ['chat']
    assert len(calls) == 1
    entry = memory.cache[apps.PUBLIC_APPROVED_APPS_CACHE_KEY]
    assert entry.ttl == 30
    entry.timestamp -= 31
    apps.get_public_approved_apps_cached_db()
    assert len(calls) == 2
    memory.delete(apps.PUBLIC_APPROVED_APPS_CACHE_KEY)
    apps.get_public_approved_apps_cached_db()
    assert len(calls) == 3


def test_empty_catalog_and_redis_empty_set_are_hits(catalog, monkeypatch):
    _, calls = catalog
    monkeypatch.setattr(apps, 'get_generic_cache', lambda key: [])
    assert apps.get_public_approved_apps_cached_db() == []
    assert apps.get_public_approved_apps_cached_db() == []
    assert calls == []


def test_simultaneous_cold_readers_make_one_database_query(catalog, monkeypatch):
    _, calls = catalog
    ready, entered, release = Barrier(9), Event(), Event()

    def read():
        calls.append(1)
        entered.set()
        assert release.wait(5)
        return []

    def request():
        ready.wait(timeout=5)
        return apps.get_public_approved_apps_cached_db()

    monkeypatch.setattr(apps, 'get_public_approved_apps_db', read)
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = [pool.submit(request) for _ in range(8)]
        ready.wait(timeout=5)
        assert entered.wait(5)
        release.set()
        assert [f.result(timeout=5) for f in futures] == [[]] * 8
    assert len(calls) == 1


def test_kill_switch_and_failed_fill_do_not_cache_errors(catalog, monkeypatch):
    _, calls = catalog
    monkeypatch.setenv('FSR_PUBLIC_CATALOG_CACHE', 'off')
    apps.get_public_approved_apps_cached_db()
    apps.get_public_approved_apps_cached_db()
    assert len(calls) == 2
    monkeypatch.delenv('FSR_PUBLIC_CATALOG_CACHE')

    def fail():
        raise RuntimeError('synthetic database failure')

    monkeypatch.setattr(apps, 'get_public_approved_apps_db', fail)
    with pytest.raises(RuntimeError):
        apps.get_public_approved_apps_cached_db()
    monkeypatch.setattr(apps, 'get_public_approved_apps_db', lambda: [])
    assert apps.get_public_approved_apps_cached_db() == []


def test_pubsub_unavailable_preserves_database_read(catalog, monkeypatch):
    _, calls = catalog

    def unavailable():
        raise ConnectionError('synthetic unavailable subscriber')

    monkeypatch.setattr(apps, 'get_memory_cache', unavailable)
    assert apps.get_public_approved_apps_cached_db()[0]['id'] == 'public'
    assert len(calls) == 1


def test_simultaneous_first_requests_initialize_one_shared_cache(monkeypatch):
    ready, entered, release = Barrier(9), Event(), Event()
    instances = []

    class Subscriber:
        def __init__(self, client):
            instances.append(self)

        def register_callback(self, *args):
            pass

        def start(self):
            entered.set()
            assert release.wait(5)

    monkeypatch.setattr(shared_cache, '_initialized', False)
    monkeypatch.setattr(shared_cache, '_memory_cache', None)
    monkeypatch.setattr(shared_cache, '_pubsub_manager', None)
    monkeypatch.setattr(shared_cache, 'RedisPubSubManager', Subscriber)

    def request():
        ready.wait(timeout=5)
        return shared_cache.get_memory_cache()

    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = [pool.submit(request) for _ in range(8)]
        ready.wait(timeout=5)
        assert entered.wait(5)
        release.set()
        values = [future.result(timeout=5) for future in futures]
    assert len(instances) == 1
    assert all(value is values[0] for value in values)
