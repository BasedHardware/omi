import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

import routers.auto_model as am


def test_score_formula_clamping_and_weights():
    """Test score formula normalizes quality [0, 100] and speed [0, 250]."""
    # Quality 100, Speed 250 -> 0.65 * 1.0 + 0.35 * 1.0 = 1.0
    assert am._score(100.0, 250.0) == pytest.approx(1.0)

    # Quality 0, Speed 0 -> 0.0
    assert am._score(0.0, 0.0) == pytest.approx(0.0)

    # Clamping upper bound: quality 150 -> 100, speed 500 -> 250
    assert am._score(150.0, 500.0) == pytest.approx(1.0)

    # Clamping lower bound
    assert am._score(-50.0, -10.0) == pytest.approx(0.0)

    # Intermediate calculation
    # Quality 80 -> 0.8 * 0.65 = 0.52
    # Speed 125 -> 0.5 * 0.35 = 0.175
    # Total = 0.695
    assert am._score(80.0, 125.0) == pytest.approx(0.695)


@pytest.mark.asyncio
async def test_fetch_and_score_without_api_key(monkeypatch):
    """When ARTIFICIALANALYSIS_API_KEY is not set, default to geminiFlashLive."""
    monkeypatch.delenv("ARTIFICIALANALYSIS_API_KEY", raising=False)
    provider, detail = await am._fetch_and_score()
    assert provider == "geminiFlashLive"
    assert "no ARTIFICIALANALYSIS_API_KEY" in detail["reason"]


@pytest.mark.asyncio
async def test_fetch_and_score_with_mocked_models(monkeypatch):
    """Verify provider selection picks the highest weighted score from mock API data."""
    monkeypatch.setenv("ARTIFICIALANALYSIS_API_KEY", "mock_key_aa")

    mock_models = [
        {
            "slug": "gemini-3-5-flash-001",
            "evaluations": {"artificial_analysis_intelligence_index": 70.0},
            "median_output_tokens_per_second": 200.0,
        },
        {
            "slug": "gpt-5-preview",
            "evaluations": {"artificial_analysis_intelligence_index": 90.0},
            "median_output_tokens_per_second": 150.0,
        },
    ]

    mock_resp = MagicMock()
    mock_resp.json.return_value = {"data": mock_models}
    mock_resp.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_resp)
    mock_client.__aenter__.return_value = mock_client
    mock_client.__aexit__.return_value = None

    # backend/AGENTS.md: use patch.object on the target module instead of string patch
    with patch.object(httpx, "AsyncClient", return_value=mock_client):
        provider, detail = await am._fetch_and_score()
        # gemini: 0.65*(70/100) + 0.35*(200/250) = 0.455 + 0.28 = 0.735
        # gpt5:   0.65*(90/100) + 0.35*(150/250) = 0.585 + 0.21 = 0.795
        assert provider == "gptRealtime2"
        assert "gptRealtime2" in detail["scores"]
        assert "geminiFlashLive" in detail["scores"]


@pytest.mark.asyncio
async def test_auto_model_pick_caching_and_expiration(monkeypatch):
    """Test auto_model_pick caching and 24-hour expiration behavior."""
    # Isolate module cache with monkeypatch so teardown restores original
    monkeypatch.setattr(am, "_cache", {"provider": None, "ts": 0.0, "detail": {}})
    monkeypatch.delenv("ARTIFICIALANALYSIS_API_KEY", raising=False)

    base_time = 100000.0
    monkeypatch.setattr(time, "time", lambda: base_time)

    # First call initializes cache
    pick1 = await am.auto_model_pick(uid="user_123")
    assert pick1["provider"] == "geminiFlashLive"
    assert am._cache["ts"] == base_time

    # Advance time within 24-hour TTL (e.g., 1 hour later) -> should return cached value
    am._cache["provider"] = "cached_test_provider"
    monkeypatch.setattr(time, "time", lambda: base_time + 3600.0)
    pick2 = await am.auto_model_pick(uid="user_456")
    assert pick2["provider"] == "cached_test_provider"

    # Advance time past 24-hour TTL (e.g., 25 hours later) -> cache expires and re-fetches
    monkeypatch.setattr(time, "time", lambda: base_time + am.TTL_SECONDS + 10.0)
    pick3 = await am.auto_model_pick(uid="user_789")
    assert pick3["provider"] == "geminiFlashLive"
    assert am._cache["ts"] == base_time + am.TTL_SECONDS + 10.0


@pytest.mark.asyncio
async def test_auto_model_pick_concurrent_misses_single_refresh(monkeypatch):
    """Verify that multiple concurrent cache misses trigger only one _fetch_and_score refresh."""
    monkeypatch.setattr(am, "_cache", {"provider": None, "ts": 0.0, "detail": {}})

    fetch_mock = AsyncMock(return_value=("geminiFlashLive", {"reason": "single_fetch"}))
    monkeypatch.setattr(am, "_fetch_and_score", fetch_mock)

    # Trigger 5 concurrent calls
    tasks = [am.auto_model_pick(uid=f"user_{i}") for i in range(5)]
    results = await asyncio.gather(*tasks)

    # All calls should return the same provider
    for r in results:
        assert r["provider"] == "geminiFlashLive"

    # _fetch_and_score must have been called exactly once due to _cache_lock
    assert fetch_mock.call_count == 1
