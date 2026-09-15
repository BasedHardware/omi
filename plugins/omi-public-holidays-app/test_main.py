"""Hermetic regression tests for plugins/omi-public-holidays-app/main.py.

Standard library only: fastapi, httpx, and pydantic are replaced with minimal
stubs before importing the module under test so the suite runs without
site-packages (the manifest lane runs plain python3).

Covers BasedHardware/omi#13928:
- Nager.Date error objects (JSON dicts like {"status": 404, ...}) are not
  lists; slicing them raised TypeError: unhashable type: 'slice' in
  get_public_holidays, get_next_public_holidays, and get_long_weekends.
- _request_json read app.state.http_client unconditionally, so endpoints
  crashed with AttributeError whenever lifespan never ran (tests, serverless).
- country_code validators ran in pydantic's default mode="after", so
  whitespace-padded codes like " US " failed the max_length=2 constraint
  before _normalize_country_code could strip them.
- _format_holiday/_format_long_weekend called dict methods and joined raw
  values without type guards; non-dict items or non-list types/bridgeDays
  crashed or produced garbage.
- list_supported_countries called item.get on every entry — same defect
  class — so a non-dict entry crashed the handler.
"""

import json
import os
import sys
import types
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

_STUBBED_MODULES = (
    "fastapi",
    "fastapi.exceptions",
    "fastapi.responses",
    "httpx",
    "pydantic",
)

_REQUIRED = object()


class _FieldSpec:
    """Stand-in for pydantic.Field metadata."""

    def __init__(self, default=_REQUIRED, **constraints):
        self.required = default is _REQUIRED or default is Ellipsis
        self.default = None if self.required else default
        self.min_length = constraints.get("min_length")
        self.max_length = constraints.get("max_length")
        self.ge = constraints.get("ge")
        self.le = constraints.get("le")


class _ValidatorMarker:
    """Stand-in for a pydantic field_validator registration."""

    def __init__(self, field, mode, func):
        self.field = field
        self.mode = mode
        self.func = func


