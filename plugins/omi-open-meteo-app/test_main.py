"""Hermetic regression tests for plugins/omi-open-meteo-app/main.py.

Standard library only: fastapi, fastapi.responses, httpx and pydantic are
replaced with minimal stubs before importing the module under test so the
suite runs without site-packages (the manifest lane runs plain python3).

Covers the crashes reported in #13924: daily metric arrays that are missing,
``null``, or shorter than ``daily["time"]`` raised ``IndexError`` in
``get_weather_forecast``; ``null`` unit fields raised ``TypeError`` on
``' ' + units.get(...)`` concatenation in all three tool handlers (and leaked
``"None"`` into rendered output through ``_format_number``); and an empty or
missing ``daily["time"]`` returned a bare header with no explanation.
"""

import asyncio
import os
import sys
import types
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def _install_module_stubs():
    fastapi = types.ModuleType("fastapi")

    class _App:
        def __init__(self, *args, **kwargs):
            pass

        def get(self, *args, **kwargs):
            return lambda handler: handler

        post = get
        put = get
        delete = get

    fastapi.FastAPI = _App

    responses = types.ModuleType("fastapi.responses")
    responses.HTMLResponse = str

    pydantic = types.ModuleType("pydantic")

    class _BaseModel:
        def __init__(self, **data):
            annotations = {}
            for klass in reversed(type(self).__mro__):
                annotations.update(getattr(klass, "__annotations__", {}))
            for name in annotations:
                if name in data:
                    setattr(self, name, data[name])
                else:
                    setattr(self, name, getattr(type(self), name, None))

    pydantic.BaseModel = _BaseModel
    pydantic.Field = lambda default=None, **kwargs: default

    httpx = types.ModuleType("httpx")

    class _HTTPError(Exception):
        pass

    class _AsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def get(self, *args, **kwargs):
            raise AssertionError("network access is not allowed in tests")

    httpx.HTTPError = _HTTPError
    httpx.AsyncClient = _AsyncClient

    sys.modules["fastapi"] = fastapi
    sys.modules["fastapi.responses"] = responses
    sys.modules["pydantic"] = pydantic
    sys.modules["httpx"] = httpx


_install_module_stubs()

import main  # noqa: E402


def _place(name="Berlin"):
    return {
        "name": name,
        "admin1": name,
        "country": "Germany",
        "latitude": 52.52,
        "longitude": 13.41,
    }


def _run(coro):
    return asyncio.run(coro)


class _PatchedEndpoints:
    """Patch the two network seams the tool handlers call."""

    def __init__(self, payload):
        self._resolve = mock.patch.object(
            main, "_resolve_location", new=mock.AsyncMock(return_value=(_place(), None))
        )
        self._request = mock.patch.object(
            main, "_request_json", new=mock.AsyncMock(return_value=payload)
        )

    def __enter__(self):
        self._resolve.__enter__()
        self._request.__enter__()
        return self

    def __exit__(self, *exc):
        self._request.__exit__(*exc)
        self._resolve.__exit__(*exc)
        return False


FORECAST_DAYS = ["2025-01-01", "2025-01-02", "2025-01-03"]


class SafeItemTests(unittest.TestCase):
    def test_returns_item_at_index(self):
        self.assertEqual(main._safe_item([10, 20, 30], 1), 20)

    def test_out_of_range_returns_default(self):
        self.assertIsNone(main._safe_item([10], 5))
        self.assertEqual(main._safe_item([10], 5, default="x"), "x")

    def test_non_sequence_returns_default(self):
        self.assertIsNone(main._safe_item(None, 0))
        self.assertIsNone(main._safe_item({"a": 1}, 0))
        self.assertIsNone(main._safe_item(42, 0))


class FormatUnitSuffixTests(unittest.TestCase):
    def test_null_and_non_string_units_become_empty(self):
        self.assertEqual(main._format_unit_suffix(None), "")
        self.assertEqual(main._format_unit_suffix(5), "")
        self.assertEqual(main._format_unit_suffix(""), "")

    def test_string_unit_gets_prefix(self):
        self.assertEqual(main._format_unit_suffix("km/h"), " km/h")
        self.assertEqual(main._format_unit_suffix("°C", ""), "°C")


