"""Hermetic Crossref pooling and payload-guard regressions (#13978).

Import the production module with framework-only stubs, then exercise its real
lifespan, HTTP helper, and tool handlers. No network, credentials, or
third-party runtime packages are required.
"""

import importlib.util
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch


class FakeHTTPError(Exception):
    pass


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise FakeHTTPError(f"status {self.status_code}")

    def json(self):
        return self._payload


class FakeAsyncClient:
    """Stands in for httpx.AsyncClient; records construction and requests."""

    instances = []

    def __init__(self, *args, **kwargs):
        self.kwargs = kwargs
        self.requests = []
        self.closed = False
        self.next_payload = {"message": {}}
        FakeAsyncClient.instances.append(self)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        self.closed = True
        return False

    async def get(self, url, params=None):
        self.requests.append((url, params))
        return FakeResponse(self.next_payload)


def load_app():
    class FastAPI:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def get(self, *args, **kwargs):
            return lambda handler: handler

        post = get

    class BaseModel:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    httpx = ModuleType("httpx")
    httpx.AsyncClient = FakeAsyncClient
    httpx.HTTPError = FakeHTTPError
    fastapi = ModuleType("fastapi")
    fastapi.FastAPI = FastAPI
    pydantic = ModuleType("pydantic")
    pydantic.BaseModel = BaseModel

    spec = importlib.util.spec_from_file_location("crossref_app", Path(__file__).with_name("main.py"))
    module = importlib.util.module_from_spec(spec)
    with patch.dict(
        sys.modules,
        {
            "httpx": httpx,
            "fastapi": fastapi,
            "pydantic": pydantic,
        },
    ):
        spec.loader.exec_module(module)
    return module


app = load_app()

WORK_ITEM = {
    "title": ["Scaling neural networks"],
    "DOI": "10.1234/omi.1",
    "issued": {"date-parts": [[2024, 3, 1]]},
}


def search_input(query="sleep", max_results=5):
    return app.SearchWorksInput(query=query, max_results=max_results)


def work_input(doi="10.1234/omi.1"):
    return app.GetWorkInput(doi=doi)


def author_input(author="janssen", max_results=5):
    return app.AuthorWorksInput(author=author, max_results=max_results)


class LifespanPoolingTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        FakeAsyncClient.instances.clear()

    def test_app_wires_lifespan_handler(self):
        self.assertIs(app.app.kwargs.get("lifespan"), app.lifespan)

    async def test_lifespan_creates_and_closes_pooled_client(self):
        fake_app = SimpleNamespace(state=SimpleNamespace())
        async with app.lifespan(fake_app):
            client = fake_app.state.http_client
            self.assertIsInstance(client, FakeAsyncClient)
            self.assertEqual(client.kwargs.get("timeout"), app.TIMEOUT)
            self.assertFalse(client.closed)
        self.assertTrue(client.closed)

    async def test_crossref_get_reuses_pooled_client(self):
        pooled = FakeAsyncClient()
        pooled.next_payload = {"message": {"items": []}}
        FakeAsyncClient.instances.clear()
        with patch.object(app.app, "state", SimpleNamespace(http_client=pooled), create=True):
            result = await app.crossref_get("/works", {"query": "sleep"})
        self.assertEqual(result, {"message": {"items": []}})
        self.assertEqual(pooled.requests, [("https://api.crossref.org/works", {"query": "sleep"})])
        self.assertEqual(FakeAsyncClient.instances, [])

    async def test_crossref_get_falls_back_without_pooled_client(self):
        FakeAsyncClient.instances.clear()
        result = await app.crossref_get("/works/10.1234/omi.1", {})
        self.assertEqual(len(FakeAsyncClient.instances), 1)
        fallback = FakeAsyncClient.instances[0]
        self.assertTrue(fallback.closed)
        self.assertEqual(fallback.kwargs.get("timeout"), app.TIMEOUT)
        self.assertEqual(fallback.requests, [("https://api.crossref.org/works/10.1234/omi.1", {})])
        self.assertEqual(result, {"message": {}})

    async def test_crossref_get_falls_back_when_state_lacks_client(self):
        with patch.object(app.app, "state", SimpleNamespace(), create=True):
            FakeAsyncClient.instances.clear()
            await app.crossref_get("/works", {})
        self.assertEqual(len(FakeAsyncClient.instances), 1)


class SearchWorksTests(unittest.IsolatedAsyncioTestCase):
    async def run_search(self, payload, **kwargs):
        with patch.object(app, "crossref_get", AsyncMock(return_value=payload)):
            return await app.search_crossref_works(search_input(**kwargs))

    async def test_happy_path_formats_results(self):
        response = await self.run_search({"message": {"items": [WORK_ITEM]}})
        self.assertIsNone(response.error)
        self.assertIn("Top 1 Crossref results for 'sleep':", response.result)
        self.assertIn("1. Scaling neural networks (2024)", response.result)
        self.assertIn("DOI: 10.1234/omi.1", response.result)

    async def test_null_message_returns_no_results(self):
        response = await self.run_search({"message": None})
        self.assertIsNone(response.error)
        self.assertIn("No Crossref results found", response.result)

    async def test_non_dict_payloads_return_no_results(self):
        for payload in ("504 Gateway Timeout", ["error"], None, 42):
            with self.subTest(payload=payload):
                response = await self.run_search(payload)
                self.assertIsNone(response.error)
                self.assertIn("No Crossref results found", response.result)

    async def test_non_dict_message_and_items_return_no_results(self):
        for payload in ({"message": "cloudflare"}, {"message": {"items": "oops"}}):
            with self.subTest(payload=payload):
                response = await self.run_search(payload)
                self.assertIsNone(response.error)
                self.assertIn("No Crossref results found", response.result)

    async def test_non_dict_items_render_as_untitled(self):
        payload = {"message": {"items": [None, "junk", WORK_ITEM]}}
        response = await self.run_search(payload)
        self.assertIsNone(response.error)
        self.assertIn("1. Untitled ()", response.result)
        self.assertIn("3. Scaling neural networks (2024)", response.result)

    async def test_scalar_title_is_not_truncated_to_first_letter(self):
        item = dict(WORK_ITEM, title="Machine Learning Survey")
        response = await self.run_search({"message": {"items": [item]}})
        self.assertIsNone(response.error)
        self.assertIn("1. Machine Learning Survey (2024)", response.result)

    async def test_short_query_rejected(self):
        response = await self.run_search({"message": {"items": [WORK_ITEM]}}, query="a")
        self.assertEqual(response.error, "Query must be at least 2 characters.")

    async def test_request_failure_returns_error(self):
        with patch.object(app, "crossref_get", AsyncMock(side_effect=FakeHTTPError("boom"))):
            response = await app.search_crossref_works(search_input())
        self.assertIn("Crossref request failed", response.error)


