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


def load_app_module():
    """Load open library main module hermetically without contaminating sys.modules."""
    stubs = {}

    try:
        import pydantic
    except (ImportError, ModuleNotFoundError):
        pydantic_mod = types.ModuleType("pydantic")

        class BaseModelStub:
            def __init__(self, **data):
                for k, v in data.items():
                    setattr(self, k, v)

            def model_dump(self):
                return {k: v for k, v in self.__dict__.items() if not k.startswith("_")}

        pydantic_mod.BaseModel = BaseModelStub
        stubs["pydantic"] = pydantic_mod

    try:
        import fastapi
        import fastapi.responses
    except (ImportError, ModuleNotFoundError):
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

    try:
        import httpx
    except (ImportError, ModuleNotFoundError):
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
        cls.main = load_app_module()

    def test_health(self):
        """Verify health endpoint returns ok."""
        res = asyncio.run(self.main.health())
        self.assertEqual(res, {"status": "ok"})

    def test_omi_tools_manifest(self):
        """Verify manifest contains all declared tools."""
        manifest = asyncio.run(self.main.get_omi_tools_manifest())
        tools = manifest.get("tools", [])
        self.assertEqual(len(tools), 3)
        tool_names = [t["name"] for t in tools]
        self.assertIn("search_books", tool_names)
        self.assertIn("get_book_details", tool_names)
        self.assertIn("search_subject", tool_names)

    def test_subject_slug(self):
        """Verify subject slug generation across ascii, unicode, and invalid inputs."""
        self.assertEqual(self.main._subject_slug("science fiction"), "science_fiction")
        self.assertEqual(self.main._subject_slug("history"), "history")
        self.assertEqual(self.main._subject_slug("  space   flight  "), "space_flight")
        self.assertEqual(self.main._subject_slug("español"), "español")
        self.assertEqual(self.main._subject_slug("中文"), "中文")
        self.assertEqual(self.main._subject_slug("música"), "música")
        self.assertEqual(self.main._subject_slug("日本語"), "日本語")
        self.assertEqual(self.main._subject_slug("science / fiction?"), "science_fiction")
        self.assertEqual(self.main._subject_slug("art & design"), "art_design")
        self.assertEqual(self.main._subject_slug("c++"), "c")
        self.assertEqual(self.main._subject_slug(""), None)
        self.assertEqual(self.main._subject_slug("   "), None)
        self.assertEqual(self.main._subject_slug(None), None)

    def test_parsing_helpers(self):
        """Verify parsing helpers for work IDs, ISBNs, limits, and descriptions."""
        self.assertEqual(self.main._work_id("OL45883W"), "OL45883W")
        self.assertEqual(self.main._work_id("/works/OL45883W"), "OL45883W")
        self.assertEqual(self.main._work_id("invalid"), None)
        self.assertEqual(self.main._work_id(""), None)

        self.assertEqual(self.main._safe_isbn("0-306-40615-2"), "0306406152")
        self.assertEqual(self.main._safe_isbn("978-0-306-40615-7"), "9780306406157")
        self.assertEqual(self.main._safe_isbn("123"), None)

        self.assertEqual(self.main._safe_limit(3), 3)
        self.assertEqual(self.main._safe_limit(100), 10)
        self.assertEqual(self.main._safe_limit("not-int"), 5)

        self.assertEqual(self.main._clean_text("<b>Title</b> &amp; subtitle"), "Title & subtitle")
        self.assertEqual(self.main._description_text({"value": "Some description"}), "Some description")
        self.assertEqual(self.main._description_text("Direct description"), "Direct description")

    def test_search_books_success(self):
        """Verify search_books formats results properly."""
        mock_data = {
            "docs": [
                {
                    "title": "Dune",
                    "author_name": ["Frank Herbert"],
                    "first_publish_year": 1965,
                    "key": "/works/OL893415W",
                    "subject": ["Science Fiction", "Space"],
                }
            ]
        }
        with patch.object(self.main, "_request_json", new=AsyncMock(return_value=mock_data)):
            resp = asyncio.run(self.main.search_books({"query": "Dune"}))
            self.assertIsNone(resp.error)
            self.assertIn('Books for "Dune":', resp.result)
            self.assertIn("1. Dune", resp.result)
            self.assertIn("Author: Frank Herbert", resp.result)
            self.assertIn("First published: 1965", resp.result)

    def test_search_books_empty(self):
        """Verify search_books handles empty matches."""
        mock_data = {"docs": []}
        with patch.object(self.main, "_request_json", new=AsyncMock(return_value=mock_data)):
            resp = asyncio.run(self.main.search_books({"query": "nonexistentbook123xyz"}))
            self.assertIsNone(resp.error)
            self.assertEqual(resp.result, "No matching books found.")

    def test_search_books_non_dict_error(self):
        """Verify search_books handles non-dict API response gracefully."""
        with patch.object(self.main, "_request_json", new=AsyncMock(return_value=["bad", "list"])):
            resp = asyncio.run(self.main.search_books({"query": "Dune"}))
            self.assertIsNotNone(resp.error)
            self.assertIn("invalid response", resp.error)

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

    def test_get_book_details_404(self):
        """Verify get_book_details handles 404 cleanly."""
        status_err = self.main.httpx.HTTPStatusError("Not Found", request=MagicMock(), response=MagicMock(status_code=404))
        with patch.object(self.main, "_request_json", new=AsyncMock(side_effect=status_err)):
            resp = asyncio.run(self.main.get_book_details({"work_id": "OL99999999W"}))
            self.assertIsNone(resp.error)
            self.assertIn("No matching Open Library record found", resp.result)

    def test_search_subject_success(self):
        """Verify search_subject handles results and encoding."""
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
        with patch.object(self.main, "_request_json", new=AsyncMock(return_value=mock_data)):
            resp = asyncio.run(self.main.search_subject({"subject": "español", "limit": 5}))
            self.assertIsNone(resp.error)
            self.assertIn("Open Library books for subject español:", resp.result)
            self.assertIn("Don Quijote", resp.result)
            self.assertIn("Author: Miguel de Cervantes", resp.result)

    def test_search_subject_missing(self):
        """Verify search_subject requires subject."""
        resp = asyncio.run(self.main.search_subject({"subject": "   "}))
        self.assertEqual(resp.error, "Provide a subject to browse.")


if __name__ == "__main__":
    unittest.main()
