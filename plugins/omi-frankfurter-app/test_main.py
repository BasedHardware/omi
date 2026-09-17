"""Hermetic unit tests for Frankfurter Currency Omi integration.

No third-party runtime dependencies required. Runs deterministically under
both standard library `python3 -S` and `pytest`.
"""

import asyncio
from decimal import Decimal
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import AsyncMock, patch


def load_app():
    class DummyState:
        pass

    class DummyFastAPI:
        def __init__(self, **kwargs):
            self.routes = []
            self.lifespan = kwargs.get("lifespan")
            self.state = DummyState()

        def get(self, path, **kwargs):
            return self._route("GET", path, kwargs.get("response_model"))

        def post(self, path, **kwargs):
            return self._route("POST", path, kwargs.get("response_model"))

        def exception_handler(self, exc_class):
            def decorator(func):
                return func

            return decorator

        def _route(self, method, path, response_model):
            def decorator(func):
                self.routes.append({
                    "method": method,
                    "path": path,
                    "func": func,
                    "response_model": response_model,
                })
                return func

            return decorator

    class DummyBaseModel:
        def __init__(self, **kwargs):
            for key, value in kwargs.items():
                setattr(self, key, value)

        def model_dump(self):
            return {k: v for k, v in self.__dict__.items() if not k.startswith("_")}

    def Field(default=None, **_kwargs):
        return default

    def field_validator(*_args, **_kwargs):
        def decorator(func):
            return func

        return decorator

    class HTTPError(Exception):
        pass

    class HTTPStatusError(HTTPError):
        def __init__(self, message=None, response=None):
            super().__init__(message)
            self.response = response or types.SimpleNamespace(status_code=500)

    class DummyAsyncClient:
        def __init__(self, *args, **kwargs):
            self.is_closed = False

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            self.is_closed = True

        async def aclose(self):
            self.is_closed = True

        async def get(self, url, params=None):
            raise NotImplementedError

    fastapi = types.ModuleType("fastapi")
    fastapi.FastAPI = DummyFastAPI
    fastapi.Request = object
    fastapi_responses = types.ModuleType("fastapi.responses")
    fastapi_responses.HTMLResponse = str
    fastapi_responses.JSONResponse = dict
    fastapi_exceptions = types.ModuleType("fastapi.exceptions")

    class RequestValidationError(Exception):
        pass

    fastapi_exceptions.RequestValidationError = RequestValidationError

    pydantic = types.ModuleType("pydantic")
    pydantic.BaseModel = DummyBaseModel
    pydantic.Field = Field
    pydantic.field_validator = field_validator

    httpx = types.ModuleType("httpx")
    httpx.HTTPError = HTTPError
    httpx.HTTPStatusError = HTTPStatusError
    httpx.AsyncClient = DummyAsyncClient

    spec = importlib.util.spec_from_file_location("frankfurter_app_hermetic", Path(__file__).with_name("main.py"))
    module = importlib.util.module_from_spec(spec)
    with patch.dict(
        sys.modules,
        {
            "fastapi": fastapi,
            "fastapi.responses": fastapi_responses,
            "fastapi.exceptions": fastapi_exceptions,
            "pydantic": pydantic,
            "httpx": httpx,
        },
    ):
        spec.loader.exec_module(module)
    return module


main = load_app()


class RouteWiringTests(unittest.TestCase):
    def test_routes_registered_with_correct_methods_and_paths(self):
        registered = {(r["method"], r["path"]): r for r in main.app.routes}
        expected_endpoints = {
            ("GET", "/"),
            ("GET", "/health"),
            ("GET", "/.well-known/omi-tools.json"),
            ("POST", "/tools/convert_currency"),
            ("POST", "/tools/get_latest_rates"),
            ("POST", "/tools/list_supported_currencies"),
        }
        for endpoint in expected_endpoints:
            self.assertIn(endpoint, registered)

        self.assertIs(registered[("POST", "/tools/convert_currency")]["response_model"], main.ChatToolResponse)
        self.assertIs(registered[("POST", "/tools/get_latest_rates")]["response_model"], main.ChatToolResponse)
        self.assertIs(registered[("POST", "/tools/list_supported_currencies")]["response_model"], main.ChatToolResponse)

    def test_tools_manifest_matches_registered_routes(self):
        manifest = asyncio.run(main.omi_tools())
        tools = manifest["tools"]
        self.assertEqual(len(tools), 3)
        tool_endpoints = {t["endpoint"]: t["method"] for t in tools}
        self.assertEqual(
            tool_endpoints,
            {
                "/tools/convert_currency": "POST",
                "/tools/get_latest_rates": "POST",
                "/tools/list_supported_currencies": "POST",
            },
        )

    def test_root_and_health_endpoints(self):
        health_resp = asyncio.run(main.health())
        self.assertEqual(health_resp, {"status": "ok"})

        root_resp = asyncio.run(main.root())
        self.assertIn("Omi Frankfurter Currency Integration", root_resp)


