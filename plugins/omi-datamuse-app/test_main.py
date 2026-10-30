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


class DatamuseHelperTests(unittest.TestCase):
    def test_extract_words_skips_malformed_rows(self):
        payload = [{"word": "cat"}, {"score": 5}, "bad", {"word": 42}, {"word": "bat"}]
        self.assertEqual(main._extract_words(payload), ["cat", "bat"])
        self.assertEqual(main._extract_words(None), [])
        self.assertEqual(main._extract_words({"word": "x"}), [])
        self.assertEqual(main._extract_words([]), [])

    def test_clean_query(self):
        self.assertEqual(main._clean_query("  light   house "), "light house")


class DatamuseEndpointTests(unittest.IsolatedAsyncioTestCase):
    async def test_find_rhymes(self):
        payload = [{"word": "chime", "score": 1}, {"word": "time", "score": 2}]
        req = main.WordRequest(word="rhyme")
        with patch.object(main, "_request_json", new=AsyncMock(return_value=payload)):
            res = await main.find_rhymes(req)

        self.assertIsNone(res.error)
        self.assertIn("rhyme with 'rhyme'", res.result)
        self.assertIn("chime, time", res.result)

    async def test_find_rhymes_empty(self):
        req = main.WordRequest(word="orange")
        with patch.object(main, "_request_json", new=AsyncMock(return_value=[])):
            res = await main.find_rhymes(req)
        self.assertIsNone(res.error)
        self.assertIn("No rhymes found for 'orange'", res.result)

    async def test_find_related_words_synonym(self):
        payload = [{"word": "sea"}, {"word": "oceanic"}, {"word": "marine"}]
        req = main.RelatedWordsRequest(word="ocean", relation="synonym")
        with patch.object(main, "_request_json", new=AsyncMock(return_value=payload)):
            res = await main.find_related_words(req)

        self.assertIsNone(res.error)
        self.assertIn("Synonyms 'ocean':", res.result)
        self.assertIn("sea, oceanic, marine", res.result)

    async def test_find_related_words_empty(self):
        req = main.RelatedWordsRequest(word="zzzqqq", relation="synonym")
        with patch.object(main, "_request_json", new=AsyncMock(return_value=[])):
            res = await main.find_related_words(req)
        self.assertIsNone(res.error)
        self.assertIn("none found", res.result)

    async def test_suggest_spelling(self):
        payload = [{"word": "elephant"}, {"word": "elephants"}, {"word": "elegant"}]
        req = main.SpellingRequest(partial="eleph")
        with patch.object(main, "_request_json", new=AsyncMock(return_value=payload)):
            res = await main.suggest_spelling(req)

        self.assertIsNone(res.error)
        self.assertIn("Suggestions for 'eleph':", res.result)
        self.assertIn("elephant", res.result)

    async def test_suggest_spelling_empty(self):
        req = main.SpellingRequest(partial="zzzzz")
        with patch.object(main, "_request_json", new=AsyncMock(return_value=[])):
            res = await main.suggest_spelling(req)
        self.assertIsNone(res.error)
        self.assertIn("No suggestions", res.result)


if __name__ == "__main__":
    unittest.main()
