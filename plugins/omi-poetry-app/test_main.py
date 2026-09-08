"""Hermetic unit tests for Omi Classical Poetry & Verse Integration App."""

import unittest
from unittest.mock import AsyncMock, MagicMock

from fastapi.testclient import TestClient

from main import (
    SimpleTTLCache,
    _format_poem,
    app,
    get_poem_by_title,
    get_random_poem,
    health,
    list_poets,
    omi_tools,
    poetry_cache,
    search_poems_by_author,
)
from models import (
    ChatToolResponse,
    GetPoemByTitleRequest,
    GetRandomPoemRequest,
    ListPoetsRequest,
    SearchPoemsByAuthorRequest,
)

SAMPLE_POEM = {
    "title": "Ozymandias",
    "author": "Percy Bysshe Shelley",
    "lines": [
        "I met a traveller from an antique land,",
        "Who said—'Two vast and trunkless legs of stone",
        "Stand in the desert. . . . Near them, on the sand,",
        "Half sunk a shattered visage lies, whose frown,",
        "And wrinkled lip, and sneer of cold command,",
        "Tell that its sculptor well those passions read",
        "Which yet survive, stamped on these lifeless things,",
        "The hand that mocked them, and the heart that fed;",
        "And on the pedestal, these words appear:",
        "My name is Ozymandias, King of Kings;",
        "Look on my Works, ye Mighty, and despair!",
        "Nothing beside remains. Round the decay",
        "Of that colossal Wreck, boundless and bare",
        "The lone and level sands stretch far away.'",
    ],
    "linecount": "14",
}


class TestModels(unittest.TestCase):
    """Test Pydantic schemas and input sanitization."""

    def test_chat_tool_response_valid_result(self):
        resp = ChatToolResponse(result="Poem text here")
        self.assertEqual(resp.result, "Poem text here")
        self.assertIsNone(resp.error)

    def test_chat_tool_response_valid_error(self):
        resp = ChatToolResponse(error="Poem not found")
        self.assertEqual(resp.error, "Poem not found")
        self.assertIsNone(resp.result)

    def test_chat_tool_response_invalid_both(self):
        with self.assertRaises(ValueError):
            ChatToolResponse(result="Text", error="Error")

    def test_chat_tool_response_invalid_neither(self):
        with self.assertRaises(ValueError):
            ChatToolResponse()

    def test_get_random_poem_request_validation(self):
        req = GetRandomPoemRequest(author="  Emily   Dickinson  ", max_lines=15)
        self.assertEqual(req.author, "Emily Dickinson")
        self.assertEqual(req.max_lines, 15)

    def test_get_random_poem_request_bounds(self):
        with self.assertRaises(ValueError):
            GetRandomPoemRequest(max_lines=0)
        with self.assertRaises(ValueError):
            GetRandomPoemRequest(max_lines=500)

    def test_search_poems_by_author_sanitization(self):
        req = SearchPoemsByAuthorRequest(author="  John  Keats  ", max_results=5)
        self.assertEqual(req.author, "John Keats")
        self.assertEqual(req.max_results, 5)

        with self.assertRaises(ValueError):
            SearchPoemsByAuthorRequest(author="   ")

    def test_get_poem_by_title_sanitization(self):
        req = GetPoemByTitleRequest(title="  The   Raven  ", author="  Edgar Allan Poe  ")
        self.assertEqual(req.title, "The Raven")
        self.assertEqual(req.author, "Edgar Allan Poe")

        with self.assertRaises(ValueError):
            GetPoemByTitleRequest(title="   ")


class TestHelpers(unittest.TestCase):
    """Test poem formatting and LRU cache."""

    def test_format_poem_full(self):
        text = _format_poem(SAMPLE_POEM, max_lines=20)
        self.assertIn("Ozymandias", text)
        self.assertIn("Percy Bysshe Shelley", text)
        self.assertIn("King of Kings", text)
        self.assertNotIn("more lines in full poem", text)

    def test_format_poem_truncated(self):
        text = _format_poem(SAMPLE_POEM, max_lines=5)
        self.assertIn("Ozymandias", text)
        self.assertIn("antique land", text)
        self.assertIn("[9 more lines in full poem]", text)

    def test_ttl_cache_operations(self):
        cache = SimpleTTLCache(maxsize=2, ttl_seconds=60)
        cache.set("a", 1)
        cache.set("b", 2)
        cache.set("c", 3)
        self.assertIsNone(cache.get("a"))
        self.assertEqual(cache.get("b"), 2)
        self.assertEqual(cache.get("c"), 3)


