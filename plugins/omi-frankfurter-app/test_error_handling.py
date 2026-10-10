"""Hermetic error handling and exception sanitization tests for Frankfurter App.

Verifies that internal exceptions, system paths, private IPs, sensitive tokens,
and raw tracebacks never leak into chat tool responses.
Runs under standard library unittest without external network dependencies.
"""

import asyncio
from decimal import Decimal
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import AsyncMock, patch


class DummyState:
    pass


class DummyFastAPI:
    def __init__(self, **kwargs):
        self.routes = []
        self.lifespan = kwargs.get("lifespan")
        self.state = DummyState()

    def get(self, path, **kwargs):
        return lambda func: func

    post = get

    def exception_handler(self, exc_class):
        return lambda func: func


class _FieldInfo:
    def __init__(self, default, metadata):
        self.default = default
        self.metadata = metadata

    def get_default(self):
        factory = self.metadata.get("default_factory")
        if factory is not None:
            return factory()
        return self.default


class DummyBaseModel:
    def __init__(self, **kwargs):
        annotations = {}
        defaults = {}
        for cls in reversed(type(self).__mro__):
            annotations.update(getattr(cls, "__annotations__", {}))
            for name, member in getattr(cls, "__dict__", {}).items():
                if isinstance(member, _FieldInfo):
                    defaults[name] = member

        for name in annotations:
            if name in kwargs:
                setattr(self, name, kwargs[name])
            elif name in defaults:
                setattr(self, name, defaults[name].get_default())
            else:
                setattr(self, name, None)

        for key, value in kwargs.items():
            if key not in annotations:
                setattr(self, key, value)

    def model_dump(self):
        return {k: v for k, v in self.__dict__.items() if not k.startswith("_")}


class HTTPError(Exception):
    pass


class HTTPStatusError(HTTPError):
    def __init__(self, message="", response=None):
        super().__init__(message)
        self.response = response or types.SimpleNamespace(status_code=500)


class RequestError(HTTPError):
    pass


def make_module(name, **attributes):
    mod = types.ModuleType(name)
    mod.__dict__.update(attributes)
    return mod


def load_frankfurter_module():
    fastapi_responses = make_module(
        "fastapi.responses",
        HTMLResponse=lambda *a, **k: None,
        JSONResponse=lambda *a, **k: None,
    )
    fastapi_exceptions = make_module(
        "fastapi.exceptions",
        RequestValidationError=Exception,
    )
    fastapi = make_module(
        "fastapi",
        FastAPI=DummyFastAPI,
        Request=types.SimpleNamespace,
        responses=fastapi_responses,
        exceptions=fastapi_exceptions,
    )

    pydantic = make_module(
        "pydantic",
        BaseModel=DummyBaseModel,
        Field=lambda default=..., **kwargs: _FieldInfo(default, kwargs),
        field_validator=lambda *fields, **kwargs: (lambda func: func),
    )

    httpx_client = types.SimpleNamespace(
        is_closed=False,
        aclose=AsyncMock(),
        get=AsyncMock(),
    )
    httpx = make_module(
        "httpx",
        AsyncClient=lambda *a, **k: httpx_client,
        HTTPError=HTTPError,
        HTTPStatusError=HTTPStatusError,
        RequestError=RequestError,
    )

    module_name = "plugins.omi_frankfurter_app.main"
    file_path = Path(__file__).resolve().parent / "main.py"
    spec = importlib.util.spec_from_file_location(module_name, file_path)
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


class FrankfurterErrorHandlingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.main = load_frankfurter_module()

    def test_convert_currency_http_status_error_sanitized(self):
        fake_response = types.SimpleNamespace(status_code=502)
        exc = HTTPStatusError("Bad Gateway upstream: https://api.frankfurter.dev/v1/latest", response=fake_response)
        with patch.object(self.main, "_request_json", new_callable=AsyncMock) as mock_req:
            mock_req.side_effect = exc
            req = self.main.ConvertCurrencyRequest(amount=100, from_currency="USD", to_currencies=["EUR"])
            resp = asyncio.run(self.main.convert_currency(req))
            self.assertEqual(resp.error, "currency conversion failed with API error 502")
            self.assertNotIn("https://api.frankfurter.dev", resp.error)
            self.assertNotIn("Bad Gateway", resp.error)

    def test_convert_currency_network_error_sanitized_no_ip_leak(self):
        exc = RequestError("Connection refused to 192.168.1.100:8443 (internal proxy token=SECRET_TOKEN_123)")
        with patch.object(self.main, "_request_json", new_callable=AsyncMock) as mock_req:
            mock_req.side_effect = exc
            req = self.main.ConvertCurrencyRequest(amount=100, from_currency="USD", to_currencies=["EUR"])
            resp = asyncio.run(self.main.convert_currency(req))
            self.assertEqual(resp.error, "currency conversion failed due to a network error")
            self.assertNotIn("192.168.1.100", resp.error)
            self.assertNotIn("SECRET_TOKEN_123", resp.error)

    def test_convert_currency_corrupt_response_sanitized(self):
        exc = ValueError("Corrupt malformed non-JSON payload at offset 42 in /var/data/rates.db")
        with patch.object(self.main, "_request_json", new_callable=AsyncMock) as mock_req:
            mock_req.side_effect = exc
            req = self.main.ConvertCurrencyRequest(amount=100, from_currency="USD", to_currencies=["EUR"])
            resp = asyncio.run(self.main.convert_currency(req))
            self.assertEqual(resp.error, "currency conversion failed due to an invalid API response")
            self.assertNotIn("/var/data/rates.db", resp.error)

    def test_convert_currency_unexpected_exception_sanitized_no_stack_leak(self):
        exc = RuntimeError("Database memory corruption at 0xdeadbeef while executing query")
        with patch.object(self.main, "_request_json", new_callable=AsyncMock) as mock_req:
            mock_req.side_effect = exc
            req = self.main.ConvertCurrencyRequest(amount=100, from_currency="USD", to_currencies=["EUR"])
            resp = asyncio.run(self.main.convert_currency(req))
            self.assertEqual(resp.error, "currency conversion failed due to an internal error")
            self.assertNotIn("0xdeadbeef", resp.error)
            self.assertNotIn("RuntimeError", resp.error)

    def test_get_latest_rates_http_status_error_sanitized(self):
        fake_response = types.SimpleNamespace(status_code=504)
        exc = HTTPStatusError("Gateway Timeout upstream", response=fake_response)
        with patch.object(self.main, "_request_json", new_callable=AsyncMock) as mock_req:
            mock_req.side_effect = exc
            req = self.main.LatestRatesRequest(base_currency="USD", to_currencies=["EUR"])
            resp = asyncio.run(self.main.get_latest_rates(req))
            self.assertEqual(resp.error, "latest rates request failed with API error 504")

    def test_get_latest_rates_network_error_sanitized_no_host_leak(self):
        exc = RequestError("DNS lookup failed for backend-lb.corp.internal:443")
        with patch.object(self.main, "_request_json", new_callable=AsyncMock) as mock_req:
            mock_req.side_effect = exc
            req = self.main.LatestRatesRequest(base_currency="USD", to_currencies=["EUR"])
            resp = asyncio.run(self.main.get_latest_rates(req))
            self.assertEqual(resp.error, "latest rates request failed due to a network error")
            self.assertNotIn("corp.internal", resp.error)

    def test_get_latest_rates_unexpected_exception_sanitized(self):
        exc = KeyError("missing_internal_telemetry_key")
        with patch.object(self.main, "_request_json", new_callable=AsyncMock) as mock_req:
            mock_req.side_effect = exc
            req = self.main.LatestRatesRequest(base_currency="USD", to_currencies=["EUR"])
            resp = asyncio.run(self.main.get_latest_rates(req))
            self.assertEqual(resp.error, "latest rates request failed due to an internal error")
            self.assertNotIn("missing_internal_telemetry_key", resp.error)

    def test_list_supported_currencies_http_status_error_sanitized(self):
        fake_response = types.SimpleNamespace(status_code=503)
        exc = HTTPStatusError("Service Unavailable", response=fake_response)
        with patch.object(self.main, "_request_json", new_callable=AsyncMock) as mock_req:
            mock_req.side_effect = exc
            resp = asyncio.run(self.main.list_supported_currencies())
            self.assertEqual(resp.error, "currency list request failed with API error 503")

    def test_list_supported_currencies_network_error_sanitized(self):
        exc = RequestError("SSL handshake timed out connecting to 10.0.0.8")
        with patch.object(self.main, "_request_json", new_callable=AsyncMock) as mock_req:
            mock_req.side_effect = exc
            resp = asyncio.run(self.main.list_supported_currencies())
            self.assertEqual(resp.error, "currency list request failed due to a network error")
            self.assertNotIn("10.0.0.8", resp.error)

    def test_list_supported_currencies_unexpected_exception_sanitized(self):
        exc = TypeError("unsupported operand type(s) for +: 'NoneType' and 'int'")
        with patch.object(self.main, "_request_json", new_callable=AsyncMock) as mock_req:
            mock_req.side_effect = exc
            resp = asyncio.run(self.main.list_supported_currencies())
            self.assertEqual(resp.error, "currency list request failed due to an internal error")
            self.assertNotIn("NoneType", resp.error)


if __name__ == "__main__":
    unittest.main()
