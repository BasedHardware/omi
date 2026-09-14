"""Hermetic unit tests for Open Library Omi integration.

No third-party runtime dependencies required.
"""

import asyncio
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import AsyncMock, patch
from urllib.parse import unquote


class DummyFastAPI:
    def __init__(self, **_kwargs):
        self.routes = []

    def get(self, path, **_kwargs):
        return self._route("GET", path)

    def post(self, path, **_kwargs):
        return self._route("POST", path)

    def _route(self, method, path):
        def decorator(func):
            self.routes.append((method, path, func))
            return func

        return decorator


class DummyBaseModel:
    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)


def install_dependency_stubs():
    fastapi = types.ModuleType("fastapi")
    fastapi.FastAPI = DummyFastAPI
    fastapi.Request = object
    fastapi_responses = types.ModuleType("fastapi.responses")
    fastapi_responses.HTMLResponse = str
    sys.modules.setdefault("fastapi", fastapi)
    sys.modules.setdefault("fastapi.responses", fastapi_responses)

    pydantic = types.ModuleType("pydantic")
    pydantic.BaseModel = DummyBaseModel
    sys.modules.setdefault("pydantic", pydantic)

    httpx = types.ModuleType("httpx")
    httpx.HTTPError = Exception
    httpx.AsyncClient = object
    sys.modules.setdefault("httpx", httpx)


install_dependency_stubs()
import main


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

    async def test_search_books_missing_params_error(self):
        resp = await main.search_books({})
        self.assertEqual(resp.error, "Provide query, author, or subject.")

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


if __name__ == "__main__":
    unittest.main()