def _install_module_stubs():
    fastapi = types.ModuleType("fastapi")

    class FastAPI:
        def __init__(self, *args, **kwargs):
            self.state = types.SimpleNamespace()

        def get(self, *args, **kwargs):
            return lambda handler: handler

        def post(self, *args, **kwargs):
            return lambda handler: handler

        def exception_handler(self, *args, **kwargs):
            return lambda handler: handler

    class Request:
        pass

    fastapi.FastAPI = FastAPI
    fastapi.Request = Request
    sys.modules["fastapi"] = fastapi

    exceptions = types.ModuleType("fastapi.exceptions")

    class RequestValidationError(Exception):
        def errors(self):
            return []

    exceptions.RequestValidationError = RequestValidationError
    fastapi.exceptions = exceptions
    sys.modules["fastapi.exceptions"] = exceptions

    responses = types.ModuleType("fastapi.responses")

    class _Response:
        def __init__(self, *args, **kwargs):
            self.content = kwargs.get("content")
            self.status_code = kwargs.get("status_code")

    responses.HTMLResponse = _Response
    responses.JSONResponse = _Response
    fastapi.responses = responses
    sys.modules["fastapi.responses"] = responses

    httpx = types.ModuleType("httpx")

    class HTTPError(Exception):
        pass

    class AsyncClient:
        def __init__(self, *args, **kwargs):
            self.is_closed = False

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            self.is_closed = True

        async def get(self, *args, **kwargs):
            raise HTTPError("stub AsyncClient has no transport")

        async def aclose(self):
            self.is_closed = True

    httpx.HTTPError = HTTPError
    httpx.AsyncClient = AsyncClient
    sys.modules["httpx"] = httpx

    pydantic = types.ModuleType("pydantic")

    def Field(default=_REQUIRED, **constraints):
        return _FieldSpec(default, **constraints)

    def field_validator(field, mode="after", **_kwargs):
        def decorator(func):
            raw = getattr(func, "__func__", func)
            return _ValidatorMarker(field, mode, raw)

        return decorator

    def _collect_fields(model_cls):
        fields = {}
        for klass in reversed(model_cls.__mro__):
            for name in getattr(klass, "__annotations__", {}):
                fields[name] = klass.__dict__.get(name, _REQUIRED)
        return fields

    def _collect_validators(model_cls):
        before, after = {}, {}
        for klass in reversed(model_cls.__mro__):
            for attr in vars(klass).values():
                if isinstance(attr, _ValidatorMarker):
                    target = before if attr.mode == "before" else after
                    target.setdefault(attr.field, []).append(attr.func)
        return before, after

    def _run_validator(func, model_cls, value):
        try:
            return func(model_cls, value)
        except TypeError:
            return func(value)

    def _check_constraints(name, value, spec):
        if isinstance(value, str):
            if spec.min_length is not None and len(value) < spec.min_length:
                raise ValueError(f"{name}: string should have at least {spec.min_length} characters")
            if spec.max_length is not None and len(value) > spec.max_length:
                raise ValueError(f"{name}: string should have at most {spec.max_length} characters")
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            if spec.ge is not None and value < spec.ge:
                raise ValueError(f"{name}: input should be greater than or equal to {spec.ge}")
            if spec.le is not None and value > spec.le:
                raise ValueError(f"{name}: input should be less than or equal to {spec.le}")

    class BaseModel:
        def __init__(self, **data):
            model_cls = type(self)
            before, after = _collect_validators(model_cls)
            for name, default in _collect_fields(model_cls).items():
                spec = default if isinstance(default, _FieldSpec) else None
                if name in data:
                    value = data[name]
                elif spec is not None and not spec.required:
                    value = spec.default
                elif default is not _REQUIRED and spec is None:
                    value = default
                else:
                    raise ValueError(f"{name}: field required")
                for func in before.get(name, []):
                    value = _run_validator(func, model_cls, value)
                if spec is not None:
                    _check_constraints(name, value, spec)
                for func in after.get(name, []):
                    value = _run_validator(func, model_cls, value)
                setattr(self, name, value)

        def model_dump(self):
            return {name: getattr(self, name, None) for name in _collect_fields(type(self))}

    pydantic.BaseModel = BaseModel
    pydantic.Field = Field
    pydantic.field_validator = field_validator
    sys.modules["pydantic"] = pydantic


_saved_modules = {name: sys.modules.get(name) for name in _STUBBED_MODULES}
_install_module_stubs()
try:
    sys.modules.pop("main", None)
    import main  # noqa: E402
finally:
    for _name, _original in _saved_modules.items():
        if _original is None:
            sys.modules.pop(_name, None)
        else:
            sys.modules[_name] = _original


def _holiday(date, name, **extra):
    item = {"date": date, "localName": name, "name": name, "global": True, "types": ["Public"]}
    item.update(extra)
    return item


class _FakeResponse:
    def __init__(self, payload, status_code=200, bad_json=False):
        self._payload = payload
        self.status_code = status_code
        self._bad_json = bad_json
        self.content = b"" if status_code == 204 else json.dumps(payload).encode()

    def raise_for_status(self):
        if self.status_code >= 400:
            raise main.httpx.HTTPError(f"HTTP {self.status_code}")

    def json(self):
        if self._bad_json:
            raise json.JSONDecodeError("bad payload", "", 0)
        return self._payload


class _FakeClient:
    def __init__(self, payload=None, status_code=200, closed=False, bad_json=False):
        self.is_closed = closed
        self._response = _FakeResponse(payload, status_code, bad_json)

    async def get(self, url):
        if self.is_closed:
            raise main.httpx.HTTPError("client is closed")
        return self._response

    async def aclose(self):
        self.is_closed = True


def _drop_http_client():
    if hasattr(main.app.state, "http_client"):
        del main.app.state.http_client


