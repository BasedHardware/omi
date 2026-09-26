"""Hermetic unit tests for Omi World Universities App."""

from __future__ import annotations

import asyncio
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import AsyncMock, patch

# Provide lightweight stubs for third-party runtime dependencies so test_main.py
# runs hermetically on any clean standard library Python environment without
# requiring FastAPI, httpx, or Pydantic to be installed.
if "httpx" not in sys.modules:
    try:
        import httpx  # type: ignore
    except ImportError:
        httpx = types.ModuleType("httpx")

        class HTTPError(Exception):
            pass

        class HTTPStatusError(HTTPError):
            def __init__(self, message="", request=None, response=None):
                super().__init__(message)
                self.response = response or types.SimpleNamespace(status_code=500)

        class RequestError(HTTPError):
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

            async def aclose(self):
                pass

        httpx.HTTPError = HTTPError
        httpx.HTTPStatusError = HTTPStatusError
        httpx.RequestError = RequestError
        httpx.AsyncClient = AsyncClient
        sys.modules["httpx"] = httpx

if "fastapi" not in sys.modules:
    try:
        import fastapi  # type: ignore
        import fastapi.responses  # type: ignore
    except ImportError:
        fastapi = types.ModuleType("fastapi")

        class FastAPI:
            def __init__(self, *args, **kwargs):
                pass

            def get(self, *args, **kwargs):
                return lambda f: f

            def post(self, *args, **kwargs):
                return lambda f: f

        fastapi.FastAPI = FastAPI
        fastapi.Query = lambda default=None, **kwargs: default
        fastapi.status = types.SimpleNamespace(HTTP_200_OK=200, HTTP_422_UNPROCESSABLE_ENTITY=422)
        sys.modules["fastapi"] = fastapi

        responses = types.ModuleType("fastapi.responses")

        class HTMLResponse:
            def __init__(self, content="", status_code=200):
                self.content = content
                self.status_code = status_code

        class JSONResponse:
            def __init__(self, content=None, status_code=200):
                self.content = content or {}
                self.status_code = status_code

        responses.HTMLResponse = HTMLResponse
        responses.JSONResponse = JSONResponse
        sys.modules["fastapi.responses"] = responses
        fastapi.responses = responses

if "pydantic" not in sys.modules:
    try:
        import pydantic  # type: ignore
    except ImportError:
        pydantic = types.ModuleType("pydantic")

        def Field(default=None, **kwargs):
            return default

        class BaseModel:
            def __init__(self, **kwargs):
                for cls in reversed(self.__class__.__mro__):
                    for k, v in getattr(cls, "__dict__", {}).items():
                        if not k.startswith("_") and not callable(v):
                            setattr(self, k, None if v is ... else v)
                for k, v in kwargs.items():
                    setattr(self, k, v)

        pydantic.BaseModel = BaseModel
        pydantic.Field = Field
        sys.modules["pydantic"] = pydantic

# Add plugin directory to path so main can be loaded hermetically
PLUGIN_DIR = Path(__file__).resolve().parent
if str(PLUGIN_DIR) not in sys.path:
    sys.path.insert(0, str(PLUGIN_DIR))

import main

SAMPLE_UNIVERSITIES = [
    {
        "name": "Stanford University",
        "country": "United States",
        "alpha_two_code": "US",
        "state-province": "California",
        "domains": ["stanford.edu"],
        "web_pages": ["http://www.stanford.edu/"],
    },
    {
        "name": "University of Oxford",
        "country": "United Kingdom",
        "alpha_two_code": "GB",
        "state-province": "Oxfordshire",
        "domains": ["ox.ac.uk"],
        "web_pages": ["http://www.ox.ac.uk/"],
    },
]


