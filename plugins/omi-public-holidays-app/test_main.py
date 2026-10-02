"""Hermetic regression tests for the Omi public holidays app.

The suite runs with the Python standard library only. Lightweight stubs replace
FastAPI, httpx, and Pydantic before importing the application, and every API
response is supplied by an in-memory async mock.
"""

from __future__ import annotations

import asyncio
import importlib
import sys
import types
import unittest
from unittest.mock import AsyncMock, patch


class _FieldInfo:
    def __init__(self, default, metadata):
        self.default = default
        self.metadata = metadata


def _install_dependency_stubs():
    saved = {name: sys.modules.get(name) for name in ("httpx", "fastapi", "fastapi.exceptions", "fastapi.responses", "pydantic")}

    httpx = types.ModuleType("httpx")

    class HTTPError(Exception):
        pass

    class AsyncClient:
        def __init__(self, *args, **kwargs):
            self.is_closed = False

        async def get(self, *args, **kwargs):
            raise AssertionError("tests must stub the HTTP response")

    httpx.HTTPError = HTTPError
    httpx.AsyncClient = AsyncClient
    sys.modules["httpx"] = httpx

    fastapi = types.ModuleType("fastapi")

    class FastAPI:
        def __init__(self, *args, **kwargs):
            self.state = types.SimpleNamespace()

        def get(self, *args, **kwargs):
            return lambda function: function

        def post(self, *args, **kwargs):
            return lambda function: function

        def exception_handler(self, *args, **kwargs):
            return lambda function: function

    fastapi.FastAPI = FastAPI
    fastapi.Request = type("Request", (), {})
    sys.modules["fastapi"] = fastapi

    fastapi_exceptions = types.ModuleType("fastapi.exceptions")

    class RequestValidationError(Exception):
        def errors(self):
            return []

    fastapi_exceptions.RequestValidationError = RequestValidationError
    sys.modules["fastapi.exceptions"] = fastapi_exceptions
    fastapi.exceptions = fastapi_exceptions

    fastapi_responses = types.ModuleType("fastapi.responses")

    class HTMLResponse:
        pass

    class JSONResponse:
        def __init__(self, status_code, content):
            self.status_code = status_code
            self.content = content

    fastapi_responses.HTMLResponse = HTMLResponse
    fastapi_responses.JSONResponse = JSONResponse
    sys.modules["fastapi.responses"] = fastapi_responses
    fastapi.responses = fastapi_responses

    pydantic = types.ModuleType("pydantic")

    def Field(default=..., **metadata):
        return _FieldInfo(default, metadata)

    def field_validator(*fields, **options):
        def decorator(function):
            raw = function.__func__ if isinstance(function, classmethod) else function
            raw.__field_validator__ = (fields, options)
            return function

        return decorator

    class BaseModel:
        def __init__(self, **values):
            annotations = {}
            defaults = {}
            for cls in reversed(type(self).__mro__):
                annotations.update(getattr(cls, "__annotations__", {}))
                for name, member in getattr(cls, "__dict__", {}).items():
                    if isinstance(member, _FieldInfo):
                        defaults[name] = member.default

            resolved = {}
            for name in annotations:
                if name in values:
                    resolved[name] = values[name]
                elif name in defaults and defaults[name] is not ...:
                    resolved[name] = defaults[name]

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
            return self.__dict__.copy()

    pydantic.BaseModel = BaseModel
    pydantic.Field = Field
    pydantic.field_validator = field_validator
    sys.modules["pydantic"] = pydantic
    return saved


_saved_modules = _install_dependency_stubs()
try:
    if "main" in sys.modules:
        del sys.modules["main"]
    import main  # noqa: E402
finally:
    for _name, _original in _saved_modules.items():
        if _original is None:
            sys.modules.pop(_name, None)
        else:
            sys.modules[_name] = _original


def _run(coro):
    return asyncio.run(coro)


class _FakeResponse:
    status_code = 200
    content = b"{}"

    def raise_for_status(self):
        return None

    def json(self):
        return {"ok": True}


class _RecordingClient:
    instances = []

    def __init__(self, *args, **kwargs):
        self.is_closed = False
        self.args = args
        self.kwargs = kwargs
        self.calls = []
        self.__class__.instances.append(self)

    async def get(self, url):
        self.calls.append(url)
        return _FakeResponse()


