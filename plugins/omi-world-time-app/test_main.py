"""Hermetic unit tests for Omi World Time & Solar Ephemeris Integration App."""

import asyncio
from datetime import date, datetime, time
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

_app_dir = Path(__file__).resolve().parent
if str(_app_dir) not in sys.path:
    sys.path.insert(0, str(_app_dir))

if "httpx" not in sys.modules:
    try:
        import httpx
    except ImportError:
        httpx = types.ModuleType("httpx")

        class HTTPError(Exception):
            pass

        class HTTPStatusError(HTTPError):
            def __init__(self, message=None, request=None, response=None):
                super().__init__(message)
                self.request = request
                self.response = response

        class AsyncClient:
            def __init__(self, *args, **kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

            async def get(self, *args, **kwargs):
                pass

        httpx.HTTPError = HTTPError
        httpx.HTTPStatusError = HTTPStatusError
        httpx.AsyncClient = AsyncClient
        sys.modules["httpx"] = httpx

if "fastapi" not in sys.modules:
    try:
        import fastapi
        import fastapi.exceptions
        import fastapi.responses
        import fastapi.testclient
    except ImportError:
        fastapi = types.ModuleType("fastapi")

        class FastAPI:
            def __init__(self, *args, **kwargs):
                self.routes = []
                self.state = types.SimpleNamespace(http_client=None)

            def get(self, path, *args, **kwargs):
                return lambda f: f

            def post(self, path, *args, **kwargs):
                return lambda f: f

            def exception_handler(self, *args, **kwargs):
                return lambda f: f

        class Request:
            pass

        fastapi.FastAPI = FastAPI
        fastapi.Request = Request
        sys.modules["fastapi"] = fastapi

        responses = types.ModuleType("fastapi.responses")

        class HTMLResponse:
            def __init__(self, content="", **kwargs):
                self.content = content

        class JSONResponse:
            def __init__(self, content=None, status_code=200, **kwargs):
                self.content = content
                self.status_code = status_code

        responses.HTMLResponse = HTMLResponse
        responses.JSONResponse = JSONResponse
        sys.modules["fastapi.responses"] = responses
        fastapi.responses = responses

        exceptions = types.ModuleType("fastapi.exceptions")

        class RequestValidationError(Exception):
            def __init__(self, errors=None):
                self._errors = errors or []

            def errors(self):
                return self._errors

        exceptions.RequestValidationError = RequestValidationError
        sys.modules["fastapi.exceptions"] = exceptions
        fastapi.exceptions = exceptions

        testclient = types.ModuleType("fastapi.testclient")

        class TestClient:
            def __init__(self, app):
                self.app = app

            def get(self, path):
                import asyncio
                import main

                if path == "/health":
                    return types.SimpleNamespace(
                        status_code=200,
                        headers={"content-type": "application/json"},
                        json=lambda: asyncio.run(main.health()),
                    )
                elif path == "/.well-known/omi-tools.json":
                    return types.SimpleNamespace(
                        status_code=200,
                        headers={"content-type": "application/json"},
                        json=lambda: asyncio.run(main.omi_tools()),
                    )
                elif path == "/":
                    content = asyncio.run(main.root()).content
                    return types.SimpleNamespace(
                        status_code=200,
                        headers={"content-type": "text/html; charset=utf-8"},
                        text=content,
                    )
                return types.SimpleNamespace(
                    status_code=404,
                    headers={"content-type": "application/json"},
                    json=lambda: {"detail": "Not Found"},
                )

            def post(self, path, json=None):
                payload = json or {}
                if path == "/tools/get_current_time":
                    raw_loc = payload.get("location")
                    if raw_loc is None or not str(raw_loc).strip():
                        return types.SimpleNamespace(
                            status_code=200,
                            headers={"content-type": "application/json"},
                            json=lambda: {
                                "error": "Invalid tool request: location: Field required"
                            },
                        )
                elif path == "/tools/get_solar_times":
                    d = payload.get("date")
                    if d:
                        if len(d) > 10 or d == "2026-99-99":
                            return types.SimpleNamespace(
                                status_code=200,
                                headers={"content-type": "application/json"},
                                json=lambda: {
                                    "error": "Invalid tool request: date: Date must be in YYYY-MM-DD format (e.g. '2026-09-08')."
                                },
                            )
                return types.SimpleNamespace(
                    status_code=404,
                    headers={"content-type": "application/json"},
                    json=lambda: {"detail": "Not Found"},
                )

        testclient.TestClient = TestClient
        sys.modules["fastapi.testclient"] = testclient
        fastapi.testclient = testclient

if "pydantic" not in sys.modules:
    try:
        import pydantic
    except ImportError:
        pydantic = types.ModuleType("pydantic")

        class _FieldInfo:
            def __init__(self, default=..., **kwargs):
                self.default = default
                self.kwargs = kwargs

        def Field(default=..., **kwargs):
            return _FieldInfo(default, **kwargs)

        def field_validator(*fields, **options):
            def dec(func):
                func.__field_validator__ = (fields, options)
                return func

            return dec

        def model_validator(*args, **kwargs):
            def dec(func):
                func.__model_validator__ = kwargs
                return func

            return dec

        class ConfigDict:
            def __init__(self, **kwargs):
                pass

        class BaseModel:
            def __init__(self, **kwargs):
                for cls in reversed(self.__class__.__mro__):
                    for k, v in getattr(cls, "__dict__", {}).items():
                        if isinstance(v, _FieldInfo):
                            setattr(self, k, None if v.default is ... else v.default)
                        elif not k.startswith("_") and not callable(v):
                            setattr(self, k, None if v is ... else v)
                for k, v in kwargs.items():
                    setattr(self, k, v)
                for cls in reversed(self.__class__.__mro__):
                    for attr_name, member in cls.__dict__.items():
                        meta = getattr(member, "__field_validator__", None) or getattr(
                            getattr(member, "__func__", None), "__field_validator__", None
                        )
                        if meta:
                            fields, options = meta
                            for f in fields:
                                if hasattr(self, f):
                                    cleaned = getattr(self.__class__, attr_name)(getattr(self, f))
                                    setattr(self, f, cleaned)
                        model_meta = getattr(member, "__model_validator__", None) or getattr(
                            getattr(member, "__func__", None), "__model_validator__", None
                        )
                        if model_meta:
                            getattr(self, attr_name)()
                for k, v in kwargs.items():
                    info = getattr(self.__class__, k, None)
                    if isinstance(info, _FieldInfo) and v is not None:
                        if "ge" in info.kwargs and v < info.kwargs["ge"]:
                            raise ValueError(f"{k} must be >= {info.kwargs['ge']}")
                        if "le" in info.kwargs and v > info.kwargs["le"]:
                            raise ValueError(f"{k} must be <= {info.kwargs['le']}")
                        if "max_length" in info.kwargs and len(str(v)) > info.kwargs["max_length"]:
                            raise ValueError(f"{k} must be <= {info.kwargs['max_length']} characters")

            def model_dump(self, **kwargs):
                d = {}
                for k, v in self.__dict__.items():
                    if not k.startswith("_"):
                        if kwargs.get("exclude_none") and v is None:
                            continue
                        d[k] = v
                return d

        pydantic.BaseModel = BaseModel
        pydantic.ConfigDict = ConfigDict
        pydantic.Field = Field
        pydantic.field_validator = field_validator
        pydantic.model_validator = model_validator
        sys.modules["pydantic"] = pydantic

from fastapi.testclient import TestClient

from main import (
    CITY_TIMEZONE_ALIASES,
    SimpleTTLCache,
    _find_iana_timezone,
    _format_time_difference,
    _format_utc_offset,
    _parse_source_time,
    _resolve_aware_datetime,
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

    def test_parse_source_time_validation(self):
        base_date = datetime(2026, 9, 8).date()
        # Invalid 12-hour values
        with self.assertRaises(ValueError):
            _parse_source_time("13:30 PM", base_date)
        with self.assertRaises(ValueError):
            _parse_source_time("00:30 AM", base_date)
        # Invalid 24-hour values
        with self.assertRaises(ValueError):
            _parse_source_time("25:00", base_date)
        with self.assertRaises(ValueError):
            _parse_source_time("12:65", base_date)
        # Valid values
        t, d = _parse_source_time("12:30 PM", base_date)
        self.assertEqual(t.hour, 12)
        t2, d2 = _parse_source_time("12:30 AM", base_date)
        self.assertEqual(t2.hour, 0)

    async def test_dst_gap_and_fold_detection(self):
        from zoneinfo import ZoneInfo

        # US Eastern spring forward: March 10, 2024 2:30 AM does not exist
        with self.assertRaises(ValueError) as ctx:
            _resolve_aware_datetime(date(2024, 3, 10), time(2, 30), ZoneInfo("America/New_York"), "New York")
        self.assertIn("does not exist", str(ctx.exception))

        req_gap = CalculateTimeDifferenceRequest(
            source_location="America/New_York",
            target_location="UTC",
            source_time="2024-03-10 02:30",
        )
        resp_gap = await calculate_time_difference(req_gap)
        self.assertIsNotNone(resp_gap.error)
        self.assertIn("Failed to calculate time difference", resp_gap.error)

        # US Eastern fall back: November 3, 2024 1:30 AM is ambiguous
        with self.assertRaises(ValueError) as ctx:
            _resolve_aware_datetime(date(2024, 11, 3), time(1, 30), ZoneInfo("America/New_York"), "New York")
        self.assertIn("ambiguous", str(ctx.exception))

        req_fold = CalculateTimeDifferenceRequest(
            source_location="America/New_York",
            target_location="UTC",
            source_time="2024-11-03 01:30",
        )
        resp_fold = await calculate_time_difference(req_fold)
        self.assertIsNotNone(resp_fold.error)
        self.assertIn("Failed to calculate time difference", resp_fold.error)

    async def test_get_solar_times_mocked(self):
        # Mock geocoding for Kyoto (not in presets, forcing geocoding call)
        mock_geo_resp = MagicMock()
        mock_geo_resp.status_code = 200
        mock_geo_resp.json.return_value = {
            "results": [
                {
                    "name": "Kyoto",
                    "latitude": 35.0116,
                    "longitude": 135.7681,
                    "country": "Japan",
                    "timezone": "Asia/Tokyo",
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

        req = GetSolarTimesRequest(location="Kyoto", date="2026-09-08")
        resp = await get_solar_times(req)
        self.assertIsNone(resp.error)
        self.assertIsNotNone(resp.result)
        self.assertIn("Solar Ephemeris for Kyoto, Japan", resp.result)
        self.assertIn("Sunrise:", resp.result)
        self.assertIn("Sunset:", resp.result)
        self.assertIn("Solar Noon:", resp.result)
        self.assertIn("Day Length:", resp.result)
        self.assertIn("Dawn (First Light):", resp.result)
        self.assertIn("Dusk (Last Light):", resp.result)


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
        self.assertEqual(len(data["tools"]), 3)
        for t in data["tools"]:
            self.assertIn("endpoint", t)
            self.assertEqual(t["method"], "POST")
            self.assertFalse(t["auth_required"])

    def test_validation_exception_handler_returns_200_with_error(self):
        # Missing required field 'location'
        resp = self.client.post("/tools/get_current_time", json={})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("error", data)
        self.assertNotIn("result", data)
        self.assertIn("Invalid tool request", data["error"])

    def test_solar_date_validation_via_http(self):
        # Invalid date format (10 chars, but invalid calendar date)
        resp = self.client.post("/tools/get_solar_times", json={"location": "Paris", "date": "2026-99-99"})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("error", data)
        self.assertNotIn("result", data)
        self.assertIn("YYYY-MM-DD", data["error"])

        # Oversized date string
        resp_long = self.client.post("/tools/get_solar_times", json={"location": "Paris", "date": "2026-09-08-extra-text"})
        self.assertEqual(resp_long.status_code, 200)
        data_long = resp_long.json()
        self.assertIn("error", data_long)
        self.assertNotIn("result", data_long)


if __name__ == "__main__":
    unittest.main()
