"""Unit tests for The Metropolitan Museum of Art Omi Integration Plugin."""

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

SAMPLE_DEPARTMENTS_PAYLOAD = {
    "departments": [
        {"departmentId": 1, "displayName": "American Decorative Arts"},
        {"departmentId": 3, "displayName": "Ancient Near Eastern Art"},
        {"departmentId": 4, "displayName": "Arms and Armor"},
        {"departmentId": 5, "displayName": "Arts of Africa, Oceania, and the Americas"},
        {"departmentId": 6, "displayName": "Asian Art"},
        {"departmentId": 11, "displayName": "European Paintings"},
    ]
}

SAMPLE_SEARCH_PAYLOAD = {
    "total": 2,
    "objectIDs": [437112, 437106],
}

SAMPLE_OBJECT_437112 = {
    "objectID": 437112,
    "isHighlight": True,
    "isPublicDomain": True,
    "title": "Bouquet of Sunflowers",
    "artistDisplayName": "Claude Monet",
    "artistDisplayBio": "French, Paris 1840–1926 Giverny",
    "artistNationality": "French",
    "culture": "French",
    "period": "Impressionism",
    "objectDate": "1881",
    "medium": "Oil on canvas",
    "dimensions": "39 3/4 x 32 1/8 in. (101 x 81.6 cm)",
    "department": "European Paintings",
    "creditLine": "Bequest of Mrs. H. O. Havemeyer, 1929",
    "classification": "Paintings",
    "primaryImage": "https://images.metmuseum.org/CRDImages/ep/original/DP-14286-023.jpg",
    "primaryImageSmall": "https://images.metmuseum.org/CRDImages/ep/web-large/DP-14286-023.jpg",
    "objectURL": "https://www.metmuseum.org/art/collection/search/437112",
    "tags": [{"term": "Flowers"}, {"term": "Sunflowers"}],
}

SAMPLE_OBJECT_437106 = {
    "objectID": 437106,
    "isHighlight": False,
    "isPublicDomain": True,
    "title": "Spring (Fruit Trees in Bloom)",
    "artistDisplayName": "Claude Monet",
    "artistDisplayBio": "French, Paris 1840–1926 Giverny",
    "artistNationality": "French",
    "culture": "French",
    "period": "Impressionism",
    "objectDate": "1873",
    "medium": "Oil on canvas",
    "dimensions": "24 1/2 x 39 5/8 in. (62.2 x 100.6 cm)",
    "department": "European Paintings",
    "creditLine": "Bequest of Mary Stillman Harkness, 1950",
    "classification": "Paintings",
    "primaryImage": "https://images.metmuseum.org/CRDImages/ep/original/DP-14286-001.jpg",
    "primaryImageSmall": "https://images.metmuseum.org/CRDImages/ep/web-large/DP-14286-001.jpg",
    "objectURL": "https://www.metmuseum.org/art/collection/search/437106",
    "tags": [{"term": "Trees"}, {"term": "Spring"}],
}


class MockTransport(httpx.AsyncBaseTransport):
    """Mock transport simulating upstream Met Museum Collection API responses."""

    def __init__(
        self,
        departments_status: int = 200,
        search_status: int = 200,
        search_total: int = 2,
        object_status: int = 200,
    ) -> None:
        self.departments_status = departments_status
        self.search_status = search_status
        self.search_total = search_total
        self.object_status = object_status

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        url_str = str(request.url)

        if "/departments" in url_str:
            if self.departments_status == 200:
                return httpx.Response(200, json=SAMPLE_DEPARTMENTS_PAYLOAD)
            return httpx.Response(self.departments_status, text="Error fetching departments")

        elif "/search" in url_str:
            if self.search_status == 200:
                if self.search_total == 0:
                    return httpx.Response(200, json={"total": 0, "objectIDs": None})
                return httpx.Response(200, json=SAMPLE_SEARCH_PAYLOAD)
            return httpx.Response(self.search_status, text="Error during search")

        elif "/objects/" in url_str:
            if self.object_status == 200:
                if "437112" in url_str:
                    return httpx.Response(200, json=SAMPLE_OBJECT_437112)
                elif "437106" in url_str:
                    return httpx.Response(200, json=SAMPLE_OBJECT_437106)
                else:
                    return httpx.Response(404, json={"message": "ObjectID not found"})
            elif self.object_status == 404:
                return httpx.Response(404, json={"message": "ObjectID not found"})
            return httpx.Response(self.object_status, text="Error fetching object")

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
    assert "search_artworks" in data["endpoints"]


