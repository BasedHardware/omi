"""Hermetic unit tests for Open Library Omi integration.

No third-party runtime dependencies required. Loads main.py inside a scoped
patch.dict(sys.modules) to ensure zero global test pollution.
"""

import asyncio
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import AsyncMock, patch
from urllib.parse import unquote


def load_app():
    class DummyFastAPI:
        def __init__(self, **_kwargs):
            self.routes = []

        def get(self, path, **kwargs):
            return self._route("GET", path, kwargs.get("response_model"))

        def post(self, path, **kwargs):
            return self._route("POST", path, kwargs.get("response_model"))

        def _route(self, method, path, response_model):
            def decorator(func):
                self.routes.append({
                    "method": method,
                    "path": path,
                    "func": func,
                    "response_model": response_model,
                })
                return func

            return decorator

    class DummyBaseModel:
        def __init__(self, **kwargs):
            for key, value in kwargs.items():
                setattr(self, key, value)

    class HTTPError(Exception):
        pass

    class HTTPStatusError(HTTPError):
        def __init__(self, message=None, response=None):
            super().__init__(message)
            self.response = response or types.SimpleNamespace(status_code=500)

    fastapi = types.ModuleType("fastapi")
    fastapi.FastAPI = DummyFastAPI
    fastapi.Request = object
    fastapi_responses = types.ModuleType("fastapi.responses")
    fastapi_responses.HTMLResponse = str

    pydantic = types.ModuleType("pydantic")
    pydantic.BaseModel = DummyBaseModel

    httpx = types.ModuleType("httpx")
    httpx.HTTPError = HTTPError
    httpx.HTTPStatusError = HTTPStatusError
    httpx.AsyncClient = object

    spec = importlib.util.spec_from_file_location("open_library_app_hermetic", Path(__file__).with_name("main.py"))
    module = importlib.util.module_from_spec(spec)
    with patch.dict(
        sys.modules,
        {
            "fastapi": fastapi,
            "fastapi.responses": fastapi_responses,
            "pydantic": pydantic,
            "httpx": httpx,
        },
    ):
        spec.loader.exec_module(module)
    return module


main = load_app()


class RouteWiringTests(unittest.TestCase):
    def test_routes_registered_with_correct_methods_and_paths(self):
        registered = {(r["method"], r["path"]): r for r in main.app.routes}
        expected_endpoints = {
            ("GET", "/"),
            ("GET", "/health"),
            ("GET", "/.well-known/omi-tools.json"),
            ("POST", "/tools/search_books"),
            ("POST", "/tools/get_book_details"),
            ("POST", "/tools/search_subject"),
        }
        for endpoint in expected_endpoints:
            self.assertIn(endpoint, registered)

        self.assertIs(registered[("POST", "/tools/search_books")]["response_model"], main.ChatToolResponse)
        self.assertIs(registered[("POST", "/tools/get_book_details")]["response_model"], main.ChatToolResponse)
        self.assertIs(registered[("POST", "/tools/search_subject")]["response_model"], main.ChatToolResponse)

    def test_tools_manifest_matches_registered_routes(self):
        manifest = asyncio.run(main.get_omi_tools_manifest())
        tools = manifest["tools"]
        self.assertEqual(len(tools), 3)
        tool_endpoints = {t["endpoint"]: t["method"] for t in tools}
        self.assertEqual(
            tool_endpoints,
            {
                "/tools/search_books": "POST",
                "/tools/get_book_details": "POST",
                "/tools/search_subject": "POST",
            },
        )


class SubjectSlugTests(unittest.TestCase):
    def test_subject_slug_ascii(self):
        self.assertEqual(main._subject_slug("science fiction"), "science_fiction")
        self.assertEqual(main._subject_slug("history"), "history")
        self.assertEqual(main._subject_slug("  space   flight  "), "space_flight")

    def test_subject_slug_unicode(self):
        self.assertEqual(main._subject_slug("español"), "español")
        self.assertEqual(main._subject_slug("中文"), "中文")
        self.assertEqual(main._subject_slug("música"), "música")
        self.assertEqual(main._subject_slug("日本語"), "日本語")

    def test_subject_slug_punctuation_dropped(self):
        self.assertEqual(main._subject_slug("science / fiction?"), "science_fiction")
        self.assertEqual(main._subject_slug("art & design"), "art_design")
        self.assertEqual(main._subject_slug("c++"), "c")
        self.assertEqual(main._subject_slug("history: ancient"), "history_ancient")

    def test_subject_slug_blank_and_invalid(self):
        self.assertIsNone(main._subject_slug(""))
        self.assertIsNone(main._subject_slug("   "))
        self.assertIsNone(main._subject_slug("???///"))
        self.assertIsNone(main._subject_slug(None))


