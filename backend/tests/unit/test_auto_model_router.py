import asyncio
import time
import pytest
import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient

from routers.auto_model import router, _reset_cache, _score
from utils.other.endpoints import get_current_user_uid

LEAK_SECRET = "sec_abc123xyz789_api_key_forbidden"


@pytest.fixture(autouse=True)
def clean_cache():
    _reset_cache()
    yield
    _reset_cache()


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user_uid] = lambda: "user_valid_123"
    with TestClient(app) as tc:
        yield tc
    app.dependency_overrides.clear()


def test_score_formula():
    # 50 quality, 125 speed -> 0.65 * 0.5 + 0.35 * (125 / 250) = 0.325 + 0.175 = 0.5
    s = _score(50.0, 125.0)
    assert s == pytest.approx(0.5)

    # Clamping tests
    assert _score(-10.0, -50.0) == pytest.approx(0.0)
    assert _score(150.0, 500.0) == pytest.approx(1.0)

    # Malformed non-numeric values gracefully return None
    assert _score("invalid", 100) is None
    assert _score(100, None) is None
    assert _score({}, []) is None


def test_auto_model_pick_no_api_key(client, monkeypatch):
    monkeypatch.delenv("ARTIFICIALANALYSIS_API_KEY", raising=False)
    resp = client.get("/v1/auto/model-pick")
    assert resp.status_code == 200
    data = resp.json()
    assert data["provider"] == "geminiFlashLive"
    assert "no ARTIFICIALANALYSIS_API_KEY" in data["detail"]["reason"]
    assert data["attribution"] == "https://artificialanalysis.ai/"


def test_auto_model_pick_success_gemini_highest(client, monkeypatch):
    monkeypatch.setenv("ARTIFICIALANALYSIS_API_KEY", "test_key")

    mock_models = [
        {
            "slug": "google/gemini-3-5-flash",
            "median_output_tokens_per_second": 200.0,
            "evaluations": {
                "artificial_analysis_intelligence_index": 90.0,
            },
        },
        {
            "slug": "openai/gpt-5",
            "median_output_tokens_per_second": 150.0,
            "evaluations": {
                "artificial_analysis_intelligence_index": 80.0,
            },
        },
    ]

    async def mock_get(self, url, **kwargs):
        req = httpx.Request("GET", url)
        return httpx.Response(200, json={"data": mock_models}, request=req)

    monkeypatch.setattr(httpx.AsyncClient, "get", mock_get)

    resp = client.get("/v1/auto/model-pick")
    assert resp.status_code == 200
    data = resp.json()
    assert data["provider"] == "geminiFlashLive"
    assert "geminiFlashLive" in data["detail"]["scores"]
    assert "gptRealtime2" in data["detail"]["scores"]
    assert data["detail"]["scores"]["geminiFlashLive"] > data["detail"]["scores"]["gptRealtime2"]


def test_auto_model_pick_success_gpt_highest(client, monkeypatch):
    monkeypatch.setenv("ARTIFICIALANALYSIS_API_KEY", "test_key")

    mock_models = [
        {
            "slug": "google/gemini-3-5-flash",
            "median_output_tokens_per_second": 100.0,
            "evaluations": {
                "artificial_analysis_intelligence_index": 70.0,
            },
        },
        {
            "slug": "openai/gpt-5",
            "median_output_tokens_per_second": 220.0,
            "evaluations": {
                "artificial_analysis_intelligence_index": 95.0,
            },
        },
    ]

    async def mock_get(self, url, **kwargs):
        req = httpx.Request("GET", url)
        return httpx.Response(200, json={"data": mock_models}, request=req)

    monkeypatch.setattr(httpx.AsyncClient, "get", mock_get)

    resp = client.get("/v1/auto/model-pick")
    assert resp.status_code == 200
    data = resp.json()
    assert data["provider"] == "gptRealtime2"