class GetWorkTests(unittest.IsolatedAsyncioTestCase):
    async def run_get_work(self, payload, doi="10.1234/omi.1"):
        with patch.object(app, "crossref_get", AsyncMock(return_value=payload)):
            return await app.get_crossref_work(work_input(doi))

    async def test_happy_path_formats_record(self):
        message = dict(
            WORK_ITEM,
            publisher="MIT Press",
            URL="https://doi.org/10.1234/omi.1",
            abstract="<jats:p>Deep study.</jats:p>",
        )
        response = await self.run_get_work({"message": message})
        self.assertIsNone(response.error)
        self.assertIn("Title: Scaling neural networks", response.result)
        self.assertIn("Year: 2024", response.result)
        self.assertIn("Publisher: MIT Press", response.result)
        self.assertIn("Abstract: Deep study.", response.result)

    async def test_null_message_returns_clean_error(self):
        response = await self.run_get_work({"message": None})
        self.assertIsNotNone(response.error)
        self.assertIn("10.1234/omi.1", response.error)

    async def test_non_dict_payloads_return_clean_error(self):
        for payload in ("Cloudflare challenge", ["error"], None, {"message": "oops"}, {"message": {}}):
            with self.subTest(payload=payload):
                response = await self.run_get_work(payload)
                self.assertIsNotNone(response.error)

    async def test_scalar_title_renders_fully(self):
        message = dict(WORK_ITEM, title="Machine Learning Survey")
        response = await self.run_get_work({"message": message})
        self.assertIsNone(response.error)
        self.assertIn("Title: Machine Learning Survey", response.result)

    async def test_invalid_doi_rejected(self):
        response = await self.run_get_work({"message": WORK_ITEM}, doi="nope")
        self.assertEqual(response.error, "Invalid DOI format. Example: 10.1038/nphys1170")
        response = await self.run_get_work({"message": WORK_ITEM}, doi="10.1/../x")
        self.assertEqual(response.error, "Invalid DOI value.")


class AuthorWorksTests(unittest.IsolatedAsyncioTestCase):
    async def run_author(self, payload, **kwargs):
        with patch.object(app, "crossref_get", AsyncMock(return_value=payload)):
            return await app.get_crossref_works_by_author(author_input(**kwargs))

    async def test_happy_path_formats_results(self):
        response = await self.run_author({"message": {"items": [WORK_ITEM]}})
        self.assertIsNone(response.error)
        self.assertIn("Recent works for 'janssen':", response.result)
        self.assertIn("1. Scaling neural networks (2024)", response.result)

    async def test_null_or_non_dict_payloads_return_no_results(self):
        for payload in ({"message": None}, "timeout", {"message": {"items": None}}):
            with self.subTest(payload=payload):
                response = await self.run_author(payload)
                self.assertIsNone(response.error)
                self.assertIn("No recent works found", response.result)

    async def test_short_author_rejected(self):
        response = await self.run_author({"message": {"items": []}}, author="x")
        self.assertEqual(response.error, "Author must be at least 2 characters.")


class ExtractYearTests(unittest.TestCase):
    def test_valid_date_parts(self):
        self.assertEqual(app.extract_year(WORK_ITEM), "2024")

    def test_prefers_print_over_issued(self):
        item = {
            "issued": {"date-parts": [[2000]]},
            "published-print": {"date-parts": [[1999]]},
        }
        self.assertEqual(app.extract_year(item), "1999")

    def test_malformed_structures_return_empty(self):
        cases = [
            {"issued": {"date-parts": [[]]}},
            {"issued": {"date-parts": "2020"}},
            {"issued": "2020"},
            {"issued": {"date-parts": [None]}},
            {"issued": None},
            "not a dict",
            None,
        ]
        for item in cases:
            with self.subTest(item=item):
                self.assertEqual(app.extract_year(item), "")


class ExtractTitleTests(unittest.TestCase):
    def test_malformed_titles_fall_back_to_untitled(self):
        cases = [
            {"title": []},
            {"title": None},
            {"title": [None]},
            {},
            "not a dict",
            None,
        ]
        for item in cases:
            with self.subTest(item=item):
                self.assertEqual(app._extract_title(item), "Untitled")

    def test_scalar_and_list_titles(self):
        self.assertEqual(app._extract_title({"title": "Solo"}), "Solo")
        self.assertEqual(app._extract_title({"title": ["First", "Second"]}), "First")


if __name__ == "__main__":
    unittest.main()
