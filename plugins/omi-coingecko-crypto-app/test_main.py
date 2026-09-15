"""Hermetic stdlib tests for the CoinGecko crypto app (issue #13935).

Loads the production module with framework-only stubs so the real request
models, payload guards, formatting helpers, and HTTP client fallback paths
execute without network access or third-party packages.
"""

from pathlib import Path
import sys
import types
import unittest
import unittest.mock


# --- Minimal functional stubs for pydantic / fastapi / httpx -----------------


class _FieldInfo:
    """Stand-in for pydantic.Field metadata."""

    def __init__(self, default, constraints):
        self.default = default
        self.required = default is ...
        self.min_length = constraints.get("min_length")
        self.max_length = constraints.get("max_length")
        self.ge = constraints.get("ge")
        self.le = constraints.get("le")


def _field(default=..., **constraints):
    return _FieldInfo(default, constraints)


def _field_validator(*field_names, mode="after"):
    def decorator(func):
        target = getattr(func, "__func__", func)
        configs = getattr(target, "_field_validator_configs", [])
        target._field_validator_configs = configs + [(field_names, mode)]
        return func

    return decorator


def _model_validator(mode="after"):
    def decorator(func):
        target = getattr(func, "__func__", func)
        target._model_validator_mode = mode
        return func

    return decorator


class _BaseModel:
    """Tiny functional subset of pydantic.BaseModel.

    Runs ``mode="before"`` validators before field constraint checks and
    ``mode="after"`` validators afterwards, matching pydantic v2 ordering.
    """

    def __init__(self, **kwargs):
        cls = type(self)
        annotations = {}
        validators = {}
        model_validators = []
        for klass in reversed(cls.__mro__):
            annotations.update(getattr(klass, "__annotations__", {}))
            for name, member in vars(klass).items():
                func = getattr(member, "__func__", member)
                for names, mode in getattr(func, "_field_validator_configs", []):
                    for field_name in names:
                        validators.setdefault(field_name, []).append((mode, name))
                if getattr(func, "_model_validator_mode", None) == "after":
                    model_validators.append(name)
        for field_name, annotation in annotations.items():
            info = getattr(cls, field_name, _FieldInfo(..., {}))
            if field_name in kwargs:
                value = kwargs[field_name]
            elif isinstance(info, _FieldInfo) and info.required:
                raise ValueError(f"{field_name}: field required")
            elif isinstance(info, _FieldInfo):
                value = info.default
            else:
                value = info
            for mode, validator_name in validators.get(field_name, []):
                if mode == "before":
                    value = getattr(cls, validator_name)(value)
            value = self._enforce(field_name, annotation, info, value)
            for mode, validator_name in validators.get(field_name, []):
                if mode == "after":
                    value = getattr(cls, validator_name)(value)
            setattr(self, field_name, value)
        for validator_name in model_validators:
            getattr(self, validator_name)()

    @staticmethod
    def _enforce(field_name, annotation, info, value):
        if annotation is str and not isinstance(value, str):
            raise ValueError(f"{field_name}: Input should be a valid string")
        if annotation is int and not isinstance(value, int):
            try:
                value = int(value)
            except (TypeError, ValueError):
                raise ValueError(f"{field_name}: Input should be a valid integer")
        if isinstance(info, _FieldInfo):
            if isinstance(value, str):
                if info.min_length is not None and len(value) < info.min_length:
                    raise ValueError(f"{field_name}: string shorter than {info.min_length}")
                if info.max_length is not None and len(value) > info.max_length:
                    raise ValueError(f"{field_name}: string longer than {info.max_length}")
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                if info.ge is not None and value < info.ge:
                    raise ValueError(f"{field_name}: less than {info.ge}")
                if info.le is not None and value > info.le:
                    raise ValueError(f"{field_name}: greater than {info.le}")
        return value

    def model_dump(self):
        return dict(vars(self))


class _StubHTTPError(Exception):
    pass


class _StubTimeoutException(_StubHTTPError):
    pass


class _StubResponse:
    def __init__(self, payload=None, status_code=200, text=""):
        self._payload = payload
        self.status_code = status_code
        self.text = text

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise _StubHTTPError(f"HTTP {self.status_code}")


