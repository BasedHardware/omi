"""Unit tests for NASA Space & Astronomy Intelligence Omi Integration Plugin."""

import time
from typing import Any, Dict
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

SAMPLE_APOD_PAYLOAD = {
    "date": "2026-09-07",
    "title": "The Pelican Nebula in Gas, Dust, and Stars",
    "explanation": "The Pelican Nebula is slowly transforming. IC 5070, the formal designation, is divided from the larger North America Nebula by a dark cloud of dense molecular dust.",
    "media_type": "image",
    "url": "https://apod.nasa.gov/apod/image/2609/Pelican_Nebula_1080.jpg",
    "hdurl": "https://apod.nasa.gov/apod/image/2609/Pelican_Nebula_4000.jpg",
    "copyright": "NASA / Space Science Institute",
}

SAMPLE_NEO_PAYLOAD = {
    "element_count": 3,
    "near_earth_objects": {
        "2026-09-07": [
            {
                "id": "3672901",
                "name": "(2014 DV110)",
                "is_potentially_hazardous_asteroid": False,
                "estimated_diameter": {
                    "meters": {
                        "estimated_diameter_min": 45.0,
                        "estimated_diameter_max": 80.0,
                    }
                },
                "close_approach_data": [
                    {
                        "close_approach_date": "2026-09-07",
                        "close_approach_date_full": "2026-Sep-07 14:20",
                        "relative_velocity": {
                            "kilometers_per_hour": "38520.4",
                        },
                        "miss_distance": {
                            "kilometers": "62374092.5",
                        },
                    }
                ],
            },
            {
                "id": "3837644",
                "name": "(2019 BT2)",
                "is_potentially_hazardous_asteroid": True,
                "estimated_diameter": {
                    "meters": {
                        "estimated_diameter_min": 320.0,
                        "estimated_diameter_max": 620.0,
                    }
                },
                "close_approach_data": [
                    {
                        "close_approach_date": "2026-09-07",
                        "close_approach_date_full": "2026-Sep-07 18:45",
                        "relative_velocity": {
                            "kilometers_per_hour": "54210.0",
                        },
                        "miss_distance": {
                            "kilometers": "69253362.0",
                        },
                    }
                ],
            },
        ]
    },
}

SAMPLE_IMAGE_SEARCH_PAYLOAD = {
    "collection": {
        "version": "1.0",
        "href": "https://images-api.nasa.gov/search?q=james+webb",
        "items": [
            {
                "href": "https://images-assets.nasa.gov/image/PIA11195/collection.json",
                "data": [
                    {
                        "center": "JPL",
                        "title": "Shake, Rattle and Roll: James Webb Components",
                        "nasa_id": "PIA11195",
                        "date_created": "2008-09-24T16:13:12Z",
                        "media_type": "image",
                        "description": "This image shows a model of one of three detectors for the Mid-Infrared Instrument on NASA James Webb Space Telescope.",
                    }
                ],
                "links": [
                    {
                        "href": "https://images-assets.nasa.gov/image/PIA11195/PIA11195~thumb.jpg",
                        "rel": "preview",
                        "render": "image",
                    }
                ],
            }
        ],
    }
}


class MockTransport(httpx.AsyncBaseTransport):
    """Mock transport simulating upstream NASA and images-api endpoints."""

    def __init__(
        self,
        apod_status: int = 200,
        apod_not_found: bool = False,
        neo_status: int = 200,
        neo_empty: bool = False,
        search_status: int = 200,
        search_empty: bool = False,
    ) -> None:
        self.apod_status = apod_status
        self.apod_not_found = apod_not_found
        self.neo_status = neo_status
        self.neo_empty = neo_empty
        self.search_status = search_status
        self.search_empty = search_empty

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        url_str = str(request.url)

        if "/planetary/apod" in url_str:
            if self.apod_not_found:
                return httpx.Response(
                    400,
                    json={
                        "code": 400,
                        "msg": "Date must be between Jun 16, 1995 and 2026-09-07.",
                    },
                )
            if self.apod_status == 200:
                return httpx.Response(200, json=SAMPLE_APOD_PAYLOAD)
            return httpx.Response(self.apod_status, text="Error fetching APOD")

        elif "/neo/rest/v1/feed" in url_str:
            if self.neo_status == 200:
                if self.neo_empty:
                    return httpx.Response(
                        200, json={"element_count": 0, "near_earth_objects": {}}
                    )
                return httpx.Response(200, json=SAMPLE_NEO_PAYLOAD)
            return httpx.Response(self.neo_status, text="Error fetching NeoWs")

        elif "/search" in url_str:
            if self.search_status == 200:
                if self.search_empty:
                    return httpx.Response(200, json={"collection": {"items": []}})
                return httpx.Response(200, json=SAMPLE_IMAGE_SEARCH_PAYLOAD)
            return httpx.Response(
                self.search_status, text="Error searching NASA images"
            )

        return httpx.Response(404, json={"message": "Not Found"})