class OpenLibraryToolTests(unittest.IsolatedAsyncioTestCase):
    async def test_search_subject_unicode_encoding_and_response(self):
        mock_data = {
            "name": "español",
            "works": [
                {
                    "key": "/works/OL123W",
                    "title": "Don Quijote",
                    "authors": [{"name": "Miguel de Cervantes"}],
                    "first_publish_year": 1605,
                }
            ],
        }

        with patch.object(main, "_request_json", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = mock_data
            resp = await main.search_subject({"subject": "español", "limit": 5})
            self.assertIsNone(resp.error)
            self.assertIn("Don Quijote", resp.result)

            mock_req.assert_awaited_once()
            called_path = mock_req.await_args[0][0]
            self.assertEqual(called_path, "/subjects/espa%C3%B1ol.json")
            slug_segment = called_path.removeprefix("/subjects/").removesuffix(".json")
            self.assertEqual(unquote(slug_segment), "español")

    async def test_search_subject_non_latin_chinese(self):
        mock_data = {
            "name": "中文",
            "works": [
                {
                    "key": "/works/OL456W",
                    "title": "Chinese Literature",
                    "authors": [{"name": "Lu Xun"}],
                    "first_publish_year": 1918,
                }
            ],
        }

        with patch.object(main, "_request_json", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = mock_data
            resp = await main.search_subject({"subject": "中文", "limit": 2})
            self.assertIsNone(resp.error)
            self.assertIn("Chinese Literature", resp.result)

            mock_req.assert_awaited_once()
            called_path = mock_req.await_args[0][0]
            self.assertEqual(called_path, "/subjects/%E4%B8%AD%E6%96%87.json")
            slug_segment = called_path.removeprefix("/subjects/").removesuffix(".json")
            self.assertEqual(unquote(slug_segment), "中文")

    async def test_search_subject_missing_subject(self):
        resp = await main.search_subject({"subject": "   "})
        self.assertEqual(resp.error, "Provide a subject to browse.")

    async def test_search_subject_null_works_graceful(self):
        with patch.object(main, "_request_json", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = {"name": "Test Subject", "works": None}
            resp = await main.search_subject({"subject": "Test Subject"})
            self.assertIsNone(resp.error)
            self.assertEqual(resp.result, "No books found for subject Test Subject.")

    async def test_search_subject_non_dict_payload_graceful(self):
        with patch.object(main, "_request_json", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = "<html>Rate limited</html>"
            resp = await main.search_subject({"subject": "Economics"})
            self.assertIsNone(resp.error)
            self.assertEqual(resp.result, "No books found for subject Economics.")

    async def test_search_books_success(self):
        mock_data = {
            "docs": [
                {
                    "key": "/works/OL45883W",
                    "title": "Fantastic Mr Fox",
                    "author_name": ["Roald Dahl"],
                    "first_publish_year": 1970,
                    "subject": ["Children's fiction", "Foxes"],
                }
            ]
        }
        with patch.object(main, "_request_json", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = mock_data
            resp = await main.search_books({"query": "Fantastic Mr Fox"})
            self.assertIsNone(resp.error)
            self.assertIn("Fantastic Mr Fox", resp.result)
            self.assertIn("Roald Dahl", resp.result)

    async def test_search_books_null_docs_graceful(self):
        with patch.object(main, "_request_json", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = {"docs": None}
            resp = await main.search_books({"query": "Nonexistent"})
            self.assertIsNone(resp.error)
            self.assertEqual(resp.result, "No matching books found.")

    async def test_search_books_non_dict_payload_graceful(self):
        with patch.object(main, "_request_json", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = "<html>502 Bad Gateway</html>"
            resp = await main.search_books({"query": "Dune"})
            self.assertIsNone(resp.error)
            self.assertEqual(resp.result, "No matching books found.")

    async def test_search_books_missing_params_error(self):
        resp = await main.search_books({})
        self.assertEqual(resp.error, "Provide query, author, or subject.")

    async def test_get_book_details_isbn_success(self):
        isbn = "9780140328721"
        mock_data = {
            f"ISBN:{isbn}": {
                "title": "Matilda",
                "authors": [{"name": "Roald Dahl"}],
                "publishers": [{"name": "Puffin"}],
                "publish_date": "1988",
                "subjects": [{"name": "Children's Stories"}],
                "url": "https://openlibrary.org/books/OL123M",
            }
        }
        with patch.object(main, "_request_json", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = mock_data
            resp = await main.get_book_details({"isbn": isbn})
            self.assertIsNone(resp.error)
            self.assertIn("Matilda", resp.result)
            self.assertIn("Author: Roald Dahl", resp.result)
            self.assertIn("Publisher: Puffin", resp.result)

    async def test_get_book_details_isbn_null_payload_graceful(self):
        isbn = "9780140328721"
        mock_data = {
            f"ISBN:{isbn}": {
                "title": "Test Book",
                "authors": None,
                "publishers": None,
                "publish_date": None,
                "subjects": None,
                "url": "https://openlibrary.org/books/OL123M",
            }
        }
        with patch.object(main, "_request_json", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = mock_data
            resp = await main.get_book_details({"isbn": isbn})
            self.assertIsNone(resp.error)
            self.assertIn("Test Book", resp.result)
            self.assertIn("Author: unknown author", resp.result)

    async def test_get_book_details_isbn_empty_record_graceful(self):
        isbn = "9780140328721"
        mock_data = {f"ISBN:{isbn}": {}}
        with patch.object(main, "_request_json", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = mock_data
            resp = await main.get_book_details({"isbn": isbn})
            self.assertIsNone(resp.error)
            self.assertEqual(resp.result, f"No Open Library details found for ISBN {isbn}.")

    async def test_get_book_details_isbn_non_dict_payload_graceful(self):
        isbn = "9780140328721"
        with patch.object(main, "_request_json", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = "<html>500 Server Error</html>"
            resp = await main.get_book_details({"isbn": isbn})
            self.assertIsNone(resp.error)
            self.assertEqual(resp.result, f"No Open Library details found for ISBN {isbn}.")

    async def test_get_book_details_work_id_success(self):
        mock_data = {
            "title": "Dune",
            "description": {"type": "/type/text", "value": "A desert planet story."},
            "subjects": ["Science Fiction", "Planets"],
            "created": {"type": "/type/datetime", "value": "2008-04-01T03:28:50"},
        }
        with patch.object(main, "_request_json", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = mock_data
            resp = await main.get_book_details({"work_id": "OL29340W"})
            self.assertIsNone(resp.error)
            self.assertIn("Dune", resp.result)
            self.assertIn("Science Fiction", resp.result)
            self.assertIn("Description: A desert planet story.", resp.result)

    async def test_get_book_details_work_id_non_dict_payload_graceful(self):
        with patch.object(main, "_request_json", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = "<html>404 Not Found</html>"
            resp = await main.get_book_details({"work_id": "OL29340W"})
            self.assertIsNone(resp.error)
            self.assertEqual(resp.result, "No Open Library details found for work OL29340W.")

    async def test_get_book_details_work_id_empty_payload_graceful(self):
        with patch.object(main, "_request_json", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = {}
            resp = await main.get_book_details({"work_id": "OL29340W"})
            self.assertIsNone(resp.error)
            self.assertEqual(resp.result, "No Open Library details found for work OL29340W.")

    async def test_get_book_details_missing_work_and_isbn(self):
        resp = await main.get_book_details({})
        self.assertIn("Provide a valid Open Library work_id", resp.error)


class FormattingTests(unittest.TestCase):
    def test_format_subject_work_null_authors(self):
        work = {
            "title": "Anonymous Manuscript",
            "authors": None,
            "first_publish_year": 1400,
            "key": "/works/OL999W",
            "edition_count": 1,
        }
        result = main._format_subject_work(work, 1)
        self.assertIn("Anonymous Manuscript", result)
        self.assertIn("Author: unknown author", result)

    def test_format_subject_work_non_dict(self):
        result = main._format_subject_work("invalid", 1)
        self.assertEqual(result, "1. Untitled")

    def test_format_book_null_authors_and_subjects(self):
        doc = {
            "title": "Old Fragment",
            "author_name": None,
            "first_publish_year": None,
            "key": None,
            "subject": None,
        }
        result = main._format_book(doc, 1)
        self.assertIn("Old Fragment", result)
        self.assertIn("Author: unknown author", result)
        self.assertIn("First published: unknown year", result)

    def test_format_book_non_dict(self):
        result = main._format_book("invalid", 1)
        self.assertEqual(result, "1. Untitled")


if __name__ == "__main__":
    unittest.main()