class _FakeClient:
    """Records GET requests; replays per-instance then class-level responses."""

    created = []
    queued = []

    def __init__(self, *args, **kwargs):
        self.kwargs = kwargs
        self.requests = []
        self.responses = []
        _FakeClient.created.append(self)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def get(self, url, params=None):
        self.requests.append((url, params))
        source = self.responses if self.responses else _FakeClient.queued
        if not source:
            raise AssertionError(f"unexpected GET {url}")
        item = source.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


class _StubFastAPI:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.state = types.SimpleNamespace()

    def _route(self, method, path):
        def decorator(func):
            return func

        return decorator

    def get(self, path, **kwargs):
        return self._route("GET", path)

    def post(self, path, **kwargs):
        return self._route("POST", path)

    def exception_handler(self, exc_class):
        return lambda func: func


class _StubJSONResponse:
    def __init__(self, status_code=200, content=None, **kwargs):
        self.status_code = status_code
        self.content = content


def _install_stubs():
    httpx = types.ModuleType("httpx")
    httpx.TimeoutException = _StubTimeoutException
    httpx.HTTPError = _StubHTTPError
    httpx.AsyncClient = _FakeClient

    fastapi = types.ModuleType("fastapi")
    fastapi.FastAPI = _StubFastAPI
    fastapi.Request = type("Request", (), {})
    exceptions = types.ModuleType("fastapi.exceptions")
    exceptions.RequestValidationError = type("RequestValidationError", (Exception,), {})
    fastapi.exceptions = exceptions
    responses = types.ModuleType("fastapi.responses")
    responses.HTMLResponse = str
    responses.JSONResponse = _StubJSONResponse
    fastapi.responses = responses

    pydantic = types.ModuleType("pydantic")
    pydantic.BaseModel = _BaseModel
    pydantic.Field = _field
    pydantic.field_validator = _field_validator
    pydantic.model_validator = _model_validator

    sys.modules.update(
        {
            "httpx": httpx,
            "fastapi": fastapi,
            "fastapi.exceptions": exceptions,
            "fastapi.responses": responses,
            "pydantic": pydantic,
        }
    )


_install_stubs()
sys.path.insert(0, str(Path(__file__).resolve().parent))

import main  # noqa: E402
import models  # noqa: E402


# --- Request model tests ------------------------------------------------------


class RequestModelTests(unittest.TestCase):
    def test_vs_currency_whitespace_stripped_before_length_check(self):
        req = models.GetCryptoPriceRequest(coin_ids="bitcoin", vs_currency="      eur      ")
        self.assertEqual(req.vs_currency, "eur")

    def test_vs_currency_blank_rejected(self):
        with self.assertRaises(ValueError):
            models.GetCryptoPriceRequest(coin_ids="bitcoin", vs_currency="   ")

    def test_vs_currency_non_string_rejected_cleanly(self):
        with self.assertRaises(ValueError):
            models.GetCryptoPriceRequest(coin_ids="bitcoin", vs_currency=123)

    def test_coin_ids_string_normalized_and_deduped(self):
        req = models.GetCryptoPriceRequest(coin_ids=" Bitcoin ,ETH,bitcoin ")
        self.assertEqual(req.coin_ids, ["bitcoin", "eth"])

    def test_coin_ids_empty_rejected(self):
        with self.assertRaises(ValueError):
            models.GetCryptoPriceRequest(coin_ids=" , ,")

    def test_query_whitespace_stripped_before_length_check(self):
        req = models.SearchCryptoCoinsRequest(query="  " + "sol" + "  ", max_results=3)
        self.assertEqual(req.query, "sol")

    def test_query_blank_rejected(self):
        with self.assertRaises(ValueError):
            models.SearchCryptoCoinsRequest(query="   ")

    def test_market_overview_limit_bounds(self):
        with self.assertRaises(ValueError):
            models.GetCryptoMarketOverviewRequest(limit=25)

    def test_chat_tool_response_requires_exactly_one_field(self):
        with self.assertRaises(ValueError):
            models.ChatToolResponse()
        with self.assertRaises(ValueError):
            models.ChatToolResponse(result="a", error="b")
        self.assertEqual(models.ChatToolResponse(result="ok").result, "ok")


# --- Formatting helper tests --------------------------------------------------