class TestEndpointsHermetic(unittest.IsolatedAsyncioTestCase):
    """Hermetic handler unit tests with mocked upstream HTTP client."""

    async def asyncSetUp(self):
        poetry_cache.clear()
        self.mock_client = AsyncMock()
        app.state.http_client = self.mock_client

    async def test_health_endpoint(self):
        res = await health()
        self.assertEqual(res.get("status"), "ok")
        self.assertEqual(res.get("service"), "omi-poetry-app")

    async def test_manifest_endpoint(self):
        manifest = await omi_tools()
        self.assertEqual(manifest.get("schema_version"), "1.0")
        self.assertEqual(manifest.get("auth", {}).get("type"), "none")
        tools = manifest.get("tools", [])
        self.assertEqual(len(tools), 4)

        tool_names = [t["name"] for t in tools]
        self.assertIn("get_random_poem", tool_names)
        self.assertIn("search_poems_by_author", tool_names)
        self.assertIn("get_poem_by_title", tool_names)
        self.assertIn("list_poets", tool_names)

        for t in tools:
            self.assertIn("endpoint", t)
            self.assertEqual(t["method"], "POST")
            self.assertFalse(t["auth_required"])

    async def test_get_random_poem_no_author(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = [SAMPLE_POEM]
        self.mock_client.get.return_value = mock_resp

        req = GetRandomPoemRequest(max_lines=30)
        resp = await get_random_poem(req)
        self.assertIsNone(resp.error)
        self.assertIsNotNone(resp.result)
        self.assertIn("Ozymandias", resp.result)
        self.assertIn("Shelley", resp.result)

    async def test_get_random_poem_with_author(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = [SAMPLE_POEM]
        self.mock_client.get.return_value = mock_resp

        req = GetRandomPoemRequest(author="Shelley", max_lines=14)
        resp = await get_random_poem(req)
        self.assertIsNone(resp.error)
        self.assertIsNotNone(resp.result)
        self.assertIn("Ozymandias", resp.result)

    async def test_get_random_poem_author_not_found(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"status": 404, "reason": "Not found"}
        self.mock_client.get.return_value = mock_resp

        req = GetRandomPoemRequest(author="NonexistentPoetXYZ")
        resp = await get_random_poem(req)
        self.assertIsNotNone(resp.error)
        self.assertIn("No poems found", resp.error)

    async def test_search_poems_by_author_success(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = [SAMPLE_POEM]
        self.mock_client.get.return_value = mock_resp

        req = SearchPoemsByAuthorRequest(author="Shelley", max_results=3)
        resp = await search_poems_by_author(req)
        self.assertIsNone(resp.error)
        self.assertIsNotNone(resp.result)
        self.assertIn("Found 1 poem by Shelley", resp.result)
        self.assertIn("Ozymandias", resp.result)

    async def test_search_poems_by_author_caching(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = [SAMPLE_POEM]
        self.mock_client.get.return_value = mock_resp

        req = SearchPoemsByAuthorRequest(author="Shelley", max_results=3)
        resp1 = await search_poems_by_author(req)
        self.assertIsNone(resp1.error)
        self.assertEqual(self.mock_client.get.call_count, 1)

        # Second invocation should hit local cache
        resp2 = await search_poems_by_author(req)
        self.assertIsNone(resp2.error)
        self.assertEqual(self.mock_client.get.call_count, 1)

    async def test_get_poem_by_title_success(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = [SAMPLE_POEM]
        self.mock_client.get.return_value = mock_resp

        req = GetPoemByTitleRequest(title="Ozymandias")
        resp = await get_poem_by_title(req)
        self.assertIsNone(resp.error)
        self.assertIsNotNone(resp.result)
        self.assertIn("Ozymandias", resp.result)
        self.assertIn("King of Kings", resp.result)

    async def test_get_poem_by_title_with_author(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = [SAMPLE_POEM]
        self.mock_client.get.return_value = mock_resp

        req = GetPoemByTitleRequest(title="Ozymandias", author="Shelley")
        resp = await get_poem_by_title(req)
        self.assertIsNone(resp.error)
        self.assertIn("antique land", resp.result)

    async def test_get_poem_by_title_not_found(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"status": 404}
        self.mock_client.get.return_value = mock_resp

        req = GetPoemByTitleRequest(title="MythicalPoemNeverWritten123")
        resp = await get_poem_by_title(req)
        self.assertIsNotNone(resp.error)
        self.assertIn("not found", resp.error)

    async def test_list_poets_all(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"authors": ["Emily Dickinson", "John Keats", "Percy Bysshe Shelley"]}
        self.mock_client.get.return_value = mock_resp

        req = ListPoetsRequest()
        resp = await list_poets(req)
        self.assertIsNone(resp.error)
        self.assertIsNotNone(resp.result)
        self.assertIn("Emily Dickinson", resp.result)
        self.assertIn("John Keats", resp.result)

    async def test_list_poets_filtered(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"authors": ["Emily Dickinson", "John Keats", "Percy Bysshe Shelley"]}
        self.mock_client.get.return_value = mock_resp

        req = ListPoetsRequest(query="Shelley")
        resp = await list_poets(req)
        self.assertIsNone(resp.error)
        self.assertIn("Percy Bysshe Shelley", resp.result)
        self.assertNotIn("Dickinson", resp.result)

    async def test_list_poets_no_match(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"authors": ["Emily Dickinson", "John Keats"]}
        self.mock_client.get.return_value = mock_resp

        req = ListPoetsRequest(query="NonexistentAuthorQuery")
        resp = await list_poets(req)
        self.assertIsNotNone(resp.error)
        self.assertIn("No poets matching", resp.error)


class TestFastAPIHttp(unittest.TestCase):
    """Test HTTP routing, manifest, and validation error contracts."""

    def setUp(self):
        self.client = TestClient(app)

    def test_root_html(self):
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("text/html", resp.headers["content-type"])
        self.assertIn("Classical Poetry", resp.text)

    def test_health_http(self):
        resp = self.client.get("/health")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["status"], "ok")

    def test_manifest_http(self):
        resp = self.client.get("/.well-known/omi-tools.json")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["schema_version"], "1.0")
        self.assertEqual(len(data["tools"]), 4)
        for t in data["tools"]:
            self.assertIn("endpoint", t)
            self.assertEqual(t["method"], "POST")
            self.assertFalse(t["auth_required"])

    def test_validation_exception_handler_returns_200_with_error(self):
        # Missing required 'author' in search_poems_by_author
        resp = self.client.post("/tools/search_poems_by_author", json={})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("error", data)
        self.assertNotIn("result", data)
        self.assertIn("Invalid tool request", data["error"])


if __name__ == "__main__":
    unittest.main()
