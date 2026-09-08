"""Tests for the static map proxy: GET /v1/static-map and utils/static_map.py.

The route is the app's only map-preview seam: auth keeps it from becoming an
open image proxy on the project's Maps key, malformed pins fail fast with 400,
upstream failures surface 502 (the app renders its offline pin-dot canvas), and
rendered bytes are cached in Redis keyed by the quantized pin set + size so
repeat renders of the same place never re-bill the provider.

Direct-call pattern from tests/routers/test_imports.py; the utils-level cache
paths are covered with a fake Redis against the real fetch_static_map.
"""

import asyncio
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

import utils.static_map as static_map_mod
from routers import static_map as static_map_router

UID = 'user-1'


# ---------------------------------------------------------------------------
# Route-level contract
# ---------------------------------------------------------------------------


def _get(pins, width=300, height=150, uid=UID):
    # The endpoint is async; direct-call tests run its coroutine to completion.
    return asyncio.run(static_map_router.get_static_map(pins=pins, width=width, height=height, uid=uid))


def test_malformed_pins_are_rejected_with_400():
    for bad in ['abc', '1.0', '1.0,2.0,3.0', '91,0', '0,181', 'a,b', '']:
        with pytest.raises(HTTPException) as excinfo:
            _get(bad)
        assert excinfo.value.status_code == 400, bad


def test_upstream_failure_is_502_not_an_error_image():
    with patch.object(static_map_router, 'fetch_static_map', return_value=None) as fetch:
        with pytest.raises(HTTPException) as excinfo:
            _get('37.7749,-122.4194')
    fetch.assert_awaited_once()
    assert excinfo.value.status_code == 502


def test_upstream_failure_records_the_client_canvas_fallback():
    with patch.object(static_map_router, 'fetch_static_map', return_value=None):
        with patch.object(static_map_router, 'record_fallback') as fallback:
            with pytest.raises(HTTPException):
                _get('37.7749,-122.4194')
    fallback.assert_called_once_with(
        component='static_map',
        from_mode='provider_static_map',
        to_mode='client_pin_canvas',
        reason='other',
        outcome='degraded',
        log=static_map_router.logger,
    )


def test_success_returns_png_bytes_with_private_cache_headers():
    png = b'\x89PNG fake-bytes'
    with patch.object(static_map_router, 'fetch_static_map', return_value=png):
        response = _get('37.7749,-122.4194|37.7849,-122.4094')
    assert response.status_code == 200
    assert response.body == png
    assert response.media_type == 'image/png'
    assert response.headers['cache-control'] == 'private, max-age=86400'


def test_route_requires_auth():
    app = _bare_app()
    with TestClient(app) as client:
        response = client.get('/v1/static-map', params={'pins': '37.7749,-122.4194', 'width': 300, 'height': 150})
    assert response.status_code == 401


def test_dimension_bounds_are_rejected_with_422(monkeypatch):
    """FastAPI's Query(ge/le) contract is part of the route; exercise it for real."""
    from utils.other import endpoints as endpoints_mod

    # The rate-limit check after auth needs Redis; stub it so the validation
    # contract under test stays hermetic and fast.
    monkeypatch.setattr(endpoints_mod, '_enforce_rate_limit', lambda *args, **kwargs: None)
    app = _bare_app()
    app.dependency_overrides[endpoints_mod.get_current_user_uid] = lambda: UID
    with TestClient(app) as client:
        too_small = client.get('/v1/static-map', params={'pins': '1,2', 'width': 10, 'height': 150})
        too_large = client.get('/v1/static-map', params={'pins': '1,2', 'width': 300, 'height': 2000})
    assert too_small.status_code == 422
    assert too_large.status_code == 422


def _bare_app():
    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(static_map_router.router)
    return app


# ---------------------------------------------------------------------------
# utils/static_map.py: parsing, URL shape, cache
# ---------------------------------------------------------------------------


def test_parse_pins_quantizes_dedupes_and_sorts():
    pins = static_map_mod.parse_pins('37.78494,-122.40944|37.77491,-122.41941|37.774912,-122.419418')
    # First two are distinct places; the third quantizes onto the second.
    assert pins == [(37.7749, -122.4194), (37.7849, -122.4094)]


def test_parse_pins_caps_at_50():
    raw = '|'.join(f'{i / 100:.2f},0.0' for i in range(80))
    assert len(static_map_mod.parse_pins(raw)) == 50


def test_single_pin_url_centers_at_street_zoom():
    url = static_map_mod.build_static_map_url([(37.7749, -122.4194)], 300, 150, 'k-test')
    assert 'center=37.7749,-122.4194' in url
    assert 'zoom=15' in url
    assert 'visible=' not in url


