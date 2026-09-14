"""Hermetic unit tests for Omi CoinGecko Crypto Integration App.

Runs with standard library unittest and hermetic stubs without requiring
external dependencies or live network access.
"""

import asyncio
import importlib.util
import os
import sys
import types
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))


def load_app_modules(force_stubs: bool = False):
    """Load models and main modules hermetically without contaminating sys.modules."""
    stubs = {}

    if not force_stubs:
        try:
            import pydantic
        except (ImportError, ModuleNotFoundError):
            pydantic = None
    else:
        pydantic = None

    if pydantic is None:
        pydantic_mod = types.ModuleType("pydantic")

        class FieldInfoStub:
            def __init__(self, default=..., **kwargs):
                self.default = default
                self.ge = kwargs.get("ge")
                self.le = kwargs.get("le")
                self.gt = kwargs.get("gt")
                self.lt = kwargs.get("lt")
                self.min_length = kwargs.get("min_length")
                self.max_length = kwargs.get("max_length")

        class BaseModelStub:
            def __init__(self, **data):
                annotations = getattr(self.__class__, "__annotations__", {})
                for fname in annotations:
                    if fname not in data and hasattr(self.__class__, fname):
                        attr_val = getattr(self.__class__, fname)
                        if isinstance(attr_val, FieldInfoStub):
                            if attr_val.default is not ...:
                                data[fname] = attr_val.default
                            else:
                                raise ValueError(f"Field '{fname}' is required.")
                        else:
                            data[fname] = attr_val

                for k, v in data.items():
                    setattr(self, k, v)

                # Pre-field validators
                for attr_name in dir(self.__class__):
                    attr = getattr(self.__class__, attr_name)
                    func = getattr(attr, "__func__", attr)
                    if getattr(func, "_is_field_val", False):
                        target_field = getattr(func, "_target_field")
                        if hasattr(self, target_field):
                            try:
                                val = attr(getattr(self, target_field))
                            except TypeError:
                                val = func(self.__class__, getattr(self, target_field))
                            setattr(self, target_field, val)

                # Enforce constraints
                for fname in annotations:
                    if hasattr(self.__class__, fname):
                        attr_val = getattr(self.__class__, fname)
                        if isinstance(attr_val, FieldInfoStub):
                            val = getattr(self, fname, None)
                            if val is not None:
                                if attr_val.ge is not None and val < attr_val.ge:
                                    raise ValueError(f"{fname} must be >= {attr_val.ge}")
                                if attr_val.le is not None and val > attr_val.le:
                                    raise ValueError(f"{fname} must be <= {attr_val.le}")
                                if attr_val.min_length is not None and len(val) < attr_val.min_length:
                                    raise ValueError(f"{fname} minimum length is {attr_val.min_length}")
                                if attr_val.max_length is not None and len(val) > attr_val.max_length:
                                    raise ValueError(f"{fname} maximum length is {attr_val.max_length}")

                # Model validators
                for attr_name in dir(self.__class__):
                    attr = getattr(self.__class__, attr_name)
                    func = getattr(attr, "__func__", attr)
                    if getattr(func, "_is_model_val", False):
                        try:
                            attr(self)
                        except TypeError:
                            func(self)

            def model_dump(self):
                return {k: v for k, v in self.__dict__.items() if not k.startswith("_")}

        def field_validator_stub(*fields, mode=None):
            def decorator(fn):
                actual_fn = getattr(fn, "__func__", fn)
                actual_fn._is_field_val = True
                actual_fn._target_field = fields[0]
                actual_fn._mode = mode
                return fn
            return decorator

        def model_validator_stub(mode="after"):
            def decorator(fn):
                actual_fn = getattr(fn, "__func__", fn)
                actual_fn._is_model_val = True
                actual_fn._mode = mode
                return fn
            return decorator

        def field_stub(default=..., **kwargs):
            return FieldInfoStub(default, **kwargs)

        pydantic_mod.BaseModel = BaseModelStub
        pydantic_mod.Field = field_stub
        pydantic_mod.field_validator = field_validator_stub
        pydantic_mod.model_validator = model_validator_stub
        stubs["pydantic"] = pydantic_mod

    if not force_stubs:
        try:
            import fastapi
            import fastapi.exceptions
            import fastapi.responses
        except (ImportError, ModuleNotFoundError):
            fastapi = None
    else:
        fastapi = None

    if fastapi is None:
        fastapi_mod = types.ModuleType("fastapi")

        class StateStub:
            pass

        class FastAPIStub:
            def __init__(self, **kwargs):
                self.state = StateStub()
                self.routes = {}

            def get(self, path, **kwargs):
                def decorator(fn):
                    self.routes[("GET", path)] = fn
                    return fn
                return decorator

            def post(self, path, **kwargs):
                def decorator(fn):
                    self.routes[("POST", path)] = fn
                    return fn
                return decorator

            def exception_handler(self, exc_cls):
                def decorator(fn):
                    return fn
                return decorator

        class RequestValidationErrorStub(Exception):
            def __init__(self, errors=None):
                self._errors = errors or []

            def errors(self):
                return self._errors

        fastapi_mod.FastAPI = FastAPIStub
        fastapi_mod.Request = MagicMock
        fastapi_mod.HTTPException = Exception
        fastapi_exceptions = types.ModuleType("fastapi.exceptions")
        fastapi_exceptions.RequestValidationError = RequestValidationErrorStub
        fastapi_mod.exceptions = fastapi_exceptions
        fastapi_responses = types.ModuleType("fastapi.responses")

        class JSONResponseStub:
            def __init__(self, content=None, status_code=200):
                self.content = content
                self.status_code = status_code

        class HTMLResponseStub:
            pass

        fastapi_responses.JSONResponse = JSONResponseStub
        fastapi_responses.HTMLResponse = HTMLResponseStub
        fastapi_mod.responses = fastapi_responses

        stubs["fastapi"] = fastapi_mod
        stubs["fastapi.exceptions"] = fastapi_exceptions
        stubs["fastapi.responses"] = fastapi_responses

    if not force_stubs:
        try:
            import httpx
        except (ImportError, ModuleNotFoundError):
            httpx = None
    else:
        httpx = None

    if httpx is None:
        httpx_mod = types.ModuleType("httpx")

        class HTTPErrorStub(Exception):
            pass

        class TimeoutExceptionStub(HTTPErrorStub):
            pass

        class AsyncClientStub:
            def __init__(self, **kwargs):
                self.is_closed = False

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                self.is_closed = True

            async def get(self, url, **kwargs):
                resp = MagicMock()
                resp.status_code = 200
                resp.json.return_value = {}
                return resp

        httpx_mod.AsyncClient = AsyncClientStub
        httpx_mod.HTTPError = HTTPErrorStub
        httpx_mod.TimeoutException = TimeoutExceptionStub
        stubs["httpx"] = httpx_mod

    with patch.dict(sys.modules, stubs):
        models_path = os.path.join(PLUGIN_DIR, "models.py")
        models_spec = importlib.util.spec_from_file_location("models", models_path)
        models_mod = importlib.util.module_from_spec(models_spec)
        models_spec.loader.exec_module(models_mod)

        with patch.dict(sys.modules, {"models": models_mod}):
            main_path = os.path.join(PLUGIN_DIR, "main.py")
            main_spec = importlib.util.spec_from_file_location("main", main_path)
            main_mod = importlib.util.module_from_spec(main_spec)
            main_spec.loader.exec_module(main_mod)

    return main_mod, models_mod


