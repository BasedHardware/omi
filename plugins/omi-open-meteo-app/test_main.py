from pathlib import Path
import sys
import types
import unittest
from unittest.mock import AsyncMock, patch

# Provide lightweight stubs for third-party runtime dependencies so test_main.py
# runs hermetically on any clean standard library Python environment without
# requiring FastAPI, httpx, or Pydantic to be installed.
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
    except ImportError:
        fastapi = types.ModuleType("fastapi")

        class FastAPI:
            def __init__(self, *args, **kwargs):
                pass

            def get(self, *args, **kwargs):
                return lambda f: f

            def post(self, *args, **kwargs):
                return lambda f: f

        fastapi.FastAPI = FastAPI
        sys.modules["fastapi"] = fastapi

        responses = types.ModuleType("fastapi.responses")

        class HTMLResponse:
            pass

        responses.HTMLResponse = HTMLResponse
        sys.modules["fastapi.responses"] = responses
        fastapi.responses = responses

if "pydantic" not in sys.modules:
    try:
        import pydantic  # type: ignore
    except ImportError:
        pydantic = types.ModuleType("pydantic")

        def Field(default=None, **kwargs):
            return default

        class BaseModel:
            def __init__(self, **kwargs):
                for cls in reversed(self.__class__.__mro__):
                    for k, v in getattr(cls, "__dict__", {}).items():
                        if not k.startswith("_") and not callable(v):
                            setattr(self, k, None if v is ... else v)
                for k, v in kwargs.items():
                    setattr(self, k, v)

        pydantic.BaseModel = BaseModel
        pydantic.Field = Field
        sys.modules["pydantic"] = pydantic

# Add plugin directory to path so main can be loaded hermetically
PLUGIN_DIR = Path(__file__).resolve().parent
if str(PLUGIN_DIR) not in sys.path:
    sys.path.insert(0, str(PLUGIN_DIR))

import main


class OpenMeteoHelperTests(unittest.TestCase):
    def test_format_number_formats_values_correctly(self):
        self.assertEqual(main._format_number(None), "n/a")
        self.assertEqual(main._format_number(True), "n/a")
        self.assertEqual(main._format_number(False), "n/a")
        self.assertEqual(main._format_number(25), "25")
        self.assertEqual(main._format_number(25.0), "25")
        self.assertEqual(main._format_number(25.46), "25.5")
        self.assertEqual(main._format_number(25, "°C"), "25°C")
        self.assertEqual(main._format_number(25.4, None), "25.4")

    def test_safe_item_handles_bounds_and_invalid_types(self):
        self.assertEqual(main._safe_item([10, 20, 30], 1), 20)
        self.assertEqual(main._safe_item([10, 20, 30], 5), None)
        self.assertEqual(main._safe_item([10, 20, 30], -1), None)
        self.assertEqual(main._safe_item([], 0, "fallback"), "fallback")
        self.assertEqual(main._safe_item(None, 0, "fallback"), "fallback")
        self.assertEqual(main._safe_item("not_a_list", 0, "fallback"), "fallback")

    def test_format_unit_suffix_safe(self):
        self.assertEqual(main._format_unit_suffix("km/h", " "), " km/h")
        self.assertEqual(main._format_unit_suffix(None, " "), "")
        self.assertEqual(main._format_unit_suffix("", " "), "")
        self.assertEqual(main._format_unit_suffix(123, " "), "")

    def test_observed_at_formatting(self):
        # Includes timezone and offset
        current = {"time": "2026-09-11T14:00"}
        payload = {"timezone": "Europe/Berlin", "utc_offset_seconds": 7200}
        out = main._format_observed_at(current, payload)
        self.assertIn("2026-09-11T14:00", out)
        self.assertIn("Europe/Berlin", out)
        self.assertIn("UTC+02:00", out)

        # Negative offset
        current_ny = {"time": "2026-09-11T09:00"}
        payload_ny = {"timezone": "America/New_York", "utc_offset_seconds": -14400}
        out_ny = main._format_observed_at(current_ny, payload_ny)
        self.assertIn("UTC-04:00", out_ny)

        # Fallback without metadata
        self.assertEqual(main._format_observed_at({"time": "2026-09-11T14:00"}, {}), "2026-09-11T14:00")