class DictPayloadTests(unittest.IsolatedAsyncioTestCase):
    """Nager.Date error objects must not reach list slicing."""

    async def test_public_holidays_dict_payload_returns_error(self):
        payload = {"status": 404, "title": "Not Found"}
        with mock.patch.object(main, "_request_json", new=mock.AsyncMock(return_value=payload)):
            response = await main.get_public_holidays(main.HolidayRequest(country_code="US", year=2099))
        self.assertIsNone(response.result)
        self.assertIn("no holidays returned", response.error)

    async def test_next_public_holidays_dict_payload_returns_error(self):
        payload = {"status": 404, "title": "Not Found"}
        with mock.patch.object(main, "_request_json", new=mock.AsyncMock(return_value=payload)):
            response = await main.get_next_public_holidays(main.NextHolidayRequest(country_code="XX"))
        self.assertIsNone(response.result)
        self.assertIn("no upcoming holidays returned", response.error)

    async def test_long_weekends_dict_payload_returns_error(self):
        payload = {"status": 404, "title": "Not Found"}
        with mock.patch.object(main, "_request_json", new=mock.AsyncMock(return_value=payload)):
            response = await main.get_long_weekends(main.LongWeekendRequest(country_code="US", year=2099))
        self.assertIsNone(response.result)
        self.assertIn("no long weekends returned", response.error)

    async def test_string_payload_returns_error(self):
        with mock.patch.object(main, "_request_json", new=mock.AsyncMock(return_value="Not Found")):
            response = await main.get_public_holidays(main.HolidayRequest(country_code="US", year=2024))
        self.assertIsNone(response.result)
        self.assertIn("no holidays returned", response.error)


class CountryCodeValidationTests(unittest.TestCase):
    """mode="before" validators must normalize whitespace before length checks."""

    def test_whitespace_padded_code_normalizes_for_all_models(self):
        cases = [
            (main.HolidayRequest, {"year": 2024}),
            (main.NextHolidayRequest, {}),
            (main.LongWeekendRequest, {"year": 2024}),
        ]
        for model, extra in cases:
            with self.subTest(model=model.__name__):
                request = model(country_code="  us  ", **extra)
                self.assertEqual(request.country_code, "US")

    def test_lowercase_code_normalizes(self):
        request = main.HolidayRequest(country_code="de", year=2024)
        self.assertEqual(request.country_code, "DE")

    def test_invalid_codes_rejected(self):
        for bad in ("USA", "U1", "12", "", "   "):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    main.HolidayRequest(country_code=bad, year=2024)

    def test_non_string_code_rejected_with_value_error(self):
        with self.assertRaises(ValueError):
            main.HolidayRequest(country_code=12, year=2024)


class RequestJsonClientTests(unittest.IsolatedAsyncioTestCase):
    """_request_json must work when lifespan never ran or the client closed."""

    def setUp(self):
        _drop_http_client()

    def tearDown(self):
        _drop_http_client()

    async def test_missing_lifespan_client_creates_fallback(self):
        payload = [_holiday("2024-01-01", "New Year")]
        fake = _FakeClient(payload=payload)
        with mock.patch.object(main.httpx, "AsyncClient", return_value=fake):
            result = await main._request_json("/PublicHolidays/2024/US")
        self.assertEqual(result, payload)
        self.assertIs(main.app.state.http_client, fake)

    async def test_closed_client_is_replaced(self):
        closed = _FakeClient(closed=True)
        main.app.state.http_client = closed
        fresh = _FakeClient(payload={"ok": True})
        with mock.patch.object(main.httpx, "AsyncClient", return_value=fresh):
            result = await main._request_json("/AvailableCountries")
        self.assertEqual(result, {"ok": True})
        self.assertIs(main.app.state.http_client, fresh)

    async def test_204_response_returns_empty_list(self):
        fake = _FakeClient(payload=None, status_code=204)
        main.app.state.http_client = fake
        self.assertEqual(await main._request_json("/x"), [])

    async def test_invalid_json_raises_http_error(self):
        main.app.state.http_client = _FakeClient(payload=None, bad_json=True)
        with self.assertRaises(main.httpx.HTTPError):
            await main._request_json("/x")