class HelperFunctionTests(unittest.TestCase):
    def test_normalize_currency_code(self):
        self.assertEqual(main._normalize_currency_code("usd"), "USD")
        self.assertEqual(main._normalize_currency_code("  eur  "), "EUR")
        with self.assertRaises(ValueError):
            main._normalize_currency_code("US")
        with self.assertRaises(ValueError):
            main._normalize_currency_code("USDT")
        with self.assertRaises(ValueError):
            main._normalize_currency_code("123")

    def test_parse_amount_valid(self):
        self.assertEqual(main._parse_amount(50), Decimal("50"))
        self.assertEqual(main._parse_amount("19.95"), Decimal("19.95"))
        self.assertEqual(main._parse_amount(0.01), Decimal(str(0.01)))

    def test_parse_amount_zero_and_negative(self):
        with self.assertRaises(ValueError):
            main._parse_amount(0)
        with self.assertRaises(ValueError):
            main._parse_amount(-5)
        with self.assertRaises(ValueError):
            main._parse_amount("-12.50")

    def test_parse_amount_invalid_text(self):
        with self.assertRaises(ValueError):
            main._parse_amount("abc")
        with self.assertRaises(ValueError):
            main._parse_amount("")

    def test_parse_amount_non_finite_rejected(self):
        non_finite = ["NaN", "nan", "Infinity", "-Infinity", "inf", "-inf"]
        for val in non_finite:
            with self.assertRaises(ValueError):
                main._parse_amount(val)

    def test_format_decimal(self):
        self.assertEqual(main._format_decimal(Decimal("10.5000")), "10.5")
        self.assertEqual(main._format_decimal(Decimal("1.23456")), "1.2346")


class FrankfurterToolTests(unittest.IsolatedAsyncioTestCase):
    async def test_convert_currency_success(self):
        mock_data = {
            "amount": 100.0,
            "base": "USD",
            "date": "2026-09-15",
            "rates": {"EUR": 0.92, "GBP": 0.78},
        }
        with patch.object(main, "_request_json", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = mock_data
            req = main.ConvertCurrencyRequest(amount=100, from_currency="USD", to_currencies=["EUR", "GBP"])
            resp = await main.convert_currency(req)
            self.assertIsNone(resp.error)
            self.assertIn("100 USD on 2026-09-15:", resp.result)
            self.assertIn("- EUR: 0.92", resp.result)
            self.assertIn("- GBP: 0.78", resp.result)

    async def test_convert_currency_empty_rates(self):
        mock_data = {"rates": {}}
        with patch.object(main, "_request_json", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = mock_data
            req = main.ConvertCurrencyRequest(amount=50, from_currency="USD", to_currencies=["EUR"])
            resp = await main.convert_currency(req)
            self.assertEqual(resp.error, "no rates returned for the requested currencies")

    async def test_convert_currency_non_dict_payload(self):
        with patch.object(main, "_request_json", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = "<html>Error</html>"
            req = main.ConvertCurrencyRequest(amount=50, from_currency="USD", to_currencies=["EUR"])
            resp = await main.convert_currency(req)
            self.assertEqual(resp.error, "no rates returned for the requested currencies")

    async def test_convert_currency_invalid_amount(self):
        req = main.ConvertCurrencyRequest(amount="NaN", from_currency="USD", to_currencies=["EUR"])
        resp = await main.convert_currency(req)
        self.assertIn("amount must be a finite number", resp.error)

    async def test_convert_currency_http_error(self):
        with patch.object(main, "_request_json", new_callable=AsyncMock) as mock_req:
            mock_req.side_effect = main.httpx.HTTPError("Network down")
            req = main.ConvertCurrencyRequest(amount=50, from_currency="USD", to_currencies=["EUR"])
            resp = await main.convert_currency(req)
            self.assertIn("currency conversion failed: Network down", resp.error)

    async def test_get_latest_rates_success(self):
        mock_data = {
            "base": "USD",
            "date": "2026-09-15",
            "rates": {"EUR": 0.92, "JPY": 150.25},
        }
        with patch.object(main, "_request_json", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = mock_data
            req = main.LatestRatesRequest(base_currency="USD", to_currencies=["EUR", "JPY"])
            resp = await main.get_latest_rates(req)
            self.assertIsNone(resp.error)
            self.assertIn("Latest USD reference rates for 2026-09-15:", resp.result)
            self.assertIn("- 1 USD = 0.92 EUR", resp.result)
            self.assertIn("- 1 USD = 150.25 JPY", resp.result)

    async def test_get_latest_rates_empty(self):
        with patch.object(main, "_request_json", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = {"rates": None}
            req = main.LatestRatesRequest(base_currency="USD", to_currencies=[])
            resp = await main.get_latest_rates(req)
            self.assertEqual(resp.error, "no rates returned")

    async def test_list_supported_currencies_success(self):
        mock_data = {"USD": "United States Dollar", "EUR": "Euro", "GBP": "British Pound"}
        with patch.object(main, "_request_json", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = mock_data
            resp = await main.list_supported_currencies()
            self.assertIsNone(resp.error)
            self.assertIn("Frankfurter supported currencies:", resp.result)
            self.assertIn("- EUR: Euro", resp.result)
            self.assertIn("- USD: United States Dollar", resp.result)

    async def test_list_supported_currencies_non_dict(self):
        with patch.object(main, "_request_json", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = []
            resp = await main.list_supported_currencies()
            self.assertEqual(resp.error, "currency list request returned no currencies")


class LifespanAndFallbackTests(unittest.IsolatedAsyncioTestCase):
    async def test_lifespan_manages_state_http_client(self):
        async with main.lifespan(main.app):
            self.assertIsNotNone(main.app.state.http_client)
            self.assertFalse(main.app.state.http_client.is_closed)
        self.assertTrue(main.app.state.http_client.is_closed)

    async def test_request_json_fallback_when_unmanaged(self):
        main.app.state.http_client = None
        fake_response = types.SimpleNamespace(
            status_code=200,
            content=b'{"rates": {}}',
            json=lambda: {"rates": {}},
            raise_for_status=lambda: None,
        )
        with patch.object(main.httpx.AsyncClient, "get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = fake_response
            res = await main._request_json("/latest")
            self.assertEqual(res, {"rates": {}})


if __name__ == "__main__":
    unittest.main()
