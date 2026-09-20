import importlib.util
from pathlib import Path
import sys
import unittest
from unittest.mock import AsyncMock, patch

import fastapi
from fastapi import responses
import httpx
import pydantic


def load_app():
    target = Path(__file__).resolve().parent / "main.py"
    spec = importlib.util.spec_from_file_location("wikipedia_main", target)
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


main = load_app()
app = main.app


class HTTPContractTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.requests = []
        self.provider_status = 200
        self.provider_payload = {}

        async def fake_get(url, params=None, headers=None):
            req = httpx.Request("GET", url, params=params, headers=headers)
            self.requests.append(req)
            if self.provider_status >= 400:
                resp = httpx.Response(self.provider_status, request=req)
                resp.raise_for_status()
                return resp
            return httpx.Response(200, json=self.provider_payload, request=req)

        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        )
        self.get_patch = patch.object(httpx.AsyncClient, "get", side_effect=fake_get)
        self.get_patch.start()

    async def asyncTearDown(self):
        self.get_patch.stop()
        await self.client.aclose()

    async def post(self, path, **kwargs):
        response = await self.client.post(f"/tools/{path}", **kwargs)
        self.assertEqual(response.status_code, 200)
        return response.json()

    async def test_search_articles_non_string_query(self):
        cases = [2026, 3.5, ["ai"], {"q": "ai"}, True, False]
        for bad_query in cases:
            with self.subTest(query=bad_query):
                self.requests.clear()
                body = await self.post("search_articles", json={"query": bad_query})
                self.assertEqual(body, {"result": None, "error": "Missing required field: query"})
                self.assertEqual(self.requests, [])

    async def test_get_article_summary_non_string_title(self):
        cases = [2026, 3.5, ["ai"], {"q": "ai"}, True, False]
        for bad_title in cases:
            with self.subTest(title=bad_title):
                self.requests.clear()
                body = await self.post("get_article_summary", json={"title": bad_title})
                self.assertEqual(body, {"result": None, "error": "Missing required field: title"})
                self.assertEqual(self.requests, [])

    async def test_path_traversal_in_article_summary_is_encoded(self):
        self.provider_payload = {"type": "standard", "title": "Test", "extract": "A test"}
        await self.post("get_article_summary", json={"title": "../../../../w/api.php"})
        self.assertEqual(len(self.requests), 1)
        # Slashes must be percent-encoded to %2F in path segment
        self.assertNotIn("/../../../../", str(self.requests[0].url))
        self.assertIn("%2F", str(self.requests[0].url))

    async def test_safe_language_coerced_in_requests(self):
        self.provider_payload = {"query": {"search": []}}
        await self.post("search_articles", json={"query": "test", "language": "-invalid-"})
        self.assertEqual(len(self.requests), 1)
        self.assertEqual(self.requests[0].url.host, "en.wikipedia.org")


if __name__ == "__main__":
    unittest.main()
