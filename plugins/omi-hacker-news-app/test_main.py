"""Hermetic Hacker News text-cleaning and input-hardening regressions.

Import the production module with framework-only stubs, then exercise its real
cleaner, formatting, and tool handlers. No network, credentials, or third-party runtime
packages are required.
"""

import importlib.util
from pathlib import Path
import sys
from types import ModuleType
import unittest
from unittest.mock import AsyncMock, patch


def load_app():
    class FastAPI:
        def __init__(self, **kwargs):
            pass

        def get(self, *args, **kwargs):
            return lambda handler: handler

        post = get

    class BaseModel:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    class HTTPError(Exception):
        pass

    httpx = ModuleType("httpx")
    httpx.AsyncClient = object
    httpx.HTTPError = HTTPError
    fastapi = ModuleType("fastapi")
    fastapi.FastAPI = FastAPI
    responses = ModuleType("fastapi.responses")
    responses.HTMLResponse = str
    pydantic = ModuleType("pydantic")
    pydantic.BaseModel = BaseModel

    spec = importlib.util.spec_from_file_location("hacker_news_app", Path(__file__).with_name("main.py"))
    module = importlib.util.module_from_spec(spec)
    with patch.dict(
        sys.modules,
        {
            "httpx": httpx,
            "fastapi": fastapi,
            "fastapi.responses": responses,
            "pydantic": pydantic,
        },
    ):
        spec.loader.exec_module(module)
    return module


app = load_app()


class CleanTextTests(unittest.TestCase):
    def test_preserves_escaped_literal_angle_brackets(self):
        cases = {
            "Use &lt;vector&gt; for this.": "Use <vector> for this.",
            "if a &lt; b and c &gt; d": "if a < b and c > d",
            "&#60;b&#62;literal&#60;/b&#62;": "<b>literal</b>",
        }
        for raw, expected in cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(app._clean_text(raw), expected)

    def test_removes_real_markup_but_preserves_code_text(self):
        raw = "<p>Hello &amp; goodbye</p><p><code>&lt;vector&gt;</code><br>next</p>"
        self.assertEqual(app._clean_text(raw), "Hello & goodbye\n\n`<vector>`\nnext")


class SafeLimitTests(unittest.TestCase):
    def test_default_on_none_or_empty(self):
        self.assertEqual(app._safe_limit(None), 10)
        self.assertEqual(app._safe_limit(""), 10)

    def test_rejects_booleans(self):
        self.assertEqual(app._safe_limit(True), 10)
        self.assertEqual(app._safe_limit(False), 10)

    def test_clamps_bounds(self):
        self.assertEqual(app._safe_limit(-5), 1)
        self.assertEqual(app._safe_limit(0), 1)
        self.assertEqual(app._safe_limit(5), 5)
        self.assertEqual(app._safe_limit(50), 20)

    def test_unparseable_strings(self):
        self.assertEqual(app._safe_limit("invalid"), 10)
        self.assertEqual(app._safe_limit([1, 2]), 10)


class FormatStoryTests(unittest.TestCase):
    def test_format_story_handles_missing_object_id(self):
        hit = {
            "title": "A Great Story",
            "author": "tester",
            "points": 42,
            "num_comments": 15,
            "objectID": None,
            "story_id": None,
            "url": "https://example.com",
        }
        formatted = app._format_story(hit, 1)
        self.assertIn("1. A Great Story", formatted)
        self.assertIn("by tester | 42 points | 15 comments", formatted)
        self.assertNotIn("id=None", formatted)


class DiscussionHandlerTests(unittest.IsolatedAsyncioTestCase):
    async def test_discussion_preserves_escaped_text_in_post_and_comment(self):
        item = {
            "title": "Escaped text",
            "author": "alice",
            "points": 7,
            "url": "https://example.test/story",
            "text": "<p>Use &lt;vector&gt; here.</p>",
            "children": [
                {
                    "author": "bob",
                    "text": "<p>if a &lt; b and c &gt; d</p>",
                }
            ],
        }
        provider = AsyncMock(return_value=item)
        with patch.object(app, "_request_json", provider):
            response = await app.get_discussion({"item_id": 9995409, "comment_limit": 5})

        self.assertIsNone(response.error)
        self.assertIn("Post text:\nUse <vector> here.", response.result)
        self.assertIn("1. bob: if a < b and c > d", response.result)
        provider.assert_awaited_once_with("/items/9995409")

    async def test_discussion_rejects_missing_and_invalid_item_ids(self):
        cases = [None, "", True, False, -1, 0, "not-a-number"]
        for bad_id in cases:
            with self.subTest(bad_id=bad_id):
                response = await app.get_discussion({"item_id": bad_id})
                self.assertIsNotNone(response.error)

    async def test_handles_non_dict_payload_gracefully(self):
        with patch.object(app, "_request_json", AsyncMock(return_value={"hits": []})):
            response = await app.get_front_page(None)
            self.assertIsNotNone(response)

        response_search = await app.search_stories(None)
        self.assertEqual(response_search.error, "Missing required field: query")

        response_discussion = await app.get_discussion(None)
        self.assertEqual(response_discussion.error, "Missing required field: item_id")


if __name__ == "__main__":
    unittest.main()
