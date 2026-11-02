"""Hermetic cache boundaries: encrypted bytes, isolation, age, outages, middleware."""

from concurrent.futures import Future
from threading import BoundedSemaphore
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.testclient import TestClient
from routers import metrics
from utils import external_list_reads as cache
from utils.metrics import metrics_response
from utils.other.timeout import TimeoutMiddleware
from utils.observability.external_lists import EXTERNAL_LIST_HTTP_TOTAL, ExternalListMetricsMiddleware, ROUTES


@pytest.fixture(autouse=True)
def isolate_flights(monkeypatch):
    monkeypatch.setattr(cache, '_flights', {})
    monkeypatch.setenv('OMI_EXTERNAL_LIST_SINGLE_FLIGHT_ENABLED', 'false')


class FakeRedis:
    def __init__(self):
        self.entries = {}
        self.expiries = {}
        self.gets = 0
        self.fail_get = False
        self.fail_set = False

    def get(self, key):
        self.gets += 1
        if self.fail_get:
            raise ConnectionError('offline')
        return self.entries.get(key)

    def set(self, key, value, *, px):
        if self.fail_set:
            raise ConnectionError('offline')
        self.entries[key] = value
        self.expiries[key] = int(cache.time.time() * 1000) + px


class PendingPopulations:
    """Explicit executor admission/completion control; no worker or sleeps."""

    def __init__(self):
        self.jobs = []

    def __call__(self, executor, fn, *args):
        assert executor is cache.db_executor
        future = Future()
        self.jobs.append((future, fn, args))
        return future

    def drain(self):
        for future, fn, args in self.jobs:
            if future.done():
                continue
            try:
                future.set_result(fn(*args))
            except Exception as exc:
                future.set_exception(exc)


def immediate_population(executor, fn, *args):
    queue = PendingPopulations()
    future = queue(executor, fn, *args)
    queue.drain()
    return future


@pytest.fixture
def populations(monkeypatch):
    queue = PendingPopulations()
    monkeypatch.setattr(cache, 'submit_with_context', queue)
    monkeypatch.setattr(cache, '_population_slots', BoundedSemaphore(cache.MAX_CACHE_POPULATIONS))
    yield queue
    for future, _, _ in queue.jobs:
        future.cancel()


@pytest.fixture
def storage(monkeypatch):
    redis = FakeRedis()
    monkeypatch.setattr(cache, '_client', redis)
    monkeypatch.delenv('OMI_EXTERNAL_LIST_CACHE_ENABLED', raising=False)
    return redis


def lookup(*, uid='owner', app='app', key='key', token='fake-key', query=None):
    request = Request(
        {
            'type': 'http',
            'method': 'GET',
            'path': '/v1/dev/user/memories',
            'headers': [(b'authorization', token.encode())],
            'query_string': b'',
        }
    )
    hit = cache.cached_list_response(
        request, Response(), uid=uid, context=SimpleNamespace(app_id=app, key_id=key), query=query or {'limit': 25}
    )
    return request, hit


def store(request, body=b'[{"content":"private fact"}]', headers=None, status=200):
    request.state.external_list_cache_entry.store(Response(body, status_code=status, headers=headers))


def test_encrypted_full_bytes_and_query_normalization(storage):
    request, hit = lookup(query={'offset': 0, 'limit': 25})
    assert hit is None
    store(request, headers={'X-Omi-Has-More': 'true', 'X-Omi-Next-Offset': '25', 'X-Omi-Ignored-Query-Params': '9'})
    _, hit = lookup(query={'limit': 25, 'offset': 0})
    assert hit.body == b'[{"content":"private fact"}]'
    assert hit.headers['X-Omi-Next-Offset'] == '25'
    assert 'X-Omi-Ignored-Query-Params' not in hit.headers
    assert all(b'private fact' not in raw for raw in storage.entries.values())
    assert all('owner' not in key and 'fake-key' not in key for key in storage.entries)


@pytest.mark.parametrize(
    'change',
    [
        {'uid': 'other'},
        {'app': 'other'},
        {'key': 'other'},
        {'token': 'other'},
        {'query': {'limit': 26}},
        {'query': {'limit': 25, 'offset': 25}},
        {'query': {'limit': 25, 'categories': ['work']}},
    ],
)
def test_identity_filter_and_page_isolation(storage, change):
    request, _ = lookup()
    store(request)
    assert lookup(**change)[1] is None


def test_absolute_ttl_from_query_start_and_expired_read(storage, monkeypatch):
    now = [1000.0]
    mono = [20.0]
    monkeypatch.setattr(cache.time, 'time', lambda: now[0])
    monkeypatch.setattr(cache.time, 'monotonic', lambda: mono[0])
    request, _ = lookup()
    now[0] += 7
    mono[0] += 7
    store(request)
    assert list(storage.expiries.values()) == [1010000]
    assert lookup()[1] is not None
    now[0] = 1010
    mono[0] = 30
    assert lookup()[1] is None  # Even if Redis returns an expired entry.


