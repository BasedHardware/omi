"""Hermetic error handling and exception sanitization tests for CoinGecko Crypto App.

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
from unittest.mock import AsyncMock, Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent))


class Framework:
    def __init__(self, content="", status_code=200, **kwargs):
        self.content = content
        self.status_code = status_code
        self.kwargs = kwargs
        self.state = types.SimpleNamespace()

    def get(self, *args, **kwargs):
        return lambda function: function

    post = get

    def exception_handler(self, *args, **kwargs):
        return lambda function: function


class ChatToolResponseStub:
    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error

    def model_dump(self):
        return {"result": self.result, "error": self.error}


def make_module(name, **attributes):
    value = types.ModuleType(name)
    value.__dict__.update(attributes)
    return value


def load_coingecko_module():
    class HTTPError(Exception):
        pass

    class TimeoutException(Exception):
        pass

    class AsyncClient:
        def __init__(self, *args, **kwargs):
            self.is_closed = False

        async def get(self, *args, **kwargs):
            raise AssertionError("tests must stub the HTTP response")

    httpx_mod = make_module(
        "httpx",
        HTTPError=HTTPError,
        TimeoutException=TimeoutException,
        AsyncClient=AsyncClient,
    )

    class BaseModel:
        def __init__(self, **kwargs):
            for k, v in kwargs.items():
                setattr(self, k, v)

    class GetCryptoPriceRequest(BaseModel):
        coin_ids: str = "bitcoin"
        vs_currency: str = "usd"
        include_market_cap: bool = True
        include_24hr_vol: bool = True
        include_24hr_change: bool = True

    class SearchCryptoCoinsRequest(BaseModel):
        query: str = "btc"
        max_results: int = 5

    class GetTrendingCryptoRequest(BaseModel):
        limit: int = 7

    class GetCryptoMarketOverviewRequest(BaseModel):
        vs_currency: str = "usd"
        limit: int = 10

    models_mod = make_module(
        "models",
        ChatToolResponse=ChatToolResponseStub,
        GetCryptoPriceRequest=GetCryptoPriceRequest,
        SearchCryptoCoinsRequest=SearchCryptoCoinsRequest,
        GetTrendingCryptoRequest=GetTrendingCryptoRequest,
        GetCryptoMarketOverviewRequest=GetCryptoMarketOverviewRequest,
    )

    stubs = {
        "httpx": httpx_mod,
        "fastapi": make_module(
            "fastapi",
            FastAPI=Framework,
            Request=Framework,
        ),
        "fastapi.exceptions": make_module(
            "fastapi.exceptions",
            RequestValidationError=Exception,
        ),
        "fastapi.responses": make_module(
            "fastapi.responses",
            HTMLResponse=Framework,
            JSONResponse=Framework,
        ),
        "models": models_mod,
    }

    spec = importlib.util.spec_from_file_location("coingecko_main_test", Path(__file__).with_name("main.py"))
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, stubs):
        spec.loader.exec_module(module)
    return module


app = load_coingecko_module()


class CoinGeckoErrorHandlingTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.sensitive_leak = "FATAL: /var/secrets/coingecko_pro_key.json: connection reset by 192.168.1.77:443"

    async def test_get_crypto_price_sanitizes_network_error(self):
        req = app.GetCryptoPriceRequest(coin_ids="bitcoin")
        mock_client = Mock()
        mock_client.get = AsyncMock(side_effect=app.httpx.HTTPError(self.sensitive_leak))
        app.app.state.http_client = mock_client
        resp = await app.get_crypto_price(req)
        self.assertEqual(resp.error, "CoinGecko network error occurred.")
        self.assertNotIn(self.sensitive_leak, str(resp.error))
        self.assertNotIn("192.168.1.77", str(resp.error))

    async def test_get_crypto_price_sanitizes_unexpected_exception(self):
        req = app.GetCryptoPriceRequest(coin_ids="bitcoin")
        with patch.object(app, "_fetch_coingecko", side_effect=RuntimeError(self.sensitive_leak)):
            resp = await app.get_crypto_price(req)
            self.assertEqual(resp.error, "Failed to fetch cryptocurrency prices due to an internal error.")
            self.assertNotIn(self.sensitive_leak, str(resp.error))

    async def test_search_crypto_coins_sanitizes_unexpected_exception(self):
        req = app.SearchCryptoCoinsRequest(query="eth")
        with patch.object(app, "_fetch_coingecko", side_effect=RuntimeError(self.sensitive_leak)):
            resp = await app.search_crypto_coins(req)
            self.assertEqual(resp.error, "Failed to search cryptocurrency coins due to an internal error.")
            self.assertNotIn(self.sensitive_leak, str(resp.error))

    async def test_get_trending_crypto_sanitizes_unexpected_exception(self):
        req = app.GetTrendingCryptoRequest(limit=5)
        with patch.object(app, "_fetch_coingecko", side_effect=RuntimeError(self.sensitive_leak)):
            resp = await app.get_trending_crypto(req)
            self.assertEqual(resp.error, "Failed to retrieve trending cryptocurrencies due to an internal error.")
            self.assertNotIn(self.sensitive_leak, str(resp.error))

    async def test_get_crypto_market_overview_sanitizes_unexpected_exception(self):
        req = app.GetCryptoMarketOverviewRequest(vs_currency="usd")
        with patch.object(app, "_fetch_coingecko", side_effect=RuntimeError(self.sensitive_leak)):
            resp = await app.get_crypto_market_overview(req)
            self.assertEqual(resp.error, "Failed to retrieve market overview due to an internal error.")
            self.assertNotIn(self.sensitive_leak, str(resp.error))

    async def test_get_crypto_price_sanitizes_arbitrary_value_error(self):
        req = app.GetCryptoPriceRequest(coin_ids="bitcoin")
        with patch.object(app, "_fetch_coingecko", side_effect=ValueError(self.sensitive_leak)):
            resp = await app.get_crypto_price(req)
            self.assertEqual(resp.error, "Failed to fetch cryptocurrency prices due to an internal error.")
            self.assertNotIn(self.sensitive_leak, str(resp.error))

    async def test_search_crypto_coins_sanitizes_arbitrary_value_error(self):
        req = app.SearchCryptoCoinsRequest(query="eth")
        with patch.object(app, "_fetch_coingecko", side_effect=ValueError(self.sensitive_leak)):
            resp = await app.search_crypto_coins(req)
            self.assertEqual(resp.error, "Failed to search cryptocurrency coins due to an internal error.")
            self.assertNotIn(self.sensitive_leak, str(resp.error))

    async def test_get_trending_crypto_sanitizes_arbitrary_value_error(self):
        req = app.GetTrendingCryptoRequest(limit=5)
        with patch.object(app, "_fetch_coingecko", side_effect=ValueError(self.sensitive_leak)):
            resp = await app.get_trending_crypto(req)
            self.assertEqual(resp.error, "Failed to retrieve trending cryptocurrencies due to an internal error.")
            self.assertNotIn(self.sensitive_leak, str(resp.error))

    async def test_get_crypto_market_overview_sanitizes_arbitrary_value_error(self):
        req = app.GetCryptoMarketOverviewRequest(vs_currency="usd")
        with patch.object(app, "_fetch_coingecko", side_effect=ValueError(self.sensitive_leak)):
            resp = await app.get_crypto_market_overview(req)
            self.assertEqual(resp.error, "Failed to retrieve market overview due to an internal error.")
            self.assertNotIn(self.sensitive_leak, str(resp.error))


if __name__ == "__main__":
    unittest.main()
