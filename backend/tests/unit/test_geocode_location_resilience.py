"""Regression: get_google_maps_location returns None (not raise) on a geocoding failure.

The sync geocoder did a bare httpx.get() + response.json(). A connect/read timeout, a Google 5xx
HTML error page, or any non-JSON body raised out of the helper, which 500ed conversation create /
finalize (and, in finalize, stranded the conversation in 'processing' since the status is set before
the geocode call). The async twin already returns None on these; this gives the sync path the same
contract. No live services.
"""

from unittest.mock import MagicMock

import httpx

from utils.conversations import location


def test_geocode_transport_error_returns_none(monkeypatch):
    monkeypatch.setenv("GOOGLE_MAPS_API_KEY", "k")
    monkeypatch.setattr(location.r, "get", lambda *a, **k: None)  # cache miss

    def boom(*a, **k):
        raise httpx.ConnectError("maps down")

    monkeypatch.setattr(location.httpx, "get", boom)

    assert location.get_google_maps_location(37.78, -122.40) is None


def test_geocode_non_json_body_returns_none(monkeypatch):
    monkeypatch.setenv("GOOGLE_MAPS_API_KEY", "k")
    monkeypatch.setattr(location.r, "get", lambda *a, **k: None)

    resp = MagicMock()
    resp.json.side_effect = ValueError("Expecting value")  # json.JSONDecodeError subclasses ValueError

    monkeypatch.setattr(location.httpx, "get", lambda *a, **k: resp)

    assert location.get_google_maps_location(37.78, -122.40) is None


def test_geocode_success_still_returns_geolocation(monkeypatch):
    # Happy path preserved: a valid geocode response is parsed into a Geolocation.
    monkeypatch.setenv("GOOGLE_MAPS_API_KEY", "k")
    monkeypatch.setattr(location.r, "get", lambda *a, **k: None)
    monkeypatch.setattr(location.r, "set", lambda *a, **k: None)

    resp = MagicMock()
    resp.json.return_value = {
        "status": "OK",
        "results": [{"place_id": "abc123", "formatted_address": "1 Main St", "types": ["street_address"]}],
    }
    monkeypatch.setattr(location.httpx, "get", lambda *a, **k: resp)

    geo = location.get_google_maps_location(37.78, -122.40)
    assert geo is not None
    assert geo.google_place_id == "abc123"
