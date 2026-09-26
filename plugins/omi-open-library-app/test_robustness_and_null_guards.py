import asyncio
import os
import sys
import types
import unittest
from unittest.mock import patch


# Pre-emptively stub non-stdlib dependencies so this suite can run hermetically
# in minimal Python CI runners without external pip packages.
class _Framework:
    def __init__(self, *args, **kwargs):
        pass

    def get(self, *args, **kwargs):
        return lambda f: f

    post = get

    def __call__(self, *args, **kwargs):
        return self


class _BaseModelStub:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


def _stub_module(name, **attributes):
    val = types.ModuleType(name)
    val.__dict__.update(attributes)
    return val


_stubs = {
    "httpx": _stub_module(
        "httpx",
        AsyncClient=_Framework,
        RequestError=Exception,
        HTTPStatusError=Exception,
    ),
    "fastapi": _stub_module(
        "fastapi",
        FastAPI=_Framework,
        Body=lambda default=None, **kw: default,
    ),
    "fastapi.responses": _stub_module(
        "fastapi.responses",
        HTMLResponse=_Framework,
        JSONResponse=_Framework,
    ),
    "pydantic": _stub_module("pydantic", BaseModel=_BaseModelStub),
}
for _name, _mod in _stubs.items():
    if _name not in sys.modules:
        try:
            __import__(_name)
        except ImportError:
            sys.modules[_name] = _mod

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from main import (
    _clean_text,
    _extract_names,
    _format_book,
    _format_subject_work,
    _safe_limit,
    get_book_details,
    search_books,
    search_subject,
)


