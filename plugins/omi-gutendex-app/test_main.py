"""Hermetic unit tests for Omi Project Gutenberg Classic Books App."""

from __future__ import annotations

import asyncio
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import AsyncMock, patch

if "httpx" not in sys.modules:
    try:
        import httpx  # type: ignore
    except ImportError:
        httpx = types.ModuleType("httpx")

        class HTTPError(Exception):
            pass

        class HTTPStatusError(HTTPError):
            def __init__(self, message="", request=None, response=None):
                super().__init__(message)
                self.response = response or types.SimpleNamespace(status_code=500)

        class RequestError(HTTPError):
            pass

        class AsyncClient:
            def __init__(self, *args, **kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

            async def get(self, *args, **kwargs):
                pass

            async def aclose(self):
                pass

        httpx.HTTPError = HTTPError
        httpx.HTTPStatusError = HTTPStatusError
        httpx.RequestError = RequestError
        httpx.AsyncClient = AsyncClient
        sys.modules["httpx"] = httpx

if "fastapi" not in sys.modules:
    try:
        import fastapi  # type: ignore
        import fastapi.responses  # type: ignore
    except ImportError:
        fastapi = types.ModuleType("fastapi")

        class FastAPI:
            def __init__(self, *args, **kwargs):
                pass

            def get(self, *args, **kwargs):
                return lambda f: f

            def post(self, *args, **kwargs):
                return lambda f: f

        fastapi.FastAPI = FastAPI
        sys.modules["fastapi"] = fastapi

        responses = types.ModuleType("fastapi.responses")

        class HTMLResponse:
            def __init__(self, content="", status_code=200):
                self.content = content
                self.status_code = status_code

        class JSONResponse:
            def __init__(self, content=None, status_code=200):
                self.content = content or {}
                self.status_code = status_code

        responses.HTMLResponse = HTMLResponse
        responses.JSONResponse = JSONResponse
        sys.modules["fastapi.responses"] = responses
        fastapi.responses = responses

if "pydantic" not in sys.modules:
    try:
        import pydantic  # type: ignore
    except ImportError:
        pydantic = types.ModuleType("pydantic")

        def Field(default=None, **kwargs):
            return default

        class BaseModel:
            def __init__(self, **kwargs):
                for cls in reversed(self.__class__.__mro__):
                    for k, v in getattr(cls, "__dict__", {}).items():
                        if not k.startswith("_") and not callable(v):
                            setattr(self, k, None if v is ... else v)
                for k, v in kwargs.items():
                    setattr(self, k, v)

        pydantic.BaseModel = BaseModel
        pydantic.Field = Field
        sys.modules["pydantic"] = pydantic

# Add plugin directory to path so main can be loaded hermetically
PLUGIN_DIR = Path(__file__).resolve().parent
if str(PLUGIN_DIR) not in sys.path:
    sys.path.insert(0, str(PLUGIN_DIR))

import main

SAMPLE_BOOKS = [
    {
        "id": 1342,
        "title": "Pride and Prejudice",
        "authors": [{"name": "Austen, Jane", "birth_year": 1775, "death_year": 1817}],
        "subjects": ["Courtship -- Fiction", "England -- Fiction", "Domestic fiction"],
        "bookshelves": ["Best Books Ever Listings"],
        "languages": ["en"],
        "copyright": False,
        "download_count": 54300,
        "formats": {
            "text/html": "https://www.gutenberg.org/ebooks/1342.html.images",
            "application/epub+zip": "https://www.gutenberg.org/ebooks/1342.epub3.images",
            "text/plain; charset=utf-8": "https://www.gutenberg.org/ebooks/1342.txt.utf-8",
        },
    },
    {
        "id": 84,
        "title": "Frankenstein; Or, The Modern Prometheus",
        "authors": [{"name": "Shelley, Mary Wollstonecraft", "birth_year": 1797, "death_year": 1851}],
        "subjects": ["Monsters -- Fiction", "Science fiction", "Gothic fiction"],
        "bookshelves": ["Gothic Fiction"],
        "languages": ["en"],
        "copyright": False,
        "download_count": 87000,
        "formats": {
            "text/html": "https://www.gutenberg.org/ebooks/84.html.images",
            "application/epub+zip": "https://www.gutenberg.org/ebooks/84.epub3.images",
        },
    },
]


class GutendexAppTests(unittest.TestCase):
    def test_format_book_summary(self) -> None:
        summary = main.format_book_summary(SAMPLE_BOOKS[0])
        self.assertIn("📖 **Pride and Prejudice** (ID: #1342)", summary)
        self.assertIn("✍️ Author(s): Austen, Jane", summary)
        self.assertIn("🏷️ Subjects: Courtship, England, Domestic fiction", summary)
        self.assertIn("📥 Downloads: 54,300", summary)
        self.assertIn("🔗 Read / Download: https://www.gutenberg.org/ebooks/1342.html.images", summary)

    def test_manifest_endpoint(self) -> None:
        res = asyncio.run(main.manifest())
        self.assertEqual(res.content["schema_version"], "v1")
        self.assertEqual(res.content["name_for_model"], "gutenberg_books_app")
        self.assertIn("description_for_human", res.content)

    def test_ai_plugin_manifest_endpoint(self) -> None:
        res = asyncio.run(main.ai_plugin_manifest())
        self.assertEqual(res.content["name_for_model"], "gutenberg_books_app")

    def test_health_endpoint(self) -> None:
        res = asyncio.run(main.health())
        self.assertEqual(res, {"status": "ok", "app": "omi-gutendex-app"})

    def test_privacy_endpoint(self) -> None:
        res = asyncio.run(main.privacy())
        self.assertIn("Privacy Policy", res.content)

    def test_index_endpoint(self) -> None:
        res = asyncio.run(main.index())
        self.assertIn("Omi Project Gutenberg App", res.content)

    @patch("main.fetch_books_from_api")
    def test_search_books_tool_success(self, mock_fetch: AsyncMock) -> None:
        mock_fetch.return_value = SAMPLE_BOOKS
        req = main.SearchBooksRequest(query="Pride", limit=5)
        res = asyncio.run(main.tool_search_books(req))
        self.assertIsNone(res.error)
        self.assertIn("Pride and Prejudice", res.result)
        self.assertIn("Project Gutenberg Classic Books", res.result)

    @patch("main.fetch_books_from_api")
    def test_search_books_empty(self, mock_fetch: AsyncMock) -> None:
        mock_fetch.return_value = []
        req = main.SearchBooksRequest(query="XYZNonExistent999")
        res = asyncio.run(main.tool_search_books(req))
        self.assertIsNone(res.error)
        self.assertIn("No classic books found", res.result)

    def test_search_books_empty_query(self) -> None:
        req = main.SearchBooksRequest(query="   ")
        res = asyncio.run(main.tool_search_books(req))
        self.assertEqual(res.error, "Search query cannot be empty.")

    @patch("main.fetch_books_from_api")
    def test_books_by_topic_tool_success(self, mock_fetch: AsyncMock) -> None:
        mock_fetch.return_value = [SAMPLE_BOOKS[1]]
        req = main.BooksByTopicRequest(topic="Gothic", limit=5)
        res = asyncio.run(main.tool_books_by_topic(req))
        self.assertIsNone(res.error)
        self.assertIn("Classic Literature in Topic: 'Gothic'", res.result)
        self.assertIn("Frankenstein", res.result)

    @patch("main.fetch_books_from_api")
    def test_books_by_topic_empty(self, mock_fetch: AsyncMock) -> None:
        mock_fetch.return_value = []
        req = main.BooksByTopicRequest(topic="QuantumRobotics1800")
        res = asyncio.run(main.tool_books_by_topic(req))
        self.assertIsNone(res.error)
        self.assertIn("No classic books found for topic", res.result)

    @patch("main.fetch_books_from_api")
    def test_book_details_tool_success(self, mock_fetch: AsyncMock) -> None:
        mock_fetch.return_value = SAMPLE_BOOKS
        req = main.BookDetailsRequest(book_id_or_title="1342")
        res = asyncio.run(main.tool_book_details(req))
        self.assertIsNone(res.error)
        self.assertIn("Book: Pride and Prejudice (ID: #1342)", res.result)
        self.assertIn("Austen, Jane (1775–1817)", res.result)
        self.assertIn("EPUB E-Book", res.result)
        self.assertIn("Read Online (HTML)", res.result)

    @patch("main.fetch_books_from_api")
    def test_book_details_not_found(self, mock_fetch: AsyncMock) -> None:
        mock_fetch.return_value = []
        req = main.BookDetailsRequest(book_id_or_title="9999999")
        res = asyncio.run(main.tool_book_details(req))
        self.assertIsNone(res.error)
        self.assertIn("Could not find details for book", res.result)

    @patch("main.fetch_books_from_api", side_effect=RuntimeError("Gutendex API Service Unavailable"))
    def test_api_error_handling(self, mock_fetch: AsyncMock) -> None:
        req = main.SearchBooksRequest(query="Hamlet")
        res = asyncio.run(main.tool_search_books(req))
        self.assertEqual(res.error, "Gutendex API Service Unavailable")
        self.assertIsNone(res.result)


if __name__ == "__main__":
    unittest.main()