class UniversitiesAppTests(unittest.TestCase):
    def test_format_university_card(self) -> None:
        card = main.format_university_card(SAMPLE_UNIVERSITIES[0])
        self.assertIn("🏫 Stanford University", card)
        self.assertIn("📍 Location: California, United States, (US)", card)
        self.assertIn("🌐 Domain: stanford.edu", card)
        self.assertIn("🔗 Website: http://www.stanford.edu/", card)

    def test_format_university_card_minimal_fields(self) -> None:
        card = main.format_university_card({"name": "Minimal College", "country": "Canada"})
        self.assertIn("🏫 Minimal College", card)
        self.assertIn("📍 Location: Canada", card)
        self.assertNotIn("🌐 Domain", card)

    def test_manifest_endpoint(self) -> None:
        res = asyncio.run(main.manifest())
        self.assertEqual(res.content["schema_version"], "v1")
        self.assertEqual(res.content["name_for_model"], "world_universities_app")
        self.assertIn("description_for_human", res.content)

    def test_ai_plugin_manifest_endpoint(self) -> None:
        res = asyncio.run(main.ai_plugin_manifest())
        self.assertEqual(res.content["name_for_model"], "world_universities_app")

    def test_health_endpoint(self) -> None:
        res = asyncio.run(main.health())
        self.assertEqual(res, {"status": "ok", "app": "omi-universities-app"})

    def test_privacy_endpoint(self) -> None:
        res = asyncio.run(main.privacy())
        self.assertIn("Privacy Policy", res.content)

    def test_index_endpoint(self) -> None:
        res = asyncio.run(main.index())
        self.assertIn("Omi World Universities App", res.content)

    @patch("main.fetch_universities")
    def test_search_universities_tool_success(self, mock_fetch: AsyncMock) -> None:
        mock_fetch.return_value = SAMPLE_UNIVERSITIES
        req = main.SearchUniversitiesRequest(query="Stanford", limit=5)
        res = asyncio.run(main.tool_search_universities(req))
        self.assertIsNone(res.error)
        self.assertIn("Stanford University", res.result)
        self.assertIn("Global Universities Search", res.result)

    @patch("main.fetch_universities")
    def test_search_universities_tool_empty(self, mock_fetch: AsyncMock) -> None:
        mock_fetch.return_value = []
        req = main.SearchUniversitiesRequest(query="NonExistent123")
        res = asyncio.run(main.tool_search_universities(req))
        self.assertIsNone(res.error)
        self.assertIn("No universities found", res.result)

    def test_search_universities_empty_query(self) -> None:
        req = main.SearchUniversitiesRequest(query="   ")
        res = asyncio.run(main.tool_search_universities(req))
        self.assertEqual(res.error, "Search query cannot be empty.")

    @patch("main.fetch_universities")
    def test_universities_by_country_tool_success(self, mock_fetch: AsyncMock) -> None:
        mock_fetch.return_value = [SAMPLE_UNIVERSITIES[1]]
        req = main.UniversitiesByCountryRequest(country="United Kingdom", limit=10)
        res = asyncio.run(main.tool_universities_by_country(req))
        self.assertIsNone(res.error)
        self.assertIn("Universities in United Kingdom", res.result)
        self.assertIn("University of Oxford", res.result)

    @patch("main.fetch_universities")
    def test_universities_by_country_empty(self, mock_fetch: AsyncMock) -> None:
        mock_fetch.return_value = []
        req = main.UniversitiesByCountryRequest(country="Atlantis")
        res = asyncio.run(main.tool_universities_by_country(req))
        self.assertIsNone(res.error)
        self.assertIn("No universities found for country 'Atlantis'", res.result)

    @patch("main.fetch_universities")
    def test_university_details_tool_success(self, mock_fetch: AsyncMock) -> None:
        mock_fetch.return_value = SAMPLE_UNIVERSITIES
        req = main.UniversityDetailsRequest(name="Stanford University")
        res = asyncio.run(main.tool_university_details(req))
        self.assertIsNone(res.error)
        self.assertIn("University Profile: Stanford University", res.result)
        self.assertIn("Domains: stanford.edu", res.result)

    @patch("main.fetch_universities")
    def test_university_details_tool_not_found(self, mock_fetch: AsyncMock) -> None:
        mock_fetch.return_value = []
        req = main.UniversityDetailsRequest(name="Mythical College")
        res = asyncio.run(main.tool_university_details(req))
        self.assertIsNone(res.error)
        self.assertIn("Could not find university details", res.result)

    @patch("main.fetch_universities", side_effect=RuntimeError("API Gateway Timeout"))
    def test_api_error_handling(self, mock_fetch: AsyncMock) -> None:
        req = main.SearchUniversitiesRequest(query="MIT")
        res = asyncio.run(main.tool_search_universities(req))
        self.assertEqual(res.error, "API Gateway Timeout")
        self.assertIsNone(res.result)


if __name__ == "__main__":
    unittest.main()