class HandlerBehaviorTests(unittest.IsolatedAsyncioTestCase):
    async def test_public_holidays_happy_path_honors_limit(self):
        payload = [_holiday(f"2024-01-0{i}", f"Holiday {i}") for i in range(1, 4)]
        with mock.patch.object(main, "_request_json", new=mock.AsyncMock(return_value=payload)):
            request = main.HolidayRequest(country_code="US", year=2024, limit=2)
            response = await main.get_public_holidays(request)
        self.assertIsNone(response.error)
        self.assertIn("Public holidays for US in 2024:", response.result)
        self.assertIn("Holiday 1", response.result)
        self.assertIn("Holiday 2", response.result)
        self.assertNotIn("Holiday 3:", response.result)
        self.assertIn("... 1 more", response.result)

    async def test_empty_list_payload_returns_error(self):
        with mock.patch.object(main, "_request_json", new=mock.AsyncMock(return_value=[])):
            response = await main.get_public_holidays(main.HolidayRequest(country_code="US", year=2024))
        self.assertIsNone(response.result)
        self.assertIn("no holidays returned", response.error)

    async def test_http_error_becomes_tool_error(self):
        failing = mock.AsyncMock(side_effect=main.httpx.HTTPError("boom"))
        with mock.patch.object(main, "_request_json", new=failing):
            response = await main.get_next_public_holidays(main.NextHolidayRequest(country_code="US"))
        self.assertIsNone(response.result)
        self.assertIn("upcoming holiday lookup failed", response.error)

    async def test_long_weekends_happy_path(self):
        payload = [
            {"startDate": "2024-12-21", "endDate": "2024-12-26", "dayCount": 6, "bridgeDays": ["2024-12-23"]}
        ]
        with mock.patch.object(main, "_request_json", new=mock.AsyncMock(return_value=payload)):
            response = await main.get_long_weekends(main.LongWeekendRequest(country_code="DE", year=2024))
        self.assertIsNone(response.error)
        self.assertIn("Long weekends for DE in 2024:", response.result)
        self.assertIn("bridge day: 2024-12-23", response.result)

    async def test_supported_countries_tolerates_non_dict_entries(self):
        payload = [
            {"countryCode": "US", "name": "United States"},
            "Atlantis",
            42,
        ]
        with mock.patch.object(main, "_request_json", new=mock.AsyncMock(return_value=payload)):
            response = await main.list_supported_countries()
        self.assertIsNone(response.error)
        self.assertIn("- US: United States", response.result)
        self.assertIn("- Atlantis", response.result)
        self.assertIn("- 42", response.result)


class FormatterTests(unittest.TestCase):
    def test_format_holiday_tolerates_non_dict(self):
        self.assertEqual(main._format_holiday("weird"), "- weird")
        self.assertEqual(main._format_holiday(None), "- None")

    def test_format_holiday_tolerates_non_list_types(self):
        output = main._format_holiday({"date": "2024-01-01", "name": "New Year", "types": "Public"})
        self.assertEqual(output, "- 2024-01-01: New Year (all regions)")

    def test_format_holiday_tolerates_non_list_counties(self):
        output = main._format_holiday({"date": "d", "name": "n", "global": False, "counties": "US-CA"})
        self.assertIn("all regions", output)

    def test_format_holiday_coerces_non_string_types(self):
        output = main._format_holiday({"date": "d", "name": "n", "global": True, "types": ["Public", 7]})
        self.assertIn("Public, 7", output)

    def test_format_long_weekend_tolerates_non_dict(self):
        self.assertEqual(main._format_long_weekend("x"), "- x")

    def test_format_long_weekend_coerces_bridge_days(self):
        item = {"startDate": "a", "endDate": "b", "dayCount": 3, "bridgeDays": [20240102]}
        self.assertIn("bridge day: 20240102", main._format_long_weekend(item))

    def test_format_long_weekend_non_list_bridge_days(self):
        item = {"startDate": "a", "endDate": "b", "dayCount": 3, "bridgeDays": "a", "needBridgeDay": True}
        self.assertIn("bridge day needed", main._format_long_weekend(item))

    def test_format_list_tolerates_non_list(self):
        self.assertEqual(main._format_list("US-CA"), "all regions")
        self.assertEqual(main._format_list({"a": 1}), "all regions")


if __name__ == "__main__":
    unittest.main()
