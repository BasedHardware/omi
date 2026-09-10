"""Hermetic Hacker News text-cleaning regressions.

Import the production module with framework-only stubs, then exercise its real
cleaner and discussion handler. No network, credentials, or third-party runtime
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
        self.assertEqual(app._clean_text(raw), "Hello & goodbye\n`<vector>`\nnext")


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


if __name__ == "__main__":
    unittest.main()
