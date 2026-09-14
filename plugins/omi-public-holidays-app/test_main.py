from pathlib import Path
import importlib.util
import sys
import types
import unittest
from unittest.mock import AsyncMock, patch

# Provide lightweight scoped stubs for third-party runtime dependencies so test_main.py
# runs hermetically on any clean standard library Python environment without
# mutating the process-global sys.modules for other test suites.
stubs = {}

if "httpx" not in sys.modules:
    try:
        import httpx  # type: ignore
    except ImportError:
        _httpx = types.ModuleType("httpx")

        class HTTPError(Exception):
            pass

        class HTTPStatusError(HTTPError):
            pass

        class AsyncClient:
            def __init__(self, *args, **kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

            async def get(self, *args, **kwargs):
                pass

        _httpx.HTTPError = HTTPError
        _httpx.HTTPStatusError = HTTPStatusError
        _httpx.AsyncClient = AsyncClient
        stubs["httpx"] = _httpx

if "fastapi" not in sys.modules:
    try:
        import fastapi  # type: ignore
        import fastapi.exceptions  # type: ignore
        import fastapi.responses  # type: ignore
    except ImportError:
        _fastapi = types.ModuleType("fastapi")

        class FastAPI:
            def __init__(self, *args, **kwargs):
                self.state = types.SimpleNamespace()

            def get(self, *args, **kwargs):
                return lambda f: f

            def post(self, *args, **kwargs):
                return lambda f: f

            def exception_handler(self, *args, **kwargs):
                return lambda f: f

        class Request:
            pass

        _fastapi.FastAPI = FastAPI
        _fastapi.Request = Request
        stubs["fastapi"] = _fastapi

        exc_mod = types.ModuleType("fastapi.exceptions")

        class RequestValidationError(Exception):
            pass

        exc_mod.RequestValidationError = RequestValidationError
        stubs["fastapi.exceptions"] = exc_mod
        _fastapi.exceptions = exc_mod

        resp_mod = types.ModuleType("fastapi.responses")

        class HTMLResponse:
            pass

        class JSONResponse:
            def __init__(self, status_code=200, content=None):
                self.status_code = status_code
                self.content = content

        resp_mod.HTMLResponse = HTMLResponse
        resp_mod.JSONResponse = JSONResponse
        stubs["fastapi.responses"] = resp_mod
        _fastapi.responses = resp_mod

if "pydantic" not in sys.modules:
    try:
        import pydantic  # type: ignore
    except ImportError:
        _pydantic = types.ModuleType("pydantic")

        def Field(default=None, **kwargs):
            return default

        def field_validator(*args, **kwargs):
            return lambda f: f

        class BaseModel:
            def __init__(self, **kwargs):
                for cls in reversed(self.__class__.__mro__):
                    for k, v in getattr(cls, "__dict__", {}).items():
                        if not k.startswith("_") and not callable(v):
                            setattr(self, k, None if v is ... else v)
                for k, v in kwargs.items():
                    setattr(self, k, v)

            def model_dump(self):
                return self.__dict__

        _pydantic.BaseModel = BaseModel
        _pydantic.Field = Field
        _pydantic.field_validator = field_validator
        stubs["pydantic"] = _pydantic

PLUGIN_DIR = Path(__file__).resolve().parent

# Load main hermetically within an isolated patch.dict context,
# so process-global sys.modules is never permanently mutated.
with patch.dict(sys.modules, stubs):
    main_path = PLUGIN_DIR / "main.py"
    main_spec = importlib.util.spec_from_file_location("main", main_path)
    main = importlib.util.module_from_spec(main_spec)
    main_spec.loader.exec_module(main)


class PublicHolidaysHelperTests(unittest.TestCase):
    def test_normalize_country_code(self):
        self.assertEqual(main._normalize_country_code("US"), "US")
        self.assertEqual(main._normalize_country_code("de"), "DE")
        self.assertEqual(main._normalize_country_code("  fr  "), "FR")
        with self.assertRaises(ValueError):
            main._normalize_country_code("USA")
        with self.assertRaises(ValueError):
            main._normalize_country_code("12")
        with self.assertRaises(ValueError):
            main._normalize_country_code(None)

    def test_format_list(self):
        self.assertEqual(main._format_list(None), "all regions")
        self.assertEqual(main._format_list([]), "all regions")
        self.assertEqual(main._format_list(["CA", "NY"]), "CA, NY")
        long_list = ["R1", "R2", "R3", "R4", "R5", "R6", "R7"]
        self.assertEqual(main._format_list(long_list), "R1, R2, R3, R4, R5 +2 more")

    def test_format_holiday_valid_and_fallback(self):
        h1 = {
            "date": "2026-07-04",
            "name": "Independence Day",
            "localName": "Independence Day",
            "global": True,
            "types": ["Public"],
        }
        self.assertEqual(main._format_holiday(h1), "- 2026-07-04: Independence Day (global; Public)")

        h2 = {
            "date": "2026-01-01",
            "name": "New Year's Day",
            "localName": "Neujahr",
            "global": False,
            "counties": ["DE-BY"],
            "types": ["Public"],
        }
        self.assertEqual(main._format_holiday(h2), "- 2026-01-01: New Year's Day / Neujahr (DE-BY; Public)")

        # Non-dict returns empty string
        self.assertEqual(main._format_holiday("not-a-dict"), "")
        self.assertEqual(main._format_holiday(None), "")

    def test_format_long_weekend_valid_and_fallback(self):
        w1 = {
            "startDate": "2026-05-01",
            "endDate": "2026-05-03",
            "dayCount": 3,
            "needBridgeDay": False,
            "bridgeDays": None,
        }
        self.assertEqual(main._format_long_weekend(w1), "- 2026-05-01 to 2026-05-03: 3 days; no bridge day needed")

        w2 = {
            "startDate": "2026-05-14",
            "endDate": "2026-05-17",
            "dayCount": 4,
            "needBridgeDay": True,
            "bridgeDays": ["2026-05-15"],
        }
        self.assertEqual(main._format_long_weekend(w2), "- 2026-05-14 to 2026-05-17: 4 days; bridge day: 2026-05-15")

        self.assertEqual(main._format_long_weekend("not-a-dict"), "")
        self.assertEqual(main._format_long_weekend(None), "")


class PublicHolidaysEndpointTests(unittest.IsolatedAsyncioTestCase):
    async def test_get_public_holidays_success(self):
        holidays_data = [
            {
                "date": "2026-12-25",
                "name": "Christmas Day",
                "localName": "Christmas Day",
                "global": True,
                "types": ["Public"],
            }
        ]
        req = main.HolidayRequest(country_code="US", year=2026)
        with patch.object(main, "_request_json", new=AsyncMock(return_value=holidays_data)):
            res = await main.get_public_holidays(req)

        self.assertIsNone(res.error)
        self.assertIn("Public holidays for US in 2026:", res.result)
        self.assertIn("- 2026-12-25: Christmas Day (global; Public)", res.result)

    async def test_get_public_holidays_dict_response_does_not_crash(self):
        # When upstream returns error dict (e.g. 404 {"status": 404}), slicing dict must not raise TypeError
        error_dict = {"status": 404, "title": "Not Found"}
        req = main.HolidayRequest(country_code="US", year=2026)
        with patch.object(main, "_request_json", new=AsyncMock(return_value=error_dict)):
            res = await main.get_public_holidays(req)

        self.assertIsNone(res.result)
        self.assertIn("no holidays returned for US in 2026", res.error)

    async def test_get_public_holidays_http_error(self):
        req = main.HolidayRequest(country_code="US", year=2026)
        with patch.object(main, "_request_json", new=AsyncMock(side_effect=main.httpx.HTTPError("service timeout"))):
            res = await main.get_public_holidays(req)

        self.assertIsNone(res.result)
        self.assertIn("holiday lookup failed: service timeout", res.error)

    async def test_get_next_public_holidays_success_and_dict_protection(self):
        holidays_data = [
            {
                "date": "2026-11-26",
                "name": "Thanksgiving Day",
                "localName": "Thanksgiving Day",
                "global": True,
                "types": ["Public"],
            }
        ]
        req = main.NextHolidayRequest(country_code="US")
        with patch.object(main, "_request_json", new=AsyncMock(return_value=holidays_data)):
            res = await main.get_next_public_holidays(req)

        self.assertIsNone(res.error)
        self.assertIn("Upcoming public holidays for US:", res.result)
        self.assertIn("Thanksgiving Day", res.result)

        # Protect against non-list dict
        with patch.object(main, "_request_json", new=AsyncMock(return_value={"err": 1})):
            res_err = await main.get_next_public_holidays(req)
        self.assertIsNone(res_err.result)
        self.assertIn("no upcoming holidays returned for US", res_err.error)

    async def test_get_long_weekends_success_and_dict_protection(self):
        weekends_data = [
            {
                "startDate": "2026-07-03",
                "endDate": "2026-07-05",
                "dayCount": 3,
                "needBridgeDay": False,
                "bridgeDays": None,
            }
        ]
        req = main.LongWeekendRequest(country_code="US", year=2026)
        with patch.object(main, "_request_json", new=AsyncMock(return_value=weekends_data)):
            res = await main.get_long_weekends(req)

        self.assertIsNone(res.error)
        self.assertIn("Long weekends for US in 2026:", res.result)
        self.assertIn("- 2026-07-03 to 2026-07-05: 3 days; no bridge day needed", res.result)

        # Protect against non-list dict
        with patch.object(main, "_request_json", new=AsyncMock(return_value={"err": 1})):
            res_err = await main.get_long_weekends(req)
        self.assertIsNone(res_err.result)
        self.assertIn("no long weekends returned for US in 2026", res_err.error)

    async def test_list_supported_countries(self):
        countries = [
            {"countryCode": "US", "name": "United States"},
            {"countryCode": "DE", "name": "Germany"},
        ]
        with patch.object(main, "_request_json", new=AsyncMock(return_value=countries)):
            res = await main.list_supported_countries()

        self.assertIsNone(res.error)
        self.assertIn("Supported countries:", res.result)
        self.assertIn("- US: United States", res.result)
        self.assertIn("- DE: Germany", res.result)


if __name__ == "__main__":
    unittest.main()