def test_multi_pin_url_uses_visible_autofit_with_the_given_size():
    # Callers normalize dimensions before building (see _effective_dimensions);
    # the builder passes them through.
    url = static_map_mod.build_static_map_url([(37.7749, -122.4194), (37.7849, -122.4094)], 640, 640, 'k-test')
    assert 'visible=37.7749,-122.4194%7C37.7849,-122.4094' in url
    assert 'size=640x640' in url
    assert 'center=' not in url
    assert 'markers=color:0xFFFFFF%7C' in url


def test_effective_dimensions_scale_proportionally_and_share_the_cache_entry():
    # One proportional factor, not independent clamps: aspect preserved, and
    # every request that differs only by scale normalizes onto one cache key
    # (fetch_static_map computes the key from the normalized size).
    assert static_map_mod._effective_dimensions(1280, 300) == (640, 150)
    assert static_map_mod._effective_dimensions(300, 1280) == (150, 640)
    assert static_map_mod._effective_dimensions(1280, 1280) == (640, 640)
    assert static_map_mod._effective_dimensions(300, 150) == (300, 150)  # already in bounds
    pins = [(37.7749, -122.4194)]
    assert static_map_mod._cache_key(
        pins, *static_map_mod._effective_dimensions(1280, 300)
    ) == static_map_mod._cache_key(pins, 640, 150)


class _AsyncNull:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False


class _FakeRedis:
    def __init__(self):
        self.store = {}

    def get(self, key):
        return self.store.get(key)

    def set(self, key, value, ex=None, nx=False):
        if nx and key in self.store:
            return None
        self.store[key] = value
        return True

    def delete(self, key):
        self.store.pop(key, None)


def _fake_response(status_code=200, content=b'png-bytes', content_type='image/png'):
    return SimpleNamespace(status_code=status_code, headers={'content-type': content_type}, content=content)


def _patch_environment(monkeypatch, response=None, redis=None, delay=0.0):
    monkeypatch.setenv('GOOGLE_MAPS_API_KEY', 'k-test')
    fake_redis = redis if redis is not None else _FakeRedis()

    async def passthrough_run_blocking(_executor, fn, *args, **kwargs):
        return fn(*args, **kwargs)

    captured = {'url': None, 'provider_calls': 0}

    def _get_client():
        async def _get(url):
            captured['url'] = url
            captured['provider_calls'] += 1
            if delay:
                await asyncio.sleep(delay)
            return response if response is not None else _fake_response()

        return SimpleNamespace(get=_get)

    monkeypatch.setattr(static_map_mod, 'r', fake_redis)
    monkeypatch.setattr(static_map_mod, 'run_blocking', passthrough_run_blocking)
    monkeypatch.setattr(static_map_mod, 'get_maps_client', _get_client)
    monkeypatch.setattr(static_map_mod, 'get_maps_semaphore', _AsyncNull)
    return fake_redis, captured


@pytest.mark.asyncio
async def test_cache_hit_returns_bytes_without_calling_the_provider(monkeypatch):
    redis, captured = _patch_environment(monkeypatch, response=_fake_response(content=b'should-not-be-fetched'))
    redis.store[static_map_mod._cache_key([(37.7749, -122.4194)], 300, 150)] = b'cached-png'

    result = await static_map_mod.fetch_static_map([(37.7749, -122.4194)], 300, 150)

    assert result == b'cached-png'
    assert captured['url'] is None  # no upstream call on a hit


@pytest.mark.asyncio
async def test_cache_miss_fetches_caches_and_returns_bytes(monkeypatch):
    redis, captured = _patch_environment(monkeypatch)
    result = await static_map_mod.fetch_static_map([(37.7749, -122.4194)], 300, 150)

    assert result == b'png-bytes'
    assert 'maps.googleapis.com/maps/api/staticmap' in captured['url']
    assert 'key=k-test' in captured['url']
    assert static_map_mod._cache_key([(37.7749, -122.4194)], 300, 150) in redis.store
    assert redis.store[static_map_mod._cache_key([(37.7749, -122.4194)], 300, 150)] == b'png-bytes'
    # The render lock is released after the render.
    assert f"{static_map_mod._cache_key([(37.7749, -122.4194)], 300, 150)}:render-lock" not in redis.store


@pytest.mark.asyncio
async def test_oversized_request_normalizes_onto_the_shared_cache_entry(monkeypatch):
    redis, captured = _patch_environment(monkeypatch)
    result = await static_map_mod.fetch_static_map([(37.7749, -122.4194)], 1280, 300)

    assert result == b'png-bytes'
    assert 'size=640x150' in captured['url']  # proportional scale, aspect preserved
    # Stored under the normalized key — a later in-bounds request for the same
    # pin set is a hit.
    assert static_map_mod._cache_key([(37.7749, -122.4194)], 640, 150) in redis.store
    again = await static_map_mod.fetch_static_map([(37.7749, -122.4194)], 640, 150)
    assert again == b'png-bytes'
    assert captured['provider_calls'] == 1


