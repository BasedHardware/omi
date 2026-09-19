"""
Hermetic test suite for Omi Open Library Integration.
Hermetic, deterministic, and verifies null-field handling, boolean limits, and endpoints.
Runs with Python standard library only (stubs FastAPI/Pydantic/HTTPX if absent).
"""

import asyncio
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

# --- Hermetic stubs for environments without FastAPI/Pydantic/httpx installed ---
if "fastapi" not in sys.modules:
    fastapi_mod = ModuleType("fastapi")

    class DummyFastAPI:
        def __init__(self, *args, **kwargs):
            self.state = SimpleNamespace()

        def get(self, *args, **kwargs):
            return lambda f: f

        def post(self, *args, **kwargs):
            return lambda f: f

    fastapi_mod.FastAPI = DummyFastAPI
    fastapi_responses = ModuleType("fastapi.responses")
    fastapi_responses.HTMLResponse = lambda content, *args, **kwargs: content
    fastapi_mod.responses = fastapi_responses
    sys.modules["fastapi"] = fastapi_mod
    sys.modules["fastapi.responses"] = fastapi_responses

if "pydantic" not in sys.modules:
    pydantic_mod = ModuleType("pydantic")

    class DummyBaseModel:
        def __init__(self, **kwargs):
            for k, v in kwargs.items():
                setattr(self, k, v)

    pydantic_mod.BaseModel = DummyBaseModel
    sys.modules["pydantic"] = pydantic_mod

if "httpx" not in sys.modules:
    httpx_mod = ModuleType("httpx")
    httpx_mod.HTTPError = Exception
    httpx_mod.HTTPStatusError = Exception
    httpx_mod.TimeoutException = Exception

    class DummyAsyncClient:
        def __init__(self, *args, **kwargs):
            self.is_closed = False

        async def aclose(self):
            self.is_closed = True

        async def get(self, *args, **kwargs):
            raise NotImplementedError

    httpx_mod.AsyncClient = DummyAsyncClient
    sys.modules["httpx"] = httpx_mod

from main import (
    app,
    _clean_text,
    _description_text,
    _format_book,
    _format_subject_work,
    _join_values,
    _safe_isbn,
    _safe_limit,
    _subject_slug,
    _work_id,
    get_book_details,
    health,
    get_omi_tools_manifest,
    search_books,
    search_subject,
)


