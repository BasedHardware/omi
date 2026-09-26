"""Hermetic unit tests for Omi Craft Brewery Finder App."""

from __future__ import annotations

import asyncio
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import AsyncMock, patch

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

SAMPLE_BREWERIES = [
    {
        "id": "stone-brewing",
        "name": "Stone Brewing",
        "brewery_type": "regional",
        "address_1": "1999 Citracado Pkwy",
        "city": "Escondido",
        "state_province": "California",
        "postal_code": "92029",
        "country": "United States",
        "phone": "7602947866",
        "website_url": "http://www.stonebrewing.com",
    },
    {
        "id": "sierra-nevada",
        "name": "Sierra Nevada Brewing Co",
        "brewery_type": "regional",
        "address_1": "1075 E 20th St",
        "city": "Chico",
        "state_province": "California",
        "postal_code": "95928",
        "country": "United States",
        "phone": "5308933502",
        "website_url": "http://www.sierranevada.com",
    },
]


class BreweryAppTests(unittest.TestCase):
    def test_format_brewery_card(self) -> None:
        card = main.format_brewery_card(SAMPLE_BREWERIES[0])
        self.assertIn("🍺 **Stone Brewing** (Regional)", card)
        self.assertIn("📍 Address: 1999 Citracado Pkwy, Escondido, California, 92029, United States", card)
        self.assertIn("📞 Phone: 7602947866", card)
        self.assertIn("🌐 Website: http://www.stonebrewing.com", card)

    def test_manifest_endpoint(self) -> None:
        res = asyncio.run(main.manifest())
        self.assertEqual(res.content["schema_version"], "v1")
        self.assertEqual(res.content["name_for_model"], "craft_brewery_finder_app")
        self.assertIn("description_for_human", res.content)

    def test_ai_plugin_manifest_endpoint(self) -> None:
        res = asyncio.run(main.ai_plugin_manifest())
        self.assertEqual(res.content["name_for_model"], "craft_brewery_finder_app")

    def test_health_endpoint(self) -> None:
        res = asyncio.run(main.health())
        self.assertEqual(res, {"status": "ok", "app": "omi-brewery-finder-app"})

    def test_privacy_endpoint(self) -> None:
        res = asyncio.run(main.privacy())
        self.assertIn("Privacy Policy", res.content)

    def test_index_endpoint(self) -> None:
        res = asyncio.run(main.index())
        self.assertIn("Omi Craft Brewery Finder App", res.content)

    @patch("main.fetch_breweries")
    def test_search_breweries_tool_success(self, mock_fetch: AsyncMock) -> None:
        mock_fetch.return_value = SAMPLE_BREWERIES
        req = main.SearchBreweriesRequest(query="Stone", limit=5)
        res = asyncio.run(main.tool_search_breweries(req))
        self.assertIsNone(res.error)
        self.assertIn("Stone Brewing", res.result)
        self.assertIn("Craft Breweries Found", res.result)

    @patch("main.fetch_breweries")
    def test_search_breweries_empty(self, mock_fetch: AsyncMock) -> None:
        mock_fetch.return_value = []
        req = main.SearchBreweriesRequest(query="XYZNonExistentBrewery123")
        res = asyncio.run(main.tool_search_breweries(req))
        self.assertIsNone(res.error)
        self.assertIn("No craft breweries found", res.result)

    def test_search_breweries_empty_query(self) -> None:
        req = main.SearchBreweriesRequest(query="   ")
        res = asyncio.run(main.tool_search_breweries(req))
        self.assertEqual(res.error, "Search query cannot be empty.")

    @patch("main.fetch_breweries")
    def test_breweries_by_location_success(self, mock_fetch: AsyncMock) -> None:
        mock_fetch.return_value = SAMPLE_BREWERIES
        req = main.BreweriesByLocationRequest(city="San Diego", state="California", limit=5)
        res = asyncio.run(main.tool_breweries_by_location(req))
        self.assertIsNone(res.error)
        self.assertIn("Craft Breweries in San Diego, California", res.result)
        self.assertIn("Stone Brewing", res.result)

    def test_breweries_by_location_missing_params(self) -> None:
        req = main.BreweriesByLocationRequest()
        res = asyncio.run(main.tool_breweries_by_location(req))
        self.assertEqual(res.error, "Please specify at least a city, state, or country.")

    @patch("main.fetch_breweries")
    def test_random_brewery_success(self, mock_fetch: AsyncMock) -> None:
        mock_fetch.return_value = [SAMPLE_BREWERIES[0]]
        req = main.RandomBreweryRequest(size=1)
        res = asyncio.run(main.tool_random_brewery(req))
        self.assertIsNone(res.error)
        self.assertIn("Random Craft Brewery Discovery", res.result)
        self.assertIn("Stone Brewing", res.result)

    @patch("main.fetch_breweries", side_effect=RuntimeError("Connection Reset"))
    def test_api_error_handling(self, mock_fetch: AsyncMock) -> None:
        req = main.SearchBreweriesRequest(query="Lagunitas")
        res = asyncio.run(main.tool_search_breweries(req))
        self.assertEqual(res.error, "Connection Reset")
        self.assertIsNone(res.result)


if __name__ == "__main__":
    unittest.main()
