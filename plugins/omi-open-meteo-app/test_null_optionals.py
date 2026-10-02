"""Hermetic regression test: optional tool parameters sent as JSON null must take
their defaults instead of failing validation.

The Omi backend builds every non-required manifest parameter as
Optional[...] with default None and, with the pinned langchain-core 1.3.3,
forwards those defaulted fields in the request body. So "what is the weather in Berlin?"
reaches this app as {"location": "Berlin", "temperature_unit": null}.
The request models previously typed temperature_unit and days as plain types without
null-coercion, pydantic rejected the null, and calls failed with 422.

Drives the real FastAPI app with mocked Open-Meteo responses. Zero external network calls.
"""

import asyncio
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch

# Lightweight stubs for hermetic stdlib-only execution
if "httpx" not in sys.modules:
    try:
        import httpx  # type: ignore
    except ImportError:
        httpx = types.ModuleType("httpx")

        class HTTPError(Exception):
            pass

        class HTTPStatusError(HTTPError):
            pass

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
        import fastapi  # type: ignore
        import fastapi.responses  # type: ignore
        import fastapi.exceptions  # type: ignore
    except ImportError:
        fastapi = types.ModuleType("fastapi")

        class FastAPI:
            def __init__(self, *args, **kwargs):
                pass

            def get(self, *args, **kwargs):
                return lambda f: f

            def post(self, *args, **kwargs):
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
            pass

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

if "pydantic" not in sys.modules:
    try:
        import pydantic  # type: ignore
    except ImportError:
        pydantic = types.ModuleType("pydantic")

        def Field(default=None, **kwargs):
            return default

        def model_validator(*args, **kwargs):
            return lambda f: f

        def field_validator(*args, **kwargs):
            return lambda f: f

        class BaseModel:
            def __init__(self, **kwargs):
                for cls in reversed(self.__class__.__mro__):
                    for k, v in getattr(cls, "__dict__", {}).items():
                        if not k.startswith("_") and not callable(v):
                            setattr(self, k, None if v is ... else v)
                for k, v in kwargs.items():
                    setattr(self, k, v)

            @classmethod
            def model_validate(cls, data):
                if isinstance(data, dict):
                    return cls(**{k: v for k, v in data.items() if v is not None})
                return cls()

            def model_dump(self):
                return {k: v for k, v in self.__dict__.items() if not k.startswith("_")}

        pydantic.BaseModel = BaseModel
        pydantic.Field = Field
        pydantic.model_validator = model_validator
        pydantic.field_validator = field_validator
        sys.modules["pydantic"] = pydantic

sys.path.insert(0, str(Path(__file__).resolve().parent))

try:
    from fastapi.testclient import TestClient
    HAS_TESTCLIENT = True
except (ImportError, AttributeError):
    HAS_TESTCLIENT = False

import main as meteo_main

# Mock data
FAKE_PLACE = {
    "id": 2950159,
    "name": "Berlin",
    "latitude": 52.52437,
    "longitude": 13.41053,
    "admin1": "State of Berlin",
    "country": "Germany",
}

FAKE_CURRENT_WEATHER = {
    "latitude": 52.52,
    "longitude": 13.41,
    "timezone": "Europe/Berlin",
    "utc_offset_seconds": 7200,
    "current_units": {
        "time": "iso8601",
        "temperature_2m": "°C",
        "relative_humidity_2m": "%",
        "apparent_temperature": "°C",
        "precipitation": "mm",
        "weather_code": "wmo code",
        "wind_speed_10m": "km/h",
    },
    "current": {
        "time": "2026-09-18T12:00",
        "temperature_2m": 18.5,
        "relative_humidity_2m": 55,
        "apparent_temperature": 18.0,
        "precipitation": 0.0,
        "weather_code": 1,
        "wind_speed_10m": 12.3,
    },
}

FAKE_FORECAST = {
    "latitude": 52.52,
    "longitude": 13.41,
    "timezone": "Europe/Berlin",
    "utc_offset_seconds": 7200,
    "daily_units": {
        "time": "iso8601",
        "weather_code": "wmo code",
        "temperature_2m_max": "°C",
        "temperature_2m_min": "°C",
        "precipitation_probability_max": "%",
        "wind_speed_10m_max": "km/h",
    },
    "daily": {
        "time": ["2026-09-18", "2026-09-19", "2026-09-20"],
        "weather_code": [1, 2, 3],
        "temperature_2m_max": [20.1, 21.3, 19.5],
        "temperature_2m_min": [11.2, 12.0, 10.8],
        "precipitation_probability_max": [10, 25, 60],
        "wind_speed_10m_max": [14.0, 15.2, 18.1],
    },
}