@pytest.mark.asyncio
async def test_concurrent_misses_render_once_and_share_the_result(monkeypatch):
    monkeypatch.setattr(static_map_mod, '_RENDER_POLL_INTERVAL_SECONDS', 0.02)
    _redis, captured = _patch_environment(monkeypatch, delay=0.05)  # slow render, observable lock

    results = await asyncio.gather(
        static_map_mod.fetch_static_map([(37.7749, -122.4194)], 300, 150),
        static_map_mod.fetch_static_map([(37.7749, -122.4194)], 300, 150),
    )

    assert results == [b'png-bytes', b'png-bytes']  # both callers served
    assert captured['provider_calls'] == 1  # one render, not a stampede


@pytest.mark.asyncio
async def test_lock_holder_elsewhere_waiter_polls_until_the_hit_appears(monkeypatch):
    monkeypatch.setattr(static_map_mod, '_RENDER_POLL_INTERVAL_SECONDS', 0.02)
    redis, captured = _patch_environment(monkeypatch)
    pins = [(37.7749, -122.4194)]
    key = static_map_mod._cache_key(pins, 300, 150)
    # Another renderer holds the lock…
    redis.store[f'{key}:render-lock'] = '1'

    async def _holder_finishes():
        await asyncio.sleep(0.05)
        redis.store[key] = b'holder-png'

    holder = asyncio.create_task(_holder_finishes())
    result = await static_map_mod.fetch_static_map(pins, 300, 150)

    assert result == b'holder-png'  # served from the cache the holder wrote
    assert captured['provider_calls'] == 0  # the waiter never called the provider
    assert f'{key}:render-lock' in redis.store  # and never released someone else's lock
    await holder


@pytest.mark.asyncio
async def test_lock_wait_timeout_fails_open_to_an_unlocked_render(monkeypatch):
    monkeypatch.setattr(static_map_mod, '_RENDER_POLL_INTERVAL_SECONDS', 0.02)
    monkeypatch.setattr(static_map_mod, '_RENDER_WAIT_TIMEOUT_SECONDS', 0.06)
    redis, captured = _patch_environment(monkeypatch)
    pins = [(37.7749, -122.4194)]
    key = static_map_mod._cache_key(pins, 300, 150)
    redis.store[f'{key}:render-lock'] = '1'  # a wedged holder that never writes

    result = await static_map_mod.fetch_static_map(pins, 300, 150)

    assert result == b'png-bytes'  # fail-open: a lost lock never becomes a 502
    assert captured['provider_calls'] == 1
    assert f'{key}:render-lock' in redis.store  # still not our lock to release


@pytest.mark.asyncio
async def test_same_pin_set_different_order_hits_the_same_cache_entry(monkeypatch):
    redis, captured = _patch_environment(monkeypatch)
    await static_map_mod.fetch_static_map([(37.7749, -122.4194), (37.7849, -122.4094)], 300, 150)

    reordered = await static_map_mod.fetch_static_map([(37.7849, -122.4094), (37.7749, -122.4194)], 300, 150)

    assert reordered == b'png-bytes'
    assert captured['url'] is not None  # first call fetched…
    # …and the reordered call was served from cache (only one fetch happened).
    assert len([k for k in redis.store]) == 1


@pytest.mark.asyncio
async def test_provider_error_status_is_returned_as_none_and_not_cached(monkeypatch):
    redis, _ = _patch_environment(monkeypatch, response=_fake_response(status_code=403, content_type='text/html'))

    result = await static_map_mod.fetch_static_map([(37.7749, -122.4194)], 300, 150)

    assert result is None
    assert redis.store == {}  # failures are never cached


@pytest.mark.asyncio
async def test_missing_api_key_returns_none(monkeypatch):
    _patch_environment(monkeypatch)
    monkeypatch.delenv('GOOGLE_MAPS_API_KEY', raising=False)
    assert await static_map_mod.fetch_static_map([(37.7749, -122.4194)], 300, 150) is None


@pytest.mark.asyncio
async def test_redis_write_failure_still_returns_the_image(monkeypatch):
    class _BrokenSetRedis(_FakeRedis):
        def set(self, key, value, ex=None):
            raise RuntimeError('redis down')

    _patch_environment(monkeypatch, redis=_BrokenSetRedis(), response=_fake_response())
    result = await static_map_mod.fetch_static_map([(37.7749, -122.4194)], 300, 150)
    assert result == b'png-bytes'