class GetWeatherForecastTests(unittest.TestCase):
    def test_short_daily_arrays_do_not_raise(self):
        """#13924: 1-element metric arrays for a 3-day forecast must not IndexError."""
        payload = {
            "daily": {
                "time": FORECAST_DAYS,
                "weather_code": [0],
                "temperature_2m_max": [20.0],
                "temperature_2m_min": [10.0],
                "precipitation_probability_max": [],
                "wind_speed_10m_max": None,
            },
            "daily_units": {
                "temperature_2m_max": "°C",
                "temperature_2m_min": "°C",
                "precipitation_probability_max": "%",
                "wind_speed_10m_max": "km/h",
            },
        }
        with _PatchedEndpoints(payload):
            resp = _run(
                main.get_weather_forecast(main.ForecastRequest(location="Berlin", days=3))
            )
        self.assertIsNone(resp.error)
        self.assertIn("3-day forecast for Berlin, Germany", resp.result)
        self.assertIn("- 2025-01-03", resp.result)
        self.assertIn("n/a", resp.result)

    def test_empty_time_returns_no_data_message(self):
        payload = {"daily": {"time": []}, "daily_units": {}}
        with _PatchedEndpoints(payload):
            resp = _run(
                main.get_weather_forecast(main.ForecastRequest(location="Berlin", days=3))
            )
        self.assertIsNone(resp.error)
        self.assertEqual(resp.result, "No forecast data available for Berlin, Germany.")

    def test_missing_or_null_time_returns_no_data_message(self):
        for daily in ({}, {"time": None}):
            with _PatchedEndpoints({"daily": daily, "daily_units": {}}):
                resp = _run(
                    main.get_weather_forecast(main.ForecastRequest(location="Berlin", days=3))
                )
            self.assertIsNone(resp.error)
            self.assertEqual(
                resp.result, "No forecast data available for Berlin, Germany."
            )

    def test_null_units_do_not_raise(self):
        """#13924: null unit fields must not TypeError or render 'None'."""
        payload = {
            "daily": {
                "time": FORECAST_DAYS,
                "weather_code": [0, 1, 2],
                "temperature_2m_max": [20.0, 21.0, 22.0],
                "temperature_2m_min": [10.0, 11.0, 12.0],
                "precipitation_probability_max": [5, 10, 15],
                "wind_speed_10m_max": [15.0, 16.0, 17.0],
            },
            "daily_units": {
                "temperature_2m_max": None,
                "temperature_2m_min": None,
                "precipitation_probability_max": None,
                "wind_speed_10m_max": None,
            },
        }
        with _PatchedEndpoints(payload):
            resp = _run(
                main.get_weather_forecast(main.ForecastRequest(location="Berlin", days=3))
            )
        self.assertIsNone(resp.error)
        self.assertIn("high 20", resp.result)
        self.assertIn("wind up to 15", resp.result)
        self.assertNotIn("None", resp.result)

    def test_full_forecast_still_renders_units(self):
        payload = {
            "daily": {
                "time": FORECAST_DAYS,
                "weather_code": [0, 61, 3],
                "temperature_2m_max": [20.0, 18.5, 22.0],
                "temperature_2m_min": [10.0, 9.0, 12.0],
                "precipitation_probability_max": [5, 80, 15],
                "wind_speed_10m_max": [15.0, 30.0, 17.0],
            },
            "daily_units": {
                "temperature_2m_max": "°C",
                "temperature_2m_min": "°C",
                "precipitation_probability_max": "%",
                "wind_speed_10m_max": "km/h",
            },
        }
        with _PatchedEndpoints(payload):
            resp = _run(
                main.get_weather_forecast(main.ForecastRequest(location="Berlin", days=3))
            )
        self.assertIsNone(resp.error)
        self.assertIn("high 20°C, low 10°C", resp.result)
        self.assertIn("rain 80%", resp.result)
        self.assertIn("wind up to 15 km/h", resp.result)


class GetCurrentWeatherTests(unittest.TestCase):
    def test_null_units_do_not_raise(self):
        """#13924: ' ' + units.get(...) TypeError and 'None' leakage via _format_number."""
        payload = {
            "current": {
                "time": "2025-01-01T12:00",
                "temperature_2m": 20.0,
                "apparent_temperature": 19.0,
                "relative_humidity_2m": 55,
                "precipitation": 0.0,
                "weather_code": 0,
                "wind_speed_10m": 12.0,
            },
            "current_units": {
                "temperature_2m": None,
                "apparent_temperature": None,
                "relative_humidity_2m": None,
                "precipitation": None,
                "wind_speed_10m": None,
            },
        }
        with _PatchedEndpoints(payload):
            resp = _run(main.get_current_weather(main.CurrentWeatherRequest(location="Berlin")))
        self.assertIsNone(resp.error)
        self.assertIn("Temperature: 20", resp.result)
        self.assertIn("Wind: 12", resp.result)
        self.assertNotIn("None", resp.result)


class GetAirQualityTests(unittest.TestCase):
    def test_null_units_do_not_raise(self):
        payload = {
            "current": {
                "time": "2025-01-01T12:00",
                "us_aqi": 42,
                "pm2_5": 12.0,
                "pm10": 20.0,
                "ozone": 30.0,
                "nitrogen_dioxide": 5.0,
            },
            "current_units": {
                "us_aqi": None,
                "pm2_5": None,
                "pm10": None,
                "ozone": None,
                "nitrogen_dioxide": None,
            },
        }
        with _PatchedEndpoints(payload):
            resp = _run(main.get_air_quality(main.AirQualityRequest(location="Berlin")))
        self.assertIsNone(resp.error)
        self.assertIn("PM2.5: 12", resp.result)
        self.assertNotIn("None", resp.result)


if __name__ == "__main__":
    unittest.main()
