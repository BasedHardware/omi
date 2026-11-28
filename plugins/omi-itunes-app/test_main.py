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

        httpx.HTTPError = HTTPError
        httpx.HTTPStatusError = HTTPStatusError
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
            pass

        responses.HTMLResponse = HTMLResponse
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


class ITunesHelperTests(unittest.TestCase):
    def test_format_duration_ms(self):
        self.assertEqual(main._format_duration_ms(201000), "3:21")
        self.assertEqual(main._format_duration_ms(None), "")
        self.assertEqual(main._format_duration_ms(True), "")
        self.assertEqual(main._format_duration_ms(-5), "")
        self.assertEqual(main._format_duration_ms("x"), "")

    def test_format_song(self):
        item = {
            "trackName": "Get Lucky",
            "artistName": "Daft Punk",
            "collectionName": "Random Access Memories",
            "trackTimeMillis": 368000,
        }
        out = main._format_song(item)
        self.assertIn("Get Lucky — Daft Punk", out)
        self.assertIn("(Random Access Memories)", out)
        self.assertIn("6:08", out)

        # album equal to track is skipped (single)
        single = {"trackName": "Solo", "artistName": "A", "collectionName": "Solo"}
        self.assertNotIn("(Solo)", main._format_song(single))
        self.assertEqual(main._format_song(None), "Unknown track")

    def test_format_podcast(self):
        item = {"collectionName": "Tech Talk", "artistName": "Jane", "primaryGenreName": "Technology"}
        out = main._format_podcast(item)
        self.assertIn("Tech Talk", out)
        self.assertIn("— Jane", out)
        self.assertIn("[Technology]", out)
        self.assertEqual(main._format_podcast({"trackName": "Fallback"}), "Fallback")


class ITunesEndpointTests(unittest.IsolatedAsyncioTestCase):
    async def test_search_songs(self):
        payload = {
            "results": [
                {"trackName": "Song A", "artistName": "X", "collectionName": "Alb", "trackTimeMillis": 60000},
                {"trackName": "Song B", "artistName": "Y"},
            ]
        }
        req = main.SearchRequest(query="test")
        with patch.object(main, "_request_json", new=AsyncMock(return_value=payload)):
            res = await main.search_songs(req)

        self.assertIsNone(res.error)
        self.assertIn("Songs matching 'test':", res.result)
        self.assertIn("Song A — X (Alb) 1:00", res.result)
        self.assertIn("Song B — Y", res.result)

    async def test_search_songs_empty(self):
        req = main.SearchRequest(query="zzzqqq")
        with patch.object(main, "_request_json", new=AsyncMock(return_value={"results": []})):
            res = await main.search_songs(req)
        self.assertIsNone(res.error)
        self.assertIn("No songs found", res.result)

    async def test_search_podcasts(self):
        payload = {"results": [{"collectionName": "My Pod", "artistName": "Host", "primaryGenreName": "Tech"}]}
        req = main.SearchRequest(query="tech")
        with patch.object(main, "_request_json", new=AsyncMock(return_value=payload)):
            res = await main.search_podcasts(req)

        self.assertIsNone(res.error)
        self.assertIn("My Pod — Host [Tech]", res.result)

    async def test_get_artist_top_songs(self):
        search = {"results": [{"artistId": 123, "artistName": "Radiohead"}]}
        lookup = {
            "results": [
                {"wrapperType": "artist", "artistName": "Radiohead"},
                {"kind": "song", "trackName": "Karma Police", "artistName": "Radiohead"},
                {"kind": "song", "trackName": "Creep", "artistName": "Radiohead"},
            ]
        }
        req = main.SearchRequest(query="radiohead")
        mock = AsyncMock(side_effect=[search, lookup])
        with patch.object(main, "_request_json", new=mock):
            res = await main.get_artist_top_songs(req)

        self.assertIsNone(res.error)
        self.assertIn("Top songs by Radiohead:", res.result)
        self.assertIn("Karma Police", res.result)
        self.assertIn("Creep", res.result)
        # artist wrapper row must not be listed as a song
        self.assertNotIn("Unknown artist", res.result)

    async def test_get_artist_top_songs_no_artist(self):
        req = main.SearchRequest(query="zzz no artist")
        with patch.object(main, "_request_json", new=AsyncMock(return_value={"results": []})):
            res = await main.get_artist_top_songs(req)
        self.assertIsNone(res.error)
        self.assertIn("No artist found", res.result)


if __name__ == "__main__":
    unittest.main()