def test_auto_model_pick_api_error_sanitization_and_leak_prevention(client, monkeypatch):
    monkeypatch.setenv("ARTIFICIALANALYSIS_API_KEY", "test_key")

    async def mock_failing_get(self, url, **kwargs):
        req = httpx.Request("GET", f"{url}?token={LEAK_SECRET}")
        raise httpx.HTTPStatusError(
            f"500 Internal Server Error: backend db connection refused at {LEAK_SECRET}",
            request=req,
            response=httpx.Response(500, request=req, text=f"FATAL: {LEAK_SECRET}"),
        )

    monkeypatch.setattr(httpx.AsyncClient, "get", mock_failing_get)

    resp = client.get("/v1/auto/model-pick")
    assert resp.status_code == 200
    data = resp.json()
    assert data["provider"] == "geminiFlashLive"
    assert data["detail"]["reason"] == "model scoring fetch failed; default to Gemini"

    # Assert leak prevention: raw exception / secret must never appear in response body
    raw_response = resp.text
    assert LEAK_SECRET not in raw_response
    assert "FATAL" not in raw_response
    assert "connection refused" not in raw_response


def test_auto_model_pick_network_timeout(client, monkeypatch):
    monkeypatch.setenv("ARTIFICIALANALYSIS_API_KEY", "test_key")

    async def mock_timeout(self, url, **kwargs):
        req = httpx.Request("GET", url)
        raise httpx.TimeoutException("Connection timed out", request=req)

    monkeypatch.setattr(httpx.AsyncClient, "get", mock_timeout)

    resp = client.get("/v1/auto/model-pick")
    assert resp.status_code == 200
    data = resp.json()
    assert data["provider"] == "geminiFlashLive"
    assert data["detail"]["reason"] == "model scoring fetch failed; default to Gemini"


def test_auto_model_pick_malformed_json_response(client, monkeypatch):
    monkeypatch.setenv("ARTIFICIALANALYSIS_API_KEY", "test_key")

    async def mock_malformed(self, url, **kwargs):
        req = httpx.Request("GET", url)
        return httpx.Response(200, json=["unexpected", "array"], request=req)

    monkeypatch.setattr(httpx.AsyncClient, "get", mock_malformed)

    resp = client.get("/v1/auto/model-pick")
    assert resp.status_code == 200
    data = resp.json()
    assert data["provider"] == "geminiFlashLive"
    assert data["detail"]["reason"] == "no matching AA models"


def test_auto_model_pick_non_numeric_evaluations(client, monkeypatch):
    monkeypatch.setenv("ARTIFICIALANALYSIS_API_KEY", "test_key")

    mock_models = [
        {
            "slug": "gemini-3-5-flash",
            "median_output_tokens_per_second": "invalid",
            "evaluations": {
                "artificial_analysis_intelligence_index": "not_a_number",
            },
        },
        {
            "slug": "gpt-5",
            "median_output_tokens_per_second": 180.0,
            "evaluations": {
                "artificial_analysis_intelligence_index": 85.0,
            },
        },
    ]

    async def mock_get(self, url, **kwargs):
        req = httpx.Request("GET", url)
        return httpx.Response(200, json={"data": mock_models}, request=req)

    monkeypatch.setattr(httpx.AsyncClient, "get", mock_get)

    resp = client.get("/v1/auto/model-pick")
    assert resp.status_code == 200
    data = resp.json()
    assert data["provider"] == "gptRealtime2"


def test_auto_model_pick_caching_and_ttl(client, monkeypatch):
    monkeypatch.setenv("ARTIFICIALANALYSIS_API_KEY", "test_key")
    call_count = 0

    mock_models = [
        {
            "slug": "gemini-3-5-flash",
            "median_output_tokens_per_second": 210.0,
            "evaluations": {
                "artificial_analysis_intelligence_index": 92.0,
            },
        }
    ]

    async def mock_get(self, url, **kwargs):
        nonlocal call_count
        call_count += 1
        req = httpx.Request("GET", url)
        return httpx.Response(200, json={"data": mock_models}, request=req)

    monkeypatch.setattr(httpx.AsyncClient, "get", mock_get)

    # First call: cache miss, triggers fetch
    resp1 = client.get("/v1/auto/model-pick")
    assert resp1.status_code == 200
    assert call_count == 1
    t1 = resp1.json()["updated_at"]

    # Second call: cache hit, no fetch
    resp2 = client.get("/v1/auto/model-pick")
    assert resp2.status_code == 200
    assert call_count == 1
    assert resp2.json()["updated_at"] == t1


