"""Hermetic unit tests for Open Library Omi integration app.

No third-party runtime dependencies required. Runs deterministically under
both standard library `python3 -S` and `pytest`.
"""

import asyncio
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import AsyncMock, patch


def load_app():
    class DummyFastAPI:
        def __init__(self, **kwargs):
            pass

        def get(self, path, **kwargs):
            return lambda func: func

        post = get

    class DummyBaseModel:
        def __init__(self, **kwargs):
            for k, v in kwargs.items():
                setattr(self, k, v)

        def model_dump(self):
            return {k: v for k, v in self.__dict__.items() if not k.startswith("_")}

    class DummyHTMLResponse:
        def __init__(self, content, **kwargs):
            self.content = content

    class DummyHTTPError(Exception):
        pass

    class DummyHTTPStatusError(DummyHTTPError):
        def __init__(self, message, request=None, response=None):
            super().__init__(message)
            self.response = response or types.SimpleNamespace(status_code=500)

    fastapi = types.ModuleType("fastapi")
    fastapi.FastAPI = DummyFastAPI
    fastapi_responses = types.ModuleType("fastapi.responses")
    fastapi_responses.HTMLResponse = DummyHTMLResponse

    pydantic = types.ModuleType("pydantic")
    pydantic.BaseModel = DummyBaseModel

    httpx = types.ModuleType("httpx")
    httpx.HTTPError = DummyHTTPError
    httpx.HTTPStatusError = DummyHTTPStatusError
    httpx.AsyncClient = object

    spec = importlib.util.spec_from_file_location(
        "open_library_app_hermetic", Path(__file__).with_name("main.py")
    )
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


app_module = load_app()


class SafeLimitAndCleanTextTests(unittest.TestCase):
    def test_safe_limit_defaults_and_clamping(self):
        self.assertEqual(app_module._safe_limit(5), 5)
        self.assertEqual(app_module._safe_limit("7"), 7)
        self.assertEqual(app_module._safe_limit(0), 1)
        self.assertEqual(app_module._safe_limit(99), 10)
        self.assertEqual(app_module._safe_limit("-5"), 1)
        self.assertEqual(app_module._safe_limit(None), 5)
        self.assertEqual(app_module._safe_limit(""), 5)

    def test_safe_limit_rejects_dirty_types_and_overflow(self):
        self.assertEqual(app_module._safe_limit(True), 5)
        self.assertEqual(app_module._safe_limit(False), 5)
        self.assertEqual(app_module._safe_limit("inf"), 5)
        self.assertEqual(app_module._safe_limit("-infinity"), 5)
        self.assertEqual(app_module._safe_limit("1e1000"), 5)
        self.assertEqual(app_module._safe_limit(float("inf")), 5)
        self.assertEqual(app_module._safe_limit("invalid"), 5)

    def test_clean_text_basic_and_html_strip(self):
        self.assertEqual(app_module._clean_text("Hello World"), "Hello World")
        self.assertEqual(app_module._clean_text("<b>Bold</b> &amp; Clean"), "Bold & Clean")
        self.assertEqual(app_module._clean_text("  multiple   spaces  \n"), "multiple spaces")

    def test_clean_text_invisible_characters_and_dirty_types(self):
        text_with_zw = "Open\u200bLibrary"
        self.assertEqual(app_module._clean_text(text_with_zw), "Open Library")
        self.assertEqual(app_module._clean_text(None), "")
        self.assertEqual(app_module._clean_text(True), "")
        self.assertEqual(app_module._clean_text({"dict": "val"}), "")
        self.assertEqual(app_module._clean_text(["list"]), "")