class TestOpenLibraryApp(unittest.TestCase):

    def test_subject_slug_ascii_and_unicode(self):
        self.assertEqual(_subject_slug("science fiction"), "science_fiction")
        self.assertEqual(_subject_slug("history"), "history")
        self.assertEqual(_subject_slug("  space   flight  "), "space_flight")
        self.assertEqual(_subject_slug("español"), "español")
        self.assertEqual(_subject_slug("中文"), "中文")
        self.assertEqual(_subject_slug("música"), "música")
        self.assertEqual(_subject_slug("日本語"), "日本語")

    def test_subject_slug_punctuation_and_invalid(self):
        self.assertEqual(_subject_slug("science / fiction?"), "science_fiction")
        self.assertEqual(_subject_slug("art & design"), "art_design")
        self.assertEqual(_subject_slug("c++"), "c")
        self.assertEqual(_subject_slug("history: ancient"), "history_ancient")
        self.assertIsNone(_subject_slug(""))
        self.assertIsNone(_subject_slug("   "))
        self.assertIsNone(_subject_slug("???///"))
        self.assertIsNone(_subject_slug(None))

    def test_safe_limit_booleans_and_bounds(self):
        # Boolean must not be coerced to 1 or 0
        self.assertEqual(_safe_limit(True, default=5), 5)
        self.assertEqual(_safe_limit(False, default=5), 5)
        # None and empty strings return default
        self.assertEqual(_safe_limit(None, default=7), 7)
        self.assertEqual(_safe_limit("", default=5), 5)
        self.assertEqual(_safe_limit("abc", default=4), 4)
        # Bounds clamping
        self.assertEqual(_safe_limit(0), 1)
        self.assertEqual(_safe_limit(-5), 1)
        self.assertEqual(_safe_limit(20), 10)  # MAX_LIMIT is 10
        self.assertEqual(_safe_limit("8"), 8)

    def test_work_id_parser(self):
        self.assertEqual(_work_id("OL45883W"), "OL45883W")
        self.assertEqual(_work_id("/works/OL45883W/"), "OL45883W")
        self.assertEqual(_work_id("ol12345w"), "OL12345W")
        self.assertIsNone(_work_id("OLW"))
        self.assertIsNone(_work_id("invalid"))
        self.assertIsNone(_work_id(None))

    def test_safe_isbn_parser(self):
        self.assertEqual(_safe_isbn("0-306-40615-2"), "0306406152")
        self.assertEqual(_safe_isbn("978-0-306-40615-7"), "9780306406157")
        self.assertEqual(_safe_isbn("030640615X"), "030640615X")
        self.assertIsNone(_safe_isbn("123"))
        self.assertIsNone(_safe_isbn(None))

    def test_clean_text_and_join_values(self):
        self.assertEqual(_clean_text("Hello &amp; <b>World</b>"), "Hello & World")
        self.assertEqual(_clean_text(None), "")
        self.assertEqual(_join_values(["tag1", "<b>tag2</b>", None, ""]), "tag1, tag2")
        self.assertEqual(_join_values(None), "")
        self.assertEqual(_join_values("single_item"), "single_item")

    def test_description_text(self):
        self.assertEqual(_description_text({"value": "A great novel"}), "A great novel")
        self.assertEqual(_description_text("Simple text"), "Simple text")
        long_desc = "a" * 1000
        truncated = _description_text(long_desc)
        self.assertTrue(truncated.endswith("..."))
        self.assertLessEqual(len(truncated), 903)

    def test_format_subject_work_null_authors(self):
        # When Open Library returns authors: null
        work = {
            "title": "Silent Work",
            "authors": None,
            "key": "/works/OL999W",
            "first_publish_year": 2020,
            "edition_count": 2,
        }
        res = _format_subject_work(work, 1)
        self.assertIn("Silent Work", res)
        self.assertIn("unknown author", res)
        self.assertIn("OL999W", res)

    def test_get_book_details_null_fields_isbn(self):
        # Open Library /api/books with null authors, publishers, subjects
        mock_data = {
            "ISBN:0306406152": {
                "title": "Minimal Book",
                "authors": None,
                "publishers": None,
                "subjects": None,
                "publish_date": "1999",
                "url": "https://openlibrary.org/books/OL1M",
            }
        }
        with patch("main._request_json", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = mock_data
            res = asyncio.run(get_book_details({"isbn": "0306406152"}))
            self.assertIsNone(res.error)
            self.assertIsNotNone(res.result)
            self.assertIn("Minimal Book", res.result)
            self.assertIn("unknown author", res.result)

    def test_get_book_details_valid_work(self):
        mock_work = {
            "title": "Dune",
            "description": "Epic sci-fi",
            "subjects": ["Science Fiction", "Arrakis"],
            "created": {"value": "2008-04-01T03:28:50"},
        }
        with patch("main._request_json", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = mock_work
            res = asyncio.run(get_book_details({"work_id": "OL893415W"}))
            self.assertIsNone(res.error)
            self.assertIn("Dune", res.result)
            self.assertIn("OL893415W", res.result)

    def test_get_book_details_invalid_input(self):
        res = asyncio.run(get_book_details({"work_id": "bad", "isbn": "bad"}))
        self.assertIsNotNone(res.error)
        self.assertIn("Provide a valid Open Library work_id", res.error)

    def test_search_books_query_and_null_docs(self):
        with patch("main._request_json", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = {"docs": None}
            res = asyncio.run(search_books({"query": "Foundation"}))
            self.assertIsNone(res.error)
            self.assertEqual(res.result, "No matching books found.")

        # Test missing all query params
        res_no_param = asyncio.run(search_books({}))
        self.assertIn("Provide query, author, or subject", res_no_param.error)

    def test_search_books_success(self):
        mock_docs = {
            "docs": [
                {
                    "title": "The Hobbit",
                    "author_name": ["J.R.R. Tolkien"],
                    "first_publish_year": 1937,
                    "key": "/works/OL262758W",
                    "subject": ["Fantasy"],
                }
            ]
        }
        with patch("main._request_json", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = mock_docs
            res = asyncio.run(search_books({"query": "Hobbit"}))
            self.assertIsNone(res.error)
            self.assertIn("The Hobbit", res.result)
            self.assertIn("J.R.R. Tolkien", res.result)

    def test_search_subject_success(self):
        mock_subject = {
            "name": "Fantasy",
            "works": [
                {
                    "title": "The Name of the Wind",
                    "authors": [{"name": "Patrick Rothfuss"}],
                    "first_publish_year": 2007,
                    "key": "/works/OL15842827W",
                    "edition_count": 30,
                }
            ],
        }
        with patch("main._request_json", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = mock_subject
            res = asyncio.run(search_subject({"subject": "Fantasy"}))
            self.assertIsNone(res.error)
            self.assertIn("The Name of the Wind", res.result)

    def test_payload_not_dict(self):
        for endpoint in [search_books, get_book_details, search_subject]:
            res = asyncio.run(endpoint("invalid string payload"))
            self.assertEqual(res.error, "Request payload must be a JSON object.")

    def test_health_and_manifest(self):
        h = asyncio.run(health())
        self.assertEqual(h, {"status": "ok"})
        manifest = asyncio.run(get_omi_tools_manifest())
        self.assertIn("tools", manifest)
        self.assertEqual(len(manifest["tools"]), 3)


if __name__ == "__main__":
    unittest.main()