class PublicHolidayRequestTests(unittest.TestCase):
    def test_whitespace_country_code_is_normalized_before_length_validation(self):
        self.assertEqual(main.HolidayRequest(country_code=" us ", year=2026).country_code, "US")
        self.assertEqual(main.NextHolidayRequest(country_code=" de ").country_code, "DE")
        self.assertEqual(main.LongWeekendRequest(country_code=" jp ", year=2026).country_code, "JP")

    def test_non_string_country_code_is_rejected_cleanly(self):
        with self.assertRaises(ValueError):
            main.HolidayRequest(country_code=7, year=2026)


class PublicHolidayFormattingTests(unittest.TestCase):
    def test_format_holiday_handles_unexpected_types(self):
        self.assertEqual(main._format_holiday(None), "- Unknown holiday")
        rendered = main._format_holiday(
            {"date": 2026, "name": 123, "localName": None, "counties": ["US-CA", 7], "types": ["Public", 2, None]}
        )
        self.assertIn("2026: 123", rendered)
        self.assertIn("US-CA, 7", rendered)
        self.assertIn("Public, 2", rendered)

    def test_format_long_weekend_handles_non_list_bridge_days(self):
        self.assertEqual(main._format_long_weekend("bad payload"), "- Unknown long weekend")
        rendered = main._format_long_weekend({"startDate": "2026-01-01", "endDate": "2026-01-04", "dayCount": 4, "bridgeDays": ["2026-01-02", 3]})
        self.assertIn("bridge day: 2026-01-02, 3", rendered)


class PublicHolidayHandlerTests(unittest.IsolatedAsyncioTestCase):
    async def test_dictionary_payloads_return_errors_instead_of_slice_type_errors(self):
        cases = (
            (main.get_public_holidays, main.HolidayRequest(country_code="US", year=2026), "holiday lookup returned invalid data"),
            (main.get_next_public_holidays, main.NextHolidayRequest(country_code="US"), "upcoming holiday lookup returned invalid data"),
            (main.get_long_weekends, main.LongWeekendRequest(country_code="US", year=2026), "long-weekend lookup returned invalid data"),
        )
        for handler, request, expected in cases:
            with self.subTest(handler=handler.__name__), patch.object(
                main, "_request_json", new=AsyncMock(return_value={"status": 404, "title": "Not Found"})
            ):
                response = await handler(request)
            self.assertIsNone(response.result)
            self.assertIn(expected, response.error)

    async def test_mixed_list_items_are_formatted_without_crashing(self):
        request = main.HolidayRequest(country_code="US", year=2026, limit=3)
        payload = [None, {"date": "2026-01-01", "name": "New Year", "types": "Public"}, "unexpected"]
        with patch.object(main, "_request_json", new=AsyncMock(return_value=payload)):
            response = await main.get_public_holidays(request)
        self.assertIsNone(response.error)
        self.assertIn("Unknown holiday", response.result)
        self.assertIn("New Year", response.result)


class RequestJsonTests(unittest.IsolatedAsyncioTestCase):
    async def test_request_json_initializes_missing_client(self):
        main.app.state = types.SimpleNamespace()
        _RecordingClient.instances = []
        with patch.object(main.httpx, "AsyncClient", _RecordingClient):
            payload = await main._request_json("/AvailableCountries")
        self.assertEqual(payload, {"ok": True})
        self.assertEqual(len(_RecordingClient.instances), 1)
        self.assertEqual(_RecordingClient.instances[0].calls, ["https://date.nager.at/api/v3/AvailableCountries"])

    async def test_request_json_replaces_closed_client(self):
        closed = _RecordingClient()
        closed.is_closed = True
        main.app.state = types.SimpleNamespace(http_client=closed)
        _RecordingClient.instances = [closed]
        with patch.object(main.httpx, "AsyncClient", _RecordingClient):
            await main._request_json("/NextPublicHolidays/US")
        self.assertEqual(len(_RecordingClient.instances), 2)
        self.assertIs(main.app.state.http_client, _RecordingClient.instances[-1])


if __name__ == "__main__":
    unittest.main()
