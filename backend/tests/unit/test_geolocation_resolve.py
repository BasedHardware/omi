"""Regression: resolve_geolocation must not drop the user's coordinates on a geocode miss.

get_google_maps_location / async_get_google_maps_location return None when Google reports ZERO_RESULTS,
OVER_QUERY_LIMIT, REQUEST_DENIED, or no place_id. Callers in routers/developer.py and routers/pusher.py
assigned that return directly, so a lookup miss overwrote the real lat/long with None and the conversation
was stored with no location. resolve_geolocation keeps the original coordinates on a None return (and on an
error), matching the fix already applied inline in routers/integration.py. Pinned against a fake geocoder,
no live services.
"""

import os
from unittest.mock import AsyncMock, patch

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)

import asyncio  # noqa: E402

from models.geolocation import Geolocation  # noqa: E402

import utils.conversations.location as loc  # noqa: E402


def _raw():
    return Geolocation(latitude=37.78, longitude=-122.41)  # coordinates, no google_place_id


def test_resolve_geolocation_keeps_enrichment():
    enriched = Geolocation(latitude=37.78, longitude=-122.41, google_place_id="ChIJ_test", address="1 St")
    with patch.object(loc, "get_google_maps_location", return_value=enriched):
        assert loc.resolve_geolocation(_raw()).google_place_id == "ChIJ_test"


def test_resolve_geolocation_keeps_raw_on_miss():
    with patch.object(loc, "get_google_maps_location", return_value=None):  # ZERO_RESULTS / no place_id
        raw = _raw()
        assert loc.resolve_geolocation(raw) is raw  # coordinates preserved, not dropped to None


def test_resolve_geolocation_keeps_raw_on_error():
    with patch.object(loc, "get_google_maps_location", side_effect=RuntimeError("maps unavailable")):
        raw = _raw()
        assert loc.resolve_geolocation(raw) is raw  # a geocoder error must not drop the location


def test_resolve_geolocation_skips_when_place_id_present():
    with patch.object(loc, "get_google_maps_location") as geo:
        already = Geolocation(latitude=1.0, longitude=2.0, google_place_id="ChIJ_existing")
        assert loc.resolve_geolocation(already) is already
        geo.assert_not_called()  # already enriched -> no geocoder call


def test_resolve_geolocation_none_passthrough():
    with patch.object(loc, "get_google_maps_location") as geo:
        assert loc.resolve_geolocation(None) is None
        geo.assert_not_called()


def test_async_resolve_geolocation_keeps_enrichment():
    enriched = Geolocation(latitude=37.78, longitude=-122.41, google_place_id="ChIJ_async")
    with patch.object(loc, "async_get_google_maps_location", new=AsyncMock(return_value=enriched)):
        result = asyncio.run(loc.async_resolve_geolocation(_raw()))
    assert result.google_place_id == "ChIJ_async"


def test_async_resolve_geolocation_keeps_raw_on_miss():
    with patch.object(loc, "async_get_google_maps_location", new=AsyncMock(return_value=None)):
        raw = _raw()
        result = asyncio.run(loc.async_resolve_geolocation(raw))
    assert result is raw  # cached coordinates preserved on a miss, not dropped to None
