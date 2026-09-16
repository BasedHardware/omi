"""
Hermetic test suite for the Semantic Scholar integration app.

Exercises manifest schemas, author formatting, year formatting,
identifier normalization, and tool endpoints without external services.
Runs cleanly under pure standard library Python (including python3 -S).
"""

from __future__ import annotations

import asyncio
import importlib.util
from pathlib import Path
import sys
from types import ModuleType
import unittest
from unittest.mock import AsyncMock, Mock, patch


def load_app():
    class FastAPI:
        def __init__(self, **kwargs):
            pass

        def get(self, *args, **kwargs):
            return lambda handler: handler

        post = get

    class BaseModel:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    fastapi = ModuleType("fastapi")
    fastapi.FastAPI = FastAPI

    httpx = ModuleType("httpx")
    httpx.AsyncClient = Mock()
    httpx.HTTPStatusError = type("HTTPStatusError", (Exception,), {})
    httpx.HTTPError = type("HTTPError", (Exception,), {})

    models = ModuleType("models")
    class ChatToolResponse(BaseModel):
        def __init__(self, result=None, error=None):
            self.result = result
            self.error = error

    class SearchPapersRequest(BaseModel):
        def __init__(self, query="", max_results=5, min_year=None):
            self.query = query
            self.max_results = max_results
            self.min_year = min_year

    class GetPaperRequest(BaseModel):
        def __init__(self, paper_id_or_doi=""):
            self.paper_id_or_doi = paper_id_or_doi

    class GetAuthorPapersRequest(BaseModel):
        def __init__(self, author_id="", max_results=5):
            self.author_id = author_id
            self.max_results = max_results

    models.ChatToolResponse = ChatToolResponse
    models.SearchPapersRequest = SearchPapersRequest
    models.GetPaperRequest = GetPaperRequest
    models.GetAuthorPapersRequest = GetAuthorPapersRequest

    stubs = {
        "fastapi": fastapi,
        "httpx": httpx,
        "models": models,
    }

    app_path = Path(__file__).resolve().parent / "main.py"
    spec = importlib.util.spec_from_file_location("semantic_scholar_main", app_path)
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, stubs):
        spec.loader.exec_module(module)
    return module, stubs


app_module, stubs = load_app()


class SemanticScholarAppTests(unittest.TestCase):
    def test_manifest_schema_compliance(self):
        coro = app_module.manifest()
        man = asyncio.run(coro)
        self.assertIn("tools", man)
        self.assertEqual(len(man["tools"]), 3)

        for tool in man["tools"]:
            self.assertIn("name", tool)
            self.assertIn("description", tool)
            self.assertIn("parameters", tool)
            params = tool["parameters"]
            self.assertEqual(params.get("type"), "object")
            self.assertIn("properties", params)
            self.assertIn("required", params)

    def test_format_authors(self):
        self.assertEqual(app_module.format_authors([]), "Unknown")
        self.assertEqual(app_module.format_authors([{"name": "Alice"}, {"name": "Bob"}]), "Alice, Bob")

    def test_format_year(self):
        self.assertEqual(app_module.format_year(2024), "2024")
        self.assertEqual(app_module.format_year(None), "Unknown")
        self.assertEqual(app_module.format_year("2024"), "Unknown")

    def test_normalize_identifier(self):
        self.assertEqual(app_module.normalize_identifier("10.1038/nature123"), "10.1038/nature123")
        self.assertEqual(app_module.normalize_identifier("doi:10.1038/nature123"), "DOI:10.1038/nature123")
        self.assertEqual(app_module.normalize_identifier("DOI:10.1038/nature123"), "DOI:10.1038/nature123")

    def test_search_papers_success(self):
        req = stubs["models"].SearchPapersRequest(query="deep learning", max_results=5)
        mock_data = {
            "data": [
                {
                    "title": "Attention Is All You Need",
                    "year": 2017,
                    "authors": [{"name": "Ashish Vaswani"}],
                    "venue": "NeurIPS",
                    "citationCount": 100000,
                    "url": "https://example.com/paper",
                }
            ]
        }
        with patch.object(app_module, "api_get", new=AsyncMock(return_value=mock_data)):
            resp = asyncio.run(app_module.search_papers(req))
            self.assertIn("Attention Is All You Need", resp.result)
            self.assertIn("Ashish Vaswani", resp.result)

    def test_search_papers_empty(self):
        req = stubs["models"].SearchPapersRequest(query="nonexistent_xyz_paper", max_results=5)
        with patch.object(app_module, "api_get", new=AsyncMock(return_value={"data": []})):
            resp = asyncio.run(app_module.search_papers(req))
            self.assertIn("No papers found", resp.result)

    def test_get_paper_success(self):
        req = stubs["models"].GetPaperRequest(paper_id_or_doi="10.1038/nature123")
        mock_data = {
            "title": "Structure of DNA",
            "year": 1953,
            "authors": [{"name": "Watson"}, {"name": "Crick"}],
            "venue": "Nature",
            "citationCount": 5000,
            "referenceCount": 10,
            "abstract": "Molecular structure of Nucleic Acids",
            "url": "https://example.com/dna",
        }
        with patch.object(app_module, "api_get", new=AsyncMock(return_value=mock_data)):
            resp = asyncio.run(app_module.get_paper(req))
            self.assertIn("Structure of DNA", resp.result)
            self.assertIn("Watson, Crick", resp.result)


if __name__ == "__main__":
    unittest.main()
