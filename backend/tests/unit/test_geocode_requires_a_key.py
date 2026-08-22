"""No geocode request may leave the process when GOOGLE_MAPS_API_KEY is not configured.

All three helpers read the key and interpolated it into the URL without ever checking it, so with no
key set the request still went out — `?latlng=<user's exact coordinates>&key=None` to
maps.googleapis.com — and only Google's 403 came back. On the on-prem posture that is a
zero-configuration egress of location data: nothing in the deployment has to be misconfigured for it
to happen, the operator simply has to not use Google Maps. ADR-0048 makes the network bridged (the
host CAN reach the internet), so the call is not stopped by the topology either; ADR-0001 says
on-prem must not depend on cloud services, and "sends the coordinates and gets refused" is not
compliance.

Callers: routers/integration.py, utils/conversations/finalizer.py, utils/retrieval/agentic.py. The
result is Redis-cached for 48h, so this is a per-cache-miss leak, not a per-request one.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import httpx
import pytest

from utils.conversations import location as location_mod


@pytest.fixture(autouse=True)
def _no_cache(monkeypatch):
    """Bypass the Redis geocode cache so each test reaches the network decision."""
    monkeypatch.setattr(location_mod, 'r', SimpleNamespace(get=lambda _k: None, setex=lambda *_a, **_k: None))


@pytest.fixture
def outbound(monkeypatch) -> list[str]:
    """Record every URL the module would fetch, sync or async, and never actually leave."""
    seen: list[str] = []

    def _get(url, *_a, **_k):
        seen.append(url)
        return SimpleNamespace(json=lambda: {'status': 'REQUEST_DENIED', 'results': []}, status_code=403)

    class _AsyncClient:
        def __init__(self, *_a, **_k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_exc):
            return False

        async def get(self, url, *_a, **_k):
            return _get(url)

    monkeypatch.setattr(httpx, 'get', _get)
    monkeypatch.setattr(httpx, 'AsyncClient', _AsyncClient)
    return seen


def test_sync_geocode_makes_no_request_without_a_key(monkeypatch, outbound):
    monkeypatch.delenv('GOOGLE_MAPS_API_KEY', raising=False)

    assert location_mod.get_google_maps_location(45.4642, 9.1900) is None
    assert outbound == [], f'coordinates left the process with no key configured: {outbound}'


def test_async_geocode_makes_no_request_without_a_key(monkeypatch, outbound):
    monkeypatch.delenv('GOOGLE_MAPS_API_KEY', raising=False)

    assert asyncio.run(location_mod.async_get_google_maps_location(45.4642, 9.1900)) is None
    assert outbound == [], f'coordinates left the process with no key configured: {outbound}'


def test_async_city_lookup_makes_no_request_without_a_key(monkeypatch, outbound):
    monkeypatch.delenv('GOOGLE_MAPS_API_KEY', raising=False)

    assert asyncio.run(location_mod.async_get_google_maps_city(45.4642, 9.1900)) is None
    assert outbound == [], f'coordinates left the process with no key configured: {outbound}'


def test_an_empty_key_counts_as_unconfigured(monkeypatch, outbound):
    """An operator who blanks the variable means the same thing as one who never set it."""
    monkeypatch.setenv('GOOGLE_MAPS_API_KEY', '   ')

    assert location_mod.get_google_maps_location(45.4642, 9.1900) is None
    assert outbound == [], f'coordinates left the process with a blank key: {outbound}'


def test_a_configured_key_still_geocodes(monkeypatch, outbound):
    """The guard must not disable the feature for deployments that do use Google Maps."""
    monkeypatch.setenv('GOOGLE_MAPS_API_KEY', 'real-key')

    location_mod.get_google_maps_location(45.4642, 9.1900)

    assert len(outbound) == 1, outbound
    assert 'maps.googleapis.com' in outbound[0]
    assert 'key=real-key' in outbound[0]
