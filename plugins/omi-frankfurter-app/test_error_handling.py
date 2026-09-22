"""Hermetic tests: Frankfurter chat tool endpoints must never leak raw exception text.

Loads the production module with framework-only stubs so no network, credentials,
or full FastAPI runtime is required.
"""

import importlib.util
from pathlib import Path
import sys
from types import ModuleType
import unittest
from unittest.mock import AsyncMock, patch
import asyncio

_SENTINEL = "FATAL: /var/secrets/twitter_key.json: connection reset by 192.168.1.99:443"


def _load_app():
    class FastAPI:
        def __init__(self, **kwargs):
            self._lifespan = kwargs.get("lifespan")
            self.state = type("State", (), {})()

        def get(self, *args, **kwargs):
            return lambda handler: handler

        post = get

        def exception_handler(self, *args, **kwargs):
            return lambda handler: handler

    class BaseModel:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

        def model_dump(self):
            return {k: v for k, v in self.__dict__.items() if v is not None}

        @classmethod
        def __get_validators__(cls):
            yield lambda v: v

    class HTTPError(Exception):
        pass

    class HTTPStatusError(HTTPError):
        def __init__(self, *args, **kwargs):
            super().__init__(*args)
            self.response = type("R", (), {"status_code": 500})()

    httpx_mod = ModuleType("httpx")
    httpx_mod.AsyncClient = object
    httpx_mod.HTTPError = HTTPError
    httpx_mod.HTTPStatusError = HTTPStatusError

    fastapi_mod = ModuleType("fastapi")
    fastapi_mod.FastAPI = FastAPI
    fastapi_mod.Request = object

    responses_mod = ModuleType("fastapi.responses")
    responses_mod.HTMLResponse = str
    responses_mod.JSONResponse = dict

    exceptions_mod = ModuleType("fastapi.exceptions")
    exceptions_mod.RequestValidationError = Exception

    pydantic_mod = ModuleType("pydantic")
    pydantic_mod.BaseModel = BaseModel
    pydantic_mod.Field = lambda *a, **kw: None
    pydantic_mod.field_validator = lambda *a, **kw: lambda fn: fn

    spec = importlib.util.spec_from_file_location(
        "frankfurter_app", Path(__file__).with_name("main.py")
    )
    module = importlib.util.module_from_spec(spec)
    with patch.dict(
        sys.modules,
        {
            "httpx": httpx_mod,
            "fastapi": fastapi_mod,
            "fastapi.responses": responses_mod,
            "fastapi.exceptions": exceptions_mod,
            "pydantic": pydantic_mod,
        },
    ):
        spec.loader.exec_module(module)
    return module, httpx_mod


app, httpx_stub = _load_app()


def _assert_no_leak(test_case, text, context=""):
    text = str(text)
    test_case.assertNotIn(_SENTINEL, text, f"Exception text leaked in {context}")
    test_case.assertNotIn("192.168.1.99", text, f"Internal IP leaked in {context}")
    test_case.assertNotIn("/var/secrets/", text, f"Internal path leaked in {context}")


class TestFrankfurterErrorHandling(unittest.TestCase):

    def test_convert_currency_network_error(self):
        async def run():
            with patch.object(app, "_request_json", new_callable=AsyncMock) as mock_req:
                mock_req.side_effect = httpx_stub.HTTPError(_SENTINEL)
                req = app.ConvertCurrencyRequest(
                    from_currency="USD", to_currencies=["EUR"], amount=100
                )
                response = await app.convert_currency(req)
                self.assertIsNotNone(response.error)
                _assert_no_leak(self, response.error, "convert_currency")

        asyncio.run(run())

    def test_get_latest_rates_network_error(self):
        async def run():
            with patch.object(app, "_request_json", new_callable=AsyncMock) as mock_req:
                mock_req.side_effect = httpx_stub.HTTPError(_SENTINEL)
                req = app.LatestRatesRequest(base_currency="USD", to_currencies=["EUR"])
                response = await app.get_latest_rates(req)
                self.assertIsNotNone(response.error)
                _assert_no_leak(self, response.error, "get_latest_rates")

        asyncio.run(run())

    def test_list_supported_currencies_network_error(self):
        async def run():
            with patch.object(app, "_request_json", new_callable=AsyncMock) as mock_req:
                mock_req.side_effect = httpx_stub.HTTPError(_SENTINEL)
                response = await app.list_supported_currencies()
                self.assertIsNotNone(response.error)
                _assert_no_leak(self, response.error, "list_supported_currencies")

        asyncio.run(run())

    def test_convert_currency_generic_exception(self):
        async def run():
            with patch.object(app, "_request_json", new_callable=AsyncMock) as mock_req:
                mock_req.side_effect = RuntimeError(_SENTINEL)
                req = app.ConvertCurrencyRequest(
                    from_currency="USD", to_currencies=["EUR"], amount=100
                )
                response = await app.convert_currency(req)
                self.assertIsNotNone(response.error)
                _assert_no_leak(self, response.error, "convert_currency generic")

        asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
