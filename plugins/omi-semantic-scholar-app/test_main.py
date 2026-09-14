from pathlib import Path
import importlib.util
import sys
import types
import unittest
from unittest.mock import AsyncMock, patch

# Provide lightweight scoped stubs for third-party runtime dependencies so test_main.py
# runs hermetically on any clean standard library Python environment without
# mutating the process-global sys.modules for other test suites.
stubs = {}

if "httpx" not in sys.modules:
    try:
        import httpx  # type: ignore
    except ImportError:
        _httpx = types.ModuleType("httpx")

        class HTTPError(Exception):
            pass

        class HTTPStatusError(HTTPError):
            def __init__(self, message="", *, request=None, response=None):
                super().__init__(message)
                self.request = request
                self.response = response

        class Response:
            def __init__(self, status_code=200, json_data=None):
                self.status_code = status_code
                self._json = json_data or {}

            def raise_for_status(self):
                if self.status_code >= 400:
                    raise HTTPStatusError(f"Error {self.status_code}", response=self)

            def json(self):
                return self._json

        class AsyncClient:
            def __init__(self, *args, **kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

            async def get(self, *args, **kwargs):
                return Response()

        _httpx.HTTPError = HTTPError
        _httpx.HTTPStatusError = HTTPStatusError
        _httpx.Response = Response
        _httpx.AsyncClient = AsyncClient
        stubs["httpx"] = _httpx

if "fastapi" not in sys.modules:
    try:
        import fastapi  # type: ignore
    except ImportError:
        _fastapi = types.ModuleType("fastapi")

        class FastAPI:
            def __init__(self, *args, **kwargs):
                pass

            def get(self, *args, **kwargs):
                return lambda f: f

            def post(self, *args, **kwargs):
                return lambda f: f

        _fastapi.FastAPI = FastAPI
        stubs["fastapi"] = _fastapi

if "pydantic" not in sys.modules:
    try:
        import pydantic  # type: ignore
    except ImportError:
        _pydantic = types.ModuleType("pydantic")

        def Field(default=None, **kwargs):
            return default

        def model_validator(**kwargs):
            return lambda f: f

        class BaseModel:
            def __init__(self, **kwargs):
                for cls in reversed(self.__class__.__mro__):
                    for k, v in getattr(cls, "__dict__", {}).items():
                        if not k.startswith("_") and not callable(v):
                            setattr(self, k, None if v is ... else v)
                for k, v in kwargs.items():
                    setattr(self, k, v)

        _pydantic.BaseModel = BaseModel
        _pydantic.Field = Field
        _pydantic.model_validator = model_validator
        stubs["pydantic"] = _pydantic

PLUGIN_DIR = Path(__file__).resolve().parent

# Load models and main hermetically within an isolated patch.dict context,
# so process-global sys.modules is never permanently mutated.
with patch.dict(sys.modules, stubs):
    models_path = PLUGIN_DIR / "models.py"
    models_spec = importlib.util.spec_from_file_location("models", models_path)
    models = importlib.util.module_from_spec(models_spec)
    with patch.dict(sys.modules, {"models": models}):
        models_spec.loader.exec_module(models)

    main_path = PLUGIN_DIR / "main.py"
    main_spec = importlib.util.spec_from_file_location("main", main_path)
    main = importlib.util.module_from_spec(main_spec)
    with patch.dict(sys.modules, {"models": models}):
        main_spec.loader.exec_module(main)


class SemanticScholarHelperTests(unittest.TestCase):
    def test_format_authors_various_shapes(self):
        # Valid authors
        authors = [{"name": "Alice Smith"}, {"name": "Bob Jones"}]
        self.assertEqual(main.format_authors(authors), "Alice Smith, Bob Jones")

        # More than 6 authors truncated
        seven_authors = [{"name": f"Author {i}"} for i in range(1, 8)]
        formatted = main.format_authors(seven_authors)
        self.assertEqual(formatted, "Author 1, Author 2, Author 3, Author 4, Author 5, Author 6")

        # Missing or empty names
        self.assertEqual(main.format_authors([{"name": ""}, {"name": None}, {}]), "Unknown")

        # None or non-list
        self.assertEqual(main.format_authors(None), "Unknown")
        self.assertEqual(main.format_authors("not-a-list"), "Unknown")
        self.assertEqual(main.format_authors([]), "Unknown")

        # Non-dict elements handled gracefully
        self.assertEqual(main.format_authors([None, 123, "Alice"]), "Unknown")

    def test_format_year_various_shapes(self):
        self.assertEqual(main.format_year(2024), "2024")
        self.assertEqual(main.format_year("2023"), "2023")
        self.assertEqual(main.format_year(" 2021 "), "2021")
        self.assertEqual(main.format_year(None), "Unknown")
        self.assertEqual(main.format_year(True), "Unknown")
        self.assertEqual(main.format_year(False), "Unknown")
        self.assertEqual(main.format_year("circa 2020"), "Unknown")
        self.assertEqual(main.format_year(""), "Unknown")
        self.assertEqual(main.format_year("9" * 5000), "Unknown")

    def test_normalize_identifier(self):
        # Bare DOI gets DOI: prefix
        self.assertEqual(main.normalize_identifier("10.1038/nature12373"), "DOI:10.1038/nature12373")

        # Existing DOI prefix preserved / normalized
        self.assertEqual(main.normalize_identifier("doi:10.1038/nature12373"), "DOI:10.1038/nature12373")
        self.assertEqual(main.normalize_identifier("DOI:10.1038/nature12373"), "DOI:10.1038/nature12373")

        # URL prefix stripped
        self.assertEqual(
            main.normalize_identifier("https://doi.org/10.1038/nature12373"),
            "DOI:10.1038/nature12373",
        )
        self.assertEqual(
            main.normalize_identifier("http://dx.doi.org/10.1038/nature12373"),
            "DOI:10.1038/nature12373",
        )

        # ArXiv URL & prefix (including uppercase .PDF extension)
        self.assertEqual(main.normalize_identifier("https://arxiv.org/abs/2106.15928"), "ARXIV:2106.15928")
        self.assertEqual(main.normalize_identifier("https://arxiv.org/pdf/2106.15928.pdf"), "ARXIV:2106.15928")
        self.assertEqual(main.normalize_identifier("https://arxiv.org/pdf/2106.15928.PDF"), "ARXIV:2106.15928")
        self.assertEqual(main.normalize_identifier("arxiv:2106.15928"), "ARXIV:2106.15928")

        # PMID prefix
        self.assertEqual(main.normalize_identifier("pmid:12345678"), "PMID:12345678")

        # CorpusId canonical spelling preserved
        self.assertEqual(main.normalize_identifier("CorpusId:215416146"), "CorpusId:215416146")
        self.assertEqual(main.normalize_identifier("corpusid:215416146"), "CorpusId:215416146")

        # Raw Semantic Scholar hash/id untouched
        self.assertEqual(
            main.normalize_identifier("649def34f8be52c8b66281af98ae884c09aef38b"),
            "649def34f8be52c8b66281af98ae884c09aef38b",
        )

    def test_paper_sort_key_heterogeneous_types(self):
        p1 = {"year": 2024, "citationCount": 100}
        p2 = {"year": "2023", "citationCount": "50"}
        p3 = {"year": None, "citationCount": None}
        p4 = {"year": "invalid", "citationCount": 10}
        p5 = "not-a-dict"

        self.assertEqual(main._paper_sort_key(p1), (2024, 100))
        self.assertEqual(main._paper_sort_key(p2), (2023, 50))
        self.assertEqual(main._paper_sort_key(p3), (0, 0))
        self.assertEqual(main._paper_sort_key(p4), (0, 10))
        self.assertEqual(main._paper_sort_key(p5), (0, 0))

        # Sorting heterogeneous items must never raise TypeError
        items = [p3, p1, p4, p2]
        sorted_items = sorted(items, key=main._paper_sort_key, reverse=True)
        self.assertEqual(sorted_items[0], p1)
        self.assertEqual(sorted_items[1], p2)


class SemanticScholarEndpointTests(unittest.IsolatedAsyncioTestCase):
    async def test_search_papers_success(self):
        payload = {
            "data": [
                {
                    "title": "Attention Is All You Need",
                    "year": 2017,
                    "authors": [{"name": "Ashish Vaswani"}, {"name": "Noam Shazeer"}],
                    "venue": "NeurIPS",
                    "citationCount": 115000,
                    "url": "https://www.semanticscholar.org/paper/123",
                }
            ]
        }
        req = models.SearchPapersRequest(query="Attention Is All You Need", max_results=1)
        with patch.object(main, "api_get", new=AsyncMock(return_value=payload)):
            res = await main.search_papers(req)

        self.assertIsNone(res.error)
        self.assertIn("1. Attention Is All You Need", res.result)
        self.assertIn("Authors: Ashish Vaswani, Noam Shazeer", res.result)
        self.assertIn("Year: 2017", res.result)
        self.assertIn("Citations: 115000", res.result)

    async def test_search_papers_null_data(self):
        # API returning {"data": null} must not crash with TypeError
        req = models.SearchPapersRequest(query="NonexistentTopic12345")
        with patch.object(main, "api_get", new=AsyncMock(return_value={"data": None})):
            res = await main.search_papers(req)

        self.assertIsNone(res.error)
        self.assertEqual(res.result, "No papers found.")

    async def test_search_papers_http_error(self):
        req = models.SearchPapersRequest(query="Testing Error")
        with patch.object(main, "api_get", new=AsyncMock(side_effect=main.httpx.HTTPError("network down"))):
            res = await main.search_papers(req)

        self.assertIsNone(res.result)
        self.assertIn("Semantic Scholar request failed: network down", res.error)

    async def test_get_paper_success(self):
        payload = {
            "title": "Deep Residual Learning",
            "abstract": "Deeper neural networks are more difficult to train.",
            "year": 2016,
            "authors": [{"name": "Kaiming He"}],
            "venue": "CVPR",
            "citationCount": 180000,
            "referenceCount": 42,
            "url": "https://www.semanticscholar.org/paper/resnet",
        }
        req = models.GetPaperRequest(paper_id_or_doi="10.1109/CVPR.2016.90")
        with patch.object(main, "api_get", new=AsyncMock(return_value=payload)) as mock_api:
            res = await main.get_paper(req)

        mock_api.assert_awaited_once_with(
            "/paper/DOI:10.1109%2FCVPR.2016.90",
            {"fields": "title,abstract,year,authors,citationCount,referenceCount,url,venue"},
        )
        self.assertIsNone(res.error)
        self.assertIn("Title: Deep Residual Learning", res.result)
        self.assertIn("Authors: Kaiming He", res.result)
        self.assertIn("Citations: 180000 | References: 42", res.result)

    async def test_get_paper_not_found(self):
        req = models.GetPaperRequest(paper_id_or_doi="nonexistent")
        mock_resp = types.SimpleNamespace(status_code=404)
        err = main.httpx.HTTPStatusError("Not Found", request=None, response=mock_resp)
        with patch.object(main, "api_get", new=AsyncMock(side_effect=err)):
            res = await main.get_paper(req)

        self.assertIsNone(res.result)
        self.assertEqual(res.error, "Paper not found.")

    async def test_get_author_papers_sorting_and_null_safety(self):
        # Mixed string and integer years/citations, null values, and author name fallback
        payload = {
            "name": "Geoffrey Hinton",
            "papers": [
                {"title": "Paper Old", "year": "1986", "citationCount": "5000", "url": ""},
                {"title": "Paper New", "year": 2021, "citationCount": 1200, "url": "https://example.com/new"},
                {"title": "Paper Missing Data", "year": None, "citationCount": None, "url": ""},
                None,  # non-dict entry
            ],
        }
        req = models.GetAuthorPapersRequest(author_id="1741101", max_results=3)
        with patch.object(main, "api_get", new=AsyncMock(return_value=payload)):
            res = await main.get_author_papers(req)

        self.assertIsNone(res.error)
        self.assertIn("Recent papers by Geoffrey Hinton:", res.result)
        self.assertIn("1. Paper New", res.result)
        self.assertIn("2. Paper Old", res.result)
        self.assertIn("3. Paper Missing Data", res.result)
        self.assertTrue(res.result.find("1. Paper New") < res.result.find("2. Paper Old") < res.result.find("3. Paper Missing Data"))

    async def test_get_author_papers_null_papers(self):
        req = models.GetAuthorPapersRequest(author_id="12345")
        with patch.object(main, "api_get", new=AsyncMock(return_value={"name": "Unknown", "papers": None})):
            res = await main.get_author_papers(req)

        self.assertIsNone(res.error)
        self.assertEqual(res.result, "No papers found for author Unknown.")


if __name__ == "__main__":
    unittest.main()