@pytest.fixture(autouse=True)
def reset_state():
    """Clear in-memory cache and rate limiter state before each test."""
    cache.clear()
    rate_limiter._records.clear()
    yield
    cache.clear()
    rate_limiter._records.clear()


@pytest.fixture
def client(monkeypatch):
    """Create test client with mocked HTTP transport."""
    mock_client = httpx.AsyncClient(
        transport=MockTransport(),
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
    assert "astronomy_picture" in data["endpoints"]
    assert "near_earth_asteroids" in data["endpoints"]
    assert "search_nasa_media" in data["endpoints"]


def test_health_healthy(client):
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["upstream_nasa_api"] == "reachable"


def test_health_degraded_images_failure(monkeypatch):
    mock_client = httpx.AsyncClient(
        transport=MockTransport(search_status=500),
        headers={"User-Agent": "OmiTestApp/1.0"},
    )
    monkeypatch.setattr("main.http_client", mock_client)
    with TestClient(app) as c:
        response = c.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "degraded"
        assert data["upstream_nasa_api"] == "unreachable"


def test_health_unaffected_by_apod_status_preserves_quota(monkeypatch):
    """Ensure /health probes only the keyless images API and does not burn APOD/DEMO_KEY quota."""
    mock_client = httpx.AsyncClient(
        transport=MockTransport(apod_status=500),
        headers={"User-Agent": "OmiTestApp/1.0"},
    )
    monkeypatch.setattr("main.http_client", mock_client)
    with TestClient(app) as c:
        response = c.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["upstream_nasa_api"] == "reachable"


def test_omi_tools_manifest(client):
    response = client.get("/.well-known/omi-tools.json")
    assert response.status_code == 200
    data = response.json()
    assert data["schema_version"] == "1.0"
    assert "tools" in data
    assert len(data["tools"]) == 3

    tool_map = {t["name"]: t for t in data["tools"]}
    assert "get_astronomy_picture" in tool_map
    assert "get_near_earth_asteroids" in tool_map
    assert "search_nasa_media" in tool_map

    for t in data["tools"]:
        assert "description" in t
        assert t["endpoint"].startswith("/tools/")
        assert t["method"] == "POST"
        assert t["auth_required"] is False
        assert "status_message" in t
        assert "parameters" in t
        assert t["parameters"]["type"] == "object"


def test_get_astronomy_picture_today_success(client):
    response = client.post("/tools/get-astronomy-picture", json={})
    assert response.status_code == 200
    data = response.json()
    assert "result" in data
    text = data["result"]
    assert "Pelican Nebula" in text
    assert "2026-09-07" in text
    assert "NASA / Space Science Institute" in text
    assert "View HD Image" in text


def test_get_astronomy_picture_historical_date(client):
    response = client.post("/tools/get-astronomy-picture", json={"date": "2024-07-20"})
    assert response.status_code == 200
    data = response.json()
    assert "result" in data
    assert "Pelican Nebula" in data["result"]


def test_get_astronomy_picture_out_of_range_date_400(monkeypatch):
    """Ensure out-of-range dates returning HTTP 400 from NASA APOD are handled gracefully."""
    mock_client = httpx.AsyncClient(
        transport=MockTransport(apod_not_found=True),
        headers={"User-Agent": "OmiTestApp/1.0"},
    )
    monkeypatch.setattr("main.http_client", mock_client)
    with TestClient(app) as c:
        response = c.post("/tools/get-astronomy-picture", json={"date": "1990-01-01"})
        assert response.status_code == 200
        result = response.json()["result"]
        assert (
            "No NASA Astronomy Picture of the Day found for date '1990-01-01'" in result
        )
        assert "Date must be between Jun 16, 1995" in result


def test_get_astronomy_picture_not_found_404(monkeypatch):
    """Ensure upstream HTTP 404 responses are handled gracefully."""

    class Apod404Transport(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
            return httpx.Response(404, json={"message": "Not Found"})

    mock_client = httpx.AsyncClient(
        transport=Apod404Transport(),
        headers={"User-Agent": "OmiTestApp/1.0"},
    )
    monkeypatch.setattr("main.http_client", mock_client)
    with TestClient(app) as c:
        response = c.post("/tools/get-astronomy-picture", json={"date": "1996-01-01"})
        assert response.status_code == 200
        result = response.json()["result"]
        assert (
            "No NASA Astronomy Picture of the Day found for date '1996-01-01'" in result
        )


def test_get_astronomy_picture_invalid_date_format(client):
    response = client.post("/tools/get-astronomy-picture", json={"date": "07-20-2024"})
    assert response.status_code == 422


def test_get_astronomy_picture_calendar_invalid_date_rejected(client):
    """Ensure impossible calendar dates like 2024-02-31 fail validation with HTTP 422."""
    response = client.post("/tools/get-astronomy-picture", json={"date": "2024-02-31"})
    assert response.status_code == 422
    assert "date" in response.text.lower()


def test_get_astronomy_picture_video_with_thumbnail(monkeypatch):
    """Ensure video APOD preserves and renders thumbnail_url in media links."""
    video_payload = {
        "date": "2026-09-07",
        "title": "Cosmic Orbit Simulation",
        "explanation": "A high definition rendering of gravitational orbits.",
        "media_type": "video",
        "url": "https://www.youtube.com/watch?v=sample123",
        "thumbnail_url": "https://img.youtube.com/vi/sample123/hqdefault.jpg",
        "copyright": "NASA Scientific Visualization Studio",
    }

    class VideoTransport(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=video_payload)

    mock_client = httpx.AsyncClient(
        transport=VideoTransport(),
        headers={"User-Agent": "OmiTestApp/1.0"},
    )
    monkeypatch.setattr("main.http_client", mock_client)
    with TestClient(app) as c:
        response = c.post("/tools/get-astronomy-picture", json={})
        assert response.status_code == 200
        result = response.json()["result"]
        assert "Watch Video" in result
        assert (
            "[Video Thumbnail](https://img.youtube.com/vi/sample123/hqdefault.jpg)"
            in result
        )


def test_get_astronomy_picture_upstream_failure(monkeypatch):
    mock_client = httpx.AsyncClient(
        transport=MockTransport(apod_status=500),
        headers={"User-Agent": "OmiTestApp/1.0"},
    )
    monkeypatch.setattr("main.http_client", mock_client)
    with TestClient(app) as c:
        response = c.post("/tools/get-astronomy-picture", json={})
        assert response.status_code == 502


def test_get_near_earth_asteroids_success(client):
    response = client.post("/tools/get-near-earth-asteroids", json={"limit": 2})
    assert response.status_code == 200
    data = response.json()
    assert "result" in data
    text = data["result"]
    assert "Near-Earth Asteroid Tracking" in text
    assert "(2014 DV110)" in text
    assert "Safe Trajectory" in text
    assert "Miss Distance" in text


def test_get_near_earth_asteroids_hazardous_filter(client):
    response = client.post(
        "/tools/get-near-earth-asteroids", json={"limit": 5, "hazardous_only": True}
    )
    assert response.status_code == 200
    data = response.json()
    text = data["result"]
    assert "POTENTIALLY HAZARDOUS" in text
    assert "(2019 BT2)" in text
    # Non-hazardous (2014 DV110) should be excluded
    assert "(2014 DV110)" not in text


def test_get_near_earth_asteroids_empty(monkeypatch):
    mock_client = httpx.AsyncClient(
        transport=MockTransport(neo_empty=True),
        headers={"User-Agent": "OmiTestApp/1.0"},
    )
    monkeypatch.setattr("main.http_client", mock_client)
    with TestClient(app) as c:
        response = c.post("/tools/get-near-earth-asteroids", json={})
        assert response.status_code == 200
        assert "No near-Earth asteroid encounters recorded" in response.json()["result"]


def test_get_near_earth_asteroids_invalid_limit(client):
    response = client.post("/tools/get-near-earth-asteroids", json={"limit": 20})
    assert response.status_code == 422


def test_get_near_earth_asteroids_upstream_failure(monkeypatch):
    mock_client = httpx.AsyncClient(
        transport=MockTransport(neo_status=500),
        headers={"User-Agent": "OmiTestApp/1.0"},
    )
    monkeypatch.setattr("main.http_client", mock_client)
    with TestClient(app) as c:
        response = c.post("/tools/get-near-earth-asteroids", json={})
        assert response.status_code == 502


def test_search_nasa_media_success(client):
    response = client.post(
        "/tools/search-nasa-media", json={"query": "James Webb", "limit": 2}
    )
    assert response.status_code == 200
    data = response.json()
    assert "result" in data
    text = data["result"]
    assert "NASA Official Media Archive" in text
    assert "PIA11195" in text
    assert "Shake, Rattle and Roll" in text
    assert "Preview Image" in text


def test_search_nasa_media_empty(monkeypatch):
    mock_client = httpx.AsyncClient(
        transport=MockTransport(search_empty=True),
        headers={"User-Agent": "OmiTestApp/1.0"},
    )
    monkeypatch.setattr("main.http_client", mock_client)
    with TestClient(app) as c:
        response = c.post(
            "/tools/search-nasa-media", json={"query": "nonexistentobject123xyz"}
        )
        assert response.status_code == 200
        assert "No NASA multimedia records found" in response.json()["result"]


def test_search_nasa_media_empty_query_rejected(client):
    response = client.post("/tools/search-nasa-media", json={"query": "   "})
    assert response.status_code == 422


def test_search_nasa_media_invalid_limit(client):
    response = client.post(
        "/tools/search-nasa-media", json={"query": "Mars", "limit": 50}
    )
    assert response.status_code == 422


def test_search_nasa_media_upstream_failure(monkeypatch):
    mock_client = httpx.AsyncClient(
        transport=MockTransport(search_status=500),
        headers={"User-Agent": "OmiTestApp/1.0"},
    )
    monkeypatch.setattr("main.http_client", mock_client)
    with TestClient(app) as c:
        response = c.post("/tools/search-nasa-media", json={"query": "Mars"})
        assert response.status_code == 502


def test_lru_cache_operations():
    lru = LRUCache(max_size=3)
    lru.set("a", 1, ttl_seconds=10.0)
    lru.set("b", 2, ttl_seconds=10.0)
    lru.set("c", 3, ttl_seconds=10.0)

    # Access 'a' to promote recency
    assert lru.get("a") == 1

    # Adding 'd' should evict 'b' (oldest), keeping 'c', 'a', 'd'
    lru.set("d", 4, ttl_seconds=10.0)
    assert lru.get("b") is None
    assert lru.get("a") == 1
    assert lru.get("c") == 3
    assert lru.get("d") == 4


def test_lru_cache_ttl_expiry():
    lru = LRUCache(max_size=5)
    lru.set("temp", "expired_val", ttl_seconds=100.0)
    # Hermetic zero-sleep: directly backdate timestamp past expiry
    lru._cache["temp"] = (time.time() - 10.0, "expired_val")
    assert lru.get("temp") is None


def test_lru_cache_deep_copy_isolation():
    lru = LRUCache(max_size=5)
    orig = {"key": ["initial_val"]}
    lru.set("dict_key", orig, ttl_seconds=100.0)

    retrieved = lru.get("dict_key")
    retrieved["key"].append("mutated_val")

    # In-cache value must remain untouched
    second_get = lru.get("dict_key")
    assert second_get["key"] == ["initial_val"]


def test_sliding_window_rate_limiter():
    limiter = SlidingWindowRateLimiter(requests_per_window=3, window_seconds=60.0)
    ip = "192.168.1.100"

    assert limiter.is_allowed(ip) is True
    assert limiter.is_allowed(ip) is True
    assert limiter.is_allowed(ip) is True
    assert limiter.is_allowed(ip) is False  # 4th request blocked

    # Hermetic zero-sleep: simulate window passing by aging timestamps
    limiter._records[ip] = [time.time() - 120.0 for _ in range(3)]
    assert limiter.is_allowed(ip) is True


def test_rate_limiter_blocks_via_api(client):
    # Consume all requests for test IP
    for _ in range(60):
        rate_limiter.is_allowed("testclient")
    resp = client.post("/tools/get-astronomy-picture", json={})
    assert resp.status_code == 429
    assert "Rate limit exceeded" in resp.json()["detail"]


def test_trusted_proxy_forwarded_ip_used(client, monkeypatch):
    """Verify rate limiting is keyed on client IP from X-Forwarded-For when forwarded by trusted proxy."""
    monkeypatch.setattr("main.TRUSTED_PROXIES", {"testclient", "127.0.0.1", "::1"})

    ip1 = "198.51.100.11"
    ip2 = "198.51.100.22"

    # Exhaust quota for ip1
    now = time.time()
    rate_limiter._records[ip1] = [now] * 60

    # Request with ip1 in X-Forwarded-For should receive 429
    resp_blocked = client.post(
        "/tools/get-astronomy-picture",
        json={},
        headers={"X-Forwarded-For": ip1},
    )
    assert resp_blocked.status_code == 429
    assert "Rate limit exceeded" in resp_blocked.json()["detail"]

    # Request with ip2 in X-Forwarded-For has its own quota and succeeds
    resp_allowed = client.post(
        "/tools/get-astronomy-picture",
        json={},
        headers={"X-Forwarded-For": ip2},
    )
    assert resp_allowed.status_code == 200

    # Direct request without X-Forwarded-For uses proxy host ("testclient") which has quota
    resp_direct = client.post(
        "/tools/get-astronomy-picture",
        json={},
    )
    assert resp_direct.status_code == 200


def test_rate_limiter_spoof_prevention(client, monkeypatch):
    """Verify that untrusted connections cannot bypass rate limits by spoofing X-Forwarded-For."""
    monkeypatch.setattr("main.TRUSTED_PROXIES", {"10.0.0.1"})
    monkeypatch.setattr("main.is_trusted_proxy", lambda ip: False)

    spoofed_ip = "198.51.100.99"

    # Exhaust quota for direct connection host "testclient"
    now = time.time()
    rate_limiter._records["testclient"] = [now] * 60

    # Untrusted client is blocked on direct IP regardless of header
    resp = client.post(
        "/tools/get-astronomy-picture",
        json={},
        headers={"X-Forwarded-For": spoofed_ip},
    )
    assert resp.status_code == 429
    assert "Rate limit exceeded" in resp.json()["detail"]

    # Spoofed IP was never allocated in rate limiter records
    assert spoofed_ip not in rate_limiter._records


def test_is_trusted_proxy_rejects_unconfigured_private_ips(monkeypatch):
    """Verify that RFC1918 private IPs are NOT trusted unless explicitly configured in TRUSTED_PROXIES."""
    from main import is_trusted_proxy

    monkeypatch.setattr("main.TRUSTED_PROXIES", {"127.0.0.1", "::1", "testclient"})
    assert is_trusted_proxy("192.168.1.10") is False
    assert is_trusted_proxy("10.0.0.1") is False
    assert is_trusted_proxy("172.16.5.1") is False
    assert is_trusted_proxy("127.0.0.1") is True
    assert is_trusted_proxy("testclient") is True


def test_rate_limit_dynamic_error_message(monkeypatch, client):
    """Verify that overriding RATE_LIMIT_REQUESTS updates the 429 detail message accordingly."""
    monkeypatch.setattr("main.RATE_LIMIT_REQUESTS", 15)
    monkeypatch.setattr(rate_limiter, "requests_per_window", 15)
    for _ in range(15):
        rate_limiter.is_allowed("testclient")
    resp = client.post("/tools/get-astronomy-picture", json={})
    assert resp.status_code == 429
    assert "Maximum 15 requests per minute" in resp.json()["detail"]


def test_apod_ttl_selection_for_explicit_today_vs_historical(monkeypatch, client):
    """Verify today's date receives 1h TTL while historical date receives 24h TTL."""
    today_utc = time.strftime("%Y-%m-%d", time.gmtime())
    client.post("/tools/get-astronomy-picture", json={"date": today_utc})
    today_key = f"apod:{today_utc}:True"
    assert today_key in cache._cache
    expires_at_today, _ = cache._cache[today_key]
    remaining_today = expires_at_today - time.time()
    assert 3500.0 < remaining_today <= 3600.0

    client.post("/tools/get-astronomy-picture", json={"date": "2023-01-01"})
    past_key = "apod:2023-01-01:True"
    assert past_key in cache._cache
    expires_at_past, _ = cache._cache[past_key]
    remaining_past = expires_at_past - time.time()
    assert 86300.0 < remaining_past <= 86400.0
