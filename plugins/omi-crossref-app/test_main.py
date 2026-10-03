"""Hermetic unit tests for Crossref Omi integration.

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

    pydantic = types.ModuleType("pydantic")
    pydantic.BaseModel = DummyBaseModel

    httpx = types.ModuleType("httpx")
    httpx.HTTPError = HTTPError
    httpx.HTTPStatusError = HTTPStatusError
    httpx.AsyncClient = object

    models = types.ModuleType("models")

    class ChatToolResponse(DummyBaseModel):
        result = None
        error = None

    class SearchWorksInput(DummyBaseModel):
        query = ""
        max_results = 5

    class GetWorkInput(DummyBaseModel):
        doi = ""

    class AuthorWorksInput(DummyBaseModel):
        author = ""
        max_results = 5

    models.ChatToolResponse = ChatToolResponse
    models.SearchWorksInput = SearchWorksInput
    models.GetWorkInput = GetWorkInput
    models.AuthorWorksInput = AuthorWorksInput

    spec = importlib.util.spec_from_file_location("crossref_app_hermetic", Path(__file__).with_name("main.py"))
    module = importlib.util.module_from_spec(spec)
    with patch.dict(
        sys.modules,
        {
            "fastapi": fastapi,
            "pydantic": pydantic,
            "httpx": httpx,
            "models": models,
        },
    ):
        spec.loader.exec_module(module)
    return module


main = load_app()


class RouteWiringTests(unittest.TestCase):
    def test_routes_registered_with_correct_methods_and_paths(self):
        registered = {(r["method"], r["path"]): r for r in main.app.routes}
        expected_endpoints = {
            ("GET", "/health"),
            ("GET", "/tools"),
            ("GET", "/.well-known/omi-tools.json"),
            ("POST", "/tools/search_crossref_works"),
            ("POST", "/tools/get_crossref_work"),
            ("POST", "/tools/get_crossref_works_by_author"),
        }
        for endpoint in expected_endpoints:
            self.assertIn(endpoint, registered)

        self.assertIs(registered[("POST", "/tools/search_crossref_works")]["response_model"], main.ChatToolResponse)
        self.assertIs(registered[("POST", "/tools/get_crossref_work")]["response_model"], main.ChatToolResponse)
        self.assertIs(registered[("POST", "/tools/get_crossref_works_by_author")]["response_model"], main.ChatToolResponse)

    def test_tools_manifest_matches_registered_routes(self):
        manifest = asyncio.run(main.get_omi_tools_manifest())
        tools = manifest["tools"]
        self.assertEqual(len(tools), 3)
        tool_endpoints = {t["endpoint"]: t["method"] for t in tools}
        self.assertEqual(
            tool_endpoints,
            {
                "/tools/search_crossref_works": "POST",
                "/tools/get_crossref_work": "POST",
                "/tools/get_crossref_works_by_author": "POST",
            },
        )


class CleanTextTests(unittest.TestCase):
    def test_clean_strips_jats_paragraph_tags(self):
        raw = "<jats:p>Sleep quality improved <jats:italic>slightly</jats:italic>.</jats:p>"
        self.assertEqual(main.clean(raw), "Sleep quality improved slightly.")

    def test_clean_unescapes_entities_and_strips_generic_tags(self):
        self.assertEqual(main.clean("A &amp; B <b>bold</b>"), "A & B bold")

    def test_clean_preserves_inequality_operators(self):
        self.assertEqual(main.clean("If a<b, then c>d."), "If a<b, then c>d.")

    def test_clean_strips_closing_tags_after_word_chars(self):
        self.assertEqual(main.clean("text</p> tail"), "text tail")

    def test_clean_none_and_empty(self):
        self.assertEqual(main.clean(None), "")
        self.assertEqual(main.clean(""), "")


class ExtractionHelperTests(unittest.TestCase):
    def test_extract_year_published_print(self):
        item = {"published-print": {"date-parts": [[2023, 6, 15]]}}
        self.assertEqual(main.extract_year(item), "2023")

    def test_extract_year_published_online_fallback(self):
        item = {"published-online": {"date-parts": [[2021, 1, 10]]}}
        self.assertEqual(main.extract_year(item), "2021")

    def test_extract_year_issued_fallback(self):
        item = {"issued": {"date-parts": [[2019]]}}
        self.assertEqual(main.extract_year(item), "2019")

    def test_extract_year_empty_and_malformed_structures(self):
        self.assertEqual(main.extract_year({}), "")
        self.assertEqual(main.extract_year({"published-print": None}), "")
        self.assertEqual(main.extract_year({"published-print": {"date-parts": None}}), "")
        self.assertEqual(main.extract_year({"published-print": {"date-parts": []}}), "")
        self.assertEqual(main.extract_year({"published-print": {"date-parts": [[]]}}), "")
        self.assertEqual(main.extract_year({"published-print": {"date-parts": [[None]]}}), "")
        self.assertEqual(main.extract_year("invalid non-dict"), "")

    def test_extract_title_valid_list(self):
        item = {"title": ["Deep Residual Learning"]}
        self.assertEqual(main._extract_title(item), "Deep Residual Learning")

    def test_extract_title_valid_string(self):
        item = {"title": "Attention Is All You Need"}
        self.assertEqual(main._extract_title(item), "Attention Is All You Need")

    def test_extract_title_empty_and_null(self):
        self.assertEqual(main._extract_title({}), "Untitled")
        self.assertEqual(main._extract_title({"title": None}), "Untitled")
        self.assertEqual(main._extract_title({"title": []}), "Untitled")
        self.assertEqual(main._extract_title({"title": [None]}), "Untitled")
        self.assertEqual(main._extract_title("non-dict"), "Untitled")


class CrossrefToolTests(unittest.IsolatedAsyncioTestCase):
    async def test_search_works_success(self):
        mock_data = {
            "message": {
                "items": [
                    {
                        "title": ["Neural Networks in Practice"],
                        "DOI": "10.1000/182",
                        "issued": {"date-parts": [[2024]]},
                    }
                ]
            }
        }
        with patch.object(main, "crossref_get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_data
            input_data = main.SearchWorksInput(query="neural networks", max_results=5)
            resp = await main.search_crossref_works(input_data)
            self.assertIsNone(resp.error)
            self.assertIn("Neural Networks in Practice (2024)", resp.result)
            self.assertIn("DOI: 10.1000/182", resp.result)

    async def test_search_works_empty_items(self):
        with patch.object(main, "crossref_get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = {"message": {"items": []}}
            input_data = main.SearchWorksInput(query="nonexistentqueryxyz", max_results=5)
            resp = await main.search_crossref_works(input_data)
            self.assertIsNone(resp.error)
            self.assertEqual(resp.result, "No Crossref results found for 'nonexistentqueryxyz'.")

    async def test_search_works_null_message_graceful(self):
        with patch.object(main, "crossref_get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = {"message": None}
            input_data = main.SearchWorksInput(query="quantum physics", max_results=5)
            resp = await main.search_crossref_works(input_data)
            self.assertIsNone(resp.error)
            self.assertEqual(resp.result, "No Crossref results found for 'quantum physics'.")

    async def test_search_works_non_dict_payload_graceful(self):
        with patch.object(main, "crossref_get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = "<html>504 Gateway Timeout</html>"
            input_data = main.SearchWorksInput(query="astrophysics", max_results=5)
            resp = await main.search_crossref_works(input_data)
            self.assertIsNone(resp.error)
            self.assertEqual(resp.result, "No Crossref results found for 'astrophysics'.")

    async def test_search_works_short_query_error(self):
        input_data = main.SearchWorksInput(query="a", max_results=5)
        resp = await main.search_crossref_works(input_data)
        self.assertEqual(resp.error, "Query must be at least 2 characters.")

    async def test_search_works_exception_handled(self):
        with patch.object(main, "crossref_get", new_callable=AsyncMock) as mock_get:
            mock_get.side_effect = Exception("Network unreachable")
            input_data = main.SearchWorksInput(query="climate change", max_results=5)
            resp = await main.search_crossref_works(input_data)
            self.assertIn("Crossref request failed: Network unreachable", resp.error)

    async def test_get_work_success(self):
        mock_data = {
            "message": {
                "title": ["Superconductivity at Room Temperature"],
                "DOI": "10.1038/nphys1170",
                "publisher": "Nature Publishing Group",
                "URL": "https://doi.org/10.1038/nphys1170",
                "issued": {"date-parts": [[2022, 10, 1]]},
                "abstract": "<jats:p>We report observation of resistance drops.</jats:p>",
            }
        }
        with patch.object(main, "crossref_get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_data
            input_data = main.GetWorkInput(doi="10.1038/nphys1170")
            resp = await main.get_work(input_data) if hasattr(main, "get_work") else await main.get_crossref_work(input_data)
            self.assertIsNone(resp.error)
            self.assertIn("Title: Superconductivity at Room Temperature", resp.result)
            self.assertIn("DOI: 10.1038/nphys1170", resp.result)
            self.assertIn("Year: 2022", resp.result)
            self.assertIn("Publisher: Nature Publishing Group", resp.result)
            self.assertIn("Abstract: We report observation of resistance drops.", resp.result)

    async def test_get_work_invalid_doi_format(self):
        input_data = main.GetWorkInput(doi="invalid-doi-without-slash")
        resp = await main.get_crossref_work(input_data)
        self.assertIn("Invalid DOI format", resp.error)

    async def test_get_work_whitespace_doi(self):
        input_data = main.GetWorkInput(doi="10.1000/invalid doi with spaces")
        resp = await main.get_crossref_work(input_data)
        self.assertIn("Invalid DOI format", resp.error)

    async def test_get_work_null_message_graceful(self):
        with patch.object(main, "crossref_get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = {"message": None}
            input_data = main.GetWorkInput(doi="10.1000/182")
            resp = await main.get_crossref_work(input_data)
            self.assertIsNone(resp.error)
            self.assertEqual(resp.result, "No Crossref details found for DOI 10.1000/182.")

    async def test_get_work_empty_message_graceful(self):
        with patch.object(main, "crossref_get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = {"message": {}}
            input_data = main.GetWorkInput(doi="10.1000/182")
            resp = await main.get_crossref_work(input_data)
            self.assertIsNone(resp.error)
            self.assertEqual(resp.result, "No Crossref details found for DOI 10.1000/182.")

    async def test_get_work_non_dict_payload_graceful(self):
        with patch.object(main, "crossref_get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = "<html>404 Not Found</html>"
            input_data = main.GetWorkInput(doi="10.1000/182")
            resp = await main.get_crossref_work(input_data)
            self.assertIsNone(resp.error)
            self.assertEqual(resp.result, "No Crossref details found for DOI 10.1000/182.")

    async def test_get_works_by_author_success(self):
        mock_data = {
            "message": {
                "items": [
                    {
                        "title": ["Electrodynamics of Moving Bodies"],
                        "DOI": "10.1002/andp.19053221004",
                        "issued": {"date-parts": [[1905]]},
                    }
                ]
            }
        }
        with patch.object(main, "crossref_get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_data
            input_data = main.AuthorWorksInput(author="Albert Einstein", max_results=3)
            resp = await main.get_crossref_works_by_author(input_data)
            self.assertIsNone(resp.error)
            self.assertIn("Recent works for 'Albert Einstein':", resp.result)
            self.assertIn("Electrodynamics of Moving Bodies (1905)", resp.result)

    async def test_get_works_by_author_empty_results(self):
        with patch.object(main, "crossref_get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = {"message": {"items": []}}
            input_data = main.AuthorWorksInput(author="Nobody Known", max_results=5)
            resp = await main.get_crossref_works_by_author(input_data)
            self.assertIsNone(resp.error)
            self.assertEqual(resp.result, "No recent works found for author 'Nobody Known'.")

    async def test_get_works_by_author_null_message_graceful(self):
        with patch.object(main, "crossref_get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = {"message": None}
            input_data = main.AuthorWorksInput(author="Richard Feynman", max_results=5)
            resp = await main.get_crossref_works_by_author(input_data)
            self.assertIsNone(resp.error)
            self.assertEqual(resp.result, "No recent works found for author 'Richard Feynman'.")

    async def test_get_works_by_author_non_dict_payload_graceful(self):
        with patch.object(main, "crossref_get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = "<html>500 Server Error</html>"
            input_data = main.AuthorWorksInput(author="Marie Curie", max_results=5)
            resp = await main.get_crossref_works_by_author(input_data)
            self.assertIsNone(resp.error)
            self.assertEqual(resp.result, "No recent works found for author 'Marie Curie'.")

    async def test_get_works_by_author_short_name_error(self):
        input_data = main.AuthorWorksInput(author="x", max_results=5)
        resp = await main.get_crossref_works_by_author(input_data)
        self.assertEqual(resp.error, "Author must be at least 2 characters.")


if __name__ == "__main__":
    unittest.main()
