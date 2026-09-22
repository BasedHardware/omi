"""Hermetic tests: USGS Earthquake app endpoints must never leak raw exception text."""

import asyncio
import sys
import types
import unittest
from unittest.mock import AsyncMock, patch

_SENTINEL = "FATAL: /var/secrets/twitter_key.json: connection reset by 192.168.1.99:443"


class DummyState:
    def __init__(self):
        self.http_client = None


class DummyFastAPI:
    def __init__(self, **_kwargs):
        self.routes = []
        self.state = DummyState()

    def get(self, path, **_kwargs):
        return self._route("POST", path)

    def post(self, path, **_kwargs):
        return self._route("POST", path)

    def _route(self, method, path):
        def decorator(func):
            self.routes.append((method, path, func))
            return func
        return decorator


class DummyBaseModel:
    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)


class DummyRequest:
    def __init__(self, payload=None, json_error=None):
        self.payload = payload
        self.json_error = json_error

    async def json(self):
        if self.json_error:
            raise self.json_error
        return self.payload


def install_dependency_stubs():
    fastapi = types.ModuleType("fastapi")
    fastapi.FastAPI = DummyFastAPI
    fastapi.Request = object
    sys.modules.setdefault("fastapi", fastapi)

    pydantic = types.ModuleType("pydantic")
    pydantic.BaseModel = DummyBaseModel
    pydantic.Field = lambda default=None, **_kw: default
    sys.modules.setdefault("pydantic", pydantic)

    httpx = types.ModuleType("httpx")
    class HTTPError(Exception):
        pass
    httpx.HTTPError = HTTPError

    class DummyAsyncClient:
        def __init__(self, *args, **kwargs):
            self.is_closed = False
        async def get(self, *args, **kwargs):
            raise NotImplementedError
        async def aclose(self):
            self.is_closed = True

    httpx.AsyncClient = DummyAsyncClient
    sys.modules.setdefault("httpx", httpx)
    return httpx


httpx_mod = install_dependency_stubs()
if "main" in sys.modules:
    del sys.modules["main"]
import main


def _assert_no_leak(test_case, obj, context=""):
    text = str(obj)
    test_case.assertNotIn(_SENTINEL, text, f"Exception text leaked in {context}")
    test_case.assertNotIn("192.168.1.99", text, f"Internal IP leaked in {context}")
    test_case.assertNotIn("/var/secrets/", text, f"Internal path leaked in {context}")


class UsgsErrorHandlingTests(unittest.TestCase):

    def test_usgs_get_http_error(self):
        async def run():
            with patch.object(main, "_get_http_client") as mock_client_factory:
                mock_client = AsyncMock()
                mock_client.get.side_effect = httpx_mod.HTTPError(_SENTINEL)
                mock_client_factory.return_value = (mock_client, False)

                result = await main._usgs_get({"format": "geojson"})
                self.assertIn("error", result)
                _assert_no_leak(self, result["error"], "_usgs_get")
                self.assertEqual(result["error"], "USGS request failed")

        asyncio.run(run())

    def test_tool_recent_earthquakes_http_error(self):
        async def run():
            with patch.object(main, "_get_http_client") as mock_client_factory:
                mock_client = AsyncMock()
                mock_client.get.side_effect = httpx_mod.HTTPError(_SENTINEL)
                mock_client_factory.return_value = (mock_client, False)

                request = DummyRequest(payload={"hours": 24})
                response = await main.tool_recent_earthquakes(request)
                self.assertFalse(response.success)
                _assert_no_leak(self, response.message, "tool_recent_earthquakes message")
                _assert_no_leak(self, response.data, "tool_recent_earthquakes data")
                self.assertEqual(response.message, "USGS request failed")

        asyncio.run(run())

    def test_tool_nearby_earthquakes_http_error(self):
        async def run():
            with patch.object(main, "_get_http_client") as mock_client_factory:
                mock_client = AsyncMock()
                mock_client.get.side_effect = httpx_mod.HTTPError(_SENTINEL)
                mock_client_factory.return_value = (mock_client, False)

                request = DummyRequest(payload={"latitude": 37.77, "longitude": -122.41, "radius_km": 100})
                response = await main.tool_nearby_earthquakes(request)
                self.assertFalse(response.success)
                _assert_no_leak(self, response.message, "tool_nearby_earthquakes message")
                _assert_no_leak(self, response.data, "tool_nearby_earthquakes data")
                self.assertEqual(response.message, "USGS request failed")

        asyncio.run(run())

    def test_tool_earthquake_details_http_error(self):
        async def run():
            with patch.object(main, "_get_http_client") as mock_client_factory:
                mock_client = AsyncMock()
                mock_client.get.side_effect = httpx_mod.HTTPError(_SENTINEL)
                mock_client_factory.return_value = (mock_client, False)

                request = DummyRequest(payload={"event_id": "us7000abcd"})
                response = await main.tool_earthquake_details(request)
                self.assertFalse(response.success)
                _assert_no_leak(self, response.message, "tool_earthquake_details message")
                _assert_no_leak(self, response.data, "tool_earthquake_details data")
                self.assertEqual(response.message, "USGS request failed")

        asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
