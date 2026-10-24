"""Hermetic offline test suite for NWS Severe Weather Alerts Omi App.

Tests all tool endpoints, Pydantic validation, upstream error paths, LRU cache isolation,
and sliding window rate limiting without network calls or sleep delays.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from fastapi.testclient import TestClient
import httpx
import pytest

from main import (
    LRUCache,
    SlidingWindowRateLimiter,
    app,
    cache,
    rate_limiter,
)
from models import ChatToolResponse

SAMPLE_TORNADO_ALERT = {
    "id": "urn:oid:2.49.0.1.840.0.tornado.001",
    "properties": {
        "id": "urn:oid:2.49.0.1.840.0.tornado.001",
        "event": "Tornado Warning",
        "severity": "Extreme",
        "urgency": "Immediate",
        "certainty": "Observed",
        "headline": "Tornado Warning issued September 7 at 4:30PM CDT until September 7 at 5:15PM CDT by NWS Fort Worth TX",
        "description": "At 430 PM CDT, a confirmed large and extremely dangerous tornado was located over Dallas.",
        "instruction": "TAKE COVER NOW! Move to an interior room on the lowest floor of a sturdy building. Avoid windows.",
        "onset": "2026-09-07T16:30:00-05:00",
        "expires": "2026-09-07T17:15:00-05:00",
        "areaDesc": "Dallas, TX; Tarrant, TX",
        "senderName": "NWS Fort Worth TX",
    },
}

SAMPLE_FLOOD_ALERT = {
    "id": "urn:oid:2.49.0.1.840.0.flood.002",
    "properties": {
        "id": "urn:oid:2.49.0.1.840.0.flood.002",
        "event": "Flash Flood Warning",
        "severity": "Severe",
        "urgency": "Immediate",
        "certainty": "Likely",
        "headline": "Flash Flood Warning in effect until 8:00 PM CDT",
        "description": "Flash flooding of small creeks and streams, urban areas, highways, streets and underpasses.",
        "instruction": "Turn around, don't drown when encountering flooded roads.",
        "onset": "2026-09-07T15:00:00-05:00",
        "expires": "2026-09-07T20:00:00-05:00",
        "areaDesc": "Dallas County",
        "senderName": "NWS Fort Worth TX",
    },
}

SAMPLE_HEAT_ADVISORY = {
    "id": "urn:oid:2.49.0.1.840.0.heat.003",
    "properties": {
        "id": "urn:oid:2.49.0.1.840.0.heat.003",
        "event": "Heat Advisory",
        "severity": "Moderate",
        "urgency": "Expected",
        "certainty": "Likely",
        "headline": "Heat Advisory in effect until 8:00 PM CDT",
        "description": "High temperatures and heat index values up to 108 expected.",
        "instruction": "Drink plenty of fluids and stay in an air-conditioned room.",
        "onset": "2026-09-07T11:00:00-05:00",
        "expires": "2026-09-07T20:00:00-05:00",
        "areaDesc": "Travis, TX; Williamson, TX",
        "senderName": "NWS Austin/San Antonio TX",
    },
}


class MockNwsTransport(httpx.AsyncBaseTransport):
    """Mocked HTTP transport simulating api.weather.gov GeoJSON responses."""

    def __init__(
        self,
        upstream_status: int = 200,
        empty_features: bool = False,
        not_found: bool = False,
        total_count: int = 245,
    ) -> None:
        self.upstream_status = upstream_status
        self.empty_features = empty_features
        self.not_found = not_found
        self.total_count = total_count

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        url_str = str(request.url)

        if self.upstream_status != 200:
            return httpx.Response(self.upstream_status, text="Upstream NWS Error")

        if "/alerts/active/count" in url_str:
            return httpx.Response(200, json={"total": self.total_count})

        if "/alerts/active" in url_str:
            if self.not_found:
                return httpx.Response(404, json={"title": "Not Found", "status": 404})

            if self.empty_features:
                return httpx.Response(200, json={"features": []})

            # Check for severity parameter filtering
            params = dict(request.url.params)
            severity_filter = params.get("severity")

            all_alerts = [
                SAMPLE_TORNADO_ALERT,
                SAMPLE_FLOOD_ALERT,
                SAMPLE_HEAT_ADVISORY,
            ]
            if severity_filter:
                filtered = [
                    a
                    for a in all_alerts
                    if a["properties"]["severity"].lower() in severity_filter.lower()
                ]
                return httpx.Response(200, json={"features": filtered})

            return httpx.Response(200, json={"features": all_alerts})

        return httpx.Response(404, json={"title": "Not Found"})


@pytest.fixture(autouse=True)
def reset_state():
    """Clear cache and rate limiter before and after each test."""
    cache.clear()
    rate_limiter._records.clear()
    yield
    cache.clear()
    rate_limiter._records.clear()


@pytest.fixture
def client(monkeypatch):
    """Create test client with mocked HTTP client."""
    mock_client = httpx.AsyncClient(
        transport=MockNwsTransport(),
        headers={"User-Agent": "OmiTestApp/1.0"},
    )
    monkeypatch.setattr("main.http_client", mock_client)
    with TestClient(app) as test_client:
        yield test_client


def test_root_endpoint(client):
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "online"
    assert "tools_manifest" in data["endpoints"]
    assert "alerts_by_location" in data["endpoints"]
    assert "alerts_by_state" in data["endpoints"]
    assert "national_summary" in data["endpoints"]


def test_health_healthy(client):
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["upstream_nws_api"] == "reachable"


def test_health_degraded_upstream_failure(monkeypatch):
    mock_client = httpx.AsyncClient(
        transport=MockNwsTransport(upstream_status=503),
        headers={"User-Agent": "OmiTestApp/1.0"},
    )
    monkeypatch.setattr("main.http_client", mock_client)
    with TestClient(app) as c:
        response = c.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "degraded"
        assert data["upstream_nws_api"] == "unreachable"


def test_omi_tools_manifest(client):
    response = client.get("/.well-known/omi-tools.json")
    assert response.status_code == 200
    data = response.json()
    assert data["schema_version"] == "1.0"
    assert "tools" in data
    assert len(data["tools"]) == 3

    tool_map = {t["name"]: t for t in data["tools"]}
    assert "get_active_alerts_by_location" in tool_map
    assert "get_active_alerts_by_state" in tool_map
    assert "get_national_severe_weather_summary" in tool_map

    for t in data["tools"]:
        assert "description" in t
        assert t["endpoint"].startswith("/tools/")
        assert t["method"] == "POST"
        assert t["auth_required"] is False
        assert "status_message" in t
        assert "parameters" in t
        assert t["parameters"]["type"] == "object"


def test_get_active_alerts_by_location_success(client):
    payload = {"latitude": 32.7767, "longitude": -96.7970}
    response = client.post("/tools/get-active-alerts-by-location", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "result" in data
    result = data["result"]
    assert "Tornado Warning" in result
    assert "Flash Flood Warning" in result
    assert "TAKE COVER NOW" in result
    assert "Dallas, TX" in result


def test_get_active_alerts_by_location_empty(monkeypatch):
    mock_client = httpx.AsyncClient(
        transport=MockNwsTransport(empty_features=True),
        headers={"User-Agent": "OmiTestApp/1.0"},
    )
    monkeypatch.setattr("main.http_client", mock_client)
    with TestClient(app) as c:
        response = c.post(
            "/tools/get-active-alerts-by-location",
            json={"latitude": 37.7749, "longitude": -122.4194},
        )
        assert response.status_code == 200
        result = response.json()["result"]
        assert "No Active Weather Alerts" in result
        assert "37.7749" in result


def test_get_active_alerts_by_location_empty_with_severity_filter(monkeypatch):
    mock_client = httpx.AsyncClient(
        transport=MockNwsTransport(empty_features=True),
        headers={"User-Agent": "OmiTestApp/1.0"},
    )
    monkeypatch.setattr("main.http_client", mock_client)
    with TestClient(app) as c:
        response = c.post(
            "/tools/get-active-alerts-by-location",
            json={"latitude": 37.7749, "longitude": -122.4194, "severity": "Extreme"},
        )
        assert response.status_code == 200
        result = response.json()["result"]
        assert "No Active 'Extreme' Weather Alerts" in result
        assert "active extreme-severity warnings or advisories" in result


def test_get_active_alerts_by_location_with_severity_filter(client):
    payload = {
        "latitude": 32.7767,
        "longitude": -96.7970,
        "severity": "Extreme",
    }
    response = client.post("/tools/get-active-alerts-by-location", json=payload)
    assert response.status_code == 200
    result = response.json()["result"]
    assert "Tornado Warning" in result
    assert "Heat Advisory" not in result


def test_get_active_alerts_by_location_invalid_coords(client):
    # Latitude out of range (> 90)
    resp1 = client.post(
        "/tools/get-active-alerts-by-location",
        json={"latitude": 95.0, "longitude": -96.0},
    )
    assert resp1.status_code == 422

    # Longitude out of range (< -180)
    resp2 = client.post(
        "/tools/get-active-alerts-by-location",
        json={"latitude": 32.0, "longitude": -195.0},
    )
    assert resp2.status_code == 422

    # Non-finite NaN coordinates rejected with 422 (allow_inf_nan=False)
    resp3 = client.post(
        "/tools/get-active-alerts-by-location",
        content='{"latitude": NaN, "longitude": -96.0}',
        headers={"Content-Type": "application/json"},
    )
    assert resp3.status_code == 422

    resp4 = client.post(
        "/tools/get-active-alerts-by-location",
        content='{"latitude": 32.0, "longitude": NaN}',
        headers={"Content-Type": "application/json"},
    )
    assert resp4.status_code == 422

    # Direct model validation also rejects float('nan')
    with pytest.raises(Exception):
        LocationAlertRequest(latitude=float("nan"), longitude=-96.0)
    with pytest.raises(Exception):
        LocationAlertRequest(latitude=32.0, longitude=float("nan"))


def test_get_active_alerts_by_location_invalid_severity(client):
    resp = client.post(
        "/tools/get-active-alerts-by-location",
        json={"latitude": 32.0, "longitude": -96.0, "severity": "Apocalyptic"},
    )
    assert resp.status_code == 422


def test_get_active_alerts_by_location_upstream_404(monkeypatch):
    mock_client = httpx.AsyncClient(
        transport=MockNwsTransport(not_found=True),
        headers={"User-Agent": "OmiTestApp/1.0"},
    )
    monkeypatch.setattr("main.http_client", mock_client)
    with TestClient(app) as c:
        response = c.post(
            "/tools/get-active-alerts-by-location",
            json={"latitude": 0.0, "longitude": 0.0},
        )
        assert response.status_code == 200
        assert "No National Weather Service coverage" in response.json()["result"]


def test_get_active_alerts_by_location_upstream_500(monkeypatch):
    mock_client = httpx.AsyncClient(
        transport=MockNwsTransport(upstream_status=500),
        headers={"User-Agent": "OmiTestApp/1.0"},
    )
    monkeypatch.setattr("main.http_client", mock_client)
    with TestClient(app) as c:
        response = c.post(
            "/tools/get-active-alerts-by-location",
            json={"latitude": 32.7767, "longitude": -96.7970},
        )
        assert response.status_code == 502


def test_get_active_alerts_by_state_postal_code(client):
    response = client.post(
        "/tools/get-active-alerts-by-state",
        json={"state": "TX", "limit": 2},
    )
    assert response.status_code == 200
    data = response.json()
    assert "result" in data
    result = data["result"]
    assert "TEXAS (TX)" in result
    assert "Total Active in State" in result
    assert "Tornado Warning" in result


def test_get_active_alerts_by_state_full_name_normalized(client):
    response = client.post(
        "/tools/get-active-alerts-by-state",
        json={"state": "california"},
    )
    assert response.status_code == 200
    result = response.json()["result"]
    assert "CALIFORNIA (CA)" in result


def test_get_active_alerts_by_state_empty(monkeypatch):
    mock_client = httpx.AsyncClient(
        transport=MockNwsTransport(empty_features=True),
        headers={"User-Agent": "OmiTestApp/1.0"},
    )
    monkeypatch.setattr("main.http_client", mock_client)
    with TestClient(app) as c:
        response = c.post(
            "/tools/get-active-alerts-by-state",
            json={"state": "HI"},
        )
        assert response.status_code == 200
        result = response.json()["result"]
        assert "No Active Weather Alerts" in result
        assert "HAWAII (HI)" in result


def test_get_active_alerts_by_state_empty_with_severity_filter(monkeypatch):
    mock_client = httpx.AsyncClient(
        transport=MockNwsTransport(empty_features=True),
        headers={"User-Agent": "OmiTestApp/1.0"},
    )
    monkeypatch.setattr("main.http_client", mock_client)
    with TestClient(app) as c:
        response = c.post(
            "/tools/get-active-alerts-by-state",
            json={"state": "HI", "severity": "Extreme"},
        )
        assert response.status_code == 200
        result = response.json()["result"]
        assert "No Active 'Extreme' Weather Alerts" in result
        assert "active extreme-severity warnings or watches" in result


def test_get_active_alerts_by_state_invalid_state(client):
    response = client.post(
        "/tools/get-active-alerts-by-state",
        json={"state": "Atlantis"},
    )
    assert response.status_code == 422
    assert "Invalid US state" in response.text


def test_get_active_alerts_by_state_limit_clamping(client):
    resp1 = client.post(
        "/tools/get-active-alerts-by-state", json={"state": "TX", "limit": 0}
    )
    assert resp1.status_code == 422

    resp2 = client.post(
        "/tools/get-active-alerts-by-state", json={"state": "TX", "limit": 15}
    )
    assert resp2.status_code == 422


def test_get_active_alerts_by_state_upstream_failure(monkeypatch):
    mock_client = httpx.AsyncClient(
        transport=MockNwsTransport(upstream_status=500),
        headers={"User-Agent": "OmiTestApp/1.0"},
    )
    monkeypatch.setattr("main.http_client", mock_client)
    with TestClient(app) as c:
        response = c.post(
            "/tools/get-active-alerts-by-state",
            json={"state": "TX"},
        )
        assert response.status_code == 502


def test_get_national_severe_weather_summary_success(client):
    response = client.post("/tools/get-national-severe-weather-summary", json={})
    assert response.status_code == 200
    data = response.json()
    assert "result" in data
    result = data["result"]
    assert "US National Severe Weather Situation Summary" in result
    assert "**Total Active Weather Alerts (Nationwide):** 245" in result
    assert "**Life-Threatening (Extreme):** 1" in result
    assert "**Severe Hazards:** 1" in result


def test_get_national_severe_weather_summary_empty(monkeypatch):
    mock_client = httpx.AsyncClient(
        transport=MockNwsTransport(empty_features=True, total_count=0),
        headers={"User-Agent": "OmiTestApp/1.0"},
    )
    monkeypatch.setattr("main.http_client", mock_client)
    with TestClient(app) as c:
        response = c.post(
            "/tools/get-national-severe-weather-summary",
            json={"severity_threshold": "Extreme"},
        )
        assert response.status_code == 200
        result = response.json()["result"]
        assert (
            "No extreme or higher weather emergencies currently active nationwide"
            in result
        )


def test_get_national_severe_weather_summary_invalid_threshold(client):
    response = client.post(
        "/tools/get-national-severe-weather-summary",
        json={"severity_threshold": "Moderate"},
    )
    assert response.status_code == 422


def test_get_national_severe_weather_summary_extreme_threshold_preserves_counts(client):
    response = client.post(
        "/tools/get-national-severe-weather-summary",
        json={"severity_threshold": "Extreme"},
    )
    assert response.status_code == 200
    data = response.json()
    result = data["result"]
    assert "**Life-Threatening (Extreme):** 1" in result
    assert "**Severe Hazards:** 1" in result
    assert "Tornado Warning" in result
    assert "Flash Flood Warning" not in result


def test_get_national_severe_weather_summary_upstream_count_failure(monkeypatch):
    class MockCountFailTransport(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
            if "/alerts/active/count" in str(request.url):
                return httpx.Response(500, text="Count Server Error")
            return httpx.Response(200, json={"features": []})

    mock_client = httpx.AsyncClient(
        transport=MockCountFailTransport(),
        headers={"User-Agent": "OmiTestApp/1.0"},
    )
    monkeypatch.setattr("main.http_client", mock_client)
    with TestClient(app) as c:
        response = c.post("/tools/get-national-severe-weather-summary", json={})
        assert response.status_code == 502


def test_get_national_severe_weather_summary_upstream_alerts_failure(monkeypatch):
    class MockAlertsFailTransport(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
            if "/alerts/active/count" in str(request.url):
                return httpx.Response(200, json={"total": 10})
            return httpx.Response(502, text="Alerts Gateway Timeout")

    mock_client = httpx.AsyncClient(
        transport=MockAlertsFailTransport(),
        headers={"User-Agent": "OmiTestApp/1.0"},
    )
    monkeypatch.setattr("main.http_client", mock_client)
    with TestClient(app) as c:
        response = c.post("/tools/get-national-severe-weather-summary", json={})
        assert response.status_code == 502


def test_lru_cache_operations():
    lru = LRUCache(max_size=2)
    lru.set("k1", "v1", ttl_seconds=100.0)
    lru.set("k2", "v2", ttl_seconds=100.0)
    assert lru.get("k1") == "v1"
    assert lru.get("k2") == "v2"

    # Eviction on exceeding max_size
    lru.set("k3", "v3", ttl_seconds=100.0)
    assert lru.size() == 2
    assert lru.get("k1") is None  # k1 was least recently used after k2 access
    assert lru.get("k2") == "v2"
    assert lru.get("k3") == "v3"


def test_lru_cache_ttl_expiry(monkeypatch):
    lru = LRUCache(max_size=5)
    current_time = 1000.0
    monkeypatch.setattr("time.time", lambda: current_time)

    lru.set("temp", "val", ttl_seconds=10.0)
    assert lru.get("temp") == "val"

    current_time = 1011.0
    assert lru.get("temp") is None


def test_lru_cache_deep_copy_isolation():
    lru = LRUCache(max_size=5)
    orig_data = {"items": [1, 2, 3]}
    lru.set("data", orig_data, ttl_seconds=60.0)

    retrieved = lru.get("data")
    retrieved["items"].append(999)

    second_get = lru.get("data")
    assert second_get["items"] == [1, 2, 3]


def test_sliding_window_rate_limiter(monkeypatch):
    limiter = SlidingWindowRateLimiter(requests_per_window=3, window_seconds=60.0)
    now = 1000.0
    monkeypatch.setattr("time.time", lambda: now)

    ip = "192.168.1.10"
    assert limiter.is_allowed(ip) is True
    assert limiter.is_allowed(ip) is True
    assert limiter.is_allowed(ip) is True
    assert limiter.is_allowed(ip) is False  # 4th request blocked

    # Move beyond window
    now = 1061.0
    assert limiter.is_allowed(ip) is True


def test_rate_limiter_blocks_via_api(client, monkeypatch):
    now = 1000.0
    monkeypatch.setattr("time.time", lambda: now)

    payload = {"latitude": 32.7767, "longitude": -96.7970}
    for _ in range(60):
        resp = client.post("/tools/get-active-alerts-by-location", json=payload)
        assert resp.status_code == 200

    # 61st request triggers HTTP 429
    resp_blocked = client.post("/tools/get-active-alerts-by-location", json=payload)
    assert resp_blocked.status_code == 429
    assert "Rate limit exceeded" in resp_blocked.json()["detail"]


def test_trusted_proxy_forwarded_ip_used(client):
    """Verify that when requests arrive via a trusted proxy, rate limiting isolates the forwarded IP."""
    payload = {"latitude": 32.7767, "longitude": -96.7970}
    ip_a_headers = {"X-Forwarded-For": "203.0.113.195"}
    ip_b_headers = {"X-Forwarded-For": "198.51.100.42"}

    # Exhaust rate limit window for IP A (60 requests)
    for _ in range(60):
        resp = client.post(
            "/tools/get-active-alerts-by-location", json=payload, headers=ip_a_headers
        )
        assert resp.status_code == 200

    # 61st request from IP A is blocked with 429
    resp_blocked = client.post(
        "/tools/get-active-alerts-by-location", json=payload, headers=ip_a_headers
    )
    assert resp_blocked.status_code == 429

    # Request from IP B through the same proxy connection is still permitted
    resp_allowed = client.post(
        "/tools/get-active-alerts-by-location", json=payload, headers=ip_b_headers
    )
    assert resp_allowed.status_code == 200


def test_rate_limiter_spoof_prevention(client, monkeypatch):
    """Ensure untrusted direct clients cannot spoof X-Forwarded-For to bypass limits."""
    monkeypatch.setattr("main.TRUSTED_PROXIES", set())  # No proxies trusted
    payload = {"latitude": 32.7767, "longitude": -96.7970}

    for _ in range(60):
        # Attacker rotates X-Forwarded-For
        resp = client.post(
            "/tools/get-active-alerts-by-location",
            json=payload,
            headers={"X-Forwarded-For": "203.0.113.50"},
        )
        assert resp.status_code == 200

    # Blocked because direct IP is tracked, spoof header ignored
    resp_blocked = client.post(
        "/tools/get-active-alerts-by-location",
        json=payload,
        headers={"X-Forwarded-For": "203.0.113.51"},
    )
    assert resp_blocked.status_code == 429


def test_chat_tool_response_alias_shim():
    """Verify legacy plugin callers passing 'response' alias are supported."""
    r = ChatToolResponse(response="Test legacy result message")
    assert r.result == "Test legacy result message"
