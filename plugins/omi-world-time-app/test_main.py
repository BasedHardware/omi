"""Hermetic unit tests for Omi World Time & Solar Ephemeris Integration App."""

import asyncio
from datetime import date, datetime, time
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from main import (
    CITY_TIMEZONE_ALIASES,
    SimpleTTLCache,
    _find_iana_timezone,
    _format_time_difference,
    _format_utc_offset,
    _parse_source_time,
    app,
    calculate_time_difference,
    geocoding_cache,
    get_current_time,
    get_solar_times,
    health,
    omi_tools,
    resolve_location,
    solar_cache,
)
from models import (
    CalculateTimeDifferenceRequest,
    ChatToolResponse,
    GetCurrentTimeRequest,
    GetSolarTimesRequest,
)


class TestModels(unittest.TestCase):
    """Test Pydantic v2 schemas and validation contracts."""

    def test_chat_tool_response_valid_result(self):
        resp = ChatToolResponse(result="Current time is 12:00 PM")
        self.assertEqual(resp.result, "Current time is 12:00 PM")
        self.assertIsNone(resp.error)

    def test_chat_tool_response_valid_error(self):
        resp = ChatToolResponse(error="Location not found")
        self.assertEqual(resp.error, "Location not found")
        self.assertIsNone(resp.result)

    def test_chat_tool_response_invalid_both(self):
        with self.assertRaises(ValueError):
            ChatToolResponse(result="Time", error="Err")

    def test_chat_tool_response_invalid_neither(self):
        with self.assertRaises(ValueError):
            ChatToolResponse()

    def test_get_current_time_request_sanitization(self):
        req = GetCurrentTimeRequest(location="  Tokyo   ")
        self.assertEqual(req.location, "Tokyo")

    def test_get_current_time_request_empty(self):
        with self.assertRaises(ValueError):
            GetCurrentTimeRequest(location="   ")

    def test_calculate_time_difference_request(self):
        req = CalculateTimeDifferenceRequest(
            source_location="  New York  ",
            target_location="  Tokyo  ",
            source_time="14:30",
        )
        self.assertEqual(req.source_location, "New York")
        self.assertEqual(req.target_location, "Tokyo")
        self.assertEqual(req.source_time, "14:30")

    def test_get_solar_times_request(self):
        req = GetSolarTimesRequest(location="Paris", date="2026-09-08")
        self.assertEqual(req.location, "Paris")
        self.assertEqual(req.date, "2026-09-08")


class TestHelpers(unittest.TestCase):
    """Test helper functions, caching, and time formatting."""

    def test_ttl_cache_expiration(self):
        cache = SimpleTTLCache(maxsize=2, ttl_seconds=1)
        cache.set("a", 100)
        self.assertEqual(cache.get("a"), 100)
        cache._cache["a"] = (cache._cache["a"][0] - 2, 100)  # Simulate expiration
        self.assertIsNone(cache.get("a"))

    def test_ttl_cache_lru_eviction(self):
        cache = SimpleTTLCache(maxsize=2, ttl_seconds=100)
        cache.set("a", 1)
        cache.set("b", 2)
        cache.set("c", 3)
        self.assertIsNone(cache.get("a"))  # Oldest evicted
        self.assertEqual(cache.get("b"), 2)
        self.assertEqual(cache.get("c"), 3)

    def test_find_iana_timezone(self):
        self.assertEqual(_find_iana_timezone("Asia/Tokyo"), "Asia/Tokyo")
        self.assertEqual(_find_iana_timezone("asia/tokyo"), "Asia/Tokyo")
        self.assertEqual(_find_iana_timezone("UTC"), "UTC")
        self.assertIsNone(_find_iana_timezone("NonExistentZone/Fake"))

    def test_format_time_difference(self):
        self.assertEqual(_format_time_difference(0), "the same time")
        self.assertEqual(_format_time_difference(3600), "1 hour")
        self.assertEqual(_format_time_difference(7200), "2 hours")
        self.assertEqual(_format_time_difference(5400), "1 hour and 30 minutes")
        self.assertEqual(_format_time_difference(90000), "25 hours")

    def test_parse_source_time_formats(self):
        base_d = date(2026, 9, 8)

        # 24h format
        t, d = _parse_source_time("14:30", base_d)
        self.assertEqual(t, time(14, 30))
        self.assertEqual(d, base_d)

        # 12h PM
        t, d = _parse_source_time("02:30 PM", base_d)
        self.assertEqual(t, time(14, 30))

        # 12h AM
        t, d = _parse_source_time("09:15 am", base_d)
        self.assertEqual(t, time(9, 15))

        # ISO format
        t, d = _parse_source_time("2026-12-25 18:45:30", base_d)
        self.assertEqual(t, time(18, 45, 30))
        self.assertEqual(d, date(2026, 12, 25))

        # Invalid format
        with self.assertRaises(ValueError):
            _parse_source_time("invalid-time", base_d)


