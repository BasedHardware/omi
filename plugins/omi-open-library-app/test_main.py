"""Hermetic unit tests for Omi Open Library Integration App.

Runs with standard library unittest and hermetic stubs without requiring
external dependencies or live network access.
"""

import asyncio
import importlib.util
import os
import sys
import types
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))


def load_app_module(force_stubs: bool = True):
    """Load open library main module hermetically without contaminating sys.modules.

    When force_stubs is True (the default for reproducible hermetic execution),
    stubs are installed unconditionally regardless of what packages exist in the environment.
    """
    stubs = {}

    pydantic_mod = types.ModuleType("pydantic")

    class BaseModelStub:
        def __init__(self, **data):
            for k, v in data.items():
                setattr(self, k, v)

        def model_dump(self):
            return {k: v for k, v in self.__dict__.items() if not k.startswith("_")}

    pydantic_mod.BaseModel = BaseModelStub
    stubs["pydantic"] = pydantic_mod

    fastapi_mod = types.ModuleType("fastapi")

    class FastAPIStub:
        def __init__(self, **kwargs):
            self.routes = {}

        def get(self, path, **kwargs):
            def decorator(fn):
                self.routes[("GET", path)] = fn
                return fn
            return decorator

        def post(self, path, **kwargs):
            def decorator(fn):
                self.routes[("POST", path)] = fn
                return fn
            return decorator

    fastapi_responses = types.ModuleType("fastapi.responses")

    class HTMLResponseStub:
        pass

    fastapi_responses.HTMLResponse = HTMLResponseStub
    fastapi_mod.FastAPI = FastAPIStub
    fastapi_mod.responses = fastapi_responses
    stubs["fastapi"] = fastapi_mod
    stubs["fastapi.responses"] = fastapi_responses

    httpx_mod = types.ModuleType("httpx")

    class HTTPErrorStub(Exception):
        pass

    class HTTPStatusErrorStub(HTTPErrorStub):
        def __init__(self, message="", request=None, response=None):
            super().__init__(message)
            self.response = response or MagicMock(status_code=500)

    class AsyncClientStub:
        def __init__(self, **kwargs):
            self.is_closed = False

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            self.is_closed = True

        async def get(self, url, **kwargs):
            pass

        async def aclose(self):
            self.is_closed = True

    httpx_mod.AsyncClient = AsyncClientStub
    httpx_mod.HTTPError = HTTPErrorStub
    httpx_mod.HTTPStatusError = HTTPStatusErrorStub
    stubs["httpx"] = httpx_mod

    with patch.dict(sys.modules, stubs):
        main_path = os.path.join(PLUGIN_DIR, "main.py")
        main_spec = importlib.util.spec_from_file_location("main", main_path)
        main_mod = importlib.util.module_from_spec(main_spec)
        main_spec.loader.exec_module(main_mod)

    return main_mod


