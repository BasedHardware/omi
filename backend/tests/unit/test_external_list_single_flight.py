"""Identical simultaneous authorized misses share only eligible final bytes."""

import asyncio
from concurrent.futures import Future, ThreadPoolExecutor
import threading
from types import SimpleNamespace

import pytest
from fastapi import APIRouter, Depends, FastAPI, Request, Response
from fastapi.testclient import TestClient

from tests.unit.test_external_list_cache import FakeRedis
from utils import external_list_reads as cache


@pytest.fixture
def storage(monkeypatch):
    monkeypatch.setattr(cache, '_client', FakeRedis())
    monkeypatch.setattr(cache, '_flights', {})
    monkeypatch.setattr(cache, '_waiter_slots', threading.BoundedSemaphore(cache.MAX_CACHE_WAITERS))
    monkeypatch.delenv('OMI_EXTERNAL_LIST_CACHE_ENABLED', raising=False)
    monkeypatch.delenv('OMI_EXTERNAL_LIST_SINGLE_FLIGHT_ENABLED', raising=False)


def lookup(query=None, uid='owner', route='/v1/dev/user/memories'):
    request = Request({'type': 'http', 'method': 'GET', 'path': route, 'headers': [], 'query_string': b''})
    response = Response(headers={'X-Omi-Ignored-Query-Params': 'current-request'})
    hit = cache.cached_list_response(
        request, response, uid=uid, context=SimpleNamespace(app_id='app', key_id='key'), query=query or {'limit': 25}
    )
    return request, hit


@pytest.mark.parametrize('version_changes', [False, True])
def test_follower_bytes_headers_and_writer_version(storage, monkeypatch, version_changes):
    waiting = threading.Event()

    class WaitingFuture(Future):
        def result(self, *args, **kwargs):
            waiting.set()
            return super().result(*args, **kwargs)

    monkeypatch.setattr(cache, 'Future', WaitingFuture)
    version = ['v1']
    monkeypatch.setattr(cache.action_item_versions, 'version', lambda uid: version[0])
    path = '/v1/dev/user/action-items'
    leader, _ = lookup(route=path)
    with ThreadPoolExecutor(max_workers=1) as pool:
        follower = pool.submit(lookup, route=path)
        assert waiting.wait(1)
        if version_changes:
            version[0] = 'v2'
        entry = leader.state.external_list_cache_entry
        entry.complete(Response(b'[{"id":"same"}]', headers={'X-Omi-Has-More': 'true', 'X-Request-Id': 'leader'}))
        request, hit = follower.result(1)
    if version_changes:
        assert hit is None
    else:
        assert hit.body == b'[{"id":"same"}]'
        assert hit.headers['x-omi-has-more'] == 'true'
        assert hit.headers['x-omi-ignored-query-params'] == 'current-request'
        assert 'x-request-id' not in hit.headers
        assert request.state.external_list_cache_entry is None
    assert not cache._flights


@pytest.mark.parametrize(
    'response', [None, Response(status_code=500), Response(b'[]', headers={'X-Omi-List-Truncated': 'true'})]
)
def test_failed_or_incomplete_owner_releases_waiter_to_origin(storage, monkeypatch, response):
    leader, _ = lookup()
    pending = leader.state.external_list_cache_entry.flight
    assert pending is not None
    leader.state.external_list_cache_entry.complete(response)
    assert pending.result() is None and not cache._flights


def test_identity_query_limits_and_capacity_do_not_join(storage, monkeypatch):
    leader, _ = lookup()
    other, hit = lookup(uid='other')
    assert (
        hit is None
        and other.state.external_list_cache_entry.flight is not leader.state.external_list_cache_entry.flight
    )
    filtered, hit = lookup(query={'limit': 26})
    assert hit is None and len(cache._flights) == 3
    monkeypatch.setattr(cache, 'MAX_CACHE_POPULATIONS', 3)
    full, hit = lookup(query={'limit': 27})
    assert hit is None and full.state.external_list_cache_entry.flight is None
    assert len(cache._flights) == 3
    monkeypatch.setenv('OMI_EXTERNAL_LIST_SINGLE_FLIGHT_ENABLED', 'false')
    disabled, hit = lookup()
    assert hit is None and disabled.state.external_list_cache_entry.flight is None