def test_health_healthy(client):
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["upstream_met_api"] == "reachable"


def test_health_degraded(monkeypatch):
    mock_client = httpx.AsyncClient(
        transport=MockTransport(departments_status=500),
        headers={"User-Agent": "OmiTestApp/1.0"},
    )
    monkeypatch.setattr("main.http_client", mock_client)
    with TestClient(app) as c:
        response = c.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "degraded"
        assert data["upstream_met_api"] == "unreachable"


def test_omi_tools_manifest(client):
    response = client.get("/.well-known/omi-tools.json")
    assert response.status_code == 200
    data = response.json()
    assert data["schema_version"] == "1.0"
    assert "tools" in data
    assert len(data["tools"]) == 4

    tool_map = {t["name"]: t for t in data["tools"]}
    assert "search_artworks" in tool_map
    assert "get_artwork_details" in tool_map
    assert "list_departments" in tool_map
    assert "get_department_highlights" in tool_map

    for t in data["tools"]:
        assert "description" in t
        assert t["endpoint"].startswith("/tools/")
        assert t["method"] == "POST"
        assert t["auth_required"] is False
        assert "status_message" in t
        assert "parameters" in t
        assert t["parameters"]["type"] == "object"


def test_search_artworks_success(client):
    response = client.post("/tools/search-artworks", json={"query": "sunflowers", "limit": 2})
    assert response.status_code == 200
    data = response.json()
    assert "result" in data
    text = data["result"]
    assert "Bouquet of Sunflowers" in text
    assert "Claude Monet" in text
    assert "437112" in text


def test_search_artworks_empty(monkeypatch):
    mock_client = httpx.AsyncClient(
        transport=MockTransport(search_total=0),
        headers={"User-Agent": "OmiTestApp/1.0"},
    )
    monkeypatch.setattr("main.http_client", mock_client)
    with TestClient(app) as c:
        response = c.post("/tools/search-artworks", json={"query": "nonexistent123xyz"})
        assert response.status_code == 200
        assert "No artworks found" in response.json()["result"]


def test_search_artworks_with_filters(client):
    response = client.post(
        "/tools/search-artworks",
        json={
            "query": "Monet",
            "artist_or_culture": True,
            "department_id": 11,
            "has_images": True,
            "limit": 5,
        },
    )
    assert response.status_code == 200
    assert "Claude Monet" in response.json()["result"]


def test_search_artworks_empty_query_rejected(client):
    response = client.post("/tools/search-artworks", json={"query": "   "})
    assert response.status_code == 422


def test_search_artworks_invalid_limit(client):
    response = client.post("/tools/search-artworks", json={"query": "Monet", "limit": 25})
    assert response.status_code == 422


def test_search_artworks_upstream_failure(monkeypatch):
    mock_client = httpx.AsyncClient(
        transport=MockTransport(search_status=500),
        headers={"User-Agent": "OmiTestApp/1.0"},
    )
    monkeypatch.setattr("main.http_client", mock_client)
    with TestClient(app) as c:
        response = c.post("/tools/search-artworks", json={"query": "Monet"})
        assert response.status_code == 502


def test_get_artwork_details_success(client):
    response = client.post("/tools/get-artwork-details", json={"object_id": 437112})
    assert response.status_code == 200
    data = response.json()
    assert "result" in data
    text = data["result"]
    assert "Bouquet of Sunflowers" in text
    assert "Claude Monet" in text
    assert "Oil on canvas" in text
    assert "European Paintings" in text
    assert "🌟 Met Highlight" in text
    assert "🔓 Open Access / Public Domain" in text


def test_get_artwork_details_not_found(client):
    response = client.post("/tools/get-artwork-details", json={"object_id": 9999999})
    assert response.status_code == 200
    assert "was not found in The Metropolitan Museum of Art collection" in response.json()["result"]


def test_get_artwork_details_negative_caching(client):
    # First lookup: not found, caches "NOT_FOUND"
    resp1 = client.post("/tools/get-artwork-details", json={"object_id": 9999999})
    assert resp1.status_code == 200
    assert cache.get("object:9999999") == "NOT_FOUND"

    # Second lookup hits negative cache
    resp2 = client.post("/tools/get-artwork-details", json={"object_id": 9999999})
    assert resp2.status_code == 200
    assert "was not found" in resp2.json()["result"]