class TestOpenLibraryApp(unittest.TestCase):
    """Test suite for Open Library integration endpoints and parsing helpers."""

    @classmethod
    def setUpClass(cls):
        # Always run hermetic suite deterministically against isolated stubs
        cls.main = load_app_module(force_stubs=True)

    def test_health_endpoint(self):
        """Verify health check returns ok status."""
        res = asyncio.run(self.main.health())
        self.assertEqual(res, {"status": "ok"})

    def test_omi_tools_manifest(self):
        """Verify manifest contains all three declared tools."""
        manifest = asyncio.run(self.main.get_omi_tools_manifest())
        tools = manifest["tools"]
        tool_names = [t["name"] for t in tools]
        self.assertIn("search_books", tool_names)
        self.assertIn("get_book_details", tool_names)
        self.assertIn("search_subject", tool_names)

    def test_helper_clean_text(self):
        """Verify _clean_text normalizes whitespace and none."""
        self.assertEqual(self.main._clean_text(None), "")
        self.assertEqual(self.main._clean_text(""), "")
        self.assertEqual(self.main._clean_text("  Dune   Messiah  "), "Dune Messiah")

    def test_helper_safe_limit(self):
        """Verify _safe_limit sanitizes inputs within bounds 1-10."""
        self.assertEqual(self.main._safe_limit(None), 5)
        self.assertEqual(self.main._safe_limit(""), 5)
        self.assertEqual(self.main._safe_limit("invalid"), 5)
        self.assertEqual(self.main._safe_limit(-1), 1)
        self.assertEqual(self.main._safe_limit(0), 1)
        self.assertEqual(self.main._safe_limit(7), 7)
        self.assertEqual(self.main._safe_limit(20), 10)

    def test_helper_safe_isbn(self):
        """Verify _safe_isbn normalizes valid ISBNs and rejects invalid characters."""
        self.assertEqual(self.main._safe_isbn("978-0-306-40615-7"), "9780306406157")
        self.assertEqual(self.main._safe_isbn("0451450523"), "0451450523")
        self.assertIsNone(self.main._safe_isbn("not-an-isbn"))
        self.assertIsNone(self.main._safe_isbn(None))

    def test_helper_work_id(self):
        """Verify _work_id extracts canonical work key."""
        self.assertEqual(self.main._work_id("OL45883W"), "OL45883W")
        self.assertEqual(self.main._work_id("/works/OL45883W"), "OL45883W")
        self.assertIsNone(self.main._work_id("invalid-key"))
        self.assertIsNone(self.main._work_id(None))
        self.assertIsNone(self.main._work_id(""))

    def test_helper_subject_slug(self):
        """Verify _subject_slug slugifies subject names cleanly."""
        self.assertEqual(self.main._subject_slug("Science Fiction"), "science_fiction")
        self.assertEqual(self.main._subject_slug("science / fiction?"), "science_fiction")
        self.assertEqual(self.main._subject_slug("español"), "español")
        self.assertIsNone(self.main._subject_slug(""))
        self.assertIsNone(self.main._subject_slug(None))

    def test_format_book_defensive(self):
        """Verify _format_book handles non-dict and malformed values defensively."""
        res_empty = self.main._format_book(None, 1)
        self.assertIn("1. Untitled", res_empty)

        res_malformed = self.main._format_book(
            {
                "title": "Neuromancer",
                "author_name": "NotAList",
                "first_publish_year": "1984",
                "key": "/works/OL100W",
                "subject": None,
            },
            2,
        )
        self.assertIn("2. Neuromancer", res_malformed)
        self.assertIn("First published: 1984", res_malformed)
        self.assertIn("Open Library work: OL100W", res_malformed)

    def test_format_subject_work_defensive(self):
        """Verify _format_subject_work handles non-dict and malformed values defensively."""
        res_empty = self.main._format_subject_work(None, 1)
        self.assertIn("1. Untitled", res_empty)

        res_malformed = self.main._format_subject_work(
            {
                "title": "Snow Crash",
                "authors": "NotAList",
                "first_publish_year": 1992,
                "key": "/works/OL200W",
                "edition_count": 15,
            },
            2,
        )
        self.assertIn("2. Snow Crash", res_malformed)
        self.assertIn("Editions: 15", res_malformed)

    def test_search_books_success(self):
        """Verify search_books returns formatted list of results."""
        mock_data = {
            "docs": [
                {
                    "title": "Dune",
                    "author_name": ["Frank Herbert"],
                    "first_publish_year": 1965,
                    "key": "/works/OL893415W",
                    "subject": ["Science Fiction", "Arrakis"],
                }
            ]
        }
        with patch.object(self.main, "_request_json", new=AsyncMock(return_value=mock_data)):
            resp = asyncio.run(self.main.search_books({"query": "Dune", "limit": 1}))
            self.assertIsNone(resp.error)
            self.assertIn('Books for "Dune":', resp.result)
            self.assertIn("1. Dune", resp.result)
            self.assertIn("Author: Frank Herbert", resp.result)

    def test_search_books_empty(self):
        """Verify search_books handles zero matching docs."""
        with patch.object(self.main, "_request_json", new=AsyncMock(return_value={"docs": []})):
            resp = asyncio.run(self.main.search_books({"query": "nonexistenttitle12345"}))
            self.assertIsNone(resp.error)
            self.assertIn("No matching books found.", resp.result)

    def test_search_books_non_dict_error(self):
        """Verify search_books handles non-dict API response gracefully."""
        with patch.object(self.main, "_request_json", new=AsyncMock(return_value=["bad", "list"])):
            resp = asyncio.run(self.main.search_books({"query": "Dune"}))
            self.assertIsNotNone(resp.error)
            self.assertIn("invalid response", resp.error)

    def test_search_books_docs_none_or_non_list(self):
        """Verify search_books handles None or non-list 'docs' payload gracefully (regression coverage)."""
        # docs is None
        with patch.object(self.main, "_request_json", new=AsyncMock(return_value={"docs": None})):
            resp = asyncio.run(self.main.search_books({"query": "Dune"}))
            self.assertIsNone(resp.error)
            self.assertEqual(resp.result, "No matching books found.")

        # docs is a string or scalar
        with patch.object(self.main, "_request_json", new=AsyncMock(return_value={"docs": "corrupt_string"})):
            resp = asyncio.run(self.main.search_books({"query": "Dune"}))
            self.assertIsNone(resp.error)
            self.assertEqual(resp.result, "No matching books found.")

    def test_get_book_details_by_isbn(self):
        """Verify get_book_details lookup by ISBN."""
        mock_data = {
            "ISBN:9780306406157": {
                "title": "Quantum Mechanics",
                "authors": [{"name": "David Griffiths"}],
                "publishers": [{"name": "Cambridge University Press"}],
                "publish_date": "2005",
                "url": "https://openlibrary.org/books/OL1M",
                "subjects": [{"name": "Physics"}],
            }
        }
        with patch.object(self.main, "_request_json", new=AsyncMock(return_value=mock_data)):
            resp = asyncio.run(self.main.get_book_details({"isbn": "978-0-306-40615-7"}))
            self.assertIsNone(resp.error)
            self.assertIn("Quantum Mechanics", resp.result)
            self.assertIn("Author: David Griffiths", resp.result)
            self.assertIn("Publisher: Cambridge University Press", resp.result)

    def test_get_book_details_isbn_non_dict_payload(self):
        """Verify get_book_details handles non-dict response for ISBN lookups (regression coverage)."""
        with patch.object(self.main, "_request_json", new=AsyncMock(return_value=["corrupted", "list"])):
            resp = asyncio.run(self.main.get_book_details({"isbn": "9780306406157"}))
            self.assertIsNotNone(resp.error)
            self.assertIn("invalid response for ISBN", resp.error)

    def test_get_book_details_isbn_non_list_fields(self):
        """Verify get_book_details handles None or non-list authors, publishers, and subjects."""
        mock_data = {
            "ISBN:9780306406157": {
                "title": "Quantum Mechanics",
                "authors": None,
                "publishers": "InvalidPublisherString",
                "subjects": None,
                "publish_date": "2005",
                "url": "https://openlibrary.org/books/OL1M",
            }
        }
        with patch.object(self.main, "_request_json", new=AsyncMock(return_value=mock_data)):
            resp = asyncio.run(self.main.get_book_details({"isbn": "9780306406157"}))
            self.assertIsNone(resp.error)
            self.assertIn("Quantum Mechanics", resp.result)
            self.assertIn("Author: unknown author", resp.result)
            self.assertNotIn("Publisher:", resp.result)
            self.assertNotIn("Subjects:", resp.result)

    def test_get_book_details_by_work_id(self):
        """Verify get_book_details lookup by work ID."""
        mock_data = {
            "title": "Foundation",
            "description": {"value": "Galactic empire epic."},
            "subjects": ["Science Fiction"],
            "created": {"value": "2008-04-01T03:28:50"},
        }
        with patch.object(self.main, "_request_json", new=AsyncMock(return_value=mock_data)):
            resp = asyncio.run(self.main.get_book_details({"work_id": "OL45883W"}))
            self.assertIsNone(resp.error)
            self.assertIn("Foundation", resp.result)
            self.assertIn("Open Library work: OL45883W", resp.result)
            self.assertIn("Galactic empire epic.", resp.result)

    def test_get_book_details_work_non_dict_payload(self):
        """Verify get_book_details handles non-dict response for work ID lookups (regression coverage)."""
        with patch.object(self.main, "_request_json", new=AsyncMock(return_value="unexpected text")):
            resp = asyncio.run(self.main.get_book_details({"work_id": "OL45883W"}))
            self.assertIsNotNone(resp.error)
            self.assertIn("invalid response for work", resp.error)

    def test_get_book_details_404(self):
        """Verify get_book_details handles 404 cleanly."""
        status_err = self.main.httpx.HTTPStatusError("Not Found", request=MagicMock(), response=MagicMock(status_code=404))
        with patch.object(self.main, "_request_json", new=AsyncMock(side_effect=status_err)):
            resp = asyncio.run(self.main.get_book_details({"work_id": "OL99999999W"}))
            self.assertIsNone(resp.error)
            self.assertIn("No matching Open Library record found", resp.result)

    def test_search_subject_success(self):
        """Verify search_subject handles results and explicitly tests URL encoding."""
        mock_data = {
            "name": "español",
            "works": [
                {
                    "key": "/works/OL123W",
                    "title": "Don Quijote",
                    "authors": [{"name": "Miguel de Cervantes"}],
                    "first_publish_year": 1605,
                    "edition_count": 42,
                }
            ],
        }
        mock_req = AsyncMock(return_value=mock_data)
        with patch.object(self.main, "_request_json", new=mock_req):
            resp = asyncio.run(self.main.search_subject({"subject": "español", "limit": 5}))
            self.assertIsNone(resp.error)
            self.assertIn("Open Library books for subject español:", resp.result)
            self.assertIn("Don Quijote", resp.result)
            self.assertIn("Author: Miguel de Cervantes", resp.result)
            # Explicitly assert that the endpoint was awaited with percent-encoded Unicode subject slug
            mock_req.assert_awaited_once_with("/subjects/espa%C3%B1ol.json", params={"limit": 5})

    def test_search_subject_non_dict_and_non_list_works(self):
        """Verify search_subject handles non-dict response and None/non-list 'works' (regression coverage)."""
        # Non-dict response
        with patch.object(self.main, "_request_json", new=AsyncMock(return_value=["bad", "data"])):
            resp = asyncio.run(self.main.search_subject({"subject": "history"}))
            self.assertIsNotNone(resp.error)
            self.assertIn("invalid response for history", resp.error)

        # works is None
        with patch.object(self.main, "_request_json", new=AsyncMock(return_value={"works": None})):
            resp = asyncio.run(self.main.search_subject({"subject": "history"}))
            self.assertIsNone(resp.error)
            self.assertEqual(resp.result, "No books found for subject history.")

        # works is non-list
        with patch.object(self.main, "_request_json", new=AsyncMock(return_value={"works": "not_a_list"})):
            resp = asyncio.run(self.main.search_subject({"subject": "history"}))
            self.assertIsNone(resp.error)
            self.assertEqual(resp.result, "No books found for subject history.")

    def test_search_subject_missing(self):
        """Verify search_subject requires subject."""
        resp = asyncio.run(self.main.search_subject({"subject": "   "}))
        self.assertEqual(resp.error, "Provide a subject to browse.")


if __name__ == "__main__":
    unittest.main()