def test_timeout_bypasses_and_event_loop_never_waits(storage, monkeypatch):
    leader, _ = lookup()
    pending = leader.state.external_list_cache_entry.flight
    monkeypatch.setattr(pending, 'result', lambda **kwargs: (_ for _ in ()).throw(TimeoutError()))
    follower, hit = lookup()
    assert hit is None and follower.state.external_list_cache_entry.flight is None

    async def on_loop():
        separate, hit = lookup(query={'limit': 26})
        assert hit is None and separate.state.external_list_cache_entry.flight is None

    asyncio.run(on_loop())


def test_owner_deadline_does_not_renew_and_completion_has_no_io(storage, monkeypatch):
    now = [1000.0]
    mono = [0.0]
    monkeypatch.setattr(cache.time, 'time', lambda: now[0])
    monkeypatch.setattr(cache.time, 'monotonic', lambda: mono[0])
    leader, _ = lookup()
    pending = leader.state.external_list_cache_entry.flight
    mono[0] = 10
    now[0] = 1010
    successor, _ = lookup()
    assert pending.done() and pending.result() is None
    assert successor.state.external_list_cache_entry.flight is not pending
    monkeypatch.setattr(cache.action_item_versions, 'version', lambda uid: (_ for _ in ()).throw(AssertionError('I/O')))
    asyncio.run(_complete_without_io(leader.state.external_list_cache_entry))
    assert len(cache._flights) == 1


async def _complete_without_io(entry):
    entry.complete(Response(b'[]'))


def test_waiters_are_bounded_globally_and_saturation_bypasses_immediately(storage, monkeypatch):
    waiting = threading.Event()
    counter_lock = threading.Lock()
    waits = []

    class WaitingFuture(Future):
        def result(self, *args, **kwargs):
            with counter_lock:
                waits.append('waiting')
                if len(waits) == 2:
                    waiting.set()
            return super().result(*args, **kwargs)

    monkeypatch.setattr(cache, 'Future', WaitingFuture)
    monkeypatch.setattr(cache, '_waiter_slots', threading.BoundedSemaphore(2))
    first, _ = lookup(query={'limit': 25})
    second, _ = lookup(query={'limit': 26})
    with ThreadPoolExecutor(max_workers=3) as pool:
        one = pool.submit(lookup, query={'limit': 25})
        two = pool.submit(lookup, query={'limit': 26})
        try:
            assert waiting.wait(3)
            excess, hit = pool.submit(lookup, query={'limit': 25}).result(3)
            assert hit is None and excess.state.external_list_cache_entry.flight is None
            assert len(waits) == 2  # Excess never entered the blocking primitive.
        finally:
            first.state.external_list_cache_entry.complete(Response(b'[]'))
            second.state.external_list_cache_entry.complete(Response(b'[]'))
        assert one.result(3)[1].body == two.result(3)[1].body == b'[]'
    # Completion, timeout and error paths must return the global admission slots.
    assert cache._waiter_slots.acquire(blocking=False)
    assert cache._waiter_slots.acquire(blocking=False)
    assert not cache._waiter_slots.acquire(blocking=False)


def test_real_route_finalization_coalesces_after_each_authorization(storage, monkeypatch):
    started, waiting, release = threading.Event(), threading.Event(), threading.Event()
    authorized, reads = [], []

    class WaitingFuture(Future):
        def result(self, *args, **kwargs):
            waiting.set()
            return super().result(*args, **kwargs)

    monkeypatch.setattr(cache, 'Future', WaitingFuture)
    monkeypatch.setattr(cache, '_queue_population', lambda *args: None)
    app = FastAPI()
    router = APIRouter(route_class=cache.ExternalListCacheRoute)

    def authorize():
        authorized.append('authorized')
        return SimpleNamespace(app_id='app', key_id='key')

    @router.get('/v1/dev/user/memories')
    def endpoint(request: Request, response: Response, context=Depends(authorize)):
        hit = cache.cached_list_response(request, response, uid='owner', context=context, query={'limit': 25})
        if hit is not None:
            return hit
        reads.append('source')
        started.set()
        assert release.wait(3)
        response.headers['X-Omi-Has-More'] = 'false'
        return [{'id': 'same'}]

    app.include_router(router)
    client = TestClient(app)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(client.get, '/v1/dev/user/memories')
        try:
            assert started.wait(3)
            second = pool.submit(client.get, '/v1/dev/user/memories')
            assert waiting.wait(3)
        finally:
            release.set()
        responses = [first.result(3), second.result(3)]
    assert authorized == ['authorized', 'authorized'] and reads == ['source']
    assert all(response.status_code == 200 and response.json() == [{'id': 'same'}] for response in responses)
    assert all(response.headers['X-Omi-Has-More'] == 'false' for response in responses)
    assert not cache._flights