class FormatHelperTests(unittest.TestCase):
    def test_format_currency_coerces_numeric_strings(self):
        self.assertEqual(main._format_currency("65000"), "$65,000.00")
        self.assertEqual(main._format_currency("0.00000042"), "$0.00000042")

    def test_format_currency_non_numeric_falls_back(self):
        self.assertEqual(main._format_currency("abc"), "N/A")
        self.assertEqual(main._format_currency(None), "N/A")
        self.assertEqual(main._format_currency(0), "$0.00")

    def test_format_compact_coerces_numeric_strings(self):
        self.assertEqual(main._format_compact("1500000"), "$1.50M")
        self.assertEqual(main._format_compact(2_500_000_000), "$2.50B")

    def test_format_compact_non_numeric_falls_back(self):
        self.assertEqual(main._format_compact("oops"), "N/A")
        self.assertEqual(main._format_compact(None), "N/A")

    def test_format_percentage_coerces_numeric_strings(self):
        self.assertEqual(main._format_percentage("1.5"), "+1.50%")
        self.assertEqual(main._format_percentage(-2.25), "-2.25%")

    def test_format_percentage_non_numeric_falls_back(self):
        self.assertEqual(main._format_percentage("up"), "N/A")
        self.assertEqual(main._format_percentage(None), "N/A")


# --- Endpoint handler tests ---------------------------------------------------


def _price_payload():
    return {
        "bitcoin": {
            "usd": 65000,
            "usd_24h_change": 1.5,
            "usd_market_cap": 1.25e12,
            "usd_24h_vol": 4.2e10,
        }
    }


def _markets_payload():
    return [
        {
            "market_cap_rank": 1,
            "name": "Bitcoin",
            "symbol": "btc",
            "current_price": 65000,
            "price_change_percentage_24h": 1.5,
            "market_cap": 1.25e12,
        },
        "corrupted-entry",
    ]


class EndpointTests(unittest.IsolatedAsyncioTestCase):
    async def _run(self, coroutine_factory, payload):
        async def fake_fetch(endpoint, params=None):
            return payload

        with unittest.mock.patch.object(main, "_fetch_coingecko", fake_fetch):
            return await coroutine_factory()

    async def test_market_overview_dict_error_payload_returns_clean_error(self):
        payload = {"status": {"error_code": 429, "error_message": "rate limited"}}
        response = await self._run(
            lambda: main.get_crypto_market_overview(models.GetCryptoMarketOverviewRequest()), payload
        )
        self.assertIsNone(response.result)
        self.assertEqual(response.error, "Failed to retrieve cryptocurrency market rankings.")

    async def test_market_overview_error_key_payload_returns_clean_error(self):
        response = await self._run(
            lambda: main.get_crypto_market_overview(models.GetCryptoMarketOverviewRequest()),
            {"error": "invalid vs_currency"},
        )
        self.assertIsNone(response.result)
        self.assertEqual(response.error, "Failed to retrieve cryptocurrency market rankings.")

    async def test_market_overview_list_renders_and_skips_bad_entries(self):
        response = await self._run(
            lambda: main.get_crypto_market_overview(models.GetCryptoMarketOverviewRequest()),
            _markets_payload(),
        )
        self.assertIsNone(response.error)
        self.assertIn("1. Bitcoin (BTC): $65,000.00 (24h: +1.50%) | MCap: $1.25T", response.result)

    async def test_get_crypto_price_non_dict_payload_clean_error(self):
        response = await self._run(
            lambda: main.get_crypto_price(models.GetCryptoPriceRequest(coin_ids="bitcoin")),
            ["unexpected", "list"],
        )
        self.assertIsNone(response.result)
        self.assertIn("No pricing data found", response.error)

    async def test_get_crypto_price_non_dict_coin_entry_not_found(self):
        response = await self._run(
            lambda: main.get_crypto_price(models.GetCryptoPriceRequest(coin_ids="bitcoin")),
            {"bitcoin": "corrupted"},
        )
        self.assertIsNone(response.error)
        self.assertIn("- bitcoin: Not found", response.result)

    async def test_get_crypto_price_happy_path(self):
        response = await self._run(
            lambda: main.get_crypto_price(models.GetCryptoPriceRequest(coin_ids="bitcoin")),
            _price_payload(),
        )
        self.assertIsNone(response.error)
        self.assertIn("Bitcoin (bitcoin): $65,000.00 | 24h: +1.50%", response.result)
        self.assertIn("MCap: $1.25T", response.result)

    async def test_search_crypto_coins_non_dict_payload_clean_error(self):
        response = await self._run(
            lambda: main.search_crypto_coins(models.SearchCryptoCoinsRequest(query="sol")),
            "corrupted",
        )
        self.assertIsNone(response.result)
        self.assertIsNotNone(response.error)

    async def test_search_crypto_coins_skips_non_dict_entries(self):
        payload = {
            "coins": [
                "garbage",
                {"name": "Solana", "symbol": "sol", "id": "solana", "market_cap_rank": 5},
            ]
        }
        response = await self._run(
            lambda: main.search_crypto_coins(models.SearchCryptoCoinsRequest(query="sol")),
            payload,
        )
        self.assertIsNone(response.error)
        self.assertIn("1. Solana (SOL) - Rank #5 | ID: solana", response.result)

    async def test_trending_string_price_btc_does_not_crash(self):
        payload = {
            "coins": [
                {
                    "item": {
                        "name": "Pepe",
                        "symbol": "pepe",
                        "id": "pepe",
                        "market_cap_rank": 3,
                        "price_btc": "0.00000042",
                    }
                }
            ]
        }
        response = await self._run(
            lambda: main.get_trending_crypto(models.GetTrendingCryptoRequest()),
            payload,
        )
        self.assertIsNone(response.error)
        self.assertIn("Pepe (PEPE) - Rank #3 | 0.00000042 BTC | ID: pepe", response.result)

    async def test_trending_non_dict_payload_clean_error(self):
        response = await self._run(
            lambda: main.get_trending_crypto(models.GetTrendingCryptoRequest()),
            ["not", "a", "dict"],
        )
        self.assertIsNone(response.result)
        self.assertIsNotNone(response.error)

    async def test_trending_skips_malformed_wrappers(self):
        payload = {
            "coins": [
                "junk",
                {"item": "oops"},
                {"item": {"name": "Doge", "symbol": "doge", "id": "dogecoin"}},
            ]
        }
        response = await self._run(
            lambda: main.get_trending_crypto(models.GetTrendingCryptoRequest()),
            payload,
        )
        self.assertIsNone(response.error)
        self.assertIn("Doge (DOGE)", response.result)


