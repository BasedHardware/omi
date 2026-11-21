from pathlib import Path
import sys
import types
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

# Provide lightweight stubs for third-party runtime dependencies so test_main.py
# runs hermetically on any clean standard library Python environment without
# requiring FastAPI, httpx, or Pydantic to be installed.
if "httpx" not in sys.modules:
    try:
        import httpx  # type: ignore
    except ImportError:
        httpx = types.ModuleType("httpx")

        class HTTPError(Exception):
            pass

        class HTTPStatusError(HTTPError):
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

        httpx.HTTPError = HTTPError
        httpx.HTTPStatusError = HTTPStatusError
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
            pass

        responses.HTMLResponse = HTMLResponse
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


class OpenFDAHelperTests(unittest.TestCase):
    def test_first_unwraps_lists_safely(self):
        self.assertEqual(main._first(["TYLENOL"]), "TYLENOL")
        self.assertEqual(main._first([]), "")
        self.assertEqual(main._first(None), "")
        self.assertEqual(main._first("plain"), "plain")
        self.assertEqual(main._first({"a": 1}), "")

    def test_truncate(self):
        self.assertEqual(main._truncate("short"), "short")
        self.assertTrue(main._truncate("x" * 300, 10).endswith("…"))

    def test_format_enforcement(self):
        item = {
            "product_description": ["Baby Powder 4oz"],
            "recalling_firm": ["ACME Corp"],
            "classification": ["Class II"],
            "reason_for_recall": ["Possible contamination"],
            "recall_initiation_date": ["20260901"],
        }
        out = main._format_enforcement(item)
        self.assertIn("Baby Powder 4oz", out)
        self.assertIn("ACME Corp", out)
        self.assertIn("Class II", out)
        self.assertIn("2026-09-01", out)
        self.assertIn("Possible contamination", out)

        self.assertEqual(main._format_enforcement(None), "- Malformed record")
        self.assertIn("Unknown product", main._format_enforcement({}))

    def test_clean_query(self):
        self.assertEqual(main._clean_query("  baby   aspirin "), "baby aspirin")


class OpenFDAEndpointTests(unittest.IsolatedAsyncioTestCase):
    async def test_search_drug_recalls_formats_results(self):
        payload = {
            "results": [
                {
                    "product_description": ["Metformin ER 500mg"],
                    "recalling_firm": ["PharmaCo"],
                    "classification": ["Class II"],
                    "reason_for_recall": ["NDMA impurity above limit"],
                    "recall_initiation_date": ["20260115"],
                }
            ]
        }
        req = main.RecallRequest(query="metformin")

        class FakeClient:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                pass

            async def get(self, url, params=None):
                resp = MagicMock()
                resp.status_code = 200
                resp.raise_for_status = lambda: None
                resp.json = lambda: payload
                return resp

        with patch.object(main.httpx, "AsyncClient", return_value=FakeClient()):
            res = await main.search_drug_recalls(req)

        self.assertIsNone(res.error)
        self.assertIn("FDA drug recalls for 'metformin':", res.result)
        self.assertIn("Metformin ER 500mg", res.result)
        self.assertIn("NDMA impurity", res.result)

    async def test_search_food_recalls_empty(self):
        req = main.RecallRequest(query="zzz-no-such-food")
        with patch.object(main, "_search_enforcement", new=AsyncMock(return_value=None)):
            res = await main.search_food_recalls(req)
        self.assertIsNone(res.error)
        self.assertIn("No FDA food recalls", res.result)

    async def test_get_drug_info(self):
        payload = {
            "results": [
                {
                    "openfda": {
                        "brand_name": ["ADVIL"],
                        "generic_name": ["IBUPROFEN"],
                        "manufacturer_name": ["Pfizer"],
                    },
                    "purpose": ["Pain reliever"],
                    "warnings": ["Do not exceed dose"],
                    "drug_interactions": ["May interact with aspirin"],
                }
            ]
        }
        req = main.DrugInfoRequest(drug="advil")

        class FakeClient:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                pass

            async def get(self, url, params=None):
                resp = MagicMock()
                resp.status_code = 200
                resp.raise_for_status = lambda: None
                resp.json = lambda: payload
                return resp

        with patch.object(main.httpx, "AsyncClient", return_value=FakeClient()):
            res = await main.get_drug_info(req)

        self.assertIsNone(res.error)
        self.assertIn("FDA label: ADVIL", res.result)
        self.assertIn("Generic: IBUPROFEN", res.result)
        self.assertIn("Warnings: Do not exceed dose", res.result)
        self.assertIn("Interactions: May interact with aspirin", res.result)


if __name__ == "__main__":
    unittest.main()
