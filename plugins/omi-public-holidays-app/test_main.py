"""
Hermetic test suite for the Public Holidays integration app.

Exercises manifest schema compliance, holiday formatting, country normalization,
and tool endpoints without live network requests.
Runs cleanly under pure standard library Python (including python3 -S).
"""

from __future__ import annotations

import asyncio
import importlib.util
from pathlib import Path
import sys
from types import ModuleType
import unittest
from unittest.mock import AsyncMock, Mock, patch


def load_app():
    class FastAPIState:
        def __init__(self):
            self.http_client = Mock()

    class FastAPI:
        def __init__(self, **kwargs):
            self.state = FastAPIState()

        def get(self, *args, **kwargs):
            return lambda handler: handler

        post = get

        def exception_handler(self, *args, **kwargs):
            return lambda handler: handler

    class BaseModel:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

        def model_dump(self):
            return self.__dict__

    fastapi = ModuleType("fastapi")
    fastapi.FastAPI = FastAPI
    fastapi.Request = Mock()

    exceptions = ModuleType("fastapi.exceptions")
    exceptions.RequestValidationError = type("RequestValidationError", (Exception,), {})
    fastapi.exceptions = exceptions

    responses = ModuleType("fastapi.responses")
    responses.HTMLResponse = str
    responses.JSONResponse = lambda **kwargs: kwargs

    pydantic = ModuleType("pydantic")
    pydantic.BaseModel = BaseModel
    pydantic.Field = lambda default=None, **kwargs: default
    pydantic.field_validator = lambda *args, **kwargs: lambda f: f

    httpx = ModuleType("httpx")
    httpx.AsyncClient = Mock()
    httpx.HTTPError = type("HTTPError", (Exception,), {})

    stubs = {
        "fastapi": fastapi,
        "fastapi.exceptions": exceptions,
        "fastapi.responses": responses,
        "pydantic": pydantic,
        "httpx": httpx,
    }

    app_path = Path(__file__).resolve().parent / "main.py"
    spec = importlib.util.spec_from_file_location("holidays_main", app_path)
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, stubs):
        spec.loader.exec_module(module)
    return module, stubs


app_module, stubs = load_app()


class PublicHolidaysAppTests(unittest.TestCase):
    def test_manifest_schema_compliance(self):
        coro = app_module.omi_tools()
        manifest = asyncio.run(coro)
        self.assertIn("tools", manifest)
        self.assertEqual(len(manifest["tools"]), 4)

        for tool in manifest["tools"]:
            self.assertIn("name", tool)
            self.assertIn("description", tool)
            self.assertIn("parameters", tool)
            params = tool["parameters"]
            self.assertEqual(params.get("type"), "object")
            self.assertIn("properties", params)
            self.assertIn("required", params)

    def test_normalize_country_code(self):
        self.assertEqual(app_module._normalize_country_code("us"), "US")
        self.assertEqual(app_module._normalize_country_code("  de "), "DE")
        with self.assertRaises(ValueError):
            app_module._normalize_country_code("USA")
        with self.assertRaises(ValueError):
            app_module._normalize_country_code("12")

    def test_format_holiday(self):
        holiday = {
            "date": "2026-01-01",
            "name": "New Year's Day",
            "localName": "New Year's Day",
            "global": True,
            "types": ["Public"],
        }
        res = app_module._format_holiday(holiday)
        self.assertIn("2026-01-01", res)
        self.assertIn("New Year's Day", res)
        self.assertIn("global", res)

    def test_format_long_weekend(self):
        weekend = {
            "startDate": "2026-05-01",
            "endDate": "2026-05-03",
            "dayCount": 3,
            "needBridgeDay": False,
        }
        res = app_module._format_long_weekend(weekend)
        self.assertIn("2026-05-01 to 2026-05-03", res)
        self.assertIn("3 days", res)
        self.assertIn("no bridge day needed", res)

    def test_get_public_holidays_success(self):
        req = app_module.HolidayRequest(country_code="US", year=2026, limit=5)
        mock_data = [
            {"date": "2026-01-01", "name": "New Year's Day", "localName": "New Year's Day", "global": True}
        ]
        with patch.object(app_module, "_request_json", new=AsyncMock(return_value=mock_data)):
            resp = asyncio.run(app_module.get_public_holidays(req))
            self.assertIn("Public holidays for US in 2026", resp.result)
            self.assertIn("New Year's Day", resp.result)

    def test_get_public_holidays_empty(self):
        req = app_module.HolidayRequest(country_code="US", year=2026, limit=5)
        with patch.object(app_module, "_request_json", new=AsyncMock(return_value=[])):
            resp = asyncio.run(app_module.get_public_holidays(req))
            self.assertIn("no holidays returned", resp.error)

    def test_list_supported_countries_success(self):
        mock_countries = [
            {"countryCode": "US", "name": "United States"},
            {"countryCode": "DE", "name": "Germany"},
        ]
        with patch.object(app_module, "_request_json", new=AsyncMock(return_value=mock_countries)):
            resp = asyncio.run(app_module.list_supported_countries())
            self.assertIn("Supported countries:", resp.result)
            self.assertIn("United States", resp.result)


if __name__ == "__main__":
    unittest.main()
