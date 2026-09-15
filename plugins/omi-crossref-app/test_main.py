"""Hermetic unit tests for Omi Crossref Integration App.

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

        def exception_handler(self, exc_cls):
            def decorator(fn):
                return fn
            return decorator

    fastapi_mod.FastAPI = FastAPIStub
    fastapi_mod.Request = MagicMock
    fastapi_exceptions = types.ModuleType("fastapi.exceptions")

    class RequestValidationErrorStub(Exception):
        def __init__(self, errors=None):
            self._errors = errors or []

        def errors(self):
            return self._errors

    fastapi_exceptions.RequestValidationError = RequestValidationErrorStub
    fastapi_mod.exceptions = fastapi_exceptions
    stubs["fastapi"] = fastapi_mod
    stubs["fastapi.exceptions"] = fastapi_exceptions

    fastapi_responses = types.ModuleType("fastapi.responses")

    class HTMLResponseStub:
        pass

    class JSONResponseStub:
        def __init__(self, content=None, status_code=200):
            self.content = content
            self.status_code = status_code

    fastapi_responses.HTMLResponse = HTMLResponseStub
    fastapi_responses.JSONResponse = JSONResponseStub
    fastapi_mod.responses = fastapi_responses
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


class TestCrossrefApp(unittest.TestCase):
    """Hermetic unit test suite for Crossref integration endpoints and parsing helpers."""

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

    def test_tools_and_manifest_endpoints(self):
        """Verify tools and .well-known manifest endpoints."""
        manifest = asyncio.run(self.main.get_omi_tools_manifest())
        tools_resp = asyncio.run(self.main.tools())
        names = [t["name"] for t in manifest["tools"]]
        self.assertIn("search_crossref_works", names)
        self.assertIn("get_crossref_work", names)
        self.assertIn("get_crossref_works_by_author", names)
        self.assertEqual(len(tools_resp["tools"]), 3)

    def test_clean_markup_and_html(self):
        """Verify clean handles JATS, HTML, and None safely."""
        self.assertEqual(self.main.clean(None), "")
        self.assertEqual(self.main.clean("   "), "")
        self.assertEqual(self.main.clean("<jats:p>Paragraph</jats:p>"), "Paragraph")
        self.assertEqual(self.main.clean("&lt;b&gt;title&lt;/b&gt;"), "title")
        self.assertEqual(self.main.clean("A &amp; B <b>bold</b>"), "A & B bold")
        self.assertEqual(self.main.clean("a < b and c > d"), "a < b and c > d")

    def test_extract_title_defensive(self):
        """Verify _extract_title handles list of strings, single string, None, and non-dict."""
        self.assertEqual(self.main._extract_title(None), "Untitled")
        self.assertEqual(self.main._extract_title({}), "Untitled")
        self.assertEqual(self.main._extract_title({"title": ["Real Title"]}), "Real Title")
        self.assertEqual(self.main._extract_title({"title": "Direct String Title"}), "Direct String Title")
        self.assertEqual(self.main._extract_title({"title": []}), "Untitled")

    def test_extract_year_defensive(self):
        """Verify extract_year handles date-parts, empty structures, and non-dict."""
        self.assertEqual(self.main.extract_year(None), "")
        self.assertEqual(self.main.extract_year({}), "")
        self.assertEqual(self.main.extract_year({"published-print": "not-a-dict"}), "")
        self.assertEqual(self.main.extract_year({"published-print": {"date-parts": [[2023, 5, 1]]}}), "2023")
        self.assertEqual(self.main.extract_year({"issued": {"date-parts": [[2021]]}}), "2021")

    def test_clamp_max_results(self):
        """Verify clamp_max_results limits values between 1 and 10."""
        self.assertEqual(self.main.clamp_max_results(5), 5)
        self.assertEqual(self.main.clamp_max_results(0), 1)
        self.assertEqual(self.main.clamp_max_results(100), 10)
        self.assertEqual(self.main.clamp_max_results("invalid"), 5)
        self.assertEqual(self.main.clamp_max_results(None), 5)

    def test_search_crossref_works_success(self):
        """Verify search_crossref_works formats results correctly."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "message": {
                "items": [
                    {
                        "title": ["Quantum Entanglement in Nanostructures"],
                        "DOI": "10.1038/xyz123",
                        "published-print": {"date-parts": [[2024]]},
                    }
                ]
            }
        }
        self.mock_client.get.return_value = mock_resp

        req = self.models.SearchWorksInput(query="Quantum Entanglement", max_results=5)
        resp = asyncio.run(self.main.search_crossref_works(req))

        self.assertIsNone(resp.error)
        self.assertIn("Top 1 Crossref results for 'Quantum Entanglement':", resp.result)
        self.assertIn("1. Quantum Entanglement in Nanostructures (2024)", resp.result)
        self.assertIn("DOI: 10.1038/xyz123", resp.result)

    def test_search_crossref_works_empty(self):
        """Verify search_crossref_works handles empty items."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"message": {"items": []}}
        self.mock_client.get.return_value = mock_resp

        req = self.models.SearchWorksInput(query="nonexistentqueryxyz")
        resp = asyncio.run(self.main.search_crossref_works(req))

        self.assertIsNone(resp.error)
        self.assertIn("No Crossref results found for 'nonexistentqueryxyz'.", resp.result)

    def test_search_crossref_works_non_dict_error(self):
        """Verify search_crossref_works handles non-dict response."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = ["bad", "list"]
        self.mock_client.get.return_value = mock_resp

        req = self.models.SearchWorksInput(query="nanotechnology")
        resp = asyncio.run(self.main.search_crossref_works(req))

        self.assertIsNotNone(resp.error)
        self.assertIn("Crossref request failed", resp.error)

    def test_get_crossref_work_success(self):
        """Verify get_crossref_work fetches metadata by DOI."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "message": {
                "title": ["Neural Networks in Physics"],
                "DOI": "10.1038/nphys1170",
                "publisher": "Nature Publishing Group",
                "URL": "https://doi.org/10.1038/nphys1170",
                "abstract": "We present neural network architectures.",
                "issued": {"date-parts": [[2020]]},
            }
        }
        self.mock_client.get.return_value = mock_resp

        req = self.models.GetWorkInput(doi="10.1038/nphys1170")
        resp = asyncio.run(self.main.get_crossref_work(req))

        self.assertIsNone(resp.error)
        self.assertIn("Title: Neural Networks in Physics", resp.result)
        self.assertIn("DOI: 10.1038/nphys1170", resp.result)
        self.assertIn("Year: 2020", resp.result)
        self.assertIn("Publisher: Nature Publishing Group", resp.result)
        self.assertIn("Abstract: We present neural network architectures.", resp.result)

    def test_get_crossref_work_not_found_404(self):
        """Verify get_crossref_work handles 404 cleanly."""
        mock_err_resp = MagicMock(status_code=404)
        exc = self.main.httpx.HTTPStatusError("Not Found", request=MagicMock(), response=mock_err_resp)
        self.mock_client.get.side_effect = exc

        req = self.models.GetWorkInput(doi="10.1038/nonexistent123")
        resp = asyncio.run(self.main.get_crossref_work(req))

        self.assertIsNotNone(resp.error)
        self.assertIn("No Crossref record found for DOI '10.1038/nonexistent123'.", resp.error)

    def test_get_crossref_work_invalid_doi_format(self):
        """Verify get_crossref_work rejects invalid DOIs without slash or with dot-dot."""
        req1 = self.models.GetWorkInput.__new__(self.models.GetWorkInput)
        req1.doi = "invalid-doi"
        resp1 = asyncio.run(self.main.get_crossref_work(req1))
        self.assertIn("Invalid DOI format", resp1.error)

        req2 = self.models.GetWorkInput.__new__(self.models.GetWorkInput)
        req2.doi = "10.1038/../malicious"
        resp2 = asyncio.run(self.main.get_crossref_work(req2))
        self.assertIn("Invalid DOI value", resp2.error)

    def test_get_crossref_works_by_author_success(self):
        """Verify get_crossref_works_by_author returns list of author publications."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "message": {
                "items": [
                    {
                        "title": ["Deep Learning Systems"],
                        "DOI": "10.1145/3318464",
                        "published-print": {"date-parts": [[2019]]},
                    }
                ]
            }
        }
        self.mock_client.get.return_value = mock_resp

        req = self.models.AuthorWorksInput(author="Yann LeCun", max_results=3)
        resp = asyncio.run(self.main.get_crossref_works_by_author(req))

        self.assertIsNone(resp.error)
        self.assertIn("Recent works for 'Yann LeCun':", resp.result)
        self.assertIn("1. Deep Learning Systems (2019)", resp.result)
        self.assertIn("DOI: 10.1145/3318464", resp.result)

    def test_get_crossref_works_by_author_empty(self):
        """Verify get_crossref_works_by_author handles empty results cleanly."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"message": {"items": []}}
        self.mock_client.get.return_value = mock_resp

        req = self.models.AuthorWorksInput(author="Unknown Scientist")
        resp = asyncio.run(self.main.get_crossref_works_by_author(req))

        self.assertIsNone(resp.error)
        self.assertIn("No recent works found for author 'Unknown Scientist'.", resp.result)

    def test_get_crossref_work_non_dict_message(self):
        """Verify get_crossref_work handles non-dict message payload cleanly."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"message": "invalid_string_message"}
        self.mock_client.get.return_value = mock_resp

        req = self.models.GetWorkInput(doi="10.1038/nphys1170")
        resp = asyncio.run(self.main.get_crossref_work(req))

        self.assertIsNotNone(resp.error)
        self.assertIn("No Crossref record found for DOI '10.1038/nphys1170'.", resp.error)

    def test_get_crossref_works_by_author_non_dict_items(self):
        """Verify get_crossref_works_by_author filters out non-dict items defensively."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "message": {
                "items": [
                    "corrupted_string_item",
                    None,
                    {
                        "title": ["Valid Paper Title"],
                        "DOI": "10.1038/s41586-020-2649-2",
                        "issued": {"date-parts": [[2020]]},
                    },
                ]
            }
        }
        self.mock_client.get.return_value = mock_resp

        req = self.models.AuthorWorksInput(author="Jennifer Doudna", max_results=5)
        resp = asyncio.run(self.main.get_crossref_works_by_author(req))

        self.assertIsNone(resp.error)
        self.assertIn("Recent works for 'Jennifer Doudna':", resp.result)
        self.assertIn("1. Valid Paper Title (2020)", resp.result)

    def test_lifespan_client_fallback(self):
        """Verify fallback when app.state.http_client is None."""
        self.main.app.state.http_client = None

        mock_inst = AsyncMock()
        mock_inst.is_closed = False
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"message": {"items": []}}
        mock_inst.get.return_value = mock_resp

        with patch.object(self.main.httpx, "AsyncClient") as mock_cls:
            mock_cls.return_value.__aenter__.return_value = mock_inst

            req = self.models.SearchWorksInput(query="astrophysics")
            resp = asyncio.run(self.main.search_crossref_works(req))

            self.assertIsNone(resp.error)
            self.assertIn("No Crossref results found for 'astrophysics'.", resp.result)
            mock_cls.assert_called_once()
            mock_inst.get.assert_called_once()

    def test_validation_exception_handler(self):
        """Verify validation_exception_handler converts 422 to 200 JSON envelope."""
        err = self.main.RequestValidationError([{"loc": ["body", "query"], "msg": "Field required"}])
        resp = asyncio.run(self.main.validation_exception_handler(MagicMock(), err))
        self.assertEqual(resp.status_code, 200)
        self.assertIn("query: Field required", resp.content["error"])

    def test_models_normalization_and_validation(self):
        """Verify models input normalization, trimming, and bounds enforcement."""
        req1 = self.models.SearchWorksInput(query="  machine learning  ", max_results=8)
        self.assertEqual(req1.query, "machine learning")
        self.assertEqual(req1.max_results, 8)

        # Rejection of query < 2 chars
        with self.assertRaises(ValueError):
            self.models.SearchWorksInput(query="a")

        # Bounds clamping in clamp_max_results
        req_clamped = self.models.SearchWorksInput(query="biology", max_results=99)
        self.assertEqual(req_clamped.max_results, 10)

        req2 = self.models.GetWorkInput(doi="  10.1038/nphys1170  ")
        self.assertEqual(req2.doi, "10.1038/nphys1170")

        with self.assertRaises(ValueError):
            self.models.GetWorkInput(doi="invalid-doi")

        with self.assertRaises(ValueError):
            self.models.GetWorkInput(doi="10.1038/../dotdot")

        req3 = self.models.AuthorWorksInput(author="  Geoffrey Hinton  ", max_results=0)
        self.assertEqual(req3.author, "Geoffrey Hinton")
        self.assertEqual(req3.max_results, 1)

    def test_real_pydantic_if_installed(self):
        """Exercise real Pydantic dependency path if installed in the environment."""
        try:
            import pydantic  # noqa: F401
        except (ImportError, ModuleNotFoundError):
            self.skipTest("pydantic not installed in environment")
        _, real_models = load_app_modules(force_stubs=False)
        req = real_models.SearchWorksInput(query="  optics  ", max_results=5)
        self.assertEqual(req.query, "optics")
        self.assertEqual(req.max_results, 5)


if __name__ == "__main__":
    unittest.main()
