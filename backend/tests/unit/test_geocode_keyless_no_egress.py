"""Keyless geocode must not reach Google at all.

Offline harness stages strip GOOGLE_MAPS_API_KEY by design, yet both geocode
helpers still fired the HTTP request with an empty key (observed as outbound
maps.googleapis.com traffic from a PROVIDER_MODE=offline session processing a
phone capture's location). The fix: no key -> return None before any egress.
"""

import asyncio

from utils.conversations import location


def test_sync_geocode_keyless_returns_none_without_http(monkeypatch):
    monkeypatch.delenv('GOOGLE_MAPS_API_KEY', raising=False)
    monkeypatch.setattr(location.r, 'get', lambda *a, **k: None)  # cache miss

    def boom(*args, **kwargs):
        raise AssertionError('keyless geocode must not perform an HTTP request')

    monkeypatch.setattr(location.httpx, 'get', boom)
    assert location.get_google_maps_location(10.5, 106.7) is None


def test_async_geocode_keyless_returns_none_without_http(monkeypatch):
    monkeypatch.delenv('GOOGLE_MAPS_API_KEY', raising=False)
    monkeypatch.setattr(location.r, 'get', lambda *a, **k: None)  # cache miss

    class BoomClient:
        async def get(self, *args, **kwargs):
            raise AssertionError('keyless geocode must not perform an HTTP request')

    monkeypatch.setattr(location, 'get_maps_client', lambda: BoomClient())
    assert asyncio.run(location.async_get_google_maps_location(10.5, 106.7)) is None