class WorkIdAndIsbnSanitizationTests(unittest.TestCase):
    def test_work_id_standard_tokens(self):
        self.assertEqual(app_module._work_id("OL45883W"), "OL45883W")
        self.assertEqual(app_module._work_id("ol45883w"), "OL45883W")
        self.assertEqual(app_module._work_id("works/OL45883W"), "OL45883W")
        self.assertEqual(app_module._work_id("/works/OL45883W/"), "OL45883W")
        self.assertEqual(app_module._work_id("work: OL45883W"), "OL45883W")
        self.assertEqual(app_module._work_id("#OL45883W"), "OL45883W")

    def test_work_id_url_and_slug_extraction(self):
        url = "https://openlibrary.org/works/OL45883W"
        self.assertEqual(app_module._work_id(url), "OL45883W")

        url_with_slug = "https://openlibrary.org/works/OL45883W/The_Lord_of_the_Rings"
        self.assertEqual(app_module._work_id(url_with_slug), "OL45883W")

        url_with_json = "https://openlibrary.org/works/OL45883W.json"
        self.assertEqual(app_module._work_id(url_with_json), "OL45883W")

    def test_work_id_invalid_candidates(self):
        self.assertIsNone(app_module._work_id(None))
        self.assertIsNone(app_module._work_id(""))
        self.assertIsNone(app_module._work_id("not_a_work_id"))
        self.assertIsNone(app_module._work_id("OLW"))
        self.assertIsNone(app_module._work_id(True))

    def test_safe_isbn_valid_isbn10_and_isbn13(self):
        self.assertEqual(app_module._safe_isbn("0395193958"), "0395193958")
        self.assertEqual(app_module._safe_isbn("978-0-395-19395-8"), "9780395193958")
        self.assertEqual(app_module._safe_isbn("ISBN: 9780395193958"), "9780395193958")
        self.assertEqual(app_module._safe_isbn("isbn-10: 043942089X"), "043942089X")
        self.assertEqual(app_module._safe_isbn("043942089x"), "043942089X")

    def test_safe_isbn_invalid_inputs(self):
        self.assertIsNone(app_module._safe_isbn(None))
        self.assertIsNone(app_module._safe_isbn("12345"))  # too short
        self.assertIsNone(app_module._safe_isbn("9780395193958999"))  # too long
        self.assertIsNone(app_module._safe_isbn("coca cola 1000ml"))
        self.assertIsNone(app_module._safe_isbn(True))


class SubjectSlugAndFormattingTests(unittest.TestCase):
    def test_subject_slug_ascii_and_punctuation(self):
        self.assertEqual(app_module._subject_slug("science fiction"), "science_fiction")
        self.assertEqual(app_module._subject_slug("art & design"), "art_design")
        self.assertEqual(app_module._subject_slug("history: ancient"), "history_ancient")

    def test_subject_slug_unicode(self):
        self.assertEqual(app_module._subject_slug("español"), "español")
        self.assertEqual(app_module._subject_slug("中文"), "中文")
        self.assertEqual(app_module._subject_slug("日本語"), "日本語")

    def test_subject_slug_blank(self):
        self.assertIsNone(app_module._subject_slug(""))
        self.assertIsNone(app_module._subject_slug("   "))
        self.assertIsNone(app_module._subject_slug("???///"))
        self.assertIsNone(app_module._subject_slug(None))

    def test_join_values_with_dicts_and_strings(self):
        items = ["Fiction", {"name": "Fantasy"}, {"value": "Adventure"}, None]
        self.assertEqual(app_module._join_values(items, limit=3), "Fiction, Fantasy, Adventure")

    def test_description_text_nested_and_long(self):
        self.assertEqual(app_module._description_text({"value": "A great novel."}), "A great novel.")
        self.assertEqual(app_module._description_text(["Line 1", "Line 2"]), "Line 1\nLine 2")
        long_desc = "A" * 1000
        truncated = app_module._description_text(long_desc)
        self.assertTrue(truncated.endswith("..."))
        self.assertEqual(len(truncated), 903)

    def test_format_book_and_subject_work_non_dict_safe(self):
        self.assertIn("Untitled", app_module._format_book(None, 1))
        self.assertIn("Untitled", app_module._format_subject_work("dirty_string", 1))


