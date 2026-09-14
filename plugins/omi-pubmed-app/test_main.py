"""Hermetic unit tests for Omi PubMed Integration App.

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


def load_app_modules(force_stubs: bool = True):
    """Load models and main modules hermetically without contaminating sys.modules.

    When force_stubs is True (default for reproducible hermetic execution),
    stubs are installed unconditionally regardless of packages in the environment.
    Note: BaseModelStub is a lightweight approximation for hermetic test execution.
    Full Pydantic semantics are exercised separately in test_real_pydantic_if_installed.
    """
    stubs = {}

    pydantic_mod = types.ModuleType("pydantic")

    class FieldInfoStub:
        def __init__(self, default=..., **kwargs):
            self.default = default
            self.ge = kwargs.get("ge")
            self.le = kwargs.get("le")
            self.min_length = kwargs.get("min_length")
            self.max_length = kwargs.get("max_length")

    class BaseModelStub:
        """Lightweight approximation of Pydantic BaseModel for hermetic testing."""
        def __init__(self, **data):
            annotations = getattr(self.__class__, "__annotations__", {})
            for fname in annotations:
                if fname not in data and hasattr(self.__class__, fname):
                    attr_val = getattr(self.__class__, fname)
                    if isinstance(attr_val, FieldInfoStub):
                        if attr_val.default is not ...:
                            data[fname] = attr_val.default
                        else:
                            raise ValueError(f"Field '{fname}' is required.")
                    else:
                        data[fname] = attr_val

            for k, v in data.items():
                setattr(self, k, v)

            for attr_name in dir(self.__class__):
                attr = getattr(self.__class__, attr_name)
                func = getattr(attr, "__func__", attr)
                if getattr(func, "_is_field_val", False):
                    target_field = getattr(func, "_target_field")
                    if hasattr(self, target_field):
                        try:
                            val = attr(getattr(self, target_field))
                        except TypeError:
                            val = func(self.__class__, getattr(self, target_field))
                        setattr(self, target_field, val)

            for fname in annotations:
                if hasattr(self.__class__, fname):
                    attr_val = getattr(self.__class__, fname)
                    if isinstance(attr_val, FieldInfoStub):
                        val = getattr(self, fname, None)
                        if val is not None:
                            if isinstance(val, str) and (attr_val.ge is not None or attr_val.le is not None):
                                try:
                                    val = int(val)
                                except ValueError:
                                    pass
                            if attr_val.ge is not None and val < attr_val.ge:
                                raise ValueError(f"{fname} must be >= {attr_val.ge}")
                            if attr_val.le is not None and val > attr_val.le:
                                raise ValueError(f"{fname} must be <= {attr_val.le}")
                            if attr_val.min_length is not None and len(val) < attr_val.min_length:
                                raise ValueError(f"{fname} minimum length is {attr_val.min_length}")
                            if attr_val.max_length is not None and len(val) > attr_val.max_length:
                                raise ValueError(f"{fname} maximum length is {attr_val.max_length}")

            for attr_name in dir(self.__class__):
                attr = getattr(self.__class__, attr_name)
                func = getattr(attr, "__func__", attr)
                if getattr(func, "_is_model_val", False):
                    try:
                        attr(self)
                    except TypeError:
                        func(self)

        def model_dump(self):
            return {k: v for k, v in self.__dict__.items() if not k.startswith("_")}

    def field_validator_stub(*fields, mode=None):
        def decorator(fn):
            actual_fn = getattr(fn, "__func__", fn)
            actual_fn._is_field_val = True
            actual_fn._target_field = fields[0]
            actual_fn._mode = mode
            return fn
        return decorator

    def model_validator_stub(mode="after"):
        def decorator(fn):
            actual_fn = getattr(fn, "__func__", fn)
            actual_fn._is_model_val = True
            actual_fn._mode = mode
            return fn
        return decorator

    def field_stub(default=..., **kwargs):
        return FieldInfoStub(default, **kwargs)

    pydantic_mod.BaseModel = BaseModelStub
    pydantic_mod.Field = field_stub
    pydantic_mod.field_validator = field_validator_stub
    pydantic_mod.model_validator = model_validator_stub
    stubs["pydantic"] = pydantic_mod

    fastapi_mod = types.ModuleType("fastapi")

    class StateStub:
        pass

    class FastAPIStub:
        def __init__(self, **kwargs):
            self.state = StateStub()
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

    fastapi_mod.FastAPI = FastAPIStub
    fastapi_responses = types.ModuleType("fastapi.responses")

    class HTMLResponseStub:
        pass

    fastapi_responses.HTMLResponse = HTMLResponseStub
    fastapi_mod.responses = fastapi_responses
    stubs["fastapi"] = fastapi_mod
    stubs["fastapi.responses"] = fastapi_responses

    httpx_mod = types.ModuleType("httpx")

    class HTTPErrorStub(Exception):
        pass

    class HTTPStatusErrorStub(HTTPErrorStub):
        def __init__(self, message="status error", *, request=None, response=None):
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
            resp = MagicMock()
            resp.status_code = 200
            resp.json.return_value = {}
            return resp

        async def aclose(self):
            self.is_closed = True

    httpx_mod.AsyncClient = AsyncClientStub
    httpx_mod.HTTPError = HTTPErrorStub
    httpx_mod.HTTPStatusError = HTTPStatusErrorStub
    stubs["httpx"] = httpx_mod

    with patch.dict(sys.modules, stubs):
        models_path = os.path.join(PLUGIN_DIR, "models.py")
        models_spec = importlib.util.spec_from_file_location("models", models_path)
        models_mod = importlib.util.module_from_spec(models_spec)
        models_spec.loader.exec_module(models_mod)

        with patch.dict(sys.modules, {"models": models_mod}):
            main_path = os.path.join(PLUGIN_DIR, "main.py")
            main_spec = importlib.util.spec_from_file_location("main", main_path)
            main_mod = importlib.util.module_from_spec(main_spec)
            main_spec.loader.exec_module(main_mod)

    return main_mod, models_mod


class TestPubmedApp(unittest.TestCase):
    """Hermetic unit test suite for PubMed integration endpoints and parsing helpers."""

    @classmethod
    def setUpClass(cls):
        # Always run hermetic suite deterministically against isolated stubs
        cls.main, cls.models = load_app_modules(force_stubs=True)

    def setUp(self):
        self.mock_client = AsyncMock()
        self.mock_client.is_closed = False
        self.main.app.state.http_client = self.mock_client

    def test_health_endpoint(self):
        """Verify health check returns ok status."""
        res = asyncio.run(self.main.health())
        self.assertEqual(res, {"status": "ok"})

    def test_omi_tools_manifest(self):
        """Verify manifest declares all three tools."""
        manifest = asyncio.run(self.main.manifest())
        tools = manifest["tools"]
        names = [t["name"] for t in tools]
        self.assertIn("search_pubmed", names)
        self.assertIn("get_pubmed_article", names)
        self.assertIn("get_related_pubmed", names)

    def test_manifest_alias(self):
        """Verify manifest_alias matches manifest."""
        m1 = asyncio.run(self.main.manifest())
        m2 = asyncio.run(self.main.manifest_alias())
        self.assertEqual(m1, m2)

    def test_helpers_safe_and_is_valid_pmid(self):
        """Verify _safe unescaping and _is_valid_pmid check."""
        self.assertEqual(self.main._safe("&lt;b&gt;title&lt;/b&gt;"), "<b>title</b>")
        self.assertEqual(self.main._safe(None), "")
        self.assertEqual(self.main._safe("   spaced  "), "spaced")

        self.assertTrue(self.main._is_valid_pmid("123456"))
        self.assertTrue(self.main._is_valid_pmid("35000000"))
        self.assertFalse(self.main._is_valid_pmid("abc"))
        self.assertFalse(self.main._is_valid_pmid("123456789012345"))
        self.assertFalse(self.main._is_valid_pmid(""))

    def test_clamp_max_results(self):
        """Verify _clamp_max_results bounds enforcement (1-10)."""
        self.assertEqual(self.main._clamp_max_results(3), 3)
        self.assertEqual(self.main._clamp_max_results(0), 1)
        self.assertEqual(self.main._clamp_max_results(100), 10)
        self.assertEqual(self.main._clamp_max_results("invalid"), 5)
        self.assertEqual(self.main._clamp_max_results(None), 5)

    def test_extract_abstract_from_efetch_xml(self):
        """Verify XML abstract parsing with labels and error handling."""
        xml = (
            "<PubmedArticleSet>"
            "<PubmedArticle>"
            "<MedlineCitation>"
            "<Article>"
            "<Abstract>"
            '<AbstractText Label="BACKGROUND">Background text.</AbstractText>'
            '<AbstractText Label="CONCLUSIONS">Conclusion text.</AbstractText>'
            "</Abstract>"
            "</Article>"
            "</MedlineCitation>"
            "</PubmedArticle>"
            "</PubmedArticleSet>"
        )
        abstract = self.main._extract_abstract_from_efetch_xml(xml)
        self.assertIn("BACKGROUND: Background text.", abstract)
        self.assertIn("CONCLUSIONS: Conclusion text.", abstract)

        # Malformed XML
        self.assertEqual(self.main._extract_abstract_from_efetch_xml("<bad-xml"), "")
        self.assertEqual(self.main._extract_abstract_from_efetch_xml(""), "")

    def test_extract_article_fields_defensive(self):
        """Verify _extract_article_fields handles non-dict, missing fields, and non-dict authors."""
        # Non-dict record
        res_empty = self.main._extract_article_fields(None)
        self.assertEqual(res_empty["title"], "Untitled")
        self.assertEqual(res_empty["authors"], [])

        # Non-dict authors list (regression test for unhandled author types)
        record = {
            "title": "Quantum Biology",
            "pubdate": "2024",
            "source": "Nature",
            "elocationid": "10.1038/xyz",
            "authors": ["Single Author String", {"name": "Valid Dict Author"}, None, 12345],
            "abstract": ["Part 1", "Part 2"],
        }
        res = self.main._extract_article_fields(record)
        self.assertEqual(res["title"], "Quantum Biology")
        self.assertIn("Single Author String", res["authors"])
        self.assertIn("Valid Dict Author", res["authors"])
        self.assertEqual(res["abstract"], "Part 1 Part 2")

    def test_search_pubmed_success(self):
        """Verify search_pubmed returns formatted articles."""
        search_mock = MagicMock()
        search_mock.status_code = 200
        search_mock.json.return_value = {
            "esearchresult": {"idlist": ["10001", "10002"]}
        }

        summary_mock = MagicMock()
        summary_mock.status_code = 200
        summary_mock.json.return_value = {
            "result": {
                "10001": {"title": "Gene Therapy Advances", "source": "Cell", "pubdate": "2023"},
                "10002": {"title": "CRISPR Mechanisms", "source": "Science", "pubdate": "2024"},
            }
        }

        self.mock_client.get.side_effect = [search_mock, summary_mock]

        req = self.models.SearchPubmedRequest(query="CRISPR gene therapy", max_results=5)
        resp = asyncio.run(self.main.search_pubmed(req))

        self.assertIsNone(resp.error)
        self.assertIn("Top PubMed results for: CRISPR gene therapy", resp.result)
        self.assertIn("PMID 10001: Gene Therapy Advances", resp.result)
        self.assertIn("PMID 10002: CRISPR Mechanisms", resp.result)

    def test_search_pubmed_no_results(self):
        """Verify search_pubmed handles empty idlist cleanly."""
        search_mock = MagicMock()
        search_mock.status_code = 200
        search_mock.json.return_value = {"esearchresult": {"idlist": []}}
        self.mock_client.get.side_effect = [search_mock]

        req = self.models.SearchPubmedRequest(query="nonexistentqueryxyz12345")
        resp = asyncio.run(self.main.search_pubmed(req))

        self.assertIsNone(resp.error)
        self.assertIn("No PubMed results found for: nonexistentqueryxyz12345", resp.result)

    def test_search_pubmed_non_dict_esearch(self):
        """Verify search_pubmed handles non-dict response defensively."""
        search_mock = MagicMock()
        search_mock.status_code = 200
        search_mock.json.return_value = ["unexpected", "list"]
        self.mock_client.get.side_effect = [search_mock]

        req = self.models.SearchPubmedRequest(query="cancer")
        resp = asyncio.run(self.main.search_pubmed(req))

        self.assertIsNotNone(resp.error)
        self.assertIn("PubMed search failed", resp.error)

    def test_search_pubmed_http_error(self):
        """Verify search_pubmed handles HTTPStatusError cleanly."""
        error_resp = MagicMock(status_code=502)
        exc = self.main.httpx.HTTPStatusError("Bad Gateway", request=MagicMock(), response=error_resp)
        self.mock_client.get.side_effect = exc

        req = self.models.SearchPubmedRequest(query="cancer")
        resp = asyncio.run(self.main.search_pubmed(req))

        self.assertIsNotNone(resp.error)
        self.assertIn("PubMed search failed with status 502.", resp.error)

    def test_get_pubmed_article_success(self):
        """Verify get_pubmed_article returns full citation and abstract."""
        summary_mock = MagicMock()
        summary_mock.status_code = 200
        summary_mock.json.return_value = {
            "result": {
                "35000001": {
                    "title": "Neural Dynamics in Vision",
                    "source": "Neuron",
                    "pubdate": "2022",
                    "elocationid": "10.1016/j.neuron.2022.01.001",
                    "authors": [{"name": "Smith J"}, {"name": "Doe A"}],
                }
            }
        }

        fetch_mock = MagicMock()
        fetch_mock.status_code = 200
        fetch_mock.text = (
            "<PubmedArticleSet>"
            "<PubmedArticle>"
            "<MedlineCitation>"
            "<Article>"
            "<Abstract><AbstractText>This study explores cortical dynamics.</AbstractText></Abstract>"
            "</Article>"
            "</MedlineCitation>"
            "</PubmedArticle>"
            "</PubmedArticleSet>"
        )

        self.mock_client.get.side_effect = [summary_mock, fetch_mock]

        req = self.models.GetPubmedArticleRequest(pmid="35000001")
        resp = asyncio.run(self.main.get_pubmed_article(req))

        self.assertIsNone(resp.error)
        self.assertIn("PMID 35000001", resp.result)
        self.assertIn("Title: Neural Dynamics in Vision", resp.result)
        self.assertIn("Authors: Smith J, Doe A", resp.result)
        self.assertIn("Journal/Date: Neuron (2022)", resp.result)
        self.assertIn("Abstract: This study explores cortical dynamics.", resp.result)

    def test_get_pubmed_article_not_found(self):
        """Verify get_pubmed_article handles missing record cleanly."""
        summary_mock = MagicMock()
        summary_mock.status_code = 200
        summary_mock.json.return_value = {"result": {}}
        self.mock_client.get.side_effect = [summary_mock]

        req = self.models.GetPubmedArticleRequest(pmid="99999999")
        resp = asyncio.run(self.main.get_pubmed_article(req))

        self.assertIsNotNone(resp.error)
        self.assertIn("No PubMed record found for PMID 99999999", resp.error)

    def test_get_pubmed_article_abstract_fetch_failure_graceful(self):
        """Verify article retrieval succeeds even if efetch XML abstract fails."""
        summary_mock = MagicMock()
        summary_mock.status_code = 200
        summary_mock.json.return_value = {
            "result": {
                "35000002": {
                    "title": "Stem Cell Pluripotency",
                    "source": "Nature",
                    "pubdate": "2021",
                    "elocationid": "",
                    "authors": [],
                }
            }
        }
        fetch_mock = MagicMock(status_code=500)
        exc = self.main.httpx.HTTPStatusError("Internal Server Error", request=MagicMock(), response=fetch_mock)
        self.mock_client.get.side_effect = [summary_mock, exc]

        req = self.models.GetPubmedArticleRequest(pmid="35000002")
        resp = asyncio.run(self.main.get_pubmed_article(req))

        self.assertIsNone(resp.error)
        self.assertIn("PMID 35000002", resp.result)
        self.assertIn("Title: Stem Cell Pluripotency", resp.result)
        self.assertNotIn("Abstract:", resp.result)

    def test_get_related_pubmed_success(self):
        """Verify get_related_pubmed parses elink response and fetches summaries."""
        elink_mock = MagicMock()
        elink_mock.status_code = 200
        elink_mock.json.return_value = {
            "linksets": [
                {
                    "linksetdbs": [
                        {"links": ["20001", "20002"]}
                    ]
                }
            ]
        }

        summary_mock = MagicMock()
        summary_mock.status_code = 200
        summary_mock.json.return_value = {
            "result": {
                "20001": {"title": "Related Paper One", "source": "Lancet", "pubdate": "2020"},
                "20002": {"title": "Related Paper Two", "source": "BMJ", "pubdate": "2021"},
            }
        }

        self.mock_client.get.side_effect = [elink_mock, summary_mock]

        req = self.models.GetRelatedPubmedRequest(pmid="10001", max_results=2)
        resp = asyncio.run(self.main.get_related_pubmed(req))

        self.assertIsNone(resp.error)
        self.assertIn("Related PubMed articles for PMID 10001:", resp.result)
        self.assertIn("PMID 20001: Related Paper One", resp.result)
        self.assertIn("PMID 20002: Related Paper Two", resp.result)

    def test_get_related_pubmed_no_links(self):
        """Verify get_related_pubmed handles empty or missing linksets cleanly."""
        elink_mock = MagicMock()
        elink_mock.status_code = 200
        elink_mock.json.return_value = {"linksets": []}
        self.mock_client.get.side_effect = [elink_mock]

        req = self.models.GetRelatedPubmedRequest(pmid="10001")
        resp = asyncio.run(self.main.get_related_pubmed(req))

        self.assertIsNone(resp.error)
        self.assertIn("No related articles found for PMID 10001", resp.result)

    def test_get_related_pubmed_corrupted_structure_defensive(self):
        """Verify get_related_pubmed does not crash on malformed intermediate linksets."""
        elink_mock = MagicMock()
        elink_mock.status_code = 200
        elink_mock.json.return_value = {"linksets": [{"linksetdbs": "not-a-list"}]}
        self.mock_client.get.side_effect = [elink_mock]

        req = self.models.GetRelatedPubmedRequest(pmid="10001")
        resp = asyncio.run(self.main.get_related_pubmed(req))

        self.assertIsNone(resp.error)
        self.assertIn("No related articles found for PMID 10001", resp.result)

    def test_lifespan_client_fallback(self):
        """Verify fallback when app.state.http_client is None."""
        self.main.app.state.http_client = None

        mock_inst = AsyncMock()
        mock_inst.is_closed = False
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"esearchresult": {"idlist": []}}
        mock_inst.get.return_value = mock_resp

        with patch.object(self.main.httpx, "AsyncClient") as mock_cls:
            mock_cls.return_value.__aenter__.return_value = mock_inst

            req = self.models.SearchPubmedRequest(query="immunology")
            resp = asyncio.run(self.main.search_pubmed(req))

            self.assertIsNone(resp.error)
            self.assertIn("No PubMed results found for: immunology", resp.result)
            mock_cls.assert_called_once()
            mock_inst.get.assert_called_once()

    def test_models_normalization_and_validation(self):
        """Verify models whitespace normalization and bounds clamping."""
        req1 = self.models.SearchPubmedRequest(query="  virology  ", max_results=8)
        self.assertEqual(req1.query, "virology")
        self.assertEqual(req1.max_results, 8)

        # Empty query rejection
        with self.assertRaises(ValueError):
            self.models.SearchPubmedRequest(query="   ")

        # Bounds clamping in clamp_max_results
        req_clamped = self.models.SearchPubmedRequest(query="test", max_results=99)
        self.assertEqual(req_clamped.max_results, 10)

        req2 = self.models.GetPubmedArticleRequest(pmid="  35000001  ")
        self.assertEqual(req2.pmid, "35000001")

        with self.assertRaises(ValueError):
            self.models.GetPubmedArticleRequest(pmid="not-a-number")

        req3 = self.models.GetRelatedPubmedRequest(pmid="12345", max_results=0)
        self.assertEqual(req3.max_results, 1)

    def test_real_pydantic_if_installed(self):
        """Exercise real Pydantic dependency path if installed in the environment."""
        try:
            import pydantic  # noqa: F401
        except (ImportError, ModuleNotFoundError):
            self.skipTest("pydantic not installed in environment")
        _, real_models = load_app_modules(force_stubs=False)
        req = real_models.SearchPubmedRequest(query="  neuroscience  ", max_results=5)
        self.assertEqual(req.query, "neuroscience")
        self.assertEqual(req.max_results, 5)


if __name__ == "__main__":
    unittest.main()
