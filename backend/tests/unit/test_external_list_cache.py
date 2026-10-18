"""Hermetic cache boundaries: encrypted bytes, isolation, age, outages, middleware."""

from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.testclient import TestClient
from routers import metrics
from utils import external_list_reads as cache
from utils.metrics import metrics_response
from utils.observability.external_lists import EXTERNAL_LIST_HTTP_TOTAL, ExternalListMetricsMiddleware, ROUTES


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
