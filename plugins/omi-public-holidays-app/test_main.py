"""Hermetic regression tests for the Omi Public Holidays plugin.

Standard library only: fastapi, httpx, and pydantic are replaced with minimal
stubs before importing the production module, so the suite runs anywhere in
well under a second without site-packages or network access.

Covers BasedHardware/omi#14151:
- _request_json read app.state.http_client unconditionally, so unmanaged
  contexts (no lifespan run) crashed with AttributeError.
- Nager.Date error objects (JSON dicts like {"status": 404, ...}) are not
  lists; slicing them and calling .get() on their keys crashed the tool
  handlers instead of returning a clean ChatToolResponse error.
- _format_holiday/_format_long_weekend/_format_list called dict/list
  operations on unchecked values, so non-dict items or non-list fields
  crashed or produced garbage output.
"""

import importlib.util
import json
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch


class _FakeHTTPError(Exception):
    pass


class _FakeResponse:
    def __init__(self, payload=None, status_code=200, content=b"{}", json_error=None):
        self._payload = payload
        self.status_code = status_code
        self.content = content
        self._json_error = json_error

    def raise_for_status(self):
        if self.status_code >= 400:
            raise _FakeHTTPError(f"upstream status {self.status_code}")

    def json(self):
        if self._json_error is not None:
            raise self._json_error
        return self._payload


class _FakeAsyncClient:
    """httpx.AsyncClient stand-in; instances pull canned responses from a queue."""

    queued = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.is_closed = False
        self.requested = []

    async def get(self, url):
        self.requested.append(url)
        item = _FakeAsyncClient.queued.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    async def aclose(self):
        self.is_closed = True


def load_app():
    class FastAPI:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
            self.state = SimpleNamespace()

        def get(self, *args, **kwargs):
            return lambda handler: handler

        post = get

        def exception_handler(self, *args, **kwargs):
            return lambda handler: handler

    class Request:
        pass

    class JSONResponse:
        def __init__(self, content=None, status_code=200, **kwargs):
            self.content = content
            self.status_code = status_code

    class RequestValidationError(Exception):
        def __init__(self, errors=()):
            super().__init__("request validation failed")
            self._errors = list(errors)

        def errors(self):
            return list(self._errors)

    class BaseModel:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

        def model_dump(self):
            defaults = {
                key: value
                for klass in reversed(type(self).__mro__)
                for key, value in vars(klass).items()
                if not key.startswith("_")
                and not callable(value)
                and not isinstance(value, (classmethod, staticmethod))
            }
            return {**defaults, **self.__dict__}

    def Field(default=None, **kwargs):
        return default

    def field_validator(*fields, **kwargs):
        return lambda func: func

    httpx = ModuleType("httpx")
    httpx.AsyncClient = _FakeAsyncClient
    httpx.HTTPError = _FakeHTTPError
    fastapi = ModuleType("fastapi")
    fastapi.FastAPI = FastAPI
    fastapi.Request = Request
    exceptions = ModuleType("fastapi.exceptions")
    exceptions.RequestValidationError = RequestValidationError
    fastapi.exceptions = exceptions
    responses = ModuleType("fastapi.responses")
    responses.HTMLResponse = str
    responses.JSONResponse = JSONResponse
    pydantic = ModuleType("pydantic")
    pydantic.BaseModel = BaseModel
    pydantic.Field = Field
    pydantic.field_validator = field_validator

    spec = importlib.util.spec_from_file_location("public_holidays_app", Path(__file__).with_name("main.py"))
    module = importlib.util.module_from_spec(spec)
    with patch.dict(
        sys.modules,
        {
            "httpx": httpx,
            "fastapi": fastapi,
            "fastapi.exceptions": exceptions,
            "fastapi.responses": responses,
            "pydantic": pydantic,
        },
    ):
        spec.loader.exec_module(module)
    return module


app = load_app()


def _request(**overrides):
    values = {"country_code": "US", "year": 2025, "limit": 20}
    values.update(overrides)
    return SimpleNamespace(**values)