def test_get_artwork_details_upstream_failure(monkeypatch):
    mock_client = httpx.AsyncClient(
        transport=MockTransport(object_status=500),
        headers={"User-Agent": "OmiTestApp/1.0"},
    )
    monkeypatch.setattr("main.http_client", mock_client)
    with TestClient(app) as c:
        response = c.post("/tools/get-artwork-details", json={"object_id": 437112})
        assert response.status_code == 502
        assert "The Metropolitan Museum of Art API returned status 500" in response.json()["detail"]


def test_get_artwork_details_invalid_id(client):
    response = client.post("/tools/get-artwork-details", json={"object_id": 0})
    assert response.status_code == 422


def test_list_departments_success(client):
    response = client.post("/tools/list-departments", json={})
    assert response.status_code == 200
    data = response.json()
    text = data["result"]
    assert "American Decorative Arts" in text
    assert "European Paintings" in text
    assert "Arms and Armor" in text


def test_list_departments_upstream_failure(monkeypatch):
    mock_client = httpx.AsyncClient(
        transport=MockTransport(departments_status=503),
        headers={"User-Agent": "OmiTestApp/1.0"},
    )
    monkeypatch.setattr("main.http_client", mock_client)
    with TestClient(app) as c:
        response = c.post("/tools/list-departments", json={})
        assert response.status_code == 502


def test_get_department_highlights_success(client):
    response = client.post("/tools/get-department-highlights", json={"department_id": 11, "limit": 2})
    assert response.status_code == 200
    data = response.json()
    text = data["result"]
    assert "Highlights from European Paintings" in text
    assert "Bouquet of Sunflowers" in text


def test_get_department_highlights_empty(monkeypatch):
    mock_client = httpx.AsyncClient(
        transport=MockTransport(search_total=0),
        headers={"User-Agent": "OmiTestApp/1.0"},
    )
    monkeypatch.setattr("main.http_client", mock_client)
    with TestClient(app) as c:
        resp = c.post("/tools/get-department-highlights", json={"department_id": 999})
        assert resp.status_code == 200
        assert "No curated highlights found for Met department ID `999`" in resp.json()["result"]


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
    resp = client.post("/tools/list-departments", json={})
    assert resp.status_code == 429
    assert "Rate limit exceeded" in resp.json()["detail"]


def test_trusted_proxy_forwarded_ip_used(client, monkeypatch):
    """Verify that when a request arrives from a trusted proxy, rate limiting is applied
    to the client IP in X-Forwarded-For rather than the proxy host.
    """
    monkeypatch.setattr("main.TRUSTED_PROXIES", {"testclient", "127.0.0.1", "::1"})

    ip1 = "198.51.100.11"
    ip2 = "198.51.100.22"

    # Exhaust rate limit specifically for ip1
    now = time.time()
    rate_limiter._records[ip1] = [now] * 60

    # Request with ip1 in X-Forwarded-For should receive 429
    resp_blocked = client.post(
        "/tools/list-departments",
        json={},
        headers={"X-Forwarded-For": ip1},
    )
    assert resp_blocked.status_code == 429
    assert "Rate limit exceeded" in resp_blocked.json()["detail"]

    # Request with ip2 in X-Forwarded-For has its own quota and succeeds
    resp_allowed = client.post(
        "/tools/list-departments",
        json={},
        headers={"X-Forwarded-For": ip2},
    )
    assert resp_allowed.status_code == 200

    # Direct request without X-Forwarded-For uses proxy host ("testclient") which has quota
    resp_direct = client.post(
        "/tools/list-departments",
        json={},
    )
    assert resp_direct.status_code == 200




def test_rate_limiter_spoof_prevention(client, monkeypatch):
    """Verify that untrusted connections cannot bypass rate limits by spoofing X-Forwarded-For,
    and spoofed headers do not pollute quotas of other client IPs.
    """
    # Direct host is untrusted
    monkeypatch.setattr("main.TRUSTED_PROXIES", {"10.0.0.1"})
    monkeypatch.setattr("main.is_trusted_proxy", lambda ip: False)

    spoofed_ip = "198.51.100.99"

    # Exhaust quota for the direct connection host "testclient"
    now = time.time()
    rate_limiter._records["testclient"] = [now] * 60

    # Even though X-Forwarded-For specifies spoofed_ip, the untrusted client is blocked on direct IP
    resp = client.post(
        "/tools/list-departments",
        json={},
        headers={"X-Forwarded-For": spoofed_ip},
    )
    assert resp.status_code == 429
    assert "Rate limit exceeded" in resp.json()["detail"]

    # Ensure the spoofed IP was never tracked or exhausted
    assert spoofed_ip not in rate_limiter._records



