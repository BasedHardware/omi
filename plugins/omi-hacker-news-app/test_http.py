"""HTTP contract regressions using real FastAPI routing and response models.

Install this plugin's requirements.txt, then run this file. Only the outbound
Algolia transport is replaced; requests to the app use HTTPX ASGITransport.
No live network, credentials, or framework stubs are used.
"""

import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

import httpx


_spec = importlib.util.spec_from_file_location(
    "hacker_news_http_app", Path(__file__).with_name("main.py")
)
main = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(main)

_REAL_ASYNC_CLIENT = httpx.AsyncClient
_ROUTES = (
    ("get_front_page", {"limit": 2}, "Hacker News request failed:"),
    ("search_stories", {"query": "python"}, "Hacker News search failed:"),
    ("get_discussion", {"item_id": 8863}, "Hacker News discussion request failed:"),
)


class HTTPContractTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.requests = []
        self.provider_status = 200
        self.provider_timeout = False
        self.provider_empty = False
        self.client = _REAL_ASYNC_CLIENT(
            transport=httpx.ASGITransport(app=main.app),
            base_url="http://test.local",
        )
        # Capture the real class before patching its constructor in main's module.
        # Every provider client still has real HTTPX request/response processing.
        self.client_patch = patch.object(
            main.httpx,
            "AsyncClient",
            side_effect=lambda **kwargs: _REAL_ASYNC_CLIENT(
                transport=httpx.MockTransport(self.provider), **kwargs
            ),
        )
        self.client_patch.start()
        self.addCleanup(self.client_patch.stop)
        self.addAsyncCleanup(self.client.aclose)

    def provider(self, request):
        self.requests.append(request)
        self.assertEqual(request.url.host, "hn.algolia.com")
        self.assertEqual(request.url.scheme, "https")
        if self.provider_timeout:
            raise httpx.ReadTimeout("fixture timeout", request=request)
        if self.provider_status != 200:
            return httpx.Response(self.provider_status, json={"message": "fixture"})
        if request.url.path.startswith("/api/v1/items/"):
            return httpx.Response(
                200,
                json={
                    "title": "Discussion fixture",
                    "author": "alice",
                    "points": 7,
                    "text": "<p>Use &lt;vector&gt; here.</p>",
                    "children": [
                        {"author": "bob", "text": "<p>First comment</p>"},
                        {"author": "carol", "text": "<p>Second comment</p>"},
                    ],
                },
            )
        self.assertIn(request.url.path, ("/api/v1/search", "/api/v1/search_by_date"))
        hits = [] if self.provider_empty else [
            {"title": f"Story {n}", "author": "alice", "objectID": str(n)}
            for n in range(1, 4)
        ]
        return httpx.Response(200, json={"hits": hits})

    async def post(self, route, **kwargs):
        response = await self.client.post(f"/tools/{route}", **kwargs)
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(set(body), {"result", "error"})
        return body

    async def test_front_page_reads_limit_from_json_body(self):
        body = await self.post("get_front_page", json={"limit": 2})
        self.assertIsNone(body["error"])
        self.assertIn("2. Story 2", body["result"])
        self.assertNotIn("3. Story 3", body["result"])
        self.assertEqual(len(self.requests), 1)
        self.assertEqual(dict(self.requests[0].url.params), {
            "tags": "front_page", "hitsPerPage": "2"
        })

    async def test_search_reads_query_sort_and_limit_from_json_body(self):
        body = await self.post(
            "search_stories", json={"query": " python ", "sort_by": "date", "limit": 2}
        )
        self.assertIsNone(body["error"])
        self.assertIn("Hacker News stories for 'python'", body["result"])
        self.assertNotIn("3. Story 3", body["result"])
        self.assertEqual(len(self.requests), 1)
        self.assertEqual(self.requests[0].url.path, "/api/v1/search_by_date")
        self.assertEqual(dict(self.requests[0].url.params), {
            "query": "python", "tags": "story", "hitsPerPage": "2"
        })

    async def test_discussion_reads_id_and_comment_limit_from_json_body(self):
        body = await self.post("get_discussion", json={"item_id": 8863, "comment_limit": 1})
        self.assertIsNone(body["error"])
        self.assertIn("Post text:\nUse <vector> here.", body["result"])
        self.assertIn("Top 1 comments:", body["result"])
        self.assertIn("1. bob: First comment", body["result"])
        self.assertNotIn("Second comment", body["result"])
        self.assertEqual(len(self.requests), 1)
        self.assertEqual(self.requests[0].url.path, "/api/v1/items/8863")

    async def test_body_is_not_replaced_by_query_parameters(self):
        body = await self.post(
            "search_stories",
            params={"payload": '{"query":"wrong"}', "query": "wrong"},
            json={"query": "right", "limit": 1},
        )
        self.assertIsNone(body["error"])
        self.assertEqual(len(self.requests), 1)
        self.assertEqual(self.requests[0].url.params["query"], "right")
        self.assertEqual(self.requests[0].url.params["hitsPerPage"], "1")

    async def test_omitted_null_and_non_object_bodies_keep_existing_defaults(self):
        cases = [{}, *[
            {"content": value, "headers": {"Content-Type": "application/json"}}
            for value in ("null", "[]", '"text"', "5", "true", "{}")
        ]]
        for kwargs in cases:
            with self.subTest(body=kwargs):
                self.requests.clear()
                front = await self.post("get_front_page", **kwargs)
                self.assertIsNone(front["error"])
                self.assertEqual(len(self.requests), 1)
                self.assertEqual(self.requests[0].url.params["hitsPerPage"], "10")
                self.requests.clear()
                search = await self.post("search_stories", **kwargs)
                self.assertEqual(search["error"], "Missing required field: query")
                discussion = await self.post("get_discussion", **kwargs)
                self.assertEqual(discussion["error"], "Missing required field: item_id")
                self.assertEqual(self.requests, [])

    async def test_front_page_limit_defaults_and_clamps_are_preserved(self):
        for limit, expected in ((None, 10), (True, 10), ("bad", 10), (0, 1), (99, 20)):
            with self.subTest(limit=limit):
                self.requests.clear()
                body = await self.post("get_front_page", json={"limit": limit})
                self.assertIsNone(body["error"])
                self.assertEqual(len(self.requests), 1)
                self.assertEqual(self.requests[0].url.params["hitsPerPage"], str(expected))

    async def test_provider_http_errors_keep_tool_error_envelopes(self):
        self.provider_status = 503
        for route, payload, prefix in _ROUTES:
            with self.subTest(route=route):
                self.requests.clear()
                body = await self.post(route, json=payload)
                self.assertIsNone(body["result"])
                self.assertTrue(body["error"].startswith(prefix), body)
                self.assertEqual(len(self.requests), 1)

    async def test_provider_timeouts_keep_tool_error_envelopes(self):
        self.provider_timeout = True
        for route, payload, prefix in _ROUTES:
            with self.subTest(route=route):
                self.requests.clear()
                body = await self.post(route, json=payload)
                self.assertIsNone(body["result"])
                self.assertTrue(body["error"].startswith(prefix), body)
                self.assertIn("fixture timeout", body["error"])
                self.assertEqual(len(self.requests), 1)

    async def test_empty_search_uses_json_query_and_default_sort(self):
        self.provider_empty = True
        body = await self.post("search_stories", json={"query": "absent"})
        self.assertEqual(body, {
            "result": "No Hacker News stories found for 'absent'.", "error": None
        })
        self.assertEqual(len(self.requests), 1)
        self.assertEqual(self.requests[0].url.path, "/api/v1/search")
        self.assertEqual(self.requests[0].url.params["hitsPerPage"], "10")

    async def test_invalid_json_is_rejected_before_provider_request(self):
        for route, _, _ in _ROUTES:
            with self.subTest(route=route):
                self.requests.clear()
                response = await self.client.post(
                    f"/tools/{route}", content="{",
                    headers={"Content-Type": "application/json"},
                )
                self.assertEqual(response.status_code, 422)
                self.assertEqual(self.requests, [])

    async def test_openapi_declares_json_body_not_payload_query_parameter(self):
        response = await self.client.get("/openapi.json")
        self.assertEqual(response.status_code, 200)
        for route, _, _ in _ROUTES:
            with self.subTest(route=route):
                operation = response.json()["paths"][f"/tools/{route}"]["post"]
                self.assertIn("application/json", operation.get("requestBody", {}).get("content", {}))
                self.assertFalse(operation["requestBody"].get("required", False))
                self.assertFalse(any(p["name"] == "payload" for p in operation.get("parameters", [])))

    async def test_direct_python_call_defaults_remain_none(self):
        self.assertIsNone((await main.get_front_page()).error)
        self.assertEqual(self.requests[0].url.params["hitsPerPage"], "10")
        self.requests.clear()
        self.assertEqual((await main.search_stories()).error, "Missing required field: query")
        self.assertEqual((await main.get_discussion()).error, "Missing required field: item_id")
        self.assertEqual(self.requests, [])

    async def test_health_and_tool_manifest_remain_available(self):
        health = await self.client.get("/health")
        self.assertEqual(health.json(), {"status": "ok"})
        manifest = await self.client.get("/.well-known/omi-tools.json")
        self.assertEqual(manifest.status_code, 200)
        self.assertEqual(
            {t["endpoint"] for t in manifest.json()["tools"]},
            {f"/tools/{route}" for route, _, _ in _ROUTES},
        )
        self.assertEqual(self.requests, [])


if __name__ == "__main__":
    unittest.main()
