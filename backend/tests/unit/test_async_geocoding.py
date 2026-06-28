"""Tests for async_get_google_maps_location (issue #6369 Phase 1).

Verifies that the async geocoding function uses httpx.AsyncClient
instead of blocking requests.get.
"""

import asyncio
import json
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock, patch

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[2]

_RESTORED_MODULES = (
    "database._client",
    "database.redis_db",
    "models",
    "models.conversation",
    "utils",
    "utils.conversations",
    "utils.conversations.location",
    "utils.http_client",
)
_MISSING = object()
_saved_modules = {name: sys.modules.get(name, _MISSING) for name in _RESTORED_MODULES}


def _install_module(name, module):
    sys.modules[name] = module
    if "." in name:
        parent_name, attr = name.rsplit(".", 1)
        parent = sys.modules.get(parent_name)
        if parent is not None:
            setattr(parent, attr, module)


def _restore_modules():
    for name in sorted(_RESTORED_MODULES, key=lambda module_name: module_name.count("."), reverse=True):
        current = sys.modules.get(name)
        original = _saved_modules[name]
        if original is _MISSING:
            sys.modules.pop(name, None)
            if "." in name:
                parent_name, attr = name.rsplit(".", 1)
                parent = sys.modules.get(parent_name)
                if parent is not None and getattr(parent, attr, _MISSING) is current:
                    delattr(parent, attr)
        else:
            sys.modules[name] = original
            if "." in name:
                parent_name, attr = name.rsplit(".", 1)
                parent = sys.modules.get(parent_name)
                if parent is not None:
                    setattr(parent, attr, original)


def _ensure_package_path(name: str, path: Path) -> types.ModuleType:
    module = sys.modules.get(name)
    if module is None or not hasattr(module, "__path__"):
        module = types.ModuleType(name)
        sys.modules[name] = module

    module.__path__ = [str(path)]

    if "." in name:
        parent_name, attr_name = name.rsplit(".", 1)
        parent = sys.modules.get(parent_name)
        if parent is not None:
            setattr(parent, attr_name, module)

    return module


def _drop_stale_module(name: str, expected_file: Path) -> None:
    module = sys.modules.get(name)
    if module is None:
        return

    module_file = getattr(module, "__file__", None)
    try:
        module_path = Path(module_file).resolve() if module_file else None
    except TypeError:
        module_path = None

    if module_path == expected_file.resolve():
        return

    sys.modules.pop(name, None)

    if "." in name:
        parent_name, attr_name = name.rsplit(".", 1)
        parent = sys.modules.get(parent_name)
        if parent is not None and getattr(parent, attr_name, None) is module:
            delattr(parent, attr_name)


_ensure_package_path("models", BACKEND_DIR / "models")
_ensure_package_path("utils", BACKEND_DIR / "utils")
_ensure_package_path("utils.conversations", BACKEND_DIR / "utils" / "conversations")
_drop_stale_module("models.conversation", BACKEND_DIR / "models" / "conversation.py")
_drop_stale_module("utils.conversations.location", BACKEND_DIR / "utils" / "conversations" / "location.py")


# Mock database._client before importing anything that touches GCP
_install_module("database._client", MagicMock())

# Stub database.redis_db with r attribute
_redis_mod = types.ModuleType("database.redis_db")
_redis_mod.r = MagicMock()
_install_module("database.redis_db", _redis_mod)

# Stub utils.http_client
_http_mod = sys.modules.get("utils.http_client")
if _http_mod is None:
    _http_mod = types.ModuleType("utils.http_client")
if not hasattr(_http_mod, "get_maps_client"):
    _http_mod.get_maps_client = MagicMock()
if not hasattr(_http_mod, "get_webhook_client"):
    _http_mod.get_webhook_client = MagicMock()
if not hasattr(_http_mod, "get_maps_semaphore"):
    _http_mod.get_maps_semaphore = MagicMock(return_value=asyncio.Semaphore(8))
_install_module("utils.http_client", _http_mod)

try:
    from models.conversation import Geolocation
    from utils.conversations import location as location_module

    async_get_google_maps_location = location_module.async_get_google_maps_location
finally:
    _restore_modules()


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
        with patch.object(location_module, "r") as mock_r:
            mock_r.get.return_value = json.dumps(cached)
            mock_client = AsyncMock()

            with patch.object(location_module, "get_maps_client", return_value=mock_client):
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

        with patch.object(location_module, "r") as mock_r, patch.object(
            location_module, "get_maps_client", return_value=mock_client
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

        with patch.object(location_module, "r") as mock_r, patch.object(
            location_module, "get_maps_client", return_value=mock_client
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

        with patch.object(location_module, "r") as mock_r, patch.object(
            location_module, "get_maps_client", return_value=mock_client
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

        with patch.object(location_module, "r") as mock_r, patch.object(
            location_module, "get_maps_client", return_value=mock_client
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

        with patch.object(location_module, "r") as mock_r, patch.object(
            location_module, "get_maps_client", return_value=mock_client
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

        with patch.object(location_module, "r") as mock_r, patch.object(
            location_module, "get_maps_client", return_value=mock_client
        ), patch.dict("os.environ", {"GOOGLE_MAPS_API_KEY": "test-key"}):
            mock_r.get.return_value = None
            result = await async_get_google_maps_location(37.785, -122.409)

        assert result is None