def test_slow_query_and_older_concurrent_writer_never_refresh_age(storage, monkeypatch):
    now = [1000.0]
    mono = [20.0]
    monkeypatch.setattr(cache.time, 'time', lambda: now[0])
    monkeypatch.setattr(cache.time, 'monotonic', lambda: mono[0])
    old, _ = lookup()
    now[0] += 5
    mono[0] += 5
    newer, _ = lookup()
    store(newer, b'[]')
    now[0] += 6
    mono[0] += 6
    store(old, b'["stale"]')
    assert lookup()[1].body == b'[]'
    assert list(storage.expiries.values()) == [1015000]


@pytest.mark.parametrize(
    'headers,status',
    [
        ({'X-Omi-List-Truncated': 'true'}, 200),
        ({'X-Scan-Truncated': 'true'}, 200),
        ({}, 429),
        ({}, 500),
    ],
)
def test_errors_and_truncated_pages_are_not_stored(storage, headers, status):
    request, _ = lookup()
    store(request, headers=headers, status=status)
    assert not storage.entries


def test_size_limit_flag_off_and_fail_open(storage, monkeypatch):
    request, _ = lookup()
    store(request, b'x' * (cache.MAX_BODY_BYTES + 1))
    assert not storage.entries
    storage.fail_get = storage.fail_set = True
    request, hit = lookup()
    assert hit is None
    store(request)
    monkeypatch.setenv('OMI_EXTERNAL_LIST_CACHE_ENABLED', 'false')
    before = storage.gets
    request, hit = lookup()
    assert hit is None and storage.gets == before
    assert not hasattr(request.state, 'external_list_cache_entry')


def test_corrupt_or_context_swapped_ciphertext_is_a_miss(storage):
    first, _ = lookup()
    store(first)
    second, _ = lookup(key='other')
    storage.entries[second.state.external_list_cache_entry.key] = next(iter(storage.entries.values()))
    assert lookup(key='other')[1] is None
    storage.entries[first.state.external_list_cache_entry.key] = b'garbage'
    assert lookup()[1] is None


@pytest.mark.parametrize('path', sorted(ROUTES))
def test_http_metrics_cover_errors_and_are_exported(storage, monkeypatch, path):
    app = FastAPI()
    app.add_middleware(ExternalListMetricsMiddleware)

    @app.get(path)
    def route(status: int = 200):
        if status != 200:
            raise HTTPException(status)
        return []

    client = TestClient(app)
    for status, outcome in [
        (200, 'success'),
        (401, 'auth_error'),
        (403, 'auth_error'),
        (429, 'rate_limited'),
        (400, 'validation_error'),
        (500, 'server_error'),
    ]:
        metric = EXTERNAL_LIST_HTTP_TOTAL.labels(route=path, outcome=outcome)
        before = metric._value.get()
        assert client.get(path, params={'status': status}).status_code == status
        assert metric._value.get() == before + 1
    assert client.get(path + '?status=invalid').status_code == 422
    exported = metrics_response().body.decode()
    assert 'omi_external_list_http_requests_total{' in exported
    assert f'route="{path}"' in exported
    monkeypatch.setenv('OMI_EXTERNAL_LIST_METRICS_ENABLED', 'false')
    metric = EXTERNAL_LIST_HTTP_TOTAL.labels(route=path, outcome='success')
    before = metric._value.get()
    assert client.get(path).status_code == 200
    assert metric._value.get() == before


def test_real_metrics_endpoint_and_cloud_run_export_filter(monkeypatch):
    monkeypatch.setenv('METRICS_SECRET', 'offline-metrics')
    app = FastAPI()
    app.include_router(metrics.router)
    EXTERNAL_LIST_HTTP_TOTAL.labels(route='/v1/mcp/memories', outcome='success').inc()
    response = TestClient(app).get('/metrics', headers={'Authorization': 'Bearer offline-metrics'})
    assert response.status_code == 200
    assert 'omi_external_list_http_requests_total{' in response.text
    assert EXTERNAL_LIST_HTTP_TOTAL._labelnames == ('route', 'outcome')
    config = (Path(__file__).resolve().parents[2] / 'deploy/cloud_run_gmp_sidecar.yaml').read_text()
    assert 'port: 9090' in config and 'path: /metrics' in config and 'regex: omi_.*' in config


def test_http_metrics_observe_timeout_response_outside_timeout_middleware(monkeypatch):
    monkeypatch.delenv('OMI_EXTERNAL_LIST_METRICS_ENABLED', raising=False)
    path = '/v1/mcp/memories'
    app = FastAPI()
    app.add_middleware(TimeoutMiddleware, methods_timeout={'GET': 0})
    app.add_middleware(ExternalListMetricsMiddleware)

    @app.get(path)
    async def expired_list():
        raise AssertionError('The expired middleware deadline must answer before dispatch')

    metric = EXTERNAL_LIST_HTTP_TOTAL.labels(route=path, outcome='server_error')
    before = metric._value.get()
    assert TestClient(app).get(path).status_code == 504
    assert metric._value.get() == before + 1


