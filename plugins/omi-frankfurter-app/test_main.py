import asyncio
from decimal import Decimal
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
                self.is_closed = False

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                self.is_closed = True

            async def get(self, *args, **kwargs):
                pass

        httpx.HTTPError = HTTPError
        httpx.HTTPStatusError = HTTPStatusError
        httpx.AsyncClient = AsyncClient
        sys.modules["httpx"] = httpx

if "fastapi" not in sys.modules:
    try:
        import fastapi  # type: ignore
        import fastapi.exceptions  # type: ignore
        import fastapi.responses  # type: ignore
    except ImportError:
        fastapi = types.ModuleType("fastapi")
        fastapi.exceptions = types.ModuleType("fastapi.exceptions")
        fastapi.responses = types.ModuleType("fastapi.responses")

        class FastAPI:
            def __init__(self, *args, **kwargs):
                self.title = kwargs.get("title", "")
                self.version = kwargs.get("version", "")
                self.description = kwargs.get("description", "")
                self.state = types.SimpleNamespace(http_client=None)

            def get(self, *args, **kwargs):
                return lambda f: f

            def post(self, *args, **kwargs):
                return lambda f: f

            def exception_handler(self, *args, **kwargs):
                return lambda f: f

        class Request:
            pass

        class RequestValidationError(Exception):
            pass

        class JSONResponse:
            def __init__(self, content, status_code=200):
                self.content = content
                self.status_code = status_code

        class HTMLResponse:
            def __init__(self, content):
                self.content = content

        fastapi.FastAPI = FastAPI
        fastapi.Request = Request
        fastapi.exceptions.RequestValidationError = RequestValidationError
        fastapi.responses.JSONResponse = JSONResponse
        fastapi.responses.HTMLResponse = HTMLResponse
        sys.modules["fastapi"] = fastapi
        sys.modules["fastapi.exceptions"] = fastapi.exceptions
        sys.modules["fastapi.responses"] = fastapi.responses

if "pydantic" not in sys.modules:
    try:
        import pydantic  # type: ignore
    except ImportError:
        pydantic = types.ModuleType("pydantic")

        class BaseModel:
            def __init__(self, **kwargs):
                for k, v in kwargs.items():
                    setattr(self, k, v)

        def Field(default=None, **kwargs):
            return default

        def field_validator(*args, **kwargs):
            return lambda f: f

        pydantic.BaseModel = BaseModel
        pydantic.Field = Field
        pydantic.field_validator = field_validator
        sys.modules["pydantic"] = pydantic

APP_DIR = Path(__file__).resolve().parent
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

import main  # noqa: E402


class FrankfurterStaticAndSchemaTests(unittest.TestCase):
    def test_app_metadata(self):
        self.assertEqual(main.app.title, "Omi Frankfurter Currency Integration")
        self.assertEqual(main.app.version, "1.0.0")

    def test_v1_base_url(self):
        self.assertEqual(main.FRANKFURTER_BASE_URL, "https://api.frankfurter.dev/v1")

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
        self.assertEqual(main._format_decimal(0), "0")
        self.assertEqual(main._format_decimal(Decimal("0.000042")), "0.000042")
        self.assertEqual(main._format_decimal(Decimal("0.00000123")), "0.00000123")


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
            self.assertEqual(resp.error, "invalid payload returned by currency provider")

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

    async def test_get_latest_rates_small_rate_display(self):
        mock_data = {
            "base": "IDR",
            "date": "2026-09-15",
            "rates": {"GBP": 0.000042},
        }
        with patch.object(main, "_request_json", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = mock_data
            req = main.LatestRatesRequest(base_currency="IDR", to_currencies=["GBP"])
            resp = await main.get_latest_rates(req)
            self.assertIsNone(resp.error)
            self.assertIn("- 1 IDR = 0.000042 GBP", resp.result)

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
            self.assertEqual(resp.error, "invalid currency list returned")


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