class TestEndpointsHermetic(unittest.IsolatedAsyncioTestCase):
    """Hermetic tests for FastAPI route handlers and business logic."""

    async def asyncSetUp(self):
        geocoding_cache.clear()
        solar_cache.clear()
        self.mock_client = AsyncMock()
        app.state.http_client = self.mock_client

    async def test_health_endpoint(self):
        res = await health()
        self.assertEqual(res.get("status"), "ok")
        self.assertEqual(res.get("service"), "omi-world-time-app")

    async def test_omi_tools_manifest(self):
        res = await omi_tools()
        self.assertEqual(res.get("schema_version"), "1.0")
        self.assertEqual(res.get("auth", {}).get("type"), "none")
        tools = res.get("tools", [])
        self.assertEqual(len(tools), 3)

        tool_names = [t["name"] for t in tools]
        self.assertIn("get_current_time", tool_names)
        self.assertIn("calculate_time_difference", tool_names)
        self.assertIn("get_solar_times", tool_names)

        # Validate parameters schema
        for tool in tools:
            self.assertIn("description", tool)
            self.assertIn("parameters", tool)
            self.assertEqual(tool["parameters"]["type"], "object")
            self.assertTrue(len(tool["parameters"]["required"]) > 0)

    async def test_get_current_time_tokyo(self):
        req = GetCurrentTimeRequest(location="Tokyo")
        resp = await get_current_time(req)
        self.assertIsNone(resp.error)
        self.assertIsNotNone(resp.result)
        self.assertIn("Tokyo", resp.result)
        self.assertIn("Asia/Tokyo", resp.result)
        self.assertIn("UTC+09:00", resp.result)

    async def test_get_current_time_utc(self):
        req = GetCurrentTimeRequest(location="UTC")
        resp = await get_current_time(req)
        self.assertIsNone(resp.error)
        self.assertIsNotNone(resp.result)
        self.assertIn("UTC", resp.result)

    async def test_get_current_time_invalid_location(self):
        req = GetCurrentTimeRequest(location="AtlantisUnderwaterKingdom12345")
        # Configure mock geocoding returning empty results
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"results": []}
        self.mock_client.get.return_value = mock_resp

        resp = await get_current_time(req)
        self.assertIsNotNone(resp.error)
        self.assertIsNone(resp.result)
        self.assertIn("Failed to get time", resp.error)

    async def test_calculate_time_difference_new_york_to_tokyo(self):
        req = CalculateTimeDifferenceRequest(
            source_location="New York",
            target_location="Tokyo",
            source_time="12:00 PM",
        )
        resp = await calculate_time_difference(req)
        self.assertIsNone(resp.error)
        self.assertIsNotNone(resp.result)
        self.assertIn("Tokyo", resp.result)
        self.assertIn("ahead of", resp.result)
        self.assertIn("New York", resp.result)

    async def test_calculate_time_difference_same_zone(self):
        req = CalculateTimeDifferenceRequest(
            source_location="Paris",
            target_location="Berlin",
            source_time="10:00",
        )
        resp = await calculate_time_difference(req)
        self.assertIsNone(resp.error)
        self.assertIsNotNone(resp.result)
        self.assertIn("same time zone", resp.result)

    async def test_get_solar_times_mocked(self):
        # Mock geocoding for Paris
        mock_geo_resp = MagicMock()
        mock_geo_resp.status_code = 200
        mock_geo_resp.json.return_value = {
            "results": [
                {
                    "name": "Paris",
                    "latitude": 48.8566,
                    "longitude": 2.3522,
                    "country": "France",
                    "timezone": "Europe/Paris",
                }
            ]
        }

        # Mock Sunrise-Sunset API response
        mock_solar_resp = MagicMock()
        mock_solar_resp.status_code = 200
        mock_solar_resp.json.return_value = {
            "status": "OK",
            "results": {
                "sunrise": "2026-09-08T05:15:00+00:00",
                "sunset": "2026-09-08T18:20:00+00:00",
                "solar_noon": "2026-09-08T11:47:30+00:00",
                "day_length": 47100,
                "civil_twilight_begin": "2026-09-08T04:45:00+00:00",
                "civil_twilight_end": "2026-09-08T18:50:00+00:00",
            },
        }

        async def side_effect(url, params=None):
            if "open-meteo" in url:
                return mock_geo_resp
            return mock_solar_resp

        self.mock_client.get.side_effect = side_effect

        req = GetSolarTimesRequest(location="Paris", date="2026-09-08")
        resp = await get_solar_times(req)
        self.assertIsNone(resp.error)
        self.assertIsNotNone(resp.result)
        self.assertIn("Solar Ephemeris for Paris", resp.result)
        self.assertIn("Sunrise:", resp.result)
        self.assertIn("Sunset:", resp.result)
        self.assertIn("Day Length:", resp.result)
        self.assertIn("13h 05m", resp.result)


class TestFastAPIHttp(unittest.TestCase):
    """Test HTTP endpoints using TestClient to verify routing and exception handlers."""

    def setUp(self):
        self.client = TestClient(app)

    def test_root_html(self):
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("text/html", resp.headers["content-type"])
        self.assertIn("Omi World Time", resp.text)

    def test_health_http(self):
        resp = self.client.get("/health")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "ok")

    def test_manifest_http(self):
        resp = self.client.get("/.well-known/omi-tools.json")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["schema_version"], "1.0")

    def test_validation_exception_handler_returns_200_with_error(self):
        # Missing required field 'location'
        resp = self.client.post("/tools/get_current_time", json={})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("error", data)
        self.assertIsNone(data.get("result"))
        self.assertIn("Invalid tool request", data["error"])


if __name__ == "__main__":
    unittest.main()
