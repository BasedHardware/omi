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

# Add plugin directory to path so main can be loaded hermetically
PLUGIN_DIR = Path(__file__).resolve().parent
if str(PLUGIN_DIR) not in sys.path:
    sys.path.insert(0, str(PLUGIN_DIR))

import main


class _FakeResponse:
    """Minimal httpx.Response stand-in that can also fail JSON decoding."""

    def __init__(self, payload):
        self.payload = payload
        self.status_code = 200

    def raise_for_status(self):
        return None

    def json(self):
        if isinstance(self.payload, Exception):
            raise self.payload
        return self.payload


def _fake_client_factory(responses):
    """Build a fake AsyncClient class plus a list capturing each call.

    ``responses`` maps a URL substring to the response object to serve, so a
    test exercises main.py's real request/parse path (not a stubbed helper).
    """
    calls = []

    class _FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            self.timeout = kwargs.get("timeout")

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def get(self, url, params=None):
            calls.append((url, params, self.timeout))
            for marker, response in responses.items():
                if marker in url:
                    return response
            raise AssertionError(f"unexpected request to {url}")

    return _FakeAsyncClient, calls


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

    def test_as_dict_and_as_list_guards(self):
        self.assertEqual(main._as_dict({"a": 1}), {"a": 1})
        self.assertEqual(main._as_dict(["not", "a", "dict"]), {})
        self.assertEqual(main._as_dict("bare string"), {})
        self.assertEqual(main._as_dict(None), {})
        self.assertEqual(main._as_list([1, 2]), [1, 2])
        self.assertEqual(main._as_list({"a": 1}), [])
        self.assertEqual(main._as_list(None), [])
        self.assertEqual(main._as_list("abc"), [])

    def test_as_number_rejects_bools_and_non_numbers(self):
        self.assertEqual(main._as_number(21.5), 21.5)
        self.assertEqual(main._as_number(7), 7)
        self.assertIsNone(main._as_number(True))
        self.assertIsNone(main._as_number(False))
        self.assertIsNone(main._as_number("21.5"))
        self.assertIsNone(main._as_number(None))
        self.assertIsNone(main._as_number({"value": 1}))

    def test_numeric_item_validates_positional_fields(self):
        self.assertEqual(main._numeric_item([1, 2.5, 3], 1), 2.5)
        self.assertIsNone(main._numeric_item([1, "two", 3], 1))
        self.assertIsNone(main._numeric_item([1, True, 3], 1))
        self.assertIsNone(main._numeric_item([1, None, 3], 1))
        self.assertIsNone(main._numeric_item([1], 5))
        self.assertIsNone(main._numeric_item("not_a_list", 0))

    def test_format_weather_code_rejects_non_numeric(self):
        self.assertEqual(main._format_weather_code(0), "clear sky")
        self.assertEqual(main._format_weather_code(61), "slight rain")
        self.assertEqual(main._format_weather_code(None), "unknown")
        self.assertEqual(main._format_weather_code(True), "unknown")
        self.assertEqual(main._format_weather_code("61"), "unknown")

    def test_format_observed_at_tolerates_non_dict_inputs(self):
        self.assertEqual(main._format_observed_at(None, None), "unknown time")
        self.assertEqual(main._format_observed_at(["not", "a", "dict"], "junk"), "unknown time")
        # Non-string tz must not leak a bogus suffix into the rendered line.
        self.assertEqual(
            main._format_observed_at({"time": "2026-09-11T14:00"}, {"timezone": 42}),
            "2026-09-11T14:00",
        )

    def test_format_place_tolerates_non_dict_inputs(self):
        self.assertEqual(main._format_place(None), "")
        self.assertEqual(main._format_place("junk"), "")

    def test_require_dict_raises_clean_error(self):
        self.assertEqual(main._require_dict({"a": 1}), {"a": 1})
        with self.assertRaises(main.MalformedResponseError):
            main._require_dict(["not", "a", "dict"])
        with self.assertRaises(main.MalformedResponseError):
            main._require_dict(None)

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

    async def test_current_weather_with_null_temperature_unit(self):
        place = {"name": "Berlin", "country": "Germany", "latitude": 52.5, "longitude": 13.4}
        payload = {
            "current": {"time": "2026-09-18T12:00", "temperature_2m": 20.0, "weather_code": 1},
            "current_units": {"temperature_2m": "°C"},
        }
        req = main.CurrentWeatherRequest.model_validate({"location": "Berlin", "temperature_unit": None})
        self.assertEqual(req.temperature_unit, "celsius")
        with patch.object(main, "_resolve_location", new=AsyncMock(return_value=(place, None))), \
             patch.object(main, "_request_json", new=AsyncMock(return_value=payload)):
            res = await main.get_current_weather(req)
        self.assertIsNone(res.error)
        self.assertIn("Temperature: 20°C", res.result)

    async def test_forecast_with_null_days_and_unit(self):
        place = {"name": "Berlin", "country": "Germany", "latitude": 52.5, "longitude": 13.4}
        payload = {
            "daily": {"time": ["2026-09-18", "2026-09-19", "2026-09-20"]},
            "daily_units": {},
        }
        req = main.ForecastRequest.model_validate({"location": "Berlin", "days": None, "temperature_unit": None})
        self.assertEqual(req.days, 3)
        self.assertEqual(req.temperature_unit, "celsius")
        with patch.object(main, "_resolve_location", new=AsyncMock(return_value=(place, None))), \
             patch.object(main, "_request_json", new=AsyncMock(return_value=payload)):
            res = await main.get_weather_forecast(req)
        self.assertIsNone(res.error)
        self.assertIn("3-day forecast for Berlin, Germany", res.result)