# --- HTTP client fallback tests ------------------------------------------------


class FetchClientTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        _FakeClient.created = []
        _FakeClient.queued = []
        if hasattr(main.app.state, "http_client"):
            del main.app.state.http_client

    async def test_fetch_falls_back_to_transient_client_without_lifespan(self):
        _FakeClient.queued = [_StubResponse({"bitcoin": {"usd": 1}})]
        data = await main._fetch_coingecko("/simple/price", params={"ids": "bitcoin"})
        self.assertEqual(data, {"bitcoin": {"usd": 1}})
        self.assertEqual(len(_FakeClient.created), 1)
        self.assertTrue(_FakeClient.created[0].requests[0][0].endswith("/simple/price"))

    async def test_fetch_uses_lifespan_client_when_present(self):
        client = _FakeClient()
        client.responses = [_StubResponse({"ok": True})]
        main.app.state.http_client = client
        _FakeClient.created = []
        data = await main._fetch_coingecko("/ping")
        self.assertEqual(data, {"ok": True})
        self.assertEqual(len(_FakeClient.created), 0)
        self.assertEqual(len(client.requests), 1)

    async def test_fetch_rate_limit_raises_clean_value_error(self):
        client = _FakeClient()
        client.responses = [_StubResponse(status_code=429)]
        main.app.state.http_client = client
        with self.assertRaises(ValueError) as ctx:
            await main._fetch_coingecko("/simple/price")
        self.assertIn("rate limit", str(ctx.exception))

    async def test_fetch_timeout_raises_clean_value_error(self):
        client = _FakeClient()
        client.responses = [_StubTimeoutException("slow")]
        main.app.state.http_client = client
        with self.assertRaises(ValueError) as ctx:
            await main._fetch_coingecko("/simple/price")
        self.assertIn("timed out", str(ctx.exception))

    async def test_lifespan_populates_state_client(self):
        async with main.lifespan(main.app):
            self.assertIsInstance(main.app.state.http_client, _FakeClient)
        del main.app.state.http_client


if __name__ == "__main__":
    unittest.main()
