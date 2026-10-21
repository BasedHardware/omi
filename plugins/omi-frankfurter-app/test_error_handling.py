"""Hermetic error-handling tests for the Frankfurter chat tools.

Standard library only: httpx, fastapi, and pydantic are replaced with minimal
stubs before importing the module under test, so the suite runs without
site-packages (the manifest lane runs plain python3). The async chat-tool
handlers are invoked through asyncio.run with the `_request_json` seam stubbed,
so no network access is required.

Covers the exception-text leak class: transport failures (`httpx.HTTPError`
without a status, DNS/errno details) and unexpected internal exceptions must
never be interpolated into `ChatToolResponse.error` — only fixed,
code-controlled messages may reach the chat model/client. HTTP status mappings
(429 rate limiting, 5xx unavailable) and code-controlled ValueError messages
are preserved.
"""

import asyncio
import importlib.util
import json
import sys
import types
import unittest
from pathlib import Path
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

            resolved = {}
            for name in annotations:
                if name in kwargs:
                    resolved[name] = kwargs[name]
                elif name in defaults:
                    info = defaults[name]
                    default = info.get_default()
                    if default is not ...:
                        resolved[name] = default

            for cls in reversed(type(self).__mro__):
                for name, member in getattr(cls, "__dict__", {}).items():
                    raw = member.__func__ if isinstance(member, classmethod) else member
                    metadata = getattr(raw, "__field_validator__", None)
                    if not metadata:
                        continue
                    fields, options = metadata
                    if options.get("mode") == "before":
                        for field in fields:
                            if field in resolved:
                                resolved[field] = getattr(type(self), name)(resolved[field])

            for name, value in resolved.items():
                setattr(self, name, value)

        def model_dump(self):
            return {k: v for k, v in self.__dict__.items() if not k.startswith("_")}

    def Field(default=..., **metadata):
        return _FieldInfo(default, metadata)

    def field_validator(*fields, **options):
        def decorator(func):
            raw = func.__func__ if isinstance(func, classmethod) else func
            raw.__field_validator__ = (fields, options)
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

        async def get(self, url, params=None):
            raise AssertionError("tests must stub main._request_json; no network allowed")

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

    spec = importlib.util.spec_from_file_location(
        "frankfurter_error_handling_app", Path(__file__).with_name("main.py"))
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

SCARY_TRANSPORT = (
    "[Errno -2] Name or service not known: resolve ('api.frankfurter.dev', 443) "
    "via resolver 10.0.2.15 from host omi-plugins-7f9c"
)


def _convert_req():
    return main.ConvertCurrencyRequest(amount="50", from_currency="USD", to_currencies=["EUR"])


def _transport_exc():
    return main.httpx.HTTPError(SCARY_TRANSPORT)


def _status_exc(status):
    return main.httpx.HTTPStatusError(
        "upstream exploded", response=types.SimpleNamespace(status_code=status))


class TransportSanitizationTests(unittest.TestCase):
    def test_convert_transport_error_is_sanitized(self):
        with patch.object(main, "_request_json", AsyncMock(side_effect=_transport_exc())):
            resp = asyncio.run(main.convert_currency(_convert_req()))
        self.assertEqual(
            resp.error,
            "Currency conversion failed: the Frankfurter API could not be reached. Please try again later.")
        self.assertNotIn("Errno", resp.error)
        self.assertNotIn("10.0.2.15", resp.error)
        self.assertNotIn("omi-plugins-7f9c", resp.error)

    def test_latest_rates_transport_error_is_sanitized(self):
        with patch.object(main, "_request_json", AsyncMock(side_effect=_transport_exc())):
            resp = asyncio.run(main.get_latest_rates(
                main.LatestRatesRequest(base_currency="USD", to_currencies=["EUR"])))
        self.assertEqual(
            resp.error,
            "Latest rates request failed: the Frankfurter API could not be reached. Please try again later.")
        self.assertNotIn("Errno", resp.error)

    def test_currency_list_transport_error_is_sanitized(self):
        with patch.object(main, "_request_json", AsyncMock(side_effect=_transport_exc())):
            resp = asyncio.run(main.list_supported_currencies())
        self.assertEqual(
            resp.error,
            "Currency list request failed: the Frankfurter API could not be reached. Please try again later.")
        self.assertNotIn("Errno", resp.error)


class HttpStatusMappingTests(unittest.TestCase):
    def test_rate_limit_429_is_reported(self):
        with patch.object(main, "_request_json", AsyncMock(side_effect=_status_exc(429))):
            resp = asyncio.run(main.convert_currency(
                main.ConvertCurrencyRequest(amount="5", from_currency="USD", to_currencies=["EUR"])))
        self.assertIn("rate limiting", resp.error)
        self.assertNotIn("upstream exploded", resp.error)

    def test_unavailable_503_is_reported(self):
        with patch.object(main, "_request_json", AsyncMock(side_effect=_status_exc(503))):
            resp = asyncio.run(main.get_latest_rates(
                main.LatestRatesRequest(base_currency="USD")))
        self.assertIn("temporarily unavailable", resp.error)
        self.assertNotIn("upstream exploded", resp.error)

    def test_other_status_is_reported_without_exception_text(self):
        with patch.object(main, "_request_json", AsyncMock(side_effect=_status_exc(422))):
            resp = asyncio.run(main.list_supported_currencies())
        self.assertIn("HTTP 422", resp.error)
        self.assertNotIn("upstream exploded", resp.error)


class UnexpectedExceptionTests(unittest.TestCase):
    def test_internal_error_text_never_reaches_response(self):
        secret = RuntimeError("confidential failure in /home/z/app/secret.key loader")
        with patch.object(main, "_request_json", AsyncMock(side_effect=secret)):
            resp = asyncio.run(main.convert_currency(
                main.ConvertCurrencyRequest(amount="5", from_currency="USD", to_currencies=["EUR"])))
        self.assertEqual(resp.error, "Currency conversion failed. Please try again later.")
        self.assertNotIn("secret", resp.error)
        self.assertNotIn("/home/z", resp.error)

    def test_invalid_json_response_is_reported_cleanly(self):
        with patch.object(main, "_request_json",
                          AsyncMock(side_effect=json.JSONDecodeError("Expecting value", "doc", 0))):
            resp = asyncio.run(main.convert_currency(
                main.ConvertCurrencyRequest(amount="5", from_currency="USD", to_currencies=["EUR"])))
        self.assertIn("invalid response", resp.error)


class BehaviorPreservationTests(unittest.TestCase):
    def test_code_controlled_value_errors_stay_informative(self):
        with patch.object(main, "_request_json",
                          AsyncMock(side_effect=ValueError("unsupported currency: USD"))):
            resp = asyncio.run(main.convert_currency(
                main.ConvertCurrencyRequest(amount="5", from_currency="USD", to_currencies=["USD"])))
        self.assertEqual(resp.error, "currency conversion failed: unsupported currency: USD")

    def test_happy_path_unchanged(self):
        payload = {"rates": {"EUR": 0.9}, "base": "USD", "date": "2026-01-02"}
        with patch.object(main, "_request_json", AsyncMock(return_value=payload)):
            resp = asyncio.run(main.convert_currency(_convert_req()))
        self.assertIsNone(resp.error)
        self.assertIn("EUR: 0.9", resp.result)


if __name__ == "__main__":
    unittest.main()