class OpenMeteoMalformedPayloadTests(unittest.IsolatedAsyncioTestCase):
    """Malformed upstream bodies must yield a clean tool error, never a traceback."""

    def _patch_client(self, responses):
        fake_client, calls = _fake_client_factory(responses)
        return patch.object(main.httpx, "AsyncClient", fake_client), calls

    async def test_non_dict_forecast_payload_returns_clean_error(self):
        # A proxy/edge returning a JSON list where an object was documented used
        # to raise AttributeError inside the handler.
        place = {"name": "London", "country": "United Kingdom", "latitude": 51.5, "longitude": -0.1}
        client_patch, _ = self._patch_client(
            {
                "geocoding-api": _FakeResponse({"results": [place]}),
                "api.open-meteo.com": _FakeResponse(["unexpected", "list"]),
            }
        )

        req = main.CurrentWeatherRequest(location="London")
        with client_patch:
            res = await main.get_current_weather(req)

        self.assertIsNone(res.result)
        self.assertIn("malformed JSON payload", res.error)

    async def test_non_json_body_returns_clean_error(self):
        place = {"name": "Paris", "country": "France", "latitude": 48.8, "longitude": 2.3}
        import json

        client_patch, _ = self._patch_client(
            {
                "geocoding-api": _FakeResponse({"results": [place]}),
                "api.open-meteo.com": _FakeResponse(json.JSONDecodeError("boom", "<html>", 0)),
            }
        )

        req = main.CurrentWeatherRequest(location="Paris")
        with client_patch:
            res = await main.get_current_weather(req)

        self.assertIsNone(res.result)
        self.assertIn("malformed JSON payload", res.error)

    async def test_geocoding_results_not_a_list_returns_clean_error(self):
        # results present but the wrong container type must be reported, not
        # silently treated as "no result".
        client_patch, _ = self._patch_client(
            {"geocoding-api": _FakeResponse({"results": "not-a-list"})}
        )

        req = main.CurrentWeatherRequest(location="London")
        with client_patch:
            res = await main.get_current_weather(req)

        self.assertIsNone(res.result)
        self.assertIn("geocoding results were not a JSON array", res.error)

    async def test_geocoding_without_numeric_coordinates_returns_clean_error(self):
        # place["latitude"] was indexed directly, so a text coordinate raised
        # TypeError when building the forecast query.
        client_patch, _ = self._patch_client(
            {
                "geocoding-api": _FakeResponse(
                    {"results": [{"name": "London", "latitude": "north", "longitude": None}]}
                )
            }
        )

        req = main.CurrentWeatherRequest(location="London")
        with client_patch:
            res = await main.get_current_weather(req)

        self.assertIsNone(res.result)
        self.assertIn("missing numeric coordinates", res.error)

    async def test_non_dict_current_weather_entries_degrade_to_placeholders(self):
        place = {"name": "Tokyo", "country": "Japan", "latitude": 35.6, "longitude": 139.6}
        payload = {
            "current": ["not", "a", "dict"],
            "current_units": {"temperature_2m": "°C"},
            "timezone": "Asia/Tokyo",
        }

        client_patch, _ = self._patch_client(
            {
                "geocoding-api": _FakeResponse({"results": [place]}),
                "api.open-meteo.com": _FakeResponse(payload),
            }
        )

        req = main.CurrentWeatherRequest(location="Tokyo")
        with client_patch:
            res = await main.get_current_weather(req)

        self.assertIsNone(res.error)
        self.assertIn("Current weather for Tokyo, Japan", res.result)
        self.assertIn("Condition: unknown", res.result)
        self.assertIn("Temperature: n/a", res.result)

    async def test_non_numeric_daily_arrays_degrade_per_day(self):
        place = {"name": "Paris", "country": "France", "latitude": 48.8, "longitude": 2.3}
        payload = {
            "daily": {
                "time": ["2026-09-15", "2026-09-16"],
                "weather_code": ["0", True],
                "temperature_2m_max": [None, 22.0],
                "temperature_2m_min": {"nested": "dict"},
                "precipitation_probability_max": "not-a-list",
                "wind_speed_10m_max": [10.0, "strong"],
            },
            "daily_units": {"temperature_2m_max": "°C", "temperature_2m_min": "°C"},
        }

        client_patch, _ = self._patch_client(
            {
                "geocoding-api": _FakeResponse({"results": [place]}),
                "api.open-meteo.com": _FakeResponse(payload),
            }
        )

        req = main.ForecastRequest(location="Paris", days=2)
        with client_patch:
            res = await main.get_weather_forecast(req)

        self.assertIsNone(res.error)
        self.assertIn("- 2026-09-15: unknown; high n/a, low n/a; rain n/a; wind up to 10", res.result)
        self.assertIn("- 2026-09-16: unknown; high 22°C, low n/a; rain n/a; wind up to n/a", res.result)

    async def test_daily_time_non_list_is_reported_as_no_forecast(self):
        place = {"name": "Paris", "country": "France", "latitude": 48.8, "longitude": 2.3}
        payload = {"daily": {"time": "2026-09-15"}}

        client_patch, _ = self._patch_client(
            {
                "geocoding-api": _FakeResponse({"results": [place]}),
                "api.open-meteo.com": _FakeResponse(payload),
            }
        )

        req = main.ForecastRequest(location="Paris", days=3)
        with client_patch:
            res = await main.get_weather_forecast(req)

        self.assertIsNone(res.error)
        self.assertEqual(res.result, "No forecast data available for Paris, France.")

    async def test_air_quality_non_dict_current_degrades_to_placeholders(self):
        place = {"name": "Delhi", "country": "India", "latitude": 28.6, "longitude": 77.2}
        payload = {"current": "junk", "current_units": None, "timezone": "Asia/Kolkata"}

        client_patch, _ = self._patch_client(
            {
                "geocoding-api": _FakeResponse({"results": [place]}),
                "air-quality-api": _FakeResponse(payload),
            }
        )

        req = main.AirQualityRequest(location="Delhi")
        with client_patch:
            res = await main.get_air_quality(req)

        self.assertIsNone(res.error)
        self.assertIn("Air quality for Delhi, India", res.result)
        self.assertIn("US AQI: n/a", res.result)
        self.assertIn("PM2.5: n/a", res.result)

    async def test_every_outbound_call_uses_the_timeout_constant(self):
        place = {"name": "London", "country": "United Kingdom", "latitude": 51.5, "longitude": -0.1}
        payload = {"current": {"time": "2026-09-15T12:00", "temperature_2m": 18.0}}

        client_patch, calls = self._patch_client(
            {
                "geocoding-api": _FakeResponse({"results": [place]}),
                "api.open-meteo.com": _FakeResponse(payload),
            }
        )

        req = main.CurrentWeatherRequest(location="London")
        with client_patch:
            res = await main.get_current_weather(req)

        self.assertIsNone(res.error)
        self.assertTrue(calls)
        for url, _params, timeout in calls:
            self.assertEqual(timeout, main.REQUEST_TIMEOUT_SECONDS, url)


if __name__ == "__main__":
    unittest.main()
