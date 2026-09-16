"""Hermetic Frankfurter currency-app regressions for BasedHardware/omi#14153.

Import the production module with framework-only stubs, then exercise the real
handlers, HTTP boundary, and lifespan. No network, credentials, or third-party
runtime packages are required; the suite runs under plain stdlib ``python3 -S``.
"""

from decimal import Decimal
import importlib.util
from pathlib import Path
import sys
from types import ModuleType
import unittest
from unittest.mock import AsyncMock, patch


def load_app():
    class State:
        pass

    class FastAPI:
        def __init__(self, **kwargs):
            self.state = State()

        def get(self, *args, **kwargs):
            return lambda handler: handler

        post = get

        def exception_handler(self, *args, **kwargs):
            return lambda handler: handler

    class BaseModel:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

        def model_dump(self):
            return dict(self.__dict__)

    def Field(default=None, default_factory=None, **kwargs):
        return default_factory() if default_factory is not None else default

    def field_validator(*args, **kwargs):
        return lambda fn: fn

    class HTTPError(Exception):
        pass

    class JSONResponse:
        def __init__(self, status_code=200, content=None, **kwargs):
            self.status_code = status_code
            self.content = content

    httpx = ModuleType("httpx")
    httpx.AsyncClient = object
    httpx.HTTPError = HTTPError
    fastapi = ModuleType("fastapi")
    fastapi.FastAPI = FastAPI
    fastapi.Request = object
    fastapi_exceptions = ModuleType("fastapi.exceptions")
    fastapi_exceptions.RequestValidationError = type("RequestValidationError", (Exception,), {})
    fastapi_responses = ModuleType("fastapi.responses")
    fastapi_responses.HTMLResponse = str
    fastapi_responses.JSONResponse = JSONResponse
    pydantic = ModuleType("pydantic")
    pydantic.BaseModel = BaseModel
    pydantic.Field = Field
    pydantic.field_validator = field_validator

    spec = importlib.util.spec_from_file_location("frankfurter_app", Path(__file__).with_name("main.py"))
    module = importlib.util.module_from_spec(spec)
    with patch.dict(
        sys.modules,
        {
            "httpx": httpx,
            "fastapi": fastapi,
            "fastapi.exceptions": fastapi_exceptions,
            "fastapi.responses": fastapi_responses,
            "pydantic": pydantic,
        },
    ):
        spec.loader.exec_module(module)
    return module


app = load_app()


class FakeResponse:
    def __init__(self, payload=None, error=None):
        self._payload = payload
        self._error = error

    def raise_for_status(self):
        if self._error is not None:
            raise self._error

    def json(self):
        return self._payload


class FakeClient:
    def __init__(self, payload=None, error=None, **kwargs):
        self.kwargs = kwargs
        self.payload = payload
        self.error = error
        self.requests = []
        self.closed = False

    async def get(self, url, params=None):
        self.requests.append({"url": url, "params": params})
        return FakeResponse(self.payload, self.error)

    async def aclose(self):
        self.closed = True

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        self.closed = True
        return False


class AppTestCase(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        app.app.state.http_client = None

    def tearDown(self):
        app.app.state.http_client = None


class ParseAmountTests(unittest.TestCase):
    def test_accepts_int_float_and_numeric_strings(self):
        self.assertEqual(app._parse_amount(50), Decimal("50"))
        self.assertEqual(app._parse_amount("19.95"), Decimal("19.95"))
        self.assertEqual(app._parse_amount(0.01), Decimal(str(0.01)))

    def test_rejects_zero_and_negative(self):
        for value in (0, -1, "-50.25"):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "greater than 0"):
                app._parse_amount(value)

    def test_rejects_non_numeric(self):
        with self.assertRaisesRegex(ValueError, "amount must be a number"):
            app._parse_amount("not-a-number")

    def test_rejects_non_finite(self):
        for value in ("NaN", "sNaN", "Infinity", "-Infinity", "inf", float("nan"), float("inf")):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "finite"):
                app._parse_amount(value)


class NormalizeCurrencyCodeTests(unittest.TestCase):
    def test_uppercases_and_strips(self):
        self.assertEqual(app._normalize_currency_code("usd"), "USD")
        self.assertEqual(app._normalize_currency_code("  eur\n"), "EUR")

    def test_rejects_malformed_codes(self):
        for value in ("US", "USDD", "U1D", "", "   "):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "3 letters"):
                app._normalize_currency_code(value)


