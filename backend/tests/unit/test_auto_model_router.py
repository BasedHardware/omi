import logging
import time
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from models.auto_model import AutoModelPick
from routers.auto_model import (
    PROXY,
    QUALITY_WEIGHT,
    SPEED_CAP,
    SPEED_WEIGHT,
    TTL_SECONDS,
    _cache,
    _fetch_and_score,
    _score,
    auto_model_pick,
    router,
)
from utils.other.endpoints import get_current_user_uid


@pytest.fixture
def app():
    test_app = FastAPI()
    test_app.include_router(router)
    test_app.dependency_overrides[get_current_user_uid] = lambda: "test-user-uid"
    return test_app


@pytest.fixture
def client(app):
    return TestClient(app)


@pytest.fixture(autouse=True)
def reset_cache():
    _cache.clear()
    _cache.update({"provider": None, "ts": 0.0, "detail": {}})
    yield
    _cache.clear()
    _cache.update({"provider": None, "ts": 0.0, "detail": {}})


class TestScoreFormula:
    def test_score_calculation(self):
        # quality=80.0 -> 0.8 * 0.65 = 0.52
        # speed=125.0 -> (125/250) * 0.35 = 0.5 * 0.35 = 0.175
        # total = 0.695
        score = _score(80.0, 125.0)
        assert score == pytest.approx(0.695)

    def test_score_clamping(self):
        # quality > 100 clamped to 100; speed > 250 clamped to 250
        max_score = _score(150.0, 300.0)
        assert max_score == pytest.approx(QUALITY_WEIGHT + SPEED_WEIGHT)

        # negative values clamped to 0
        min_score = _score(-10.0, -50.0)
        assert min_score == pytest.approx(0.0)

    def test_score_defensive_parsing(self):
        # Non-numeric or missing data returns None instead of raising
        assert _score(None, 100.0) is None
        assert _score(80.0, None) is None
        assert _score("invalid", 100.0) is None
        assert _score(80.0, "bad_speed") is None
        # String floats should parse correctly
        assert _score("80.0", "125.0") == pytest.approx(0.695)


class TestAutoModelPickEndpoint:
    def test_auto_model_pick_no_api_key(self, client, monkeypatch):
        monkeypatch.delenv("ARTIFICIALANALYSIS_API_KEY", raising=False)

        resp = client.get("/v1/auto/model-pick")
        assert resp.status_code == 200
        data = resp.json()

        # Validates against Pydantic model contract
        pick = AutoModelPick(**data)
        assert pick.provider == "geminiFlashLive"
        assert pick.detail.get("reason") == "no ARTIFICIALANALYSIS_API_KEY; default to Gemini"
        assert pick.attribution == "https://artificialanalysis.ai/"
        assert pick.updated_at > 0

    def test_auto_model_pick_success(self, client, monkeypatch):
        monkeypatch.setenv("ARTIFICIALANALYSIS_API_KEY", "mock-aa-key")

        mock_data = {
            "data": [
                {
                    "slug": "gemini-3-5-flash-preview",
                    "evaluations": {"artificial_analysis_intelligence_index": 70.0},
                    "median_output_tokens_per_second": 125.0,
                },
                {
                    "slug": "gpt-5-omni",
                    "evaluations": {"artificial_analysis_intelligence_index": 90.0},
                    "median_output_tokens_per_second": 125.0,
                },
            ]
        }

        req = httpx.Request("GET", "https://artificialanalysis.ai")
        with patch("httpx.AsyncClient.get", return_value=httpx.Response(200, json=mock_data, request=req)):
            resp = client.get("/v1/auto/model-pick")
            assert resp.status_code == 200
            data = resp.json()

            pick = AutoModelPick(**data)
            # gptRealtime2 has higher quality score so it should be picked
            assert pick.provider == "gptRealtime2"
            assert "scores" in pick.detail
            assert pick.attribution == "https://artificialanalysis.ai/"

    def test_error_boundary_sanitizes_reason_and_masks_secrets(self, client, monkeypatch, caplog):
        monkeypatch.setenv("ARTIFICIALANALYSIS_API_KEY", "mock-aa-key")
        leak_secret = "sec_prod_live_9988776655"
        sensitive_msg = f"HTTP 500: Database failure connecting to auth host token={leak_secret}"

        with patch("routers.auto_model._fetch_and_score", side_effect=RuntimeError(sensitive_msg)):
            with caplog.at_level(logging.ERROR):
                resp = client.get("/v1/auto/model-pick")

            assert resp.status_code == 200
            data = resp.json()

            # Schema contract validated
            pick = AutoModelPick(**data)
            assert pick.provider == "geminiFlashLive"

            # Deterministic, client-safe fallback without leaking raw exception
            assert pick.detail.get("reason") == "Model evaluation unavailable; defaulting to Gemini"
            assert leak_secret not in str(data)
            assert "Database failure" not in str(data)

            # Server-side logs should have received sanitized message
            assert "auto model-pick fetch failed" in caplog.text
            assert leak_secret not in caplog.text

    def test_defensive_parsing_malformed_upstream_response(self, client, monkeypatch):
        monkeypatch.setenv("ARTIFICIALANALYSIS_API_KEY", "mock-aa-key")

        # Response with unexpected shapes: non-dict entries, missing fields, corrupted scores
        malformed_data = {
            "data": [
                "corrupted_string_item",
                None,
                {"slug": None},
                {
                    "slug": "gemini-3-5-flash",
                    "evaluations": "not-a-dict",
                    "median_output_tokens_per_second": "invalid",
                },
            ]
        }

        req = httpx.Request("GET", "https://artificialanalysis.ai")
        with patch("httpx.AsyncClient.get", return_value=httpx.Response(200, json=malformed_data, request=req)):
            resp = client.get("/v1/auto/model-pick")
            assert resp.status_code == 200
            data = resp.json()

            pick = AutoModelPick(**data)
            assert pick.provider == "geminiFlashLive"
            assert pick.detail.get("reason") == "no matching AA models"

    def test_caching_and_ttl(self, client, monkeypatch):
        monkeypatch.delenv("ARTIFICIALANALYSIS_API_KEY", raising=False)

        resp1 = client.get("/v1/auto/model-pick")
        assert resp1.status_code == 200
        ts1 = resp1.json()["updated_at"]

        # Subsequent call hits the cache without re-evaluating
        with patch("routers.auto_model._fetch_and_score", side_effect=Exception("Should not be called")):
            resp2 = client.get("/v1/auto/model-pick")
            assert resp2.status_code == 200
            assert resp2.json()["updated_at"] == ts1

    def test_stale_cache_preservation_on_refresh_failure(self, client):
        # Prepopulate cache with an expired valid entry
        expired_ts = time.time() - (TTL_SECONDS + 100)
        _cache.update({"provider": "gptRealtime2", "ts": expired_ts, "detail": {"scores": {"gptRealtime2": 0.85}}})

        with patch("routers.auto_model._fetch_and_score", side_effect=RuntimeError("Network timeout")):
            resp = client.get("/v1/auto/model-pick")
            assert resp.status_code == 200
            data = resp.json()

            # Stale provider is preserved rather than overwritten
            assert data["provider"] == "gptRealtime2"
            assert data["detail"]["scores"]["gptRealtime2"] == 0.85
