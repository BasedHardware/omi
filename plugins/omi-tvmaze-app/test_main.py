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


class TVmazeHelperTests(unittest.TestCase):
    def test_strip_html(self):
        self.assertEqual(main._strip_html("<p>Hello <b>world</b></p>"), "Hello world")
        self.assertEqual(main._strip_html(None), "")
        self.assertEqual(main._strip_html(42), "")

    def test_format_show_line(self):
        show = {
            "name": "Severance",
            "premiered": "2022-02-18",
            "network": None,
            "webChannel": {"name": "Apple TV+"},
            "status": "Running",
            "genres": ["Drama", "Sci-Fi"],
            "rating": {"average": 8.4},
        }
        line = main._format_show_line(show)
        self.assertIn("Severance (2022)", line)
        self.assertIn("Apple TV+", line)
        self.assertIn("running", line)
        self.assertIn("8.4/10", line)
        self.assertIn("Drama, Sci-Fi", line)

        self.assertEqual(main._format_show_line({"name": "Bare"}), "Bare")
        self.assertEqual(main._format_show_line(None), "Unknown show")

    def test_format_episode(self):
        ep = {"name": "Pilot", "season": 1, "number": 2, "airdate": "2026-09-20", "airtime": "21:00"}
        self.assertEqual(main._format_episode(ep), '"Pilot" (S01E02) — 2026-09-20 21:00')
        self.assertEqual(main._format_episode({"name": "X"}), '"X" — date TBD')
        self.assertEqual(main._format_episode(None), "")

    def test_clean_query(self):
        self.assertEqual(main._clean_query("  the   bear  "), "the bear")


class TVmazeEndpointTests(unittest.IsolatedAsyncioTestCase):
    async def test_search_shows_formats_results(self):
        payload = [
            {"show": {"name": "The Bear", "premiered": "2022-06-23", "network": {"name": "Hulu"},
                      "status": "Running", "genres": ["Drama"], "rating": {"average": 8.5}}},
            {"show": {"name": "The Bear Family"}},
        ]
        req = main.ShowSearchRequest(query="the bear")
        with patch.object(main, "_request_json", new=AsyncMock(return_value=payload)):
            res = await main.search_shows(req)

        self.assertIsNone(res.error)
        self.assertIn("Top results for 'the bear':", res.result)
        self.assertIn("The Bear (2022)", res.result)
        self.assertIn("Hulu", res.result)

    async def test_search_shows_empty(self):
        req = main.ShowSearchRequest(query="zzz-no-such-show")
        with patch.object(main, "_request_json", new=AsyncMock(return_value=[])):
            res = await main.search_shows(req)
        self.assertIsNone(res.error)
        self.assertIn("No shows found", res.result)

    async def test_next_episode_running_show(self):
        show = {"id": 1, "name": "Severance"}
        detail = {
            "name": "Severance",
            "status": "Running",
            "premiered": "2022-02-18",
            "webChannel": {"name": "Apple TV+"},
            "genres": ["Drama"],
            "rating": {"average": 8.4},
            "_embedded": {
                "nextepisode": {"name": "New Ep", "season": 3, "number": 1,
                                "airdate": "2027-01-01", "airtime": "21:00"},
                "previousepisode": {"name": "Old Ep", "season": 2, "number": 10,
                                    "airdate": "2025-03-21", "airtime": "21:00"},
            },
        }
        req = main.NextEpisodeRequest(show="severance")
        with patch.object(main, "_search_show", new=AsyncMock(return_value=(show, None))), \
             patch.object(main, "_request_json", new=AsyncMock(return_value=detail)):
            res = await main.get_next_episode(req)

        self.assertIsNone(res.error)
        self.assertIn("Severance", res.result)
        self.assertIn('Next episode: "New Ep" (S03E01) — 2027-01-01 21:00', res.result)
        self.assertIn('Latest episode: "Old Ep" (S02E10) — 2025-03-21 21:00', res.result)

    async def test_next_episode_ended_show(self):
        show = {"id": 2, "name": "Breaking Bad"}
        detail = {
            "name": "Breaking Bad",
            "status": "Ended",
            "genres": [],
            "rating": {},
            "_embedded": {
                "previousepisode": {"name": "Felina", "season": 5, "number": 16,
                                    "airdate": "2013-09-29", "airtime": "21:00"},
            },
        }
        req = main.NextEpisodeRequest(show="breaking bad")
        with patch.object(main, "_search_show", new=AsyncMock(return_value=(show, None))), \
             patch.object(main, "_request_json", new=AsyncMock(return_value=detail)):
            res = await main.get_next_episode(req)

        self.assertIsNone(res.error)
        self.assertIn("the show is ended", res.result)
        self.assertIn('"Felina" (S05E16)', res.result)

    async def test_next_episode_no_match(self):
        req = main.NextEpisodeRequest(show="not a real show zzz")
        with patch.object(main, "_search_show", new=AsyncMock(return_value=(None, "no TVmaze result"))):
            res = await main.get_next_episode(req)
        self.assertIsNotNone(res.error)

    async def test_schedule_formats_items(self):
        payload = [
            {"name": "Ep One", "season": 1, "number": 1, "airtime": "20:00",
             "show": {"name": "Show A", "network": {"name": "NBC"}}},
            {"name": "Ep Two", "season": 4, "number": 3, "airtime": "21:30",
             "show": {"name": "Show B", "webChannel": {"name": "Netflix"}}},
        ]
        req = main.ScheduleRequest(country="us")
        with patch.object(main, "_request_json", new=AsyncMock(return_value=payload)):
            res = await main.get_tonights_schedule(req)

        self.assertIsNone(res.error)
        self.assertIn("Tonight's schedule (US,", res.result)
        self.assertIn('20:00 [NBC] Show A: "Ep One"', res.result)
        self.assertIn('21:30 [Netflix] Show B: "Ep Two"', res.result)

    async def test_schedule_bad_country(self):
        req = main.ScheduleRequest(country="!!")
        res = await main.get_tonights_schedule(req)
        self.assertIsNotNone(res.error)

    async def test_schedule_empty(self):
        req = main.ScheduleRequest(country="GB")
        with patch.object(main, "_request_json", new=AsyncMock(return_value=[])):
            res = await main.get_tonights_schedule(req)
        self.assertIsNone(res.error)
        self.assertIn("No scheduled episodes", res.result)


if __name__ == "__main__":
    unittest.main()