class FormatDecimalTests(unittest.TestCase):
    def test_formats_numeric_values(self):
        self.assertEqual(app._format_decimal(45.5), "45.5")
        self.assertEqual(app._format_decimal(Decimal("39.20")), "39.2")
        self.assertEqual(app._format_decimal(1), "1")
        self.assertEqual(app._format_decimal("0.92500"), "0.925")

    def test_rejects_non_numeric_values(self):
        for value in ("abc", None, {"EUR": 1}, [1, 2]):
            with self.subTest(value=value), self.assertRaises(ValueError):
                app._format_decimal(value)

    def test_rejects_non_finite_values(self):
        for value in ("NaN", "Infinity", "-Infinity"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                app._format_decimal(value)


class RequestJsonTests(AppTestCase):
    async def test_uses_managed_client_when_present(self):
        client = FakeClient(payload={"ok": True})
        app.app.state.http_client = client
        result = await app._request_json("/latest", {"from": "USD"})
        self.assertEqual(result, {"ok": True})
        self.assertEqual(
            client.requests,
            [{"url": "https://api.frankfurter.app/latest", "params": {"from": "USD"}}],
        )

    async def test_allocates_fallback_client_when_state_empty(self):
        created = []

        def factory(**kwargs):
            client = FakeClient(payload={"ok": 1}, **kwargs)
            created.append(client)
            return client

        with patch.object(app.httpx, "AsyncClient", factory):
            result = await app._request_json("/currencies")
        self.assertEqual(result, {"ok": 1})
        self.assertEqual(len(created), 1)
        self.assertIs(app.app.state.http_client, created[0])
        self.assertEqual(created[0].requests[0]["url"], "https://api.frankfurter.app/currencies")

    async def test_reuses_fallback_client_across_calls(self):
        with patch.object(app.httpx, "AsyncClient", lambda **kw: FakeClient(payload={"n": 1})):
            await app._request_json("/latest")
            first = app.app.state.http_client
            await app._request_json("/latest")
            self.assertIs(app.app.state.http_client, first)
            self.assertEqual(len(first.requests), 2)

    async def test_rejects_non_dict_payloads(self):
        for payload in (["not", "a", "dict"], "plain text", 5, None):
            app.app.state.http_client = FakeClient(payload=payload)
            with self.subTest(payload=payload), self.assertRaisesRegex(ValueError, "non-object"):
                await app._request_json("/latest")

    async def test_propagates_http_errors(self):
        app.app.state.http_client = FakeClient(error=app.httpx.HTTPError("boom"))
        with self.assertRaises(app.httpx.HTTPError):
            await app._request_json("/latest")


def make_convert_request(**overrides):
    fields = {"amount": "50", "from_currency": "USD", "to_currencies": ["EUR", "GBP"]}
    fields.update(overrides)
    return app.ConvertCurrencyRequest(**fields)


class ConvertCurrencyTests(AppTestCase):
    async def convert(self, request, payload=None, side_effect=None):
        provider = AsyncMock(return_value=payload, side_effect=side_effect)
        with patch.object(app, "_request_json", provider):
            return await app.convert_currency(request), provider

    async def test_success_formats_all_targets(self):
        payload = {"amount": 50.0, "base": "USD", "date": "2026-09-09", "rates": {"EUR": 45.5, "GBP": 39.2}}
        response, provider = await self.convert(make_convert_request(), payload)
        self.assertIsNone(response.error)
        self.assertIn("50 USD on 2026-09-09:", response.result)
        self.assertIn("- EUR: 45.5", response.result)
        self.assertIn("- GBP: 39.2", response.result)
        provider.assert_awaited_once()
        path, params = provider.call_args[0]
        self.assertEqual(path, "/latest")
        self.assertEqual(params, {"amount": "50", "from": "USD", "to": "EUR,GBP"})

    async def test_missing_or_empty_rates_return_error(self):
        for payload in ({"base": "USD"}, {"base": "USD", "rates": {}}, {"rates": None}):
            response, _ = await self.convert(make_convert_request(), payload)
            with self.subTest(payload=payload):
                self.assertIsNone(response.result)
                self.assertIn("no rates", response.error)

    async def test_non_dict_rates_return_error(self):
        for rates in ("oops", [("EUR", 1)], 5):
            response, _ = await self.convert(make_convert_request(), {"rates": rates})
            with self.subTest(rates=rates):
                self.assertIn("no rates", response.error)

    async def test_invalid_rate_value_returns_error_not_crash(self):
        response, _ = await self.convert(
            make_convert_request(to_currencies=["EUR"]),
            {"base": "USD", "rates": {"EUR": "N/A"}},
        )
        self.assertIsNone(response.result)
        self.assertIn("currency conversion failed", response.error)

    async def test_http_error_returns_error(self):
        response, _ = await self.convert(
            make_convert_request(), side_effect=app.httpx.HTTPError("down")
        )
        self.assertIn("currency conversion failed", response.error)

    async def test_non_dict_payload_returns_error_end_to_end(self):
        app.app.state.http_client = FakeClient(payload=["error", "page"])
        response = await app.convert_currency(make_convert_request(to_currencies=["EUR"]))
        self.assertIsNone(response.result)
        self.assertIn("currency conversion failed", response.error)


class LatestRatesTests(AppTestCase):
    async def test_success_lists_sorted_rates(self):
        provider = AsyncMock(
            return_value={"base": "USD", "date": "2026-09-09", "rates": {"GBP": 0.8, "EUR": 0.9}}
        )
        request = app.LatestRatesRequest(base_currency="USD")
        with patch.object(app, "_request_json", provider):
            response = await app.get_latest_rates(request)
        self.assertIsNone(response.error)
        self.assertIn("Latest USD reference rates for 2026-09-09:", response.result)
        self.assertLess(response.result.index("= 0.9 EUR"), response.result.index("= 0.8 GBP"))

    async def test_empty_or_non_dict_rates_return_error(self):
        for rates in ({}, None, "oops"):
            provider = AsyncMock(return_value={"base": "USD", "rates": rates})
            request = app.LatestRatesRequest(base_currency="USD")
            with patch.object(app, "_request_json", provider):
                response = await app.get_latest_rates(request)
            with self.subTest(rates=rates):
                self.assertIn("no rates returned", response.error)

    async def test_invalid_rate_value_returns_error_not_crash(self):
        provider = AsyncMock(return_value={"base": "USD", "rates": {"EUR": None}})
        request = app.LatestRatesRequest(base_currency="USD", to_currencies=["EUR"])
        with patch.object(app, "_request_json", provider):
            response = await app.get_latest_rates(request)
        self.assertIn("latest rates request failed", response.error)

    async def test_non_dict_payload_returns_error_end_to_end(self):
        app.app.state.http_client = FakeClient(payload="not a dict")
        request = app.LatestRatesRequest(base_currency="USD")
        response = await app.get_latest_rates(request)
        self.assertIn("latest rates request failed", response.error)


class ListSupportedCurrenciesTests(AppTestCase):
    async def test_success_lists_sorted_currencies(self):
        provider = AsyncMock(return_value={"EUR": "Euro", "AUD": "Australian Dollar"})
        with patch.object(app, "_request_json", provider):
            response = await app.list_supported_currencies()
        self.assertIsNone(response.error)
        self.assertIn("Frankfurter supported currencies:", response.result)
        self.assertLess(response.result.index("AUD"), response.result.index("EUR"))
        provider.assert_awaited_once_with("/currencies")

    async def test_empty_mapping_returns_error(self):
        provider = AsyncMock(return_value={})
        with patch.object(app, "_request_json", provider):
            response = await app.list_supported_currencies()
        self.assertIn("no currencies returned", response.error)

    async def test_non_dict_payload_returns_error_end_to_end(self):
        for payload in ([], "error page", None):
            app.app.state.http_client = FakeClient(payload=payload)
            response = await app.list_supported_currencies()
            with self.subTest(payload=payload):
                self.assertIsNone(response.result)
                self.assertIn("currency list request failed", response.error)

    async def test_http_error_returns_error(self):
        app.app.state.http_client = FakeClient(error=app.httpx.HTTPError("down"))
        response = await app.list_supported_currencies()
        self.assertIn("currency list request failed", response.error)


class LifespanTests(AppTestCase):
    async def test_installs_managed_client_and_clears_on_exit(self):
        created = []

        def factory(**kwargs):
            client = FakeClient(**kwargs)
            created.append(client)
            return client

        instance = app.app.__class__()
        with patch.object(app.httpx, "AsyncClient", factory):
            async with app.lifespan(instance):
                self.assertIs(instance.state.http_client, created[0])
            self.assertTrue(created[0].closed)
            self.assertIsNone(instance.state.http_client)

    async def test_closes_preexisting_fallback_client(self):
        fallback = FakeClient()
        managed = FakeClient()
        instance = app.app.__class__()
        instance.state.http_client = fallback
        with patch.object(app.httpx, "AsyncClient", lambda **kw: managed):
            async with app.lifespan(instance):
                self.assertIs(instance.state.http_client, managed)
        self.assertTrue(fallback.closed)
        self.assertTrue(managed.closed)


class SurfaceTests(AppTestCase):
    async def test_tools_manifest_and_health(self):
        manifest = await app.omi_tools()
        self.assertEqual(
            [tool["name"] for tool in manifest["tools"]],
            ["convert_currency", "get_latest_rates", "list_supported_currencies"],
        )
        self.assertEqual(await app.health(), {"status": "ok"})

    async def test_validation_error_handler_returns_tool_error(self):
        class FakeValidationError:
            def errors(self):
                return [{"loc": ("body", "amount"), "msg": "field required"}]

        response = await app.validation_exception_handler(None, FakeValidationError())
        self.assertEqual(response.status_code, 200)
        self.assertIn("amount", response.content["error"])
        self.assertIn("field required", response.content["error"])


if __name__ == "__main__":
    unittest.main()