class OpenMeteoEndpointTests(unittest.IsolatedAsyncioTestCase):
    async def test_get_weather_forecast_with_partial_or_empty_daily_arrays(self):
        # Prior to fix, missing or shorter arrays raised unhandled IndexError on day 1+
        place = {"name": "London", "country": "United Kingdom", "latitude": 51.5, "longitude": -0.1}
        payload = {
            "daily": {
                "time": ["2026-09-15", "2026-09-16", "2026-09-17"],
                "weather_code": [0],  # only 1 item for 3 days
                "temperature_2m_max": [21.5],  # only 1 item
                "temperature_2m_min": [],  # empty list
                "precipitation_probability_max": None,  # null
                # wind_speed_10m_max missing entirely
            },
            "daily_units": {
                "temperature_2m_max": "°C",
                "temperature_2m_min": "°C",
                "wind_speed_10m_max": None,  # null unit must not trigger TypeError
            },
        }

        req = main.ForecastRequest(location="London", days=3)
        with patch.object(main, "_resolve_location", new=AsyncMock(return_value=(place, None))), \
             patch.object(main, "_request_json", new=AsyncMock(return_value=payload)):
            res = await main.get_weather_forecast(req)

        self.assertIsNone(res.error)
        self.assertIn("3-day forecast for London, United Kingdom", res.result)
        self.assertIn("- 2026-09-15: clear sky; high 21.5°C, low n/a; rain n/a; wind up to n/a", res.result)
        self.assertIn("- 2026-09-16: unknown; high n/a, low n/a; rain n/a; wind up to n/a", res.result)
        self.assertIn("- 2026-09-17: unknown; high n/a, low n/a; rain n/a; wind up to n/a", res.result)

    async def test_get_weather_forecast_empty_time(self):
        place = {"name": "Paris", "country": "France", "latitude": 48.8, "longitude": 2.3}
        payload = {"daily": {"time": []}}

        req = main.ForecastRequest(location="Paris", days=3)
        with patch.object(main, "_resolve_location", new=AsyncMock(return_value=(place, None))), \
             patch.object(main, "_request_json", new=AsyncMock(return_value=payload)):
            res = await main.get_weather_forecast(req)

        self.assertIsNone(res.error)
        self.assertEqual(res.result, "No forecast data available for Paris, France.")

    async def test_get_current_weather_with_null_units(self):
        # Open-Meteo or proxy returning null unit values must not crash on str concatenation
        place = {"name": "Tokyo", "country": "Japan", "latitude": 35.6, "longitude": 139.6}
        payload = {
            "current": {
                "time": "2026-09-15T12:00",
                "weather_code": 1,
                "temperature_2m": 26.2,
                "apparent_temperature": 27.0,
                "relative_humidity_2m": 65,
                "precipitation": 0.0,
                "wind_speed_10m": 12.5,
            },
            "current_units": {
                "temperature_2m": "°C",
                "wind_speed_10m": None,  # null unit
                "relative_humidity_2m": "%",
            },
        }

        req = main.CurrentWeatherRequest(location="Tokyo")
        with patch.object(main, "_resolve_location", new=AsyncMock(return_value=(place, None))), \
             patch.object(main, "_request_json", new=AsyncMock(return_value=payload)):
            res = await main.get_current_weather(req)

        self.assertIsNone(res.error)
        self.assertIn("Current weather for Tokyo, Japan", res.result)
        self.assertIn("Temperature: 26.2°C", res.result)
        self.assertIn("Wind: 12.5", res.result)

    async def test_get_air_quality_with_null_units(self):
        place = {"name": "Delhi", "country": "India", "latitude": 28.6, "longitude": 77.2}
        payload = {
            "current": {
                "time": "2026-09-15T12:00",
                "us_aqi": 180,
                "pm2_5": 95.5,
                "pm10": 160.0,
                "ozone": 45.0,
                "nitrogen_dioxide": 32.0,
            },
            "current_units": {
                "pm2_5": None,
                "pm10": None,
                "ozone": "μg/m³",
                "nitrogen_dioxide": None,
            },
        }

        req = main.AirQualityRequest(location="Delhi")
        with patch.object(main, "_resolve_location", new=AsyncMock(return_value=(place, None))), \
             patch.object(main, "_request_json", new=AsyncMock(return_value=payload)):
            res = await main.get_air_quality(req)

        self.assertIsNone(res.error)
        self.assertIn("Air quality for Delhi, India", res.result)
        self.assertIn("PM2.5: 95.5", res.result)
        self.assertIn("Ozone: 45 μg/m³", res.result)


if __name__ == "__main__":
    unittest.main()