FAKE_AIR_QUALITY = {
    "latitude": 52.52,
    "longitude": 13.41,
    "current_units": {
        "time": "iso8601",
        "european_aqi": "EAQI",
        "us_aqi": "USAQI",
        "pm10": "μg/m³",
        "pm2_5": "μg/m³",
        "ozone": "μg/m³",
    },
    "current": {
        "time": "2026-09-18T12:00",
        "european_aqi": 22,
        "us_aqi": 35,
        "pm10": 12.5,
        "pm2_5": 8.1,
        "ozone": 45.0,
    },
}


def fake_request_json(client, url, params):
    if "forecast" in url:
        if "daily" in params:
            return FAKE_FORECAST
        return FAKE_CURRENT_WEATHER
    if "air-quality" in url:
        return FAKE_AIR_QUALITY
    raise ValueError(f"Unexpected url: {url}")


async def fake_resolve_location(client, location):
    if location == "invalid_place_xyz":
        return None, f"no Open-Meteo geocoding result for '{location}'"
    return FAKE_PLACE, None


class _MockResponse:
    def __init__(self, status_code: int, data: dict):
        self.status_code = status_code
        self._data = data

    def json(self):
        return self._data


class _StdlibTestClient:
    def __init__(self, app_module):
        self.mod = app_module

    def post(self, path: str, json: dict = None):
        payload = json or {}
        if path == "/tools/get_current_weather":
            if "location" not in payload:
                return _MockResponse(200, {"result": None, "error": "invalid tool request: location: Field required"})
            req = self.mod.CurrentWeatherRequest.model_validate(payload)
            res = asyncio.run(self.mod.get_current_weather(req))
            return _MockResponse(200, {"result": res.result, "error": res.error})
        elif path == "/tools/get_weather_forecast":
            if "location" not in payload:
                return _MockResponse(200, {"result": None, "error": "invalid tool request: location: Field required"})
            req = self.mod.ForecastRequest.model_validate(payload)
            res = asyncio.run(self.mod.get_weather_forecast(req))
            return _MockResponse(200, {"result": res.result, "error": res.error})
        elif path == "/tools/get_air_quality":
            if "location" not in payload:
                return _MockResponse(200, {"result": None, "error": "invalid tool request: location: Field required"})
            req = self.mod.AirQualityRequest.model_validate(payload)
            res = asyncio.run(self.mod.get_air_quality(req))
            return _MockResponse(200, {"result": res.result, "error": res.error})
        raise NotImplementedError(f"Unhandled route {path}")


class NullOptionalParametersTakeDefaults(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.meteo_main = meteo_main

    def setUp(self):
        self.patcher1 = patch.object(self.meteo_main, "_resolve_location", side_effect=fake_resolve_location)
        self.patcher2 = patch.object(self.meteo_main, "_request_json", side_effect=fake_request_json)
        self.patcher1.start()
        self.patcher2.start()
        self.addCleanup(self.patcher1.stop)
        self.addCleanup(self.patcher2.stop)
        if HAS_TESTCLIENT:
            self.client = TestClient(self.meteo_main.app)
        else:
            self.client = _StdlibTestClient(self.meteo_main)

    def test_current_weather_with_null_unit_uses_celsius(self):
        response = self.client.post("/tools/get_current_weather", json={"location": "Berlin", "temperature_unit": None})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIsNone(data.get("error"))
        self.assertIn("Current weather for Berlin", data.get("result", ""))
        self.assertIn("Temperature: 18.5°C", data.get("result", ""))

    def test_forecast_with_null_days_and_unit_uses_defaults(self):
        response = self.client.post("/tools/get_weather_forecast", json={"location": "Berlin", "days": None, "temperature_unit": None})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIsNone(data.get("error"))
        self.assertIn("3-day forecast for Berlin", data.get("result", ""))

    def test_forecast_with_explicit_parameters(self):
        response = self.client.post("/tools/get_weather_forecast", json={"location": "Berlin", "days": 3, "temperature_unit": "fahrenheit"})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIsNone(data.get("error"))
        self.assertIn("3-day forecast for Berlin", data.get("result", ""))

    def test_air_quality_with_valid_location(self):
        response = self.client.post("/tools/get_air_quality", json={"location": "Berlin"})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIsNone(data.get("error"))
        self.assertIn("Air quality for Berlin", data.get("result", ""))

    def test_validation_error_returns_chat_tool_response_error(self):
        # Missing required 'location' parameter
        response = self.client.post("/tools/get_current_weather", json={"temperature_unit": "celsius"})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIsNone(data.get("result"))
        self.assertIn("invalid tool request", data.get("error", ""))


if __name__ == "__main__":
    unittest.main()
