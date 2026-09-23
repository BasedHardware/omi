"""Hermetic tests for error sanitization in Open-Meteo app.

Verifies that internal exception details (IPs, hostnames, proxy details, tracebacks)
are never leaked in ChatToolResponse.error.
"""

import asyncio
import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

PLUGIN_DIR = Path(__file__).resolve().parent

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

spec = importlib.util.spec_from_file_location("open_meteo_main", PLUGIN_DIR / "main.py")
main = importlib.util.module_from_spec(spec)
spec.loader.exec_module(main)


class TestOpenMeteoErrorSanitization(unittest.TestCase):
    def test_get_current_weather_http_error_sanitized(self):
        async def _run():
            with patch.object(main, "_resolve_location", return_value=({"latitude": 52.52, "longitude": 13.41, "name": "Berlin"}, None)), \
                 patch.object(main, "_request_json", side_effect=main.httpx.HTTPError("proxy connection failed 10.0.0.1:3128")):
                req = main.CurrentWeatherRequest(location="Berlin")
                res = await main.get_current_weather(req)
                self.assertEqual("Open-Meteo request failed due to a network error.", res.error)
                self.assertNotIn("10.0.0.1", res.error)
                self.assertNotIn("HTTPError", res.error)

        asyncio.run(_run())

    def test_get_current_weather_unexpected_exception_propagates(self):
        async def _run():
            with patch.object(main, "_resolve_location", return_value=({"latitude": 52.52, "longitude": 13.41, "name": "Berlin"}, None)), \
                 patch.object(main, "_request_json", side_effect=RuntimeError("internal secret error")):
                req = main.CurrentWeatherRequest(location="Berlin")
                with self.assertRaises(RuntimeError):
                    await main.get_current_weather(req)

        asyncio.run(_run())

    def test_get_weather_forecast_http_error_sanitized(self):
        async def _run():
            with patch.object(main, "_resolve_location", return_value=({"latitude": 52.52, "longitude": 13.41, "name": "Berlin"}, None)), \
                 patch.object(main, "_request_json", side_effect=main.httpx.HTTPError("upstream gateway 192.168.1.1 error")):
                req = main.ForecastRequest(location="Berlin", days=3)
                res = await main.get_weather_forecast(req)
                self.assertEqual("Open-Meteo forecast request failed due to a network error.", res.error)
                self.assertNotIn("192.168.1.1", res.error)
                self.assertNotIn("HTTPError", res.error)

        asyncio.run(_run())

    def test_get_weather_forecast_unexpected_exception_propagates(self):
        async def _run():
            with patch.object(main, "_resolve_location", return_value=({"latitude": 52.52, "longitude": 13.41, "name": "Berlin"}, None)), \
                 patch.object(main, "_request_json", side_effect=RuntimeError("critical forecast crash")):
                req = main.ForecastRequest(location="Berlin", days=3)
                with self.assertRaises(RuntimeError):
                    await main.get_weather_forecast(req)

        asyncio.run(_run())

    def test_get_air_quality_http_error_sanitized(self):
        async def _run():
            with patch.object(main, "_resolve_location", return_value=({"latitude": 52.52, "longitude": 13.41, "name": "Berlin"}, None)), \
                 patch.object(main, "_request_json", side_effect=main.httpx.HTTPError("sensitive transport timeout")):
                req = main.AirQualityRequest(location="Berlin")
                res = await main.get_air_quality(req)
                self.assertEqual("Open-Meteo air-quality request failed due to a network error.", res.error)
                self.assertNotIn("sensitive transport timeout", res.error)
                self.assertNotIn("HTTPError", res.error)

        asyncio.run(_run())

    def test_get_air_quality_unexpected_exception_propagates(self):
        async def _run():
            with patch.object(main, "_resolve_location", return_value=({"latitude": 52.52, "longitude": 13.41, "name": "Berlin"}, None)), \
                 patch.object(main, "_request_json", side_effect=RuntimeError("internal air quality secret")):
                req = main.AirQualityRequest(location="Berlin")
                with self.assertRaises(RuntimeError):
                    await main.get_air_quality(req)

        asyncio.run(_run())


    def test_get_current_weather_malformed_payload_message(self):
        async def _run():
            with patch.object(main, "_resolve_location", return_value=({"latitude": 52.52, "longitude": 13.41, "name": "Berlin"}, None)), \
                 patch.object(main, "_request_json", side_effect=main.MalformedResponseError("malformed JSON payload (expected an object)")):
                req = main.CurrentWeatherRequest(location="Berlin")
                res = await main.get_current_weather(req)
                self.assertEqual("malformed JSON payload (expected an object)", res.error)
                self.assertNotIn("network error", res.error)
                self.assertNotIn("HTTPError", res.error)

        asyncio.run(_run())

    def test_get_weather_forecast_malformed_geocoding_array_message(self):
        async def _run():
            with patch.object(main, "_resolve_location", side_effect=main.MalformedResponseError("geocoding results were not a JSON array")):
                req = main.ForecastRequest(location="Berlin", days=3)
                res = await main.get_weather_forecast(req)
                self.assertEqual("geocoding results were not a JSON array", res.error)
                self.assertNotIn("network error", res.error)

        asyncio.run(_run())

    def test_get_air_quality_malformed_missing_coordinates_message(self):
        async def _run():
            with patch.object(main, "_resolve_location", side_effect=main.MalformedResponseError("geocoding result was missing numeric coordinates")):
                req = main.AirQualityRequest(location="Berlin")
                res = await main.get_air_quality(req)
                self.assertEqual("geocoding result was missing numeric coordinates", res.error)
                self.assertNotIn("network error", res.error)

        asyncio.run(_run())

    def test_malformed_response_error_not_masked_as_network_error(self):
        """MalformedResponseError subclasses HTTPError — must not fall into network branch."""
        async def _run():
            with patch.object(main, "_resolve_location", return_value=({"latitude": 52.52, "longitude": 13.41, "name": "Berlin"}, None)), \
                 patch.object(main, "_request_json", side_effect=main.MalformedResponseError("malformed JSON payload (could not decode body)")):
                req = main.CurrentWeatherRequest(location="Berlin")
                res = await main.get_current_weather(req)
                self.assertNotIn("network error", res.error)
                self.assertIn("malformed JSON payload", res.error)

        asyncio.run(_run())


if __name__ == "__main__":
    unittest.main()