class ToolEndpointsIntegrationTests(unittest.TestCase):
    def test_search_books_success(self):
        mock_data = {
            "docs": [
                {
                    "title": "The Hobbit",
                    "author_name": ["J.R.R. Tolkien"],
                    "first_publish_year": 1937,
                    "key": "/works/OL262758W",
                    "subject": ["Fantasy", "Middle-earth"],
                }
            ]
        }
        with patch.object(app_module, "_request_json", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = mock_data
            payload = {"query": "The Hobbit", "limit": 3}
            response = asyncio.run(app_module.search_books(payload))

        self.assertIsNone(response.error)
        self.assertIn("The Hobbit", response.result)
        self.assertIn("J.R.R. Tolkien", response.result)

    def test_search_books_empty_criteria(self):
        payload = {"limit": 5}
        response = asyncio.run(app_module.search_books(payload))
        self.assertEqual(response.error, "Provide query, author, or subject.")

    def test_search_books_404_or_no_matching(self):
        with patch.object(app_module, "_request_json", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = {"not_found": True, "status_code": 404}
            payload = {"query": "nonexistentbook123456789"}
            response = asyncio.run(app_module.search_books(payload))

        self.assertIsNone(response.error)
        self.assertEqual(response.result, "No matching books found.")

    def test_search_books_unexpected_non_dict_response(self):
        with patch.object(app_module, "_request_json", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = []
            payload = {"query": "test"}
            response = asyncio.run(app_module.search_books(payload))

        self.assertIn("unexpected response structure", response.error)

    def test_get_book_details_by_work_id(self):
        mock_work = {
            "title": "1984",
            "description": {"value": "Dystopian masterpiece."},
            "subjects": ["Classics", "Dystopia"],
            "created": {"value": "2008-04-01T03:28:50"},
        }
        with patch.object(app_module, "_request_json", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = mock_work
            payload = {"work_id": "https://openlibrary.org/works/OL1168007W/1984"}
            response = asyncio.run(app_module.get_book_details(payload))

        self.assertIsNone(response.error)
        self.assertIn("1984", response.result)
        self.assertIn("Open Library work: OL1168007W", response.result)
        self.assertIn("Dystopian masterpiece", response.result)

    def test_get_book_details_by_isbn(self):
        mock_data = {
            "ISBN:9780141036144": {
                "title": "Nineteen Eighty-Four",
                "authors": [{"name": "George Orwell"}],
                "publishers": [{"name": "Penguin Books"}],
                "publish_date": "2008",
                "url": "https://openlibrary.org/books/OL22849880M",
            }
        }
        with patch.object(app_module, "_request_json", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = mock_data
            payload = {"isbn": "ISBN: 978-0-141-03614-4"}
            response = asyncio.run(app_module.get_book_details(payload))

        self.assertIsNone(response.error)
        self.assertIn("Nineteen Eighty-Four", response.result)
        self.assertIn("George Orwell", response.result)
        self.assertIn("Penguin Books", response.result)

    def test_get_book_details_work_404_friendly_message(self):
        with patch.object(app_module, "_request_json", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = {"not_found": True, "status_code": 404}
            payload = {"work_id": "OL999999999W"}
            response = asyncio.run(app_module.get_book_details(payload))

        self.assertIsNone(response.error)
        self.assertEqual(response.result, "No matching Open Library record found.")

    def test_get_book_details_missing_args(self):
        payload = {}
        response = asyncio.run(app_module.get_book_details(payload))
        self.assertIn("Provide a valid Open Library work_id", response.error)

    def test_search_subject_success(self):
        mock_subject = {
            "name": "Science Fiction",
            "works": [
                {
                    "title": "Dune",
                    "authors": [{"name": "Frank Herbert"}],
                    "first_publish_year": 1965,
                    "key": "/works/OL893415W",
                    "edition_count": 87,
                }
            ],
        }
        with patch.object(app_module, "_request_json", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = mock_subject
            payload = {"subject": "science fiction", "limit": 3}
            response = asyncio.run(app_module.search_subject(payload))

        self.assertIsNone(response.error)
        self.assertIn("Open Library books for subject Science Fiction", response.result)
        self.assertIn("Dune", response.result)
        self.assertIn("Frank Herbert", response.result)

    def test_search_subject_missing_or_blank(self):
        payload = {"subject": "   "}
        response = asyncio.run(app_module.search_subject(payload))
        self.assertEqual(response.error, "Provide a subject to browse.")


if __name__ == "__main__":
    unittest.main(verbosity=2)