def test_auto_model_pick_cache_refresh_after_ttl(client, monkeypatch):
    monkeypatch.setenv("ARTIFICIALANALYSIS_API_KEY", "test_key")
    call_count = 0

    mock_models = [
        {
            "slug": "gemini-3-5-flash",
            "median_output_tokens_per_second": 210.0,
            "evaluations": {
                "artificial_analysis_intelligence_index": 92.0,
            },
        }
    ]

    async def mock_get(self, url, **kwargs):
        nonlocal call_count
        call_count += 1
        req = httpx.Request("GET", url)
        return httpx.Response(200, json={"data": mock_models}, request=req)

    monkeypatch.setattr(httpx.AsyncClient, "get", mock_get)

    # Call at t=1000
    monkeypatch.setattr(time, "time", lambda: 1000.0)
    resp1 = client.get("/v1/auto/model-pick")
    assert resp1.status_code == 200
    assert call_count == 1

    # Call at t=1000 + 86401 (past 24h TTL) -> triggers refresh
    monkeypatch.setattr(time, "time", lambda: 1000.0 + 86401.0)
    resp2 = client.get("/v1/auto/model-pick")
    assert resp2.status_code == 200
    assert call_count == 2
    assert resp2.json()["updated_at"] == 1000.0 + 86401.0


def test_auto_model_pick_stale_cache_preserved_on_refresh_failure(client, monkeypatch):
    monkeypatch.setenv("ARTIFICIALANALYSIS_API_KEY", "test_key")

    mock_models = [
        {
            "slug": "gpt-5",
            "median_output_tokens_per_second": 220.0,
            "evaluations": {
                "artificial_analysis_intelligence_index": 95.0,
            },
        }
    ]

    async def mock_success(self, url, **kwargs):
        req = httpx.Request("GET", url)
        return httpx.Response(200, json={"data": mock_models}, request=req)

    monkeypatch.setattr(httpx.AsyncClient, "get", mock_success)
    monkeypatch.setattr(time, "time", lambda: 1000.0)

    # Initial successful populate
    resp1 = client.get("/v1/auto/model-pick")
    assert resp1.status_code == 200
    assert resp1.json()["provider"] == "gptRealtime2"

    # Now simulate TTL expiration with failing API
    async def mock_failing(self, url, **kwargs):
        req = httpx.Request("GET", url)
        raise httpx.RequestError("Network drop", request=req)

    monkeypatch.setattr(httpx.AsyncClient, "get", mock_failing)
    monkeypatch.setattr(time, "time", lambda: 1000.0 + 90000.0)

    resp2 = client.get("/v1/auto/model-pick")
    assert resp2.status_code == 200
    # Preserves existing cached pick rather than wiping to fallback
    assert resp2.json()["provider"] == "gptRealtime2"


def test_auto_model_pick_unauthorized_empty_uid():
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user_uid] = lambda: "   "
    with TestClient(app) as tc:
        resp = tc.get("/v1/auto/model-pick")
        assert resp.status_code == 401
        assert resp.json()["detail"] == "Unauthorized"


@pytest.mark.anyio
async def test_auto_model_pick_concurrent_requests_single_fetch(monkeypatch):
    monkeypatch.setenv("ARTIFICIALANALYSIS_API_KEY", "test_key")
    call_count = 0

    mock_models = [
        {
            "slug": "google/gemini-3-5-flash",
            "median_output_tokens_per_second": 200.0,
            "evaluations": {
                "artificial_analysis_intelligence_index": 90.0,
            },
        }
    ]

    async def mock_get(self, url, **kwargs):
        nonlocal call_count
        call_count += 1
        await asyncio.sleep(0.05)  # simulate network latency
        req = httpx.Request("GET", url)
        return httpx.Response(200, json={"data": mock_models}, request=req)

    monkeypatch.setattr(httpx.AsyncClient, "get", mock_get)

    from routers.auto_model import auto_model_pick

    tasks = [auto_model_pick("user_test") for _ in range(5)]
    results = await asyncio.gather(*tasks)

    assert len(results) == 5
    for r in results:
        assert r["provider"] == "geminiFlashLive"
    assert call_count == 1