@pytest.mark.parametrize(
    'offset,limit,expected', [(-10, -5, (0, 1)), (-1, 0, (0, 1)), (5, 99999, (5, 200)), (7, 25, (7, 25))]
)
def test_sensitive_read_page_clamp(offset, limit, expected):
    assert cache.clamp_list_page(offset, limit, 200) == expected


def test_completed_response_does_not_wait_for_cache_population(storage, populations):
    app = FastAPI()
    app.router.route_class = cache.ExternalListCacheRoute
    path = '/v1/dev/user/memories'

    @app.get(path)
    def route(request: Request):
        hit = cache.cached_list_response(request, Response(), uid='owner', context=SimpleNamespace(), query={})
        return hit if hit is not None else [{'content': 'private fact'}]

    client = TestClient(app)
    response = client.get(path)
    assert response.status_code == 200 and response.json() == [{'content': 'private fact'}]
    assert len(populations.jobs) == 1 and not populations.jobs[0][0].done()
    assert not storage.entries  # Executor admission has not started the writer.
    populations.drain()
    assert client.get(path).content == response.content
    assert len(populations.jobs) == 1
    assert storage.entries


@pytest.mark.parametrize('completion', ['success', 'failure', 'cancel'])
def test_population_saturation_and_all_terminal_states_release_slots(storage, populations, completion):
    request, _ = lookup()
    entry = request.state.external_list_cache_entry
    response = Response(b'x' * cache.MAX_BODY_BYTES)
    for _ in range(cache.MAX_CACHE_POPULATIONS + 1):
        cache._queue_population(entry, response)
    assert len(populations.jobs) == 32  # Hard bound: at most 8 MiB of eligible bodies.
    first = populations.jobs[0][0]
    if completion == 'success':
        first.set_result(None)
    elif completion == 'failure':
        first.set_exception(RuntimeError('offline synthetic writer error'))
    else:
        assert first.cancel()
    cache._queue_population(entry, response)
    assert len(populations.jobs) == 33  # Exactly one terminal job freed one slot.
    cache._queue_population(entry, response)
    assert len(populations.jobs) == 33


def test_submission_failure_is_open_and_releases_slot(storage, populations, monkeypatch):
    request, _ = lookup()
    entry = request.state.external_list_cache_entry
    monkeypatch.setattr(cache, '_population_slots', BoundedSemaphore(1))

    def reject(*args):
        raise RuntimeError('offline executor admission failure')

    monkeypatch.setattr(cache, 'submit_with_context', reject)
    cache._queue_population(entry, Response(b'[]'))
    monkeypatch.setattr(cache, 'submit_with_context', populations)
    cache._queue_population(entry, Response(b'[]'))
    assert len(populations.jobs) == 1
    populations.drain()
    assert lookup()[1].body == b'[]'


@pytest.mark.parametrize(
    'ineligible', ['error', 'shared_truncated', 'scan_truncated', 'oversized', 'wall_expired', 'age_expired']
)
def test_ineligible_population_skips_executor_admission(storage, populations, ineligible):
    request, _ = lookup()
    entry = request.state.external_list_cache_entry
    response = Response(b'[]')
    if ineligible == 'error':
        response.status_code = 500
    elif ineligible == 'shared_truncated':
        response.headers['X-Omi-List-Truncated'] = 'true'
    elif ineligible == 'scan_truncated':
        response.headers['X-Scan-Truncated'] = 'true'
    elif ineligible == 'oversized':
        response = Response(b'x' * (cache.MAX_BODY_BYTES + 1))
    elif ineligible == 'wall_expired':
        entry.expires_at = cache.time.time() - 1
    else:
        entry.started = cache.time.monotonic() - cache.TTL_SECONDS
    cache._queue_population(entry, response)
    assert not populations.jobs and not storage.entries


def test_queued_population_preserves_expiry_and_drops_expired_work(storage, populations, monkeypatch):
    now = [1000.0]
    mono = [20.0]
    monkeypatch.setattr(cache.time, 'time', lambda: now[0])
    monkeypatch.setattr(cache.time, 'monotonic', lambda: mono[0])
    request, _ = lookup()
    cache._queue_population(request.state.external_list_cache_entry, Response(b'[]'))
    now[0] += 7
    mono[0] += 7
    populations.drain()
    assert list(storage.expiries.values()) == [1010000]
    request, _ = lookup(query={'limit': 26})
    cache._queue_population(request.state.external_list_cache_entry, Response(b'[]'))
    now[0] += 11
    mono[0] += 11
    populations.drain()
    assert len(storage.entries) == 1  # The expired queued writer added nothing.
