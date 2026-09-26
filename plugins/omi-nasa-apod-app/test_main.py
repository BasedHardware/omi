"""Hermetic unit tests for Omi NASA Astronomy & Space App."""

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

SAMPLE_APOD = {
    "title": "Pillars of Creation",
    "date": "2026-04-12",
    "explanation": "Massive columns of interstellar gas and dust photographed by the James Webb Space Telescope.",
    "hdurl": "https://apod.nasa.gov/apod/image/2604/pillars_jwst_hd.jpg",
    "url": "https://apod.nasa.gov/apod/image/2604/pillars_jwst.jpg",
    "media_type": "image",
    "copyright": "NASA / ESA / CSA",
}

SAMPLE_IMAGE_SEARCH = [
    {
        "data": [
            {
                "title": "James Webb First Deep Field",
                "description": "Deepest and sharpest infrared image of the distant universe so far.",
                "date_created": "2022-07-12T00:00:00Z",
                "nasa_id": "PIA25327",
            }
        ],
        "links": [{"href": "https://images-assets.nasa.gov/image/PIA25327/PIA25327~orig.jpg"}],
    }
]


class NasaAppTests(unittest.TestCase):
    def test_format_apod_result(self) -> None:
        formatted = main.format_apod_result(SAMPLE_APOD)
        self.assertIn("🌌 **Pillars of Creation** (2026-04-12)", formatted)
        self.assertIn("James Webb Space Telescope", formatted)
        self.assertIn("📸 Image Credit / Copyright: NASA / ESA / CSA", formatted)
        self.assertIn("🔗 View Image: https://apod.nasa.gov/apod/image/2604/pillars_jwst_hd.jpg", formatted)

    def test_manifest_endpoint(self) -> None:
        res = asyncio.run(main.manifest())
        self.assertEqual(res.content["schema_version"], "v1")
        self.assertEqual(res.content["name_for_model"], "nasa_space_app")
        self.assertIn("description_for_human", res.content)

    def test_ai_plugin_manifest_endpoint(self) -> None:
        res = asyncio.run(main.ai_plugin_manifest())
        self.assertEqual(res.content["name_for_model"], "nasa_space_app")

    def test_health_endpoint(self) -> None:
        res = asyncio.run(main.health())
        self.assertEqual(res, {"status": "ok", "app": "omi-nasa-apod-app"})

    def test_privacy_endpoint(self) -> None:
        res = asyncio.run(main.privacy())
        self.assertIn("Privacy Policy", res.content)

    def test_index_endpoint(self) -> None:
        res = asyncio.run(main.index())
        self.assertIn("Omi NASA Space App", res.content)

    @patch("main.fetch_apod")
    def test_apod_tool_single(self, mock_fetch: AsyncMock) -> None:
        mock_fetch.return_value = SAMPLE_APOD
        req = main.ApodRequest(date="2026-04-12")
        res = asyncio.run(main.tool_astronomy_picture_of_the_day(req))
        self.assertIsNone(res.error)
        self.assertIn("Pillars of Creation", res.result)

    @patch("main.fetch_apod")
    def test_apod_tool_multiple_count(self, mock_fetch: AsyncMock) -> None:
        mock_fetch.return_value = [SAMPLE_APOD, SAMPLE_APOD]
        req = main.ApodRequest(count=2)
        res = asyncio.run(main.tool_astronomy_picture_of_the_day(req))
        self.assertIsNone(res.error)
        self.assertIn("NASA Astronomy Pictures (2)", res.result)

    @patch("main.fetch_nasa_image_library")
    def test_search_nasa_images_success(self, mock_fetch: AsyncMock) -> None:
        mock_fetch.return_value = SAMPLE_IMAGE_SEARCH
        req = main.NasaImageSearchRequest(query="James Webb", limit=3)
        res = asyncio.run(main.tool_search_nasa_images(req))
        self.assertIsNone(res.error)
        self.assertIn("James Webb First Deep Field", res.result)
        self.assertIn("NASA Mission Imagery Search", res.result)

    @patch("main.fetch_nasa_image_library")
    def test_search_nasa_images_empty(self, mock_fetch: AsyncMock) -> None:
        mock_fetch.return_value = []
        req = main.NasaImageSearchRequest(query="NonExistentMission123")
        res = asyncio.run(main.tool_search_nasa_images(req))
        self.assertIsNone(res.error)
        self.assertIn("No NASA mission media found", res.result)

    def test_search_nasa_images_empty_query(self) -> None:
        req = main.NasaImageSearchRequest(query="   ")
        res = asyncio.run(main.tool_search_nasa_images(req))
        self.assertEqual(res.error, "Search query cannot be empty.")

    @patch("main.fetch_apod", side_effect=RuntimeError("NASA API Rate Limit Reached"))
    def test_api_error_handling(self, mock_fetch: AsyncMock) -> None:
        req = main.ApodRequest()
        res = asyncio.run(main.tool_astronomy_picture_of_the_day(req))
        self.assertEqual(res.error, "NASA API Rate Limit Reached")
        self.assertIsNone(res.result)


if __name__ == "__main__":
    unittest.main()