class TestCoinGeckoApp(unittest.TestCase):
    """Test suite for CoinGecko crypto integration endpoints and helpers."""

    @classmethod
    def setUpClass(cls):
        cls.main, cls.models = load_app_modules()

    def setUp(self):
        self.mock_client = AsyncMock()
        self.mock_client.is_closed = False
        self.main.app.state.http_client = self.mock_client

    def test_health_endpoint(self):
        """Verify health check returns ok status."""
        res = asyncio.run(self.main.health())
        self.assertEqual(res["status"], "ok")
        self.assertEqual(res["service"], "omi-coingecko-crypto-app")

    def test_omi_tools_manifest(self):
        """Verify manifest contains all four declared tools."""
        manifest = asyncio.run(self.main.omi_tools())
        self.assertEqual(manifest["schema_version"], "1.0")
        tool_names = [t["name"] for t in manifest["tools"]]
        self.assertIn("get_crypto_price", tool_names)
        self.assertIn("search_crypto_coins", tool_names)
        self.assertIn("get_trending_crypto", tool_names)
        self.assertIn("get_crypto_market_overview", tool_names)

    def test_format_helpers(self):
        """Verify numerical formatters handle extremes, zeros, None, and strings defensively."""
        self.assertEqual(self.main._format_currency(None), "N/A")
        self.assertEqual(self.main._format_currency(0), "$0.00")
        self.assertEqual(self.main._format_currency(50000.5), "$50,000.50")
        self.assertEqual(self.main._format_currency(0.00005), "$0.00005000")
        self.assertEqual(self.main._format_currency("invalid"), "$invalid")

        self.assertEqual(self.main._format_compact(None), "N/A")
        self.assertEqual(self.main._format_compact(0), "N/A")
        self.assertEqual(self.main._format_compact(2.5e12), "$2.50T")
        self.assertEqual(self.main._format_compact(1.2e9), "$1.20B")
        self.assertEqual(self.main._format_compact(45.6e6), "$45.60M")
        self.assertEqual(self.main._format_compact(3.5e3), "$3.50K")
        self.assertEqual(self.main._format_compact("abc"), "$abc")

        self.assertEqual(self.main._format_percentage(None), "N/A")
        self.assertEqual(self.main._format_percentage(5.25), "+5.25%")
        self.assertEqual(self.main._format_percentage(-3.1), "-3.10%")
        self.assertEqual(self.main._format_percentage("bad"), "bad%")

    def test_get_crypto_price_success(self):
        """Verify successful price lookup for multiple coins."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "bitcoin": {
                "usd": 65432.10,
                "usd_24h_change": 2.45,
                "usd_market_cap": 1280000000000.0,
                "usd_24h_vol": 35000000000.0,
            },
            "ethereum": {
                "usd": 3450.75,
                "usd_24h_change": -1.20,
                "usd_market_cap": 415000000000.0,
                "usd_24h_vol": 18000000000.0,
            },
        }
        self.mock_client.get.return_value = mock_resp

        req = self.models.GetCryptoPriceRequest(coin_ids=["bitcoin", "ethereum"], vs_currency="usd")
        resp = asyncio.run(self.main.get_crypto_price(req))

        self.assertIsNone(resp.error)
        self.assertIsNotNone(resp.result)
        self.assertIn("Bitcoin (bitcoin): $65,432.10", resp.result)
        self.assertIn("Ethereum (ethereum): $3,450.75", resp.result)

    def test_get_crypto_price_missing_coin(self):
        """Verify graceful reporting when coin is absent from response."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "bitcoin": {
                "usd": 65000,
                "usd_24h_change": 1.0,
                "usd_market_cap": 1e12,
                "usd_24h_vol": 1e10,
            }
        }
        self.mock_client.get.return_value = mock_resp

        req = self.models.GetCryptoPriceRequest(coin_ids=["bitcoin", "unknown-token"], vs_currency="usd")
        resp = asyncio.run(self.main.get_crypto_price(req))

        self.assertIsNone(resp.error)
        self.assertIn("Bitcoin (bitcoin): $65,000.00", resp.result)
        self.assertIn("- unknown-token: Not found", resp.result)

    def test_get_crypto_price_non_dict_payload(self):
        """Verify non-dict API response returns clean error rather than crashing."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = ["unexpected", "list"]
        self.mock_client.get.return_value = mock_resp

        req = self.models.GetCryptoPriceRequest(coin_ids=["bitcoin"], vs_currency="usd")
        resp = asyncio.run(self.main.get_crypto_price(req))

        self.assertIsNotNone(resp.error)
        self.assertIn("No pricing data found", resp.error)

    def test_search_crypto_coins_success(self):
        """Verify successful coin search."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "coins": [
                {"name": "Solana", "symbol": "sol", "id": "solana", "market_cap_rank": 5},
                {"name": "Solanium", "symbol": "slim", "id": "solanium", "market_cap_rank": 850},
            ]
        }
        self.mock_client.get.return_value = mock_resp

        req = self.models.SearchCryptoCoinsRequest(query="sol", max_results=2)
        resp = asyncio.run(self.main.search_crypto_coins(req))

        self.assertIsNone(resp.error)
        self.assertIn("1. Solana (SOL) - Rank #5 | ID: solana", resp.result)
        self.assertIn("2. Solanium (SLIM) - Rank #850 | ID: solanium", resp.result)

    def test_search_crypto_coins_empty(self):
        """Verify empty search results."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"coins": []}
        self.mock_client.get.return_value = mock_resp

        req = self.models.SearchCryptoCoinsRequest(query="nonexistenttoken12345")
        resp = asyncio.run(self.main.search_crypto_coins(req))

        self.assertIsNone(resp.error)
        self.assertIn("No cryptocurrency coins matched query", resp.result)

    def test_search_crypto_coins_non_dict_error(self):
        """Verify non-dict response returns clean error."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = "invalid text"
        self.mock_client.get.return_value = mock_resp

        req = self.models.SearchCryptoCoinsRequest(query="btc")
        resp = asyncio.run(self.main.search_crypto_coins(req))

        self.assertIsNotNone(resp.error)
        self.assertIn("Unexpected response", resp.error)

    def test_get_trending_crypto_success(self):
        """Verify trending coins with string price_btc formatting."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "coins": [
                {
                    "item": {
                        "name": "Pepe",
                        "symbol": "pepe",
                        "id": "pepe",
                        "market_cap_rank": 25,
                        "price_btc": "0.00000012",
                    }
                },
                {
                    "item": {
                        "name": "Dogecoin",
                        "symbol": "doge",
                        "id": "dogecoin",
                        "market_cap_rank": 8,
                        "price_btc": 0.0000025,
                    }
                },
            ]
        }
        self.mock_client.get.return_value = mock_resp

        req = self.models.GetTrendingCryptoRequest(limit=5)
        resp = asyncio.run(self.main.get_trending_crypto(req))

        self.assertIsNone(resp.error)
        self.assertIn("1. Pepe (PEPE) - Rank #25 | 0.00000012 BTC | ID: pepe", resp.result)
        self.assertIn("2. Dogecoin (DOGE) - Rank #8 | 0.00000250 BTC | ID: dogecoin", resp.result)

    def test_get_crypto_market_overview_success(self):
        """Verify successful market overview."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = [
            {
                "market_cap_rank": 1,
                "name": "Bitcoin",
                "symbol": "btc",
                "current_price": 65000.0,
                "price_change_percentage_24h": 3.2,
                "market_cap": 1280000000000.0,
            },
            {
                "market_cap_rank": 2,
                "name": "Ethereum",
                "symbol": "eth",
                "current_price": 3500.0,
                "price_change_percentage_24h": -0.8,
                "market_cap": 420000000000.0,
            },
        ]
        self.mock_client.get.return_value = mock_resp

        req = self.models.GetCryptoMarketOverviewRequest(limit=2, vs_currency="usd")
        resp = asyncio.run(self.main.get_crypto_market_overview(req))

        self.assertIsNone(resp.error)
        self.assertIn("Top 2 Cryptocurrencies by Market Cap (USD):", resp.result)
        self.assertIn("1. Bitcoin (BTC): $65,000.00 (24h: +3.20%) | MCap: $1.28T", resp.result)

    def test_get_crypto_market_overview_error_dict_regression(self):
        """Regression test: CoinGecko dict error payload must not cause AttributeError: 'str' object has no attribute 'get'."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "status": {
                "error_code": 429,
                "error_message": "You've exceeded the Rate Limit of 30 requests/minute.",
            }
        }
        self.mock_client.get.return_value = mock_resp

        req = self.models.GetCryptoMarketOverviewRequest(limit=10, vs_currency="usd")
        resp = asyncio.run(self.main.get_crypto_market_overview(req))

        self.assertIsNotNone(resp.error)
        self.assertIn("Rate Limit", resp.error)

    def test_lifespan_http_client_fallback(self):
        """Verify fallback when app.state.http_client is None."""
        self.main.app.state.http_client = None

        mock_inst = AsyncMock()
        mock_inst.is_closed = False
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"coins": []}
        mock_inst.get.return_value = mock_resp

        with patch.object(self.main.httpx, "AsyncClient") as mock_cls:
            mock_cls.return_value.__aenter__.return_value = mock_inst

            req = self.models.SearchCryptoCoinsRequest(query="eth")
            resp = asyncio.run(self.main.search_crypto_coins(req))

            self.assertIsNone(resp.error)
            self.assertIn("No cryptocurrency coins matched query", resp.result)

    def test_lifespan_http_client_closed_fallback(self):
        """Verify fallback client is spawned and used when app.state.http_client.is_closed is True."""
        closed_client = MagicMock()
        closed_client.is_closed = True
        self.main.app.state.http_client = closed_client

        mock_inst = AsyncMock()
        mock_inst.is_closed = False
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"coins": []}
        mock_inst.get.return_value = mock_resp

        with patch.object(self.main.httpx, "AsyncClient") as mock_cls:
            mock_cls.return_value.__aenter__.return_value = mock_inst

            req = self.models.SearchCryptoCoinsRequest(query="sol")
            resp = asyncio.run(self.main.search_crypto_coins(req))

            self.assertIsNone(resp.error)
            self.assertIn("No cryptocurrency coins matched query", resp.result)
            mock_cls.assert_called_once()
            mock_inst.get.assert_called_once()

    def test_get_crypto_price_empty_coin_object(self):
        """Verify coin mapping with empty object {} is reported as not found instead of all-N/A."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "bitcoin": {},
        }
        self.mock_client.get.return_value = mock_resp

        req = self.models.GetCryptoPriceRequest(coin_ids=["bitcoin"], vs_currency="usd")
        resp = asyncio.run(self.main.get_crypto_price(req))

        self.assertIsNone(resp.error)
        self.assertIn("- bitcoin: Not found (try searching with search_crypto_coins)", resp.result)
        self.assertNotIn("N/A | 24h: N/A", resp.result)

    def test_malformed_entries_filtered_before_slicing(self):
        """Verify non-dict entries in list payloads are filtered before slicing and numbering."""
        # Search: malformed entries skipped, valid entry gets index 1
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "coins": [None, "invalid", {"name": "Ethereum", "symbol": "eth", "id": "ethereum", "market_cap_rank": 2}]
        }
        self.mock_client.get.return_value = mock_resp

        req_search = self.models.SearchCryptoCoinsRequest(query="eth", max_results=1)
        resp_search = asyncio.run(self.main.search_crypto_coins(req_search))
        self.assertIsNone(resp_search.error)
        self.assertIn("1. Ethereum (ETH) - Rank #2 | ID: ethereum", resp_search.result)

        # All malformed search returns no-match message
        mock_resp.json.return_value = {"coins": [None, 123]}
        resp_empty_search = asyncio.run(self.main.search_crypto_coins(req_search))
        self.assertEqual(resp_empty_search.result, "No cryptocurrency coins matched query 'eth'.")

        # Trending: malformed entries skipped
        mock_resp.json.return_value = {
            "coins": ["malformed", {"item": "not-a-dict"}, {"item": {"name": "Solana", "symbol": "sol", "id": "solana"}}]
        }
        req_trending = self.models.GetTrendingCryptoRequest(limit=1)
        resp_trending = asyncio.run(self.main.get_trending_crypto(req_trending))
        self.assertIsNone(resp_trending.error)
        self.assertIn("1. Solana (SOL)", resp_trending.result)

        # All malformed trending returns no-data response
        mock_resp.json.return_value = {"coins": ["bad1", "bad2"]}
        resp_empty_trending = asyncio.run(self.main.get_trending_crypto(req_trending))
        self.assertEqual(resp_empty_trending.result, "No trending coins available right now.")

        # Market overview: malformed entries skipped
        mock_resp.json.return_value = [
            None,
            "corrupt",
            {"name": "Bitcoin", "symbol": "btc", "market_cap_rank": 1, "current_price": 65000, "price_change_percentage_24h": 2.0, "market_cap": 1e12},
        ]
        req_market = self.models.GetCryptoMarketOverviewRequest(limit=5, vs_currency="usd")
        resp_market = asyncio.run(self.main.get_crypto_market_overview(req_market))
        self.assertIsNone(resp_market.error)
        self.assertIn("Top 1 Cryptocurrencies by Market Cap (USD):", resp_market.result)

        # All malformed market overview returns no-data response
        mock_resp.json.return_value = [None, 999]
        resp_empty_market = asyncio.run(self.main.get_crypto_market_overview(req_market))
        self.assertEqual(resp_empty_market.result, "No market data returned for the requested parameters.")

    def test_models_normalization_and_validation(self):
        """Verify whitespace normalization and strict rejection across Pydantic models."""
        req1 = self.models.GetCryptoPriceRequest(
            coin_ids="  bitcoin ,  ethereum, bitcoin  ",
            vs_currency="  eur  ",
        )
        self.assertEqual(req1.coin_ids, ["bitcoin", "ethereum"])
        self.assertEqual(req1.vs_currency, "eur")

        # Non-string element in coin_ids list must be rejected
        with self.assertRaises(ValueError):
            self.models.GetCryptoPriceRequest(coin_ids=["bitcoin", 123])

        # Whitespace-only element in coin_ids must be rejected
        with self.assertRaises(ValueError):
            self.models.GetCryptoPriceRequest(coin_ids=["bitcoin", "   "])

        req2 = self.models.SearchCryptoCoinsRequest(query="  solana  ")
        self.assertEqual(req2.query, "solana")

        with self.assertRaises(ValueError):
            self.models.SearchCryptoCoinsRequest(query="   ")

        # Search constraints
        with self.assertRaises(ValueError):
            self.models.SearchCryptoCoinsRequest(query="sol", max_results=0)
        with self.assertRaises(ValueError):
            self.models.SearchCryptoCoinsRequest(query="sol", max_results=20)

        # Trending constraints
        with self.assertRaises(ValueError):
            self.models.GetTrendingCryptoRequest(limit=0)
        with self.assertRaises(ValueError):
            self.models.GetTrendingCryptoRequest(limit=25)

        # Market overview constraints
        req3 = self.models.GetCryptoMarketOverviewRequest(vs_currency="  gbp  ")
        self.assertEqual(req3.vs_currency, "gbp")

        with self.assertRaises(ValueError):
            self.models.GetCryptoMarketOverviewRequest(limit=0)
        with self.assertRaises(ValueError):
            self.models.GetCryptoMarketOverviewRequest(limit=50)

    def test_hermetic_stubs_enforce_constraints(self):
        """Verify hermetic fallback stubs enforce constraints identically when pydantic is absent."""
        _, stub_models = load_app_modules(force_stubs=True)

        # Valid instantiation
        req = stub_models.SearchCryptoCoinsRequest(query="btc", max_results=5)
        self.assertEqual(req.query, "btc")
        self.assertEqual(req.max_results, 5)

        # Rejection of invalid constraints
        with self.assertRaises(ValueError):
            stub_models.SearchCryptoCoinsRequest(query="btc", max_results=0)
        with self.assertRaises(ValueError):
            stub_models.SearchCryptoCoinsRequest(query="btc", max_results=20)
        with self.assertRaises(ValueError):
            stub_models.GetTrendingCryptoRequest(limit=0)
        with self.assertRaises(ValueError):
            stub_models.GetTrendingCryptoRequest(limit=25)
        with self.assertRaises(ValueError):
            stub_models.GetCryptoMarketOverviewRequest(limit=0)
        with self.assertRaises(ValueError):
            stub_models.GetCryptoMarketOverviewRequest(limit=50)
        with self.assertRaises(ValueError):
            stub_models.GetCryptoPriceRequest(coin_ids=["bitcoin", 123])
        with self.assertRaises(ValueError):
            stub_models.GetCryptoPriceRequest(coin_ids=["bitcoin", "  "])


if __name__ == "__main__":
    unittest.main()
