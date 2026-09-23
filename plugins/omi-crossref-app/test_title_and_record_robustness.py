"""Hermetic unit tests for Crossref app title extraction and record robustness.

Tests:
1. _extract_title preserves complete string titles without single-letter truncation
2. _extract_title safely handles lists, empty items, and non-string types
3. extract_year defends against malformed non-dict date metadata without AttributeError
4. clamp_max_results guards boolean and non-integer values safely
5. Endpoint formatting verifies full title preservation and malformed record safety
"""

import asyncio
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import AsyncMock, patch

PLUGIN_DIR = Path(__file__).resolve().parent
MAIN_FILE = PLUGIN_DIR / "main.py"


def _load_main_module():
    sys.path.insert(0, str(PLUGIN_DIR))

    # Stub minimal dependencies if not installed
    for mod_name in ["fastapi", "httpx", "models"]:
        if mod_name not in sys.modules:
            try:
                __import__(mod_name)
            except Exception:
                stub = types.ModuleType(mod_name)
                if mod_name == "fastapi":
                    class DummyFastAPI:
                        def __init__(self, *args, **kwargs):
                            pass
                        def get(self, *args, **kwargs):
                            return lambda f: f
                        post = get
                    stub.FastAPI = DummyFastAPI
                elif mod_name == "httpx":
                    class DummyAsyncClient:
                        def __init__(self, *args, **kwargs):
                            pass
                        async def __aenter__(self):
                            return self
                        async def __aexit__(self, *args):
                            pass
                        async def get(self, *args, **kwargs):
                            raise NotImplementedError
                    stub.AsyncClient = DummyAsyncClient
                elif mod_name == "models":
                    class ChatToolResponse:
                        def __init__(self, result=None, error=None, **kwargs):
                            self.result = result
                            self.error = error
                    class SearchWorksInput:
                        def __init__(self, query="", max_results=5):
                            self.query = query
                            self.max_results = max_results
                    class GetWorkInput:
                        def __init__(self, doi=""):
                            self.doi = doi
                    class AuthorWorksInput:
                        def __init__(self, author="", max_results=5):
                            self.author = author
                            self.max_results = max_results
                    stub.ChatToolResponse = ChatToolResponse
                    stub.SearchWorksInput = SearchWorksInput
                    stub.GetWorkInput = GetWorkInput
                    stub.AuthorWorksInput = AuthorWorksInput
                sys.modules[mod_name] = stub

    spec = importlib.util.spec_from_file_location("crossref_main", str(MAIN_FILE))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


main = _load_main_module()


class CrossrefTitleAndRecordRobustnessTests(unittest.TestCase):
    def test_extract_title_string_preservation(self):
        # Must preserve full title rather than truncating to 'Q' via [0]
        self.assertEqual(
            main._extract_title("Quantum Field Theory and Applications"),
            "Quantum Field Theory and Applications",
        )
        self.assertEqual(main._extract_title("A"), "A")

    def test_extract_title_list_and_fallbacks(self):
        self.assertEqual(main._extract_title(["Primary Title", "Subtitle"]), "Primary Title")
        self.assertEqual(main._extract_title(["", "Fallback Title"]), "Fallback Title")
        self.assertEqual(main._extract_title([]), "Untitled")
        self.assertEqual(main._extract_title(None), "Untitled")
        self.assertEqual(main._extract_title(12345), "Untitled")
        self.assertEqual(main._extract_title({"title": "Dict"}), "Untitled")

    def test_extract_title_html_cleaning(self):
        self.assertEqual(
            main._extract_title("<b>Superconductivity</b> in <i>Graphene</i>"),
            "Superconductivity in Graphene",
        )

    def test_extract_year_normal_and_malformed(self):
        # Normal record
        record_normal = {"issued": {"date-parts": [[2025, 3, 1]]}}
        self.assertEqual(main.extract_year(record_normal), "2025")

        # Malformed non-dict fields must not raise AttributeError
        record_malformed_string = {"published-print": "2024-05", "issued": {"date-parts": [[2024]]}}
        self.assertEqual(main.extract_year(record_malformed_string), "2024")

        record_malformed_list = {"published-print": [2024]}
        self.assertEqual(main.extract_year(record_malformed_list), "")

        # Non-dict inputs
        self.assertEqual(main.extract_year("not-a-dict"), "")
        self.assertEqual(main.extract_year(None), "")
        self.assertEqual(main.extract_year({}), "")

    def test_clamp_max_results_guards(self):
        self.assertEqual(main.clamp_max_results(False), 5)
        self.assertEqual(main.clamp_max_results(True), 5)
        self.assertEqual(main.clamp_max_results(None), 5)
        self.assertEqual(main.clamp_max_results("invalid"), 5)
        self.assertEqual(main.clamp_max_results(0), 1)
        self.assertEqual(main.clamp_max_results(7), 7)
        self.assertEqual(main.clamp_max_results(25), 10)


class CrossrefEndpointTitlePreservationTests(unittest.TestCase):
    def test_search_crossref_works_string_title_not_truncated(self):
        input_data = main.SearchWorksInput(query="Quantum Computing", max_results=5)
        mock_payload = {
            "message": {
                "items": [
                    {
                        "title": "Quantum Computing Architecture",  # String title
                        "DOI": "10.1038/nphys1170",
                        "issued": {"date-parts": [[2026]]},
                    }
                ]
            }
        }
        with patch.object(main, "crossref_get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_payload
            resp = asyncio.run(main.search_crossref_works(input_data))
            self.assertIsNone(resp.error)
            self.assertIn("1. Quantum Computing Architecture (2026)", resp.result)
            # Ensure it is NOT truncated to '1. Q (2026)'
            self.assertNotIn("1. Q (2026)", resp.result)

    def test_get_crossref_work_string_title_preservation(self):
        input_data = main.GetWorkInput(doi="10.1038/nphys1170")
        mock_payload = {
            "message": {
                "title": "Quantum Supremacy Experiment",  # String title
                "publisher": "Nature Publishing Group",
                "DOI": "10.1038/nphys1170",
                "URL": "https://doi.org/10.1038/nphys1170",
                "abstract": "Abstract text here.",
                "issued": {"date-parts": [[2026]]},
            }
        }
        with patch.object(main, "crossref_get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_payload
            resp = asyncio.run(main.get_crossref_work(input_data))
            self.assertIsNone(resp.error)
            self.assertIn("Title: Quantum Supremacy Experiment", resp.result)
            self.assertNotEqual(resp.result.splitlines()[0], "Title: Q")


if __name__ == "__main__":
    unittest.main()
