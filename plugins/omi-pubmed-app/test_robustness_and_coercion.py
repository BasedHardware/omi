"""Hermetic unit tests for PubMed app input robustness and coercion.

Tests:
1. _clamp_max_results guards boolean inputs (preventing False -> 0 -> 1 clamp)
2. _normalize_pmid accepts numeric integer PMIDs and guards booleans
3. Tool endpoints guard non-dict JSON bodies and boolean inputs defensively
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
    for mod_name in ["fastapi", "fastapi.responses", "httpx", "models"]:
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
                    stub.Request = object
                elif mod_name == "fastapi.responses":
                    stub.HTMLResponse = object
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
                        def model_dump(self):
                            return {"result": self.result, "error": self.error}
                    stub.ChatToolResponse = ChatToolResponse
                sys.modules[mod_name] = stub

    spec = importlib.util.spec_from_file_location("main", str(MAIN_FILE))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


main = _load_main_module()


class DummyRequest:
    def __init__(self, json_data):
        self._json_data = json_data

    async def json(self):
        if isinstance(self._json_data, Exception):
            raise self._json_data
        return self._json_data


class PubMedCoercionAndRobustnessTests(unittest.TestCase):
    def test_clamp_max_results_booleans(self):
        self.assertEqual(main._clamp_max_results(False, default=5), 5)
        self.assertEqual(main._clamp_max_results(True, default=5), 5)
        self.assertEqual(main._clamp_max_results(None, default=5), 5)
        self.assertEqual(main._clamp_max_results("invalid", default=5), 5)

    def test_clamp_max_results_integers_and_strings(self):
        self.assertEqual(main._clamp_max_results(0), 1)
        self.assertEqual(main._clamp_max_results(3), 3)
        self.assertEqual(main._clamp_max_results(10), 10)
        self.assertEqual(main._clamp_max_results(20), 10)
        self.assertEqual(main._clamp_max_results("7"), 7)

    def test_normalize_pmid_integer_support(self):
        self.assertEqual(main._normalize_pmid(34567890), "34567890")
        self.assertEqual(main._normalize_pmid(1), "1")
        self.assertEqual(main._normalize_pmid(123456789012), "123456789012")

    def test_normalize_pmid_invalid_types_and_bounds(self):
        self.assertIsNone(main._normalize_pmid(True))
        self.assertIsNone(main._normalize_pmid(False))
        self.assertIsNone(main._normalize_pmid(None))
        self.assertIsNone(main._normalize_pmid([]))
        self.assertIsNone(main._normalize_pmid({}))
        self.assertIsNone(main._normalize_pmid(-123))
        self.assertIsNone(main._normalize_pmid(1234567890123456))  # > 12 digits


class PubMedEndpointRobustnessTests(unittest.TestCase):
    def test_search_pubmed_non_dict_body(self):
        req = DummyRequest(["not", "a", "dict"])
        resp = asyncio.run(main.search_pubmed(req))
        self.assertEqual(resp.error, "Request body must be a JSON object")

    def test_search_pubmed_invalid_json(self):
        req = DummyRequest(ValueError("malformed json"))
        resp = asyncio.run(main.search_pubmed(req))
        self.assertEqual(resp.error, "Request body must be a valid JSON object")

    def test_search_pubmed_boolean_query(self):
        req = DummyRequest({"query": False})
        resp = asyncio.run(main.search_pubmed(req))
        self.assertEqual(resp.error, "query is required")

    def test_get_pubmed_article_non_dict_body(self):
        req = DummyRequest("string body")
        resp = asyncio.run(main.get_pubmed_article(req))
        self.assertEqual(resp.error, "Request body must be a JSON object")

    def test_get_pubmed_article_boolean_pmid(self):
        req = DummyRequest({"pmid": True})
        resp = asyncio.run(main.get_pubmed_article(req))
        self.assertEqual(resp.error, "pmid is required")

    def test_get_related_pubmed_non_dict_body(self):
        req = DummyRequest(12345)
        resp = asyncio.run(main.get_related_pubmed(req))
        self.assertEqual(resp.error, "Request body must be a JSON object")

    def test_get_related_pubmed_boolean_pmid(self):
        req = DummyRequest({"pmid": False})
        resp = asyncio.run(main.get_related_pubmed(req))
        self.assertEqual(resp.error, "pmid is required")

    def test_get_pubmed_article_integer_pmid_lookup(self):
        # Verify that integer PMID 34567890 passes validation and normalization
        req = DummyRequest({"pmid": 34567890})
        with patch.object(main, "_fetch_summaries", new_callable=AsyncMock) as mock_summaries:
            mock_summaries.return_value = {
                "34567890": {
                    "title": "Genomic Advances",
                    "pubdate": "2026",
                    "source": "Cell",
                    "elocationid": "",
                    "authors": [{"name": "Jane Doe"}],
                    "abstract": "Breakthrough results.",
                }
            }
            with patch.object(main, "_fetch_abstract", new_callable=AsyncMock) as mock_abs:
                mock_abs.return_value = "Breakthrough results."
                resp = asyncio.run(main.get_pubmed_article(req))
                self.assertIsNone(resp.error)
                self.assertIn("PMID 34567890", resp.result)
                self.assertIn("Title: Genomic Advances", resp.result)


if __name__ == "__main__":
    unittest.main()
