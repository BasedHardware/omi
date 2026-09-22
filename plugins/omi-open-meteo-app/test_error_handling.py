"""Hermetic error handling and exception sanitization tests for Open-Meteo App.

Verifies that internal exceptions, system paths, network addresses, and raw
tracebacks never leak into chat tool responses.
Runs under standard library unittest without external network dependencies.
"""

import asyncio
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent))


class Framework:
    def __init__(self, content="", status_code=200, **kwargs):
        self.content = content
        self.status_code = status_code
        self.kwargs = kwargs

    def get(self, *args, **kwargs):
        return lambda function: function

    post = get

    def exception_handler(self, exc_class):
        return lambda function: function


class BaseModel:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


class ChatToolResponse(BaseModel):
    def __init__(self, result=None, error=None, **kwargs):
        super().__init__(result=result, error=error, **kwargs)


def make_module(name, **attributes):
    val = types.ModuleType(name)
    val.__dict__.update(attributes)
    return val


def load_openmeteo_module():
    class HTTPError(Exception):
        pass

    class HTTPStatusError(HTTPError):
        def __init__(self, message="", request=None, response=None):
            super().__init__(message)
            self.response = response or types.SimpleNamespace(status_code=500)

    class AsyncClient:
        def __init__(self, *args, **kwargs):
            self.is_closed = False

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def get(self, *args, **kwargs):
            raise AssertionError("stub get")

        async def aclose(self):
            self.is_closed = True

    httpx_mod = make_module(
        "httpx",
        HTTPError=HTTPError,
        HTTPStatusError=HTTPStatusError,
        AsyncClient=AsyncClient,
    )

    fastapi_exceptions = make_module("fastapi.exceptions", RequestValidationError=Exception)
    fastapi_responses = make_module("fastapi.responses", HTMLResponse=Framework, JSONResponse=Framework)

    class CurrentWeatherRequest(BaseModel):
        location: str = "London"
        temperature_unit: str = "celsius"

    class ForecastRequest(BaseModel):
        location: str = "London"
        days: int = 3
        temperature_unit: str = "celsius"

    class AirQualityRequest(BaseModel):
        location: str = "London"

    pydantic_mod = make_module(
        "pydantic",
        BaseModel=BaseModel,
        Field=lambda *a, **k: None,
        field_validator=lambda *a, **k: lambda f: f,
        model_validator=lambda *a, **k: lambda f: f,
    )

    stubs = {
        "httpx": httpx_mod,
        "fastapi": make_module("fastapi", FastAPI=Framework, Request=Framework),
        "fastapi.exceptions": fastapi_exceptions,
        "fastapi.responses": fastapi_responses,
        "pydantic": pydantic_mod,
    }

    for k, v in stubs.items():
        sys.modules.setdefault(k, v)

    spec = importlib.util.spec_from_file_location(
        "openmeteo_main_test", Path(__file__).with_name("main.py")
    )
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, stubs):
        spec.loader.exec_module(module)
    return module


app = load_openmeteo_module()


class OpenMeteoErrorHandlingTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.sensitive_leak = "FATAL: /var/secrets/meteo_key.json: connection reset by 192.168.1.88:443"

    async def test_get_current_weather_sanitizes_unexpected_exception(self):
        req = app.CurrentWeatherRequest(location="San Francisco", temperature_unit="celsius")
        with patch.object(app, "_resolve_location", side_effect=RuntimeError(self.sensitive_leak)):
            resp = await app.get_current_weather(req)
            self.assertEqual(resp.error, "Open-Meteo request failed.")
            self.assertNotIn(self.sensitive_leak, str(resp.error))
            self.assertNotIn("192.168.1.88", str(resp.error))

    async def test_get_current_weather_sanitizes_network_http_error(self):
        req = app.CurrentWeatherRequest(location="San Francisco", temperature_unit="celsius")
        with patch.object(app, "_resolve_location", side_effect=app.httpx.HTTPError(self.sensitive_leak)):
            resp = await app.get_current_weather(req)
            self.assertEqual(resp.error, "Open-Meteo request failed.")
            self.assertNotIn(self.sensitive_leak, str(resp.error))

    async def test_get_weather_forecast_sanitizes_unexpected_exception(self):
        req = app.ForecastRequest(location="San Francisco", days=3, temperature_unit="celsius")
        with patch.object(app, "_resolve_location", side_effect=RuntimeError(self.sensitive_leak)):
            resp = await app.get_weather_forecast(req)
            self.assertEqual(resp.error, "Open-Meteo forecast request failed.")
            self.assertNotIn(self.sensitive_leak, str(resp.error))
            self.assertNotIn("192.168.1.88", str(resp.error))

    async def test_get_weather_forecast_sanitizes_network_http_error(self):
        req = app.ForecastRequest(location="San Francisco", days=3, temperature_unit="celsius")
        with patch.object(app, "_resolve_location", side_effect=app.httpx.HTTPError(self.sensitive_leak)):
            resp = await app.get_weather_forecast(req)
            self.assertEqual(resp.error, "Open-Meteo forecast request failed.")
            self.assertNotIn(self.sensitive_leak, str(resp.error))

    async def test_get_air_quality_sanitizes_unexpected_exception(self):
        req = app.AirQualityRequest(location="San Francisco")
        with patch.object(app, "_resolve_location", side_effect=RuntimeError(self.sensitive_leak)):
            resp = await app.get_air_quality(req)
            self.assertEqual(resp.error, "Open-Meteo air-quality request failed.")
            self.assertNotIn(self.sensitive_leak, str(resp.error))
            self.assertNotIn("192.168.1.88", str(resp.error))

    async def test_get_air_quality_sanitizes_network_http_error(self):
        req = app.AirQualityRequest(location="San Francisco")
        with patch.object(app, "_resolve_location", side_effect=app.httpx.HTTPError(self.sensitive_leak)):
            resp = await app.get_air_quality(req)
            self.assertEqual(resp.error, "Open-Meteo air-quality request failed.")
            self.assertNotIn(self.sensitive_leak, str(resp.error))

    async def test_get_current_weather_sanitizes_malformed_response(self):
        req = app.CurrentWeatherRequest(location="London", temperature_unit="celsius")
        with patch.object(app, "_resolve_location", side_effect=app.MalformedResponseError(self.sensitive_leak)):
            resp = await app.get_current_weather(req)
            self.assertEqual(resp.error, "Open-Meteo request failed.")
            self.assertNotIn(self.sensitive_leak, str(resp.error))

    async def test_get_weather_forecast_sanitizes_malformed_response(self):
        req = app.ForecastRequest(location="London", days=3, temperature_unit="celsius")
        with patch.object(app, "_resolve_location", side_effect=app.MalformedResponseError(self.sensitive_leak)):
            resp = await app.get_weather_forecast(req)
            self.assertEqual(resp.error, "Open-Meteo forecast request failed.")
            self.assertNotIn(self.sensitive_leak, str(resp.error))

    async def test_get_air_quality_sanitizes_malformed_response(self):
        req = app.AirQualityRequest(location="London")
        with patch.object(app, "_resolve_location", side_effect=app.MalformedResponseError(self.sensitive_leak)):
            resp = await app.get_air_quality(req)
            self.assertEqual(resp.error, "Open-Meteo air-quality request failed.")
            self.assertNotIn(self.sensitive_leak, str(resp.error))


if __name__ == "__main__":
    unittest.main()
