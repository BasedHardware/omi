"""Unit tests for /v1/auto/model-pick (routers/auto_model.py).

Covers the defensive boundaries added for this endpoint:
- blank/whitespace uid is rejected before any upstream work
- upstream failures never reflect raw exception text (URLs, hostnames, tokens)
  into the client-visible `detail["reason"]`
- logged upstream errors are passed through the log sanitizer
- malformed / non-numeric upstream payloads degrade instead of raising
- the daily cache is served without a second upstream call
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import routers.auto_model as auto_model


@pytest.fixture(autouse=True)
def _reset_cache():
    """Each test starts from a cold cache and a clean lock."""
    auto_model._cache.update(provider=None, ts=0.0, detail={})
    auto_model._cache_lock = asyncio.Lock()
    yield
    auto_model._cache.update(provider=None, ts=0.0, detail={})


def _client(uid: str = "user-1") -> TestClient:
    app = FastAPI()
    app.include_router(auto_model.router)
    app.dependency_overrides[auto_model.auth.get_current_user_uid] = lambda: uid
    return TestClient(app, raise_server_exceptions=False)


def _models_payload(*models):
    return {"data": list(models)}


def _model(slug, quality, speed):
    return {
        "slug": slug,
        "evaluations": {"artificial_analysis_intelligence_index": quality},
        "median_output_tokens_per_second": speed,
    }


def _patch_fetch(monkeypatch, payload=None, error=None):
    """Replace the httpx call inside _fetch_and_score with a deterministic stub."""

    class _FakeResponse:
        def __init__(self):
            self._payload = payload

        def raise_for_status(self):
            if error is not None:
                raise error

        def json(self):
            return self._payload

    class _FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def get(self, url, headers=None):
            return _FakeResponse()

    monkeypatch.setenv("ARTIFICIALANALYSIS_API_KEY", "test-key")
    monkeypatch.setattr(auto_model.httpx, "AsyncClient", _FakeClient)


# --- uid validation ---------------------------------------------------------


@pytest.mark.parametrize("uid", ["", "   ", "\t\n"])
def test_blank_uid_is_unauthorized(uid):
    """A blank or whitespace-only subject is rejected with 401."""
    response = _client(uid=uid).get("/v1/auto/model-pick")
    assert response.status_code == 401
    assert response.json()["detail"] == "Unauthorized"


def test_blank_uid_does_not_touch_upstream(monkeypatch):
    """The 401 is raised before any upstream fetch is attempted."""
    calls = {"n": 0}

    async def _spy():
        calls["n"] += 1
        return "geminiFlashLive", {}

    monkeypatch.setattr(auto_model, "_refresh_cache", _spy)
    response = _client(uid="").get("/v1/auto/model-pick")
    assert response.status_code == 401
    assert calls["n"] == 0


def test_valid_uid_returns_the_pick(monkeypatch):
    _patch_fetch(
        monkeypatch,
        payload=_models_payload(_model("gemini-3-5-flash", 90, 200), _model("gpt-5", 70, 100)),
    )
    body = _client().get("/v1/auto/model-pick").json()
    assert body["provider"] == "geminiFlashLive"
    assert body["detail"]["scores"]["geminiFlashLive"] > body["detail"]["scores"]["gptRealtime2"]


# --- no secret / infrastructure reflection ----------------------------------


def test_http_status_error_does_not_leak_url(monkeypatch):
    """raise_for_status() embeds the request URL; it must not reach the client."""
    request = httpx.Request("GET", auto_model.AA_URL)
    error = httpx.HTTPStatusError(
        "Server error '500 Internal Server Error' for url 'https://artificialanalysis.ai/api/v2/data/llms/models'",
        request=request,
        response=httpx.Response(500, request=request),
    )
    _patch_fetch(monkeypatch, error=error)
    body = _client().get("/v1/auto/model-pick").json()
    reason = body["detail"]["reason"]
    assert reason == auto_model._FALLBACK_REASON
    assert "artificialanalysis" not in reason
    assert "500" not in reason
    assert "http" not in reason.lower()


def test_connect_error_does_not_leak_hostname(monkeypatch):
    error = httpx.ConnectError(
        "[Errno -2] Name or service not known for internal-host.prod.local",
        request=httpx.Request("GET", auto_model.AA_URL),
    )
    _patch_fetch(monkeypatch, error=error)
    body = _client().get("/v1/auto/model-pick").json()
    assert "internal-host" not in body["detail"]["reason"]
    assert body["detail"]["reason"] == auto_model._FALLBACK_REASON


def test_token_in_exception_is_not_reflected(monkeypatch):
    """A token that appears inside an upstream trace must not reach the client."""
    error = httpx.HTTPStatusError(
        "401 Unauthorized for url 'https://artificialanalysis.ai/api?key=sk-live-ABCDEF1234567890'",
        request=httpx.Request("GET", auto_model.AA_URL),
        response=httpx.Response(401, request=httpx.Request("GET", auto_model.AA_URL)),
    )
    _patch_fetch(monkeypatch, error=error)
    body = _client().get("/v1/auto/model-pick").json()
    assert "sk-live-ABCDEF1234567890" not in body["detail"]["reason"]


def test_logged_error_is_sanitized(monkeypatch, caplog):
    """The raw exception is logged through sanitize(), which masks the token."""
    error = httpx.ConnectError(
        "failed against https://aa.internal/api?key=sk-live-ABCDEF1234567890",
        request=httpx.Request("GET", auto_model.AA_URL),
    )
    _patch_fetch(monkeypatch, error=error)
    with caplog.at_level("ERROR", logger="routers.auto_model"):
        _client().get("/v1/auto/model-pick")
    logged = " ".join(r.getMessage() for r in caplog.records)
    assert "auto model-pick fetch failed" in logged
    assert "sk-live-ABCDEF1234567890" not in logged


# --- defensive scoring / schema parsing -------------------------------------


def test_non_numeric_metrics_do_not_crash(monkeypatch):
    """String / null / list metrics are skipped, not passed to _score."""
    _patch_fetch(
        monkeypatch,
        payload=_models_payload(
            _model("gemini-3-5-flash", "not-a-number", 200),
            _model("gpt-5", 80, None),
        ),
    )
    response = _client().get("/v1/auto/model-pick")
    assert response.status_code == 200
    body = response.json()
    assert body["provider"] == "geminiFlashLive"
    assert body["detail"]["reason"] == auto_model._FALLBACK_NO_MODELS


def test_numeric_string_metrics_are_coerced(monkeypatch):
    """A numeric string is still usable, so the pick is computed, not defaulted."""
    _patch_fetch(
        monkeypatch,
        payload=_models_payload(
            _model("gemini-3-5-flash", "90", "200"),
            _model("gpt-5", "60", "100"),
        ),
    )
    body = _client().get("/v1/auto/model-pick").json()
    assert body["provider"] == "geminiFlashLive"
    assert body["detail"]["scores"]["geminiFlashLive"] == pytest.approx(0.865, abs=1e-3)


def test_malformed_body_is_handled(monkeypatch):
    """A body that is not an object, or has no list under "data", degrades."""
    _patch_fetch(monkeypatch, payload=["unexpected"])
    response = _client().get("/v1/auto/model-pick")
    assert response.status_code == 200
    assert response.json()["detail"]["reason"] == auto_model._FALLBACK_NO_MODELS


def test_non_dict_entries_in_data_are_skipped(monkeypatch):
    _patch_fetch(
        monkeypatch,
        payload=_models_payload("nope", 42, _model("gpt-5", 60, 100)),
    )
    body = _client().get("/v1/auto/model-pick").json()
    assert body["provider"] == "gptRealtime2"


def test_missing_api_key_uses_default_without_fetch(monkeypatch):
    _patch_fetch(monkeypatch)
    monkeypatch.delenv("ARTIFICIALANALYSIS_API_KEY", raising=False)
    body = _client().get("/v1/auto/model-pick").json()
    assert body["provider"] == "geminiFlashLive"
    assert body["detail"]["reason"] == auto_model._FALLBACK_NO_KEY


# --- cache behaviour --------------------------------------------------------


def test_second_request_is_served_from_cache(monkeypatch):
    calls = {"n": 0}
    original = auto_model._fetch_and_score

    async def _counting():
        calls["n"] += 1
        return await original()

    _patch_fetch(
        monkeypatch,
        payload=_models_payload(_model("gemini-3-5-flash", 90, 200), _model("gpt-5", 70, 100)),
    )
    monkeypatch.setattr(auto_model, "_fetch_and_score", _counting)
    client = _client()
    client.get("/v1/auto/model-pick")
    client.get("/v1/auto/model-pick")
    assert calls["n"] == 1


def test_upstream_failure_keeps_serving_a_pick(monkeypatch):
    """A failed refresh still yields a usable provider rather than a 500."""
    _patch_fetch(monkeypatch, error=httpx.ConnectError("boom", request=httpx.Request("GET", auto_model.AA_URL)))
    response = _client().get("/v1/auto/model-pick")
    assert response.status_code == 200
    body = response.json()
    assert body["provider"] == "geminiFlashLive"
    assert body["attribution"] == "https://artificialanalysis.ai/"
    assert isinstance(body["detail"]["reason"], str)