class _ClientStateTestCase(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        _FakeAsyncClient.queued = []
        if hasattr(app.app.state, "http_client"):
            delattr(app.app.state, "http_client")


class RequestJsonTests(_ClientStateTestCase):
    async def test_allocates_fallback_client_when_lifespan_never_ran(self):
        _FakeAsyncClient.queued = [_FakeResponse(payload=[{"date": "2025-01-01"}])]
        payload = await app._request_json("/PublicHolidays/2025/US")
        self.assertEqual(payload, [{"date": "2025-01-01"}])
        client = app.app.state.http_client
        self.assertIsInstance(client, _FakeAsyncClient)
        self.assertEqual(client.kwargs.get("timeout"), app.REQUEST_TIMEOUT_SECONDS)
        self.assertEqual(client.requested, ["https://date.nager.at/api/v3/PublicHolidays/2025/US"])

    async def test_reuses_managed_client_from_state(self):
        managed = _FakeAsyncClient()
        app.app.state.http_client = managed
        _FakeAsyncClient.queued = [_FakeResponse(payload=[1])]
        self.assertEqual(await app._request_json("/x"), [1])
        self.assertIs(app.app.state.http_client, managed)
        self.assertEqual(managed.requested, ["https://date.nager.at/api/v3/x"])

    async def test_replaces_closed_client(self):
        closed = _FakeAsyncClient()
        closed.is_closed = True
        app.app.state.http_client = closed
        _FakeAsyncClient.queued = [_FakeResponse(payload=[2])]
        self.assertEqual(await app._request_json("/y"), [2])
        self.assertIsNot(app.app.state.http_client, closed)
        self.assertEqual(closed.requested, [])

    async def test_no_content_status_returns_empty_list(self):
        _FakeAsyncClient.queued = [_FakeResponse(status_code=204, content=b"")]
        self.assertEqual(await app._request_json("/z"), [])

    async def test_empty_body_returns_empty_list(self):
        _FakeAsyncClient.queued = [_FakeResponse(status_code=200, content=b"")]
        self.assertEqual(await app._request_json("/z"), [])

    async def test_invalid_json_raises_http_error(self):
        _FakeAsyncClient.queued = [
            _FakeResponse(content=b"<html>", json_error=json.JSONDecodeError("bad", "doc", 0))
        ]
        with self.assertRaises(_FakeHTTPError):
            await app._request_json("/z")


class LifespanTests(unittest.IsolatedAsyncioTestCase):
    async def test_lifespan_disposes_client_and_clears_state(self):
        app_instance = SimpleNamespace(state=SimpleNamespace())
        async with app.lifespan(app_instance):
            client = app_instance.state.http_client
            self.assertIsInstance(client, _FakeAsyncClient)
            self.assertFalse(client.is_closed)
        self.assertTrue(client.is_closed)
        self.assertIsNone(app_instance.state.http_client)


class FormatListTests(unittest.TestCase):
    def test_none_and_empty_return_all_regions(self):
        self.assertEqual(app._format_list(None), "all regions")
        self.assertEqual(app._format_list([]), "all regions")

    def test_non_list_values_return_all_regions(self):
        for value in ("US-CA", {"region": 1}, 7):
            with self.subTest(value=value):
                self.assertEqual(app._format_list(value), "all regions")

    def test_truncates_with_suffix(self):
        self.assertEqual(
            app._format_list(["a", "b", "c", "d", "e", "f", "g"]),
            "a, b, c, d, e +2 more",
        )

    def test_coerces_non_string_items(self):
        self.assertEqual(app._format_list([1, True]), "1, True")


class FormatHolidayTests(unittest.TestCase):
    def test_renders_global_holiday_with_types(self):
        holiday = {
            "date": "2025-01-01",
            "name": "New Year's Day",
            "localName": "New Year's Day",
            "global": True,
            "types": ["Public"],
        }
        self.assertEqual(
            app._format_holiday(holiday),
            "- 2025-01-01: New Year's Day (global; Public)",
        )

    def test_renders_distinct_local_name_and_counties(self):
        holiday = {
            "date": "2025-12-25",
            "name": "Christmas Day",
            "localName": "Weihnachten",
            "global": False,
            "counties": ["DE-BW"],
            "types": ["Public"],
        }
        self.assertEqual(
            app._format_holiday(holiday),
            "- 2025-12-25: Christmas Day / Weihnachten (DE-BW; Public)",
        )

    def test_non_dict_returns_fallback_line(self):
        self.assertEqual(app._format_holiday("not-a-holiday"), "- not-a-holiday")
        self.assertEqual(app._format_holiday(None), "- None")

    def test_missing_fields_use_safe_fallbacks(self):
        self.assertEqual(
            app._format_holiday({}),
            "- unknown date: unknown holiday (all regions)",
        )

    def test_local_name_only_does_not_render_none(self):
        holiday = {"date": "2025-01-01", "localName": "Nur Lokal"}
        self.assertEqual(app._format_holiday(holiday), "- 2025-01-01: Nur Lokal (all regions)")

    def test_non_list_types_field_is_ignored(self):
        holiday = {
            "date": "2025-01-01",
            "name": "Founders Day",
            "localName": "Founders Day",
            "global": True,
            "types": "Public",
        }
        self.assertEqual(app._format_holiday(holiday), "- 2025-01-01: Founders Day (global)")


class FormatLongWeekendTests(unittest.TestCase):
    def test_renders_bridge_days(self):
        item = {
            "startDate": "2025-05-01",
            "endDate": "2025-05-04",
            "dayCount": 4,
            "bridgeDays": ["2025-05-02"],
        }
        self.assertEqual(
            app._format_long_weekend(item),
            "- 2025-05-01 to 2025-05-04: 4 days; bridge day: 2025-05-02",
        )

    def test_renders_needed_bridge_day(self):
        item = {"startDate": "a", "endDate": "b", "dayCount": 3, "needBridgeDay": True}
        self.assertEqual(
            app._format_long_weekend(item),
            "- a to b: 3 days; bridge day needed",
        )

    def test_renders_no_bridge_day(self):
        item = {"startDate": "a", "endDate": "b", "dayCount": 3}
        self.assertEqual(
            app._format_long_weekend(item),
            "- a to b: 3 days; no bridge day needed",
        )

    def test_non_dict_returns_fallback_line(self):
        self.assertEqual(app._format_long_weekend("oops"), "- oops")

    def test_non_list_bridge_days_are_ignored(self):
        item = {"startDate": "a", "endDate": "b", "dayCount": 3, "bridgeDays": "2025-05-02"}
        self.assertEqual(
            app._format_long_weekend(item),
            "- a to b: 3 days; no bridge day needed",
        )


class GetPublicHolidaysTests(unittest.IsolatedAsyncioTestCase):
    async def test_lists_holidays(self):
        payload = [
            {
                "date": "2025-01-01",
                "name": "New Year's Day",
                "localName": "New Year's Day",
                "global": True,
                "types": ["Public"],
            }
        ]
        with patch.object(app, "_request_json", AsyncMock(return_value=payload)) as provider:
            response = await app.get_public_holidays(_request())
        self.assertIsNone(response.error)
        self.assertIn("Public holidays for US in 2025:", response.result)
        self.assertIn("New Year's Day", response.result)
        provider.assert_awaited_once_with("/PublicHolidays/2025/US")

    async def test_error_object_payload_returns_clean_error(self):
        with patch.object(
            app, "_request_json", AsyncMock(return_value={"status": 404, "title": "Not Found"})
        ):
            response = await app.get_public_holidays(_request())
        self.assertIsNone(response.result)
        self.assertIn("no holidays returned for US in 2025", response.error)

    async def test_null_payload_returns_clean_error(self):
        with patch.object(app, "_request_json", AsyncMock(return_value=None)):
            response = await app.get_public_holidays(_request())
        self.assertIsNone(response.result)
        self.assertIn("no holidays returned", response.error)

    async def test_empty_list_returns_clean_error(self):
        with patch.object(app, "_request_json", AsyncMock(return_value=[])):
            response = await app.get_public_holidays(_request())
        self.assertIsNone(response.result)
        self.assertIn("no holidays returned", response.error)

    async def test_truncates_to_limit_with_remainder_line(self):
        payload = [
            {"date": f"2025-01-0{i}", "name": f"Day {i}", "localName": f"Day {i}", "global": True}
            for i in range(1, 4)
        ]
        with patch.object(app, "_request_json", AsyncMock(return_value=payload)):
            response = await app.get_public_holidays(_request(limit=2))
        self.assertIn("- 2025-01-02: Day 2", response.result)
        self.assertNotIn("Day 3 (", response.result)
        self.assertIn("... 1 more", response.result)

    async def test_non_dict_item_renders_fallback_line(self):
        with patch.object(app, "_request_json", AsyncMock(return_value=["bogus-entry"])):
            response = await app.get_public_holidays(_request())
        self.assertIsNone(response.error)
        self.assertIn("- bogus-entry", response.result)

    async def test_http_error_returns_error_response(self):
        with patch.object(app, "_request_json", AsyncMock(side_effect=_FakeHTTPError("boom"))):
            response = await app.get_public_holidays(_request())
        self.assertIsNone(response.result)
        self.assertIn("holiday lookup failed: boom", response.error)


class GetNextPublicHolidaysTests(unittest.IsolatedAsyncioTestCase):
    async def test_lists_upcoming_holidays(self):
        payload = [
            {"date": "2025-07-04", "name": "Independence Day", "localName": "Independence Day", "global": True}
        ]
        with patch.object(app, "_request_json", AsyncMock(return_value=payload)) as provider:
            response = await app.get_next_public_holidays(_request())
        self.assertIsNone(response.error)
        self.assertIn("Upcoming public holidays for US:", response.result)
        provider.assert_awaited_once_with("/NextPublicHolidays/US")

    async def test_error_object_payload_returns_clean_error(self):
        with patch.object(app, "_request_json", AsyncMock(return_value={"status": 404})):
            response = await app.get_next_public_holidays(_request())
        self.assertIsNone(response.result)
        self.assertIn("no upcoming holidays returned for US", response.error)


class GetLongWeekendsTests(unittest.IsolatedAsyncioTestCase):
    async def test_lists_long_weekends(self):
        payload = [
            {"startDate": "2025-05-01", "endDate": "2025-05-04", "dayCount": 4, "bridgeDays": ["2025-05-02"]}
        ]
        with patch.object(app, "_request_json", AsyncMock(return_value=payload)) as provider:
            response = await app.get_long_weekends(_request())
        self.assertIsNone(response.error)
        self.assertIn("Long weekends for US in 2025:", response.result)
        self.assertIn("bridge day: 2025-05-02", response.result)
        provider.assert_awaited_once_with("/LongWeekend/2025/US")

    async def test_error_object_payload_returns_clean_error(self):
        with patch.object(app, "_request_json", AsyncMock(return_value={"status": 404})):
            response = await app.get_long_weekends(_request())
        self.assertIsNone(response.result)
        self.assertIn("no long weekends returned for US in 2025", response.error)


class ListSupportedCountriesTests(unittest.IsolatedAsyncioTestCase):
    async def test_lists_countries(self):
        payload = [
            {"countryCode": "US", "name": "United States"},
            {"countryCode": "DE", "name": "Germany"},
        ]
        with patch.object(app, "_request_json", AsyncMock(return_value=payload)):
            response = await app.list_supported_countries()
        self.assertIsNone(response.error)
        self.assertIn("Supported countries:", response.result)
        self.assertIn("- US: United States", response.result)
        self.assertIn("- DE: Germany", response.result)

    async def test_skips_non_dict_entries(self):
        payload = [{"countryCode": "US", "name": "United States"}, "junk", 42]
        with patch.object(app, "_request_json", AsyncMock(return_value=payload)):
            response = await app.list_supported_countries()
        self.assertIsNone(response.error)
        self.assertIn("- US: United States", response.result)
        self.assertNotIn("junk", response.result)
        self.assertNotIn("42", response.result)

    async def test_all_non_dict_entries_return_clean_error(self):
        with patch.object(app, "_request_json", AsyncMock(return_value=["junk", 7])):
            response = await app.list_supported_countries()
        self.assertIsNone(response.result)
        self.assertIn("no countries", response.error)

    async def test_non_list_payload_returns_clean_error(self):
        with patch.object(app, "_request_json", AsyncMock(return_value={"status": 500})):
            response = await app.list_supported_countries()
        self.assertIsNone(response.result)
        self.assertIn("no countries", response.error)

    async def test_http_error_returns_error_response(self):
        with patch.object(app, "_request_json", AsyncMock(side_effect=_FakeHTTPError("down"))):
            response = await app.list_supported_countries()
        self.assertIsNone(response.result)
        self.assertIn("country list request failed: down", response.error)


class ValidationHandlerTests(unittest.IsolatedAsyncioTestCase):
    async def test_returns_error_payload_with_status_200(self):
        exc = app.RequestValidationError(
            [{"loc": ("body", "country_code"), "msg": "bad code"}]
        )
        response = await app.validation_exception_handler(None, exc)
        self.assertEqual(response.status_code, 200)
        self.assertIn("country_code", response.content["error"])
        self.assertIn("bad code", response.content["error"])


class NormalizeCountryCodeTests(unittest.TestCase):
    def test_normalizes_lowercase_and_whitespace(self):
        self.assertEqual(app._normalize_country_code(" us "), "US")

    def test_rejects_wrong_length(self):
        for value in ("USA", "U"):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    app._normalize_country_code(value)

    def test_rejects_non_alpha(self):
        with self.assertRaises(ValueError):
            app._normalize_country_code("U1")


class MetadataTests(unittest.IsolatedAsyncioTestCase):
    async def test_health_endpoint(self):
        self.assertEqual(await app.health(), {"status": "ok"})

    async def test_tool_manifest_lists_four_tools(self):
        manifest = await app.omi_tools()
        names = [tool["name"] for tool in manifest["tools"]]
        self.assertEqual(
            names,
            [
                "get_public_holidays",
                "get_next_public_holidays",
                "get_long_weekends",
                "list_supported_countries",
            ],
        )


if __name__ == "__main__":
    unittest.main()