class TestOpenLibraryRobustnessAndNullGuards(unittest.TestCase):
    def test_safe_limit_booleans_and_edge_cases(self):
        # Booleans must not be coerced to 1 or 0
        self.assertEqual(_safe_limit(True, default=5), 5)
        self.assertEqual(_safe_limit(False, default=5), 5)
        self.assertEqual(_safe_limit(None, default=5), 5)
        self.assertEqual(_safe_limit("", default=5), 5)
        self.assertEqual(_safe_limit("not-a-number", default=5), 5)
        self.assertEqual(_safe_limit("7", default=5), 7)
        self.assertEqual(_safe_limit(20, default=5), 10)  # clamped to MAX_LIMIT 10
        self.assertEqual(_safe_limit(0, default=5), 1)  # clamped to min 1
        self.assertEqual(_safe_limit(-3, default=5), 1)

    def test_extract_names_heterogeneous_collections(self):
        # Handles None, empty lists, single dict, single string, and mixed items
        self.assertEqual(_extract_names(None), "")
        self.assertEqual(_extract_names([]), "")
        self.assertEqual(_extract_names({"name": "Penguin Books"}), "Penguin Books")
        self.assertEqual(_extract_names("HarperCollins"), "HarperCollins")
        self.assertEqual(
            _extract_names([{"name": "Alice"}, {"name": "Bob"}]),
            "Alice, Bob",
        )
        self.assertEqual(
            _extract_names(["Sci-Fi", "Fantasy", "Mystery"]),
            "Sci-Fi, Fantasy, Mystery",
        )
        self.assertEqual(
            _extract_names([{"name": "Dict Author"}, "String Author", None]),
            "Dict Author, String Author",
        )

    def test_format_book_malformed_and_nulls(self):
        # Must not raise on non-dict
        res_non_dict = _format_book("not a dict", 1)
        self.assertIn("1. Untitled", res_non_dict)

        # Must not raise on null author_name or null subject
        doc = {
            "title": "Clean Code",
            "author_name": None,
            "first_publish_year": 2008,
            "key": "/works/OL12345W",
            "subject": None,
        }
        res = _format_book(doc, 1)
        self.assertIn("Clean Code", res)
        self.assertIn("unknown author", res)
        self.assertIn("OL12345W", res)

    def test_format_subject_work_null_authors_and_keys(self):
        # Must not raise on non-dict
        res_non_dict = _format_subject_work(None, 1)
        self.assertIn("1. Untitled", res_non_dict)

        # In Open Library, "authors": null causes work.get("authors", []) to return None
        # Our implementation must safely handle None authors without TypeError
        work = {
            "title": "A Book With Null Authors",
            "authors": None,
            "first_publish_year": 1999,
            "key": None,
            "edition_count": None,
        }
        res = _format_subject_work(work, 2)
        self.assertIn("2. A Book With Null Authors", res)
        self.assertIn("Author: unknown author", res)
        self.assertIn("Work: unknown", res)

    def test_non_dict_payload_guards(self):
        # All tool endpoints must reject non-dict payloads safely
        for handler in [search_books, get_book_details, search_subject]:
            for bad_payload in [None, "string_payload", [1, 2, 3], 42]:
                resp = asyncio.run(handler(bad_payload))
                self.assertIsNotNone(resp.error)
                self.assertIn("Request body must be a JSON object", resp.error)

    def test_get_book_details_null_isbn_fields(self):
        # Simulate Open Library /api/books response with null authors, publishers, subjects
        mock_data = {
            "ISBN:9780132350884": {
                "title": "Clean Architecture",
                "authors": None,
                "publishers": None,
                "publish_date": None,
                "subjects": None,
                "url": "https://openlibrary.org/books/OL1M",
            }
        }
        with patch("main._request_json") as mock_req:
            mock_req.return_value = mock_data
            resp = asyncio.run(get_book_details({"isbn": "9780132350884"}))
            self.assertIsNone(resp.error)
            self.assertIn("Clean Architecture", resp.result)
            self.assertIn("Author: unknown author", resp.result)
            self.assertIn("Published: unknown date", resp.result)

    def test_get_book_details_string_publishers_and_subjects(self):
        mock_data = {
            "ISBN:9780132350884": {
                "title": "Clean Architecture",
                "authors": [{"name": "Robert C. Martin"}],
                "publishers": ["Prentice Hall", "Pearson"],
                "publish_date": "2017",
                "subjects": ["Software Architecture", "Programming"],
                "url": "https://openlibrary.org/books/OL1M",
            }
        }
        with patch("main._request_json") as mock_req:
            mock_req.return_value = mock_data
            resp = asyncio.run(get_book_details({"isbn": "9780132350884"}))
            self.assertIsNone(resp.error)
            self.assertIn("Publisher: Prentice Hall, Pearson", resp.result)
            self.assertIn(
                "Subjects: Software Architecture, Programming", resp.result
            )

    def test_get_book_details_work_created_string_or_dict(self):
        # Created can be an ISO string or a dict {"value": "..."}
        mock_work_str = {
            "title": "Design Patterns",
            "created": "1994-10-31T00:00:00.000",
            "description": "Catalog of reusable patterns",
            "subjects": ["Object-oriented programming"],
        }
        with patch("main._request_json") as mock_req:
            mock_req.return_value = mock_work_str
            resp = asyncio.run(get_book_details({"work_id": "OL123W"}))
            self.assertIsNone(resp.error)
            self.assertIn("Record created: 1994-10-31", resp.result)

    def test_search_subject_null_authors_in_works(self):
        mock_subject_data = {
            "name": "Artificial Intelligence",
            "works": [
                {
                    "key": "/works/OL999W",
                    "title": "Deep Learning",
                    "authors": None,
                    "first_publish_year": 2016,
                }
            ],
        }
        with patch("main._request_json") as mock_req:
            mock_req.return_value = mock_subject_data
            resp = asyncio.run(
                search_subject({"subject": "artificial intelligence"})
            )
            self.assertIsNone(resp.error)
            self.assertIn("Deep Learning", resp.result)
            self.assertIn("Author: unknown author", resp.result)


if __name__ == "__main__":
    unittest.main()
