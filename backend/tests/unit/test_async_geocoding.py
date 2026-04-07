"""Tests for async_get_google_maps_location (issue #6369 Phase 1).

Verifies that the async geocoding function uses httpx.AsyncClient
instead of blocking requests.get.
"""

import json
import sys
import types
from unittest.mock import MagicMock, AsyncMock, patch

import pytest

# Mock database._client before importing anything that touches GCP
sys.modules.setdefault("database._client", MagicMock())

# Stub database.redis_db with r attribute
_redis_mod = sys.modules.get("database.redis_db")
if _redis_mod is None:
    _redis_mod = types.ModuleType("database.redis_db")
    sys.modules["database.redis_db"] = _redis_mod
if not hasattr(_redis_mod, 'r'):
    _redis_mod.r = MagicMock()

# Stub utils.http_client
if "utils.http_client" not in sys.modules:
    _http_mod = types.ModuleType("utils.http_client")
    _http_mod.get_maps_client = MagicMock()
    _http_mod.get_webhook_client = MagicMock()
    sys.modules["utils.http_client"] = _http_mod

from models.conversation import Geolocation
from utils.conversations.location import async_get_google_maps_location


class TestAsyncCacheHit:
    """When Redis has cached data, return without calling Google API."""

    @pytest.mark.asyncio
    async def test_cache_hit_returns_geolocation(self):
        cached = {
            "google_place_id": "ChIJIQBpAG2ahYAR_6128GcTUEo",
            "latitude": 37.785,
            "longitude": -122.409,
            "address": "San Francisco, CA",
            "location_type": "locality",
        }
        with patch("utils.conversations.location.r") as mock_r:
            mock_r.get.return_value = json.dumps(cached)
            mock_client = AsyncMock()

            with patch("utils.conversations.location.get_maps_client", return_value=mock_client):
                result = await async_get_google_maps_location(37.78512, -122.40932)

                # Should NOT call httpx
                mock_client.get.assert_not_called()

        assert isinstance(result, Geolocation)
        assert result.google_place_id == "ChIJIQBpAG2ahYAR_6128GcTUEo"


class TestAsyncCacheMiss:
    """When Redis has no cached data, call Google API via httpx and cache result."""

    @pytest.mark.asyncio
    async def test_cache_miss_calls_httpx(self):
        api_response = {
            "status": "OK",
            "results": [
                {
                    "place_id": "ChIJ_test",
                    "formatted_address": "123 Test St",
                    "types": ["street_address"],
                }
            ],
        }
        mock_httpx_response = MagicMock()
        mock_httpx_response.json.return_value = api_response

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_httpx_response)

        with patch("utils.conversations.location.r") as mock_r, patch(
            "utils.conversations.location.get_maps_client", return_value=mock_client
        ), patch.dict("os.environ", {"GOOGLE_MAPS_API_KEY": "test-key"}):
            mock_r.get.return_value = None

            result = await async_get_google_maps_location(37.785, -122.409)

        assert result is not None
        assert result.google_place_id == "ChIJ_test"
        mock_client.get.assert_called_once()

        # Verify cached with 48h TTL
        cache_call = mock_r.set.call_args
        assert cache_call[1]["ex"] == 172800

    @pytest.mark.asyncio
    async def test_uses_params_not_url_interpolation(self):
        """Verify httpx uses params dict instead of URL string interpolation."""
        api_response = {
            "status": "OK",
            "results": [{"place_id": "ChIJ_test", "formatted_address": "123 Test St", "types": ["route"]}],
        }
        mock_httpx_response = MagicMock()
        mock_httpx_response.json.return_value = api_response

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_httpx_response)

        with patch("utils.conversations.location.r") as mock_r, patch(
            "utils.conversations.location.get_maps_client", return_value=mock_client
        ), patch.dict("os.environ", {"GOOGLE_MAPS_API_KEY": "test-key"}):
            mock_r.get.return_value = None

            await async_get_google_maps_location(37.785, -122.409)

        call_kwargs = mock_client.get.call_args.kwargs
        assert "params" in call_kwargs
        assert "37.785,-122.409" in call_kwargs["params"]["latlng"]


class TestAsyncApiEdgeCases:
    """Edge cases in async Google Maps API responses."""

    @pytest.mark.asyncio
    async def test_api_status_not_ok_returns_none(self):
        mock_httpx_response = MagicMock()
        mock_httpx_response.json.return_value = {"status": "ZERO_RESULTS", "results": []}

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_httpx_response)

        with patch("utils.conversations.location.r") as mock_r, patch(
            "utils.conversations.location.get_maps_client", return_value=mock_client
        ), patch.dict("os.environ", {"GOOGLE_MAPS_API_KEY": "test-key"}):
            mock_r.get.return_value = None
            result = await async_get_google_maps_location(37.785, -122.409)

        assert result is None

    @pytest.mark.asyncio
    async def test_missing_place_id_returns_none(self):
        mock_httpx_response = MagicMock()
        mock_httpx_response.json.return_value = {
            "status": "OK",
            "results": [{"place_id": None, "formatted_address": "Nowhere", "types": []}],
        }

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_httpx_response)

        with patch("utils.conversations.location.r") as mock_r, patch(
            "utils.conversations.location.get_maps_client", return_value=mock_client
        ), patch.dict("os.environ", {"GOOGLE_MAPS_API_KEY": "test-key"}):
            mock_r.get.return_value = None
            result = await async_get_google_maps_location(37.785, -122.409)

        assert result is None

    @pytest.mark.asyncio
    async def test_redis_failure_falls_through(self):
        api_response = {
            "status": "OK",
            "results": [{"place_id": "ChIJ_fallback", "formatted_address": "Fallback St", "types": ["route"]}],
        }
        mock_httpx_response = MagicMock()
        mock_httpx_response.json.return_value = api_response

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_httpx_response)

        with patch("utils.conversations.location.r") as mock_r, patch(
            "utils.conversations.location.get_maps_client", return_value=mock_client
        ), patch.dict("os.environ", {"GOOGLE_MAPS_API_KEY": "test-key"}):
            mock_r.get.side_effect = ConnectionError("Redis down")

            result = await async_get_google_maps_location(37.785, -122.409)

        assert result is not None
        assert result.google_place_id == "ChIJ_fallback"

    @pytest.mark.asyncio
    async def test_httpx_timeout_returns_none(self):
        """Verify httpx timeout returns None instead of propagating."""
        import httpx

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=httpx.TimeoutException("timeout"))

        with patch("utils.conversations.location.r") as mock_r, patch(
            "utils.conversations.location.get_maps_client", return_value=mock_client
        ), patch.dict("os.environ", {"GOOGLE_MAPS_API_KEY": "test-key"}):
            mock_r.get.return_value = None
            result = await async_get_google_maps_location(37.785, -122.409)

        assert result is None
