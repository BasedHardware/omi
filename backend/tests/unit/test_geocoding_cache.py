"""Tests for geocoding Redis cache (PR #4688, issue #4653).

Verifies that:
1. Cache key uses ~100m precision (3 decimal places)
2. Cache hits return Geolocation without API call
3. Cache misses call Google Maps API and store result
4. Redis failures are logged but don't break the function
5. geo.dict() is used for serialization (Pydantic-safe)
"""

import json
import sys
from unittest.mock import MagicMock, patch

# Mock database._client before importing anything that touches GCP
sys.modules.setdefault("database._client", MagicMock())

from models.conversation import Geolocation
from utils.conversations.location import get_google_maps_location


class TestCacheKeyPrecision:
    """Cache key should round to 3 decimal places (~100m)."""

    def test_3_decimal_rounding(self):
        """Coordinates rounded to .3f give ~100m precision."""
        # 37.78512 -> 37.785, -122.40932 -> -122.409
        with patch("utils.conversations.location.r") as mock_r:
            mock_r.get.return_value = None
            with patch("utils.conversations.location.requests") as mock_req:
                mock_resp = MagicMock()
                mock_resp.json.return_value = {"status": "OK", "results": []}
                mock_req.get.return_value = mock_resp

                get_google_maps_location(37.78512, -122.40932)

            mock_r.get.assert_called_once_with("geocode:37.785,-122.409")

    def test_nearby_coords_same_cache_key(self):
        """Two points <100m apart should share a cache key."""
        # Both round to 37.785,-122.409
        rounded_a = f"{37.78512:.3f},{-122.40932:.3f}"
        rounded_b = f"{37.78519:.3f},{-122.40938:.3f}"
        assert rounded_a == rounded_b

    def test_distant_coords_different_cache_key(self):
        """Two points >100m apart should have different cache keys."""
        rounded_a = f"{37.785:.3f},{-122.409:.3f}"
        rounded_b = f"{37.786:.3f},{-122.409:.3f}"
        assert rounded_a != rounded_b


class TestCacheHit:
    """When Redis has cached data, return it without calling Google API."""

    def test_cache_hit_returns_geolocation(self):
        cached = {
            "google_place_id": "ChIJIQBpAG2ahYAR_6128GcTUEo",
            "latitude": 37.785,
            "longitude": -122.409,
            "address": "San Francisco, CA",
            "location_type": "locality",
        }
        with patch("utils.conversations.location.r") as mock_r:
            mock_r.get.return_value = json.dumps(cached)
            with patch("utils.conversations.location.requests") as mock_req:
                result = get_google_maps_location(37.78512, -122.40932)

                # Should NOT call Google API
                mock_req.get.assert_not_called()

        assert isinstance(result, Geolocation)
        assert result.google_place_id == "ChIJIQBpAG2ahYAR_6128GcTUEo"
        assert result.address == "San Francisco, CA"

    def test_cache_hit_no_api_key_needed(self):
        """Cache hit works even without GOOGLE_MAPS_API_KEY set."""
        cached = {"latitude": 37.785, "longitude": -122.409}
        with patch("utils.conversations.location.r") as mock_r:
            mock_r.get.return_value = json.dumps(cached)
            with patch.dict("os.environ", {}, clear=True):
                with patch("utils.conversations.location.requests") as mock_req:
                    result = get_google_maps_location(37.785, -122.409)
                    mock_req.get.assert_not_called()
        assert result is not None


class TestCacheMiss:
    """When Redis has no cached data, call Google API and cache result."""

    def test_cache_miss_calls_api_and_caches(self):
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
        with patch("utils.conversations.location.r") as mock_r:
            mock_r.get.return_value = None
            with patch("utils.conversations.location.requests") as mock_req:
                mock_resp = MagicMock()
                mock_resp.json.return_value = api_response
                mock_req.get.return_value = mock_resp

                result = get_google_maps_location(37.785, -122.409)

        assert result is not None
        assert result.google_place_id == "ChIJ_test"
        assert result.address == "123 Test St"

        # Verify cached with geo.dict() and 48h TTL
        cache_call = mock_r.set.call_args
        cached_data = json.loads(cache_call[0][1])
        assert cached_data["google_place_id"] == "ChIJ_test"
        assert cached_data["latitude"] == 37.785
        assert cache_call[1]["ex"] == 172800

    def test_api_no_results_returns_none(self):
        with patch("utils.conversations.location.r") as mock_r:
            mock_r.get.return_value = None
            with patch("utils.conversations.location.requests") as mock_req:
                mock_resp = MagicMock()
                mock_resp.json.return_value = {"status": "OK", "results": []}
                mock_req.get.return_value = mock_resp

                result = get_google_maps_location(37.785, -122.409)

        assert result is None


class TestRedisFailure:
    """Redis errors should be logged but not break the function."""

    def test_redis_read_failure_falls_through_to_api(self):
        api_response = {
            "status": "OK",
            "results": [
                {
                    "place_id": "ChIJ_fallback",
                    "formatted_address": "Fallback St",
                    "types": ["route"],
                }
            ],
        }
        with patch("utils.conversations.location.r") as mock_r:
            mock_r.get.side_effect = ConnectionError("Redis down")
            with patch("utils.conversations.location.requests") as mock_req:
                mock_resp = MagicMock()
                mock_resp.json.return_value = api_response
                mock_req.get.return_value = mock_resp

                with patch("utils.conversations.location.logging") as mock_log:
                    result = get_google_maps_location(37.785, -122.409)
                    mock_log.warning.assert_called()

        assert result is not None
        assert result.google_place_id == "ChIJ_fallback"

    def test_redis_write_failure_still_returns_result(self):
        api_response = {
            "status": "OK",
            "results": [
                {
                    "place_id": "ChIJ_write_fail",
                    "formatted_address": "Write Fail St",
                    "types": ["route"],
                }
            ],
        }
        with patch("utils.conversations.location.r") as mock_r:
            mock_r.get.return_value = None
            mock_r.set.side_effect = ConnectionError("Redis down")
            with patch("utils.conversations.location.requests") as mock_req:
                mock_resp = MagicMock()
                mock_resp.json.return_value = api_response
                mock_req.get.return_value = mock_resp

                with patch("utils.conversations.location.logging") as mock_log:
                    result = get_google_maps_location(37.785, -122.409)
                    mock_log.warning.assert_called()

        assert result is not None
        assert result.google_place_id == "ChIJ_write_fail"


class TestApiEdgeCases:
    """Edge cases in Google Maps API responses."""

    def test_api_status_not_ok_returns_none(self):
        """Non-OK status (e.g. ZERO_RESULTS, OVER_QUERY_LIMIT) returns None."""
        with patch("utils.conversations.location.r") as mock_r:
            mock_r.get.return_value = None
            with patch("utils.conversations.location.requests") as mock_req:
                mock_resp = MagicMock()
                mock_resp.json.return_value = {"status": "ZERO_RESULTS", "results": []}
                mock_req.get.return_value = mock_resp

                result = get_google_maps_location(37.785, -122.409)

        assert result is None
        mock_r.set.assert_not_called()

    def test_missing_place_id_returns_none(self):
        """Result with no place_id returns None."""
        with patch("utils.conversations.location.r") as mock_r:
            mock_r.get.return_value = None
            with patch("utils.conversations.location.requests") as mock_req:
                mock_resp = MagicMock()
                mock_resp.json.return_value = {
                    "status": "OK",
                    "results": [{"place_id": None, "formatted_address": "Nowhere", "types": []}],
                }
                mock_req.get.return_value = mock_resp

                result = get_google_maps_location(37.785, -122.409)

        assert result is None

    def test_missing_place_id_key_returns_none(self):
        """Result with no place_id key at all returns None."""
        with patch("utils.conversations.location.r") as mock_r:
            mock_r.get.return_value = None
            with patch("utils.conversations.location.requests") as mock_req:
                mock_resp = MagicMock()
                mock_resp.json.return_value = {
                    "status": "OK",
                    "results": [{"formatted_address": "No ID St", "types": ["route"]}],
                }
                mock_req.get.return_value = mock_resp

                result = get_google_maps_location(37.785, -122.409)

        assert result is None

    def test_empty_types_gives_none_location_type(self):
        """Result with no types gives location_type=None."""
        with patch("utils.conversations.location.r") as mock_r:
            mock_r.get.return_value = None
            with patch("utils.conversations.location.requests") as mock_req:
                mock_resp = MagicMock()
                mock_resp.json.return_value = {
                    "status": "OK",
                    "results": [{"place_id": "ChIJ_notype", "formatted_address": "No Type St", "types": []}],
                }
                mock_req.get.return_value = mock_resp

                result = get_google_maps_location(37.785, -122.409)

        assert result is not None
        assert result.location_type is None

    def test_missing_types_key_gives_none_location_type(self):
        """Result with no 'types' key at all gives location_type=None."""
        with patch("utils.conversations.location.r") as mock_r:
            mock_r.get.return_value = None
            with patch("utils.conversations.location.requests") as mock_req:
                mock_resp = MagicMock()
                mock_resp.json.return_value = {
                    "status": "OK",
                    "results": [{"place_id": "ChIJ_nokey", "formatted_address": "No Key St"}],
                }
                mock_req.get.return_value = mock_resp

                result = get_google_maps_location(37.785, -122.409)

        assert result is not None
        assert result.location_type is None


class TestCorruptCache:
    """Corrupt cached data should fall back to API gracefully."""

    def test_invalid_json_falls_through_to_api(self):
        """Corrupt JSON in cache should log warning and call API."""
        api_response = {
            "status": "OK",
            "results": [
                {
                    "place_id": "ChIJ_recover",
                    "formatted_address": "Recovered St",
                    "types": ["route"],
                }
            ],
        }
        with patch("utils.conversations.location.r") as mock_r:
            mock_r.get.return_value = "not-valid-json{{"
            with patch("utils.conversations.location.requests") as mock_req:
                mock_resp = MagicMock()
                mock_resp.json.return_value = api_response
                mock_req.get.return_value = mock_resp

                with patch("utils.conversations.location.logging") as mock_log:
                    result = get_google_maps_location(37.785, -122.409)
                    mock_log.warning.assert_called()

        assert result is not None
        assert result.google_place_id == "ChIJ_recover"

    def test_schema_mismatch_falls_through_to_api(self):
        """Cached data with wrong schema should log warning and call API."""
        api_response = {
            "status": "OK",
            "results": [
                {
                    "place_id": "ChIJ_schema",
                    "formatted_address": "Schema St",
                    "types": ["route"],
                }
            ],
        }
        with patch("utils.conversations.location.r") as mock_r:
            # Missing required 'latitude' and 'longitude' fields
            mock_r.get.return_value = json.dumps({"bad_field": "bad_value"})
            with patch("utils.conversations.location.requests") as mock_req:
                mock_resp = MagicMock()
                mock_resp.json.return_value = api_response
                mock_req.get.return_value = mock_resp

                with patch("utils.conversations.location.logging") as mock_log:
                    result = get_google_maps_location(37.785, -122.409)
                    mock_log.warning.assert_called()

        assert result is not None
        assert result.google_place_id == "ChIJ_schema"
