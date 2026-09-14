"""Hermetic unit tests for Omi Wikipedia Integration App.

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


def load_app_modules(force_stubs: bool = False):
    """Load models and main modules hermetically without contaminating sys.modules."""
    stubs = {}

    if not force_stubs:
        try:
            import pydantic
        except (ImportError, ModuleNotFoundError):
            pydantic = None
    else:
        pydantic = None

    if pydantic is None:
        pydantic_mod = types.ModuleType("pydantic")

        class FieldInfoStub:
            def __init__(self, default=..., **kwargs):
                self.default = default
                self.ge = kwargs.get("ge")
                self.le = kwargs.get("le")
                self.gt = kwargs.get("gt")
                self.lt = kwargs.get("lt")
                self.min_length = kwargs.get("min_length")
                self.max_length = kwargs.get("max_length")

        class BaseModelStub:
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

    if not force_stubs:
        try:
            import fastapi
            import fastapi.exceptions
            import fastapi.responses
        except (ImportError, ModuleNotFoundError):
            fastapi = None
    else:
        fastapi = None

    if fastapi is None:
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

        class RequestValidationErrorStub(Exception):
            def __init__(self, errors=None):
                self._errors = errors or []

            def errors(self):
                return self._errors

        fastapi_mod.FastAPI = FastAPIStub
        fastapi_mod.Request = MagicMock
        fastapi_mod.HTTPException = Exception
        fastapi_exceptions = types.ModuleType("fastapi.exceptions")
        fastapi_exceptions.RequestValidationError = RequestValidationErrorStub
        fastapi_mod.exceptions = fastapi_exceptions
        fastapi_responses = types.ModuleType("fastapi.responses")

        class JSONResponseStub:
            def __init__(self, content=None, status_code=200):
                self.content = content
                self.status_code = status_code

        class HTMLResponseStub:
            pass

        fastapi_responses.JSONResponse = JSONResponseStub
        fastapi_responses.HTMLResponse = HTMLResponseStub
        fastapi_mod.responses = fastapi_responses

        stubs["fastapi"] = fastapi_mod
        stubs["fastapi.exceptions"] = fastapi_exceptions
        stubs["fastapi.responses"] = fastapi_responses

    if not force_stubs:
        try:
            import httpx
        except (ImportError, ModuleNotFoundError):
            httpx = None
    else:
        httpx = None

    if httpx is None:
        httpx_mod = types.ModuleType("httpx")

        class HTTPErrorStub(Exception):
            pass

        class HTTPStatusErrorStub(HTTPErrorStub):
            def __init__(self, message="status error", *, request=None, response=None):
                super().__init__(message)
                self.response = response or MagicMock(status_code=500)

        class TimeoutExceptionStub(HTTPErrorStub):
            pass

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

        httpx_mod.AsyncClient = AsyncClientStub
        httpx_mod.HTTPError = HTTPErrorStub
        httpx_mod.HTTPStatusError = HTTPStatusErrorStub
        httpx_mod.TimeoutException = TimeoutExceptionStub
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


class TestWikipediaApp(unittest.TestCase):
    """Hermetic unit tests for Wikipedia integration endpoints and helper functions."""

    @classmethod
    def setUpClass(cls):
        cls.main, cls.models = load_app_modules()

    def setUp(self):
        self.mock_client = AsyncMock()
        self.mock_client.is_closed = False
        self.main.app.state.http_client = self.mock_client

    def test_health_endpoint(self):
        """Verify health check returns ok status."""
        res = asyncio.run(self.main.health())
        self.assertEqual(res, {"status": "ok"})

    def test_omi_tools_manifest(self):
        """Verify manifest contains all three declared tools."""
        manifest = asyncio.run(self.main.get_omi_tools_manifest())
        tools = manifest["tools"]
        tool_names = [t["name"] for t in tools]
        self.assertIn("search_articles", tool_names)
        self.assertIn("get_article_summary", tool_names)
        self.assertIn("get_random_article", tool_names)

    def test_helper_safe_limit(self):
        """Verify _safe_limit sanitizes inputs within bounds 1-10."""
        self.assertEqual(self.main._safe_limit(None), 5)
        self.assertEqual(self.main._safe_limit(""), 5)
        self.assertEqual(self.main._safe_limit("invalid"), 5)
        self.assertEqual(self.main._safe_limit(-3), 1)
        self.assertEqual(self.main._safe_limit(0), 1)
        self.assertEqual(self.main._safe_limit(7), 7)
        self.assertEqual(self.main._safe_limit(20), 10)

    def test_helper_safe_language(self):
        """Verify _safe_language validates language codes."""
        self.assertEqual(self.main._safe_language(None), "en")
        self.assertEqual(self.main._safe_language(""), "en")
        self.assertEqual(self.main._safe_language("  FR  "), "fr")
        self.assertEqual(self.main._safe_language("zh-cn"), "zh-cn")
        self.assertEqual(self.main._safe_language("invalid!code"), "en")
        self.assertEqual(self.main._safe_language("a" * 20), "en")

    def test_helper_clean_snippet(self):
        """Verify _clean_snippet strips HTML tags and normalizes whitespace."""
        self.assertEqual(self.main._clean_snippet(None), "")
        self.assertEqual(self.main._clean_snippet(""), "")
        raw = '<span class="searchmatch">Albert</span> Einstein was a &amp; physicist.'
        self.assertEqual(self.main._clean_snippet(raw), "Albert Einstein was a & physicist.")

    def test_format_summary_null_safe(self):
        """Verify _format_summary handles missing or null content_urls gracefully."""
        self.assertEqual(self.main._format_summary(None, "en"), "No summary was returned for this article.")
        self.assertEqual(self.main._format_summary("not a dict", "en"), "No summary was returned for this article.")

        # Missing content_urls
        data = {"title": "Test Title", "extract": "Test extract", "description": "Test desc"}
        formatted = self.main._format_summary(data, "en")
        self.assertIn("Test Title", formatted)
        self.assertIn("Test extract", formatted)
        self.assertIn("https://en.wikipedia.org/wiki/Test_Title", formatted)

        # None content_urls
        data["content_urls"] = None
        formatted_null = self.main._format_summary(data, "en")
        self.assertIn("https://en.wikipedia.org/wiki/Test_Title", formatted_null)

        # content_urls with None desktop
        data["content_urls"] = {"desktop": None}
        formatted_null_desk = self.main._format_summary(data, "en")
        self.assertIn("https://en.wikipedia.org/wiki/Test_Title", formatted_null_desk)

    def test_search_articles_success(self):
        """Verify successful article search."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "query": {
                "search": [
                    {
                        "title": "Quantum computing",
                        "snippet": '<span class="searchmatch">Quantum</span> computing is a rapidly-emerging technology.',
                    },
                    {
                        "title": "Quantum mechanics",
                        "snippet": "Fundamental theory in physics.",
                    },
                ]
            }
        }
        self.mock_client.get.return_value = mock_resp

        req = self.models.SearchArticlesRequest(query="quantum", limit=2)
        resp = asyncio.run(self.main.search_articles(req))

        self.assertIsNone(resp.error)
        self.assertIn("Wikipedia search results for 'quantum':", resp.result)
        self.assertIn("1. Quantum computing", resp.result)
        self.assertIn("2. Quantum mechanics", resp.result)
        self.assertIn("https://en.wikipedia.org/wiki/Quantum_computing", resp.result)

    def test_search_articles_prefilters_malformed_items(self):
        """Verify non-dict entries are filtered before slicing and indexing."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "query": {
                "search": [
                    None,
                    "malformed",
                    {"title": "Valid Article", "snippet": "Valid snippet"},
                ]
            }
        }
        self.mock_client.get.return_value = mock_resp

        req = self.models.SearchArticlesRequest(query="valid", limit=1)
        resp = asyncio.run(self.main.search_articles(req))

        self.assertIsNone(resp.error)
        self.assertIn("1. Valid Article", resp.result)

        # All malformed entries return no-results message
        mock_resp.json.return_value = {"query": {"search": [None, 123]}}
        resp_empty = asyncio.run(self.main.search_articles(req))
        self.assertEqual(resp_empty.result, "No Wikipedia articles found for 'valid'.")

    def test_search_articles_empty_results(self):
        """Verify message when search returns no matching articles."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"query": {"search": []}}
        self.mock_client.get.return_value = mock_resp

        req = self.models.SearchArticlesRequest(query="nonexistenttopic123456")
        resp = asyncio.run(self.main.search_articles(req))

        self.assertIsNone(resp.error)
        self.assertIn("No Wikipedia articles found for 'nonexistenttopic123456'.", resp.result)

    def test_search_articles_non_dict_response(self):
        """Verify non-dict API response returns clean error."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = ["unexpected", "list"]
        self.mock_client.get.return_value = mock_resp

        req = self.models.SearchArticlesRequest(query="test")
        resp = asyncio.run(self.main.search_articles(req))

        self.assertIsNotNone(resp.error)
        self.assertIn("Invalid response received from Wikipedia API.", resp.error)

    def test_get_article_summary_success(self):
        """Verify successful article summary lookup."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "type": "standard",
            "title": "Artificial intelligence",
            "description": "Intelligence of machines or software",
            "extract": "Artificial intelligence is intelligence demonstrated by computers.",
            "content_urls": {
                "desktop": {"page": "https://en.wikipedia.org/wiki/Artificial_intelligence"}
            },
        }
        self.mock_client.get.return_value = mock_resp

        req = self.models.GetArticleSummaryRequest(title="Artificial intelligence", language="en")
        resp = asyncio.run(self.main.get_article_summary(req))

        self.assertIsNone(resp.error)
        self.assertIn("Artificial intelligence", resp.result)
        self.assertIn("Intelligence of machines or software", resp.result)
        self.assertIn("demonstrated by computers", resp.result)

    def test_get_article_summary_disambiguation(self):
        """Verify disambiguation pages append helpful guidance."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "type": "disambiguation",
            "title": "Mercury",
            "extract": "Mercury most often refers to the chemical element or the planet.",
            "content_urls": {"desktop": {"page": "https://en.wikipedia.org/wiki/Mercury"}},
        }
        self.mock_client.get.return_value = mock_resp

        req = self.models.GetArticleSummaryRequest(title="Mercury")
        resp = asyncio.run(self.main.get_article_summary(req))

        self.assertIsNone(resp.error)
        self.assertIn("This is a disambiguation page. Use search_articles for more specific matches.", resp.result)

    def test_get_article_summary_not_found(self):
        """Verify 404 response reports clean not found message."""
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        error = self.main.httpx.HTTPStatusError("Not Found", request=MagicMock(), response=mock_resp)
        self.mock_client.get.side_effect = error

        req = self.models.GetArticleSummaryRequest(title="SomeNonexistentArticlePage123")
        resp = asyncio.run(self.main.get_article_summary(req))

        self.assertIsNotNone(resp.error)
        self.assertIn("No Wikipedia article found for 'SomeNonexistentArticlePage123'.", resp.error)

    def test_get_random_article_success(self):
        """Verify random article discovery."""
        random_resp = MagicMock()
        random_resp.status_code = 200
        random_resp.json.return_value = {
            "query": {
                "random": [{"id": 42, "title": "Mount Everest", "ns": 0}]
            }
        }
        summary_resp = MagicMock()
        summary_resp.status_code = 200
        summary_resp.json.return_value = {
            "title": "Mount Everest",
            "extract": "Mount Everest is Earth's highest mountain above sea level.",
            "content_urls": {"desktop": {"page": "https://en.wikipedia.org/wiki/Mount_Everest"}},
        }

        self.mock_client.get.side_effect = [random_resp, summary_resp]

        req = self.models.GetRandomArticleRequest(language="en")
        resp = asyncio.run(self.main.get_random_article(req))

        self.assertIsNone(resp.error)
        self.assertIn("Random Wikipedia article:", resp.result)
        self.assertIn("Mount Everest", resp.result)
        self.assertIn("Earth's highest mountain", resp.result)

    def test_get_random_article_empty_query(self):
        """Verify graceful message when random query returns no items."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"query": {"random": []}}
        self.mock_client.get.side_effect = [mock_resp]

        resp = asyncio.run(self.main.get_random_article())
        self.assertIsNone(resp.error)
        self.assertIn("No random Wikipedia article was returned.", resp.result)

    def test_lifespan_http_client_fallback(self):
        """Verify fallback when app.state.http_client is None."""
        self.main.app.state.http_client = None

        mock_inst = AsyncMock()
        mock_inst.is_closed = False
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"query": {"search": []}}
        mock_inst.get.return_value = mock_resp

        with patch.object(self.main.httpx, "AsyncClient") as mock_cls:
            mock_cls.return_value.__aenter__.return_value = mock_inst

            req = self.models.SearchArticlesRequest(query="earth")
            resp = asyncio.run(self.main.search_articles(req))

            self.assertIsNone(resp.error)
            self.assertIn("No Wikipedia articles found for 'earth'.", resp.result)
            mock_cls.assert_called_once()
            mock_inst.get.assert_called_once()

    def test_lifespan_http_client_closed_fallback(self):
        """Verify fallback when app.state.http_client.is_closed is True."""
        closed_client = MagicMock()
        closed_client.is_closed = True
        self.main.app.state.http_client = closed_client

        mock_inst = AsyncMock()
        mock_inst.is_closed = False
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"query": {"search": []}}
        mock_inst.get.return_value = mock_resp

        with patch.object(self.main.httpx, "AsyncClient") as mock_cls:
            mock_cls.return_value.__aenter__.return_value = mock_inst

            req = self.models.SearchArticlesRequest(query="moon")
            resp = asyncio.run(self.main.search_articles(req))

            self.assertIsNone(resp.error)
            self.assertIn("No Wikipedia articles found for 'moon'.", resp.result)
            mock_cls.assert_called_once()
            mock_inst.get.assert_called_once()

    def test_models_normalization_and_validation(self):
        """Verify Pydantic models whitespace normalization and rejection of invalid inputs."""
        req1 = self.models.SearchArticlesRequest(query="  physics  ", language="  DE  ", limit=8)
        self.assertEqual(req1.query, "physics")
        self.assertEqual(req1.language, "de")
        self.assertEqual(req1.limit, 8)

        # Empty query rejection
        with self.assertRaises(ValueError):
            self.models.SearchArticlesRequest(query="   ")

        # Limit constraints (1-10)
        with self.assertRaises(ValueError):
            self.models.SearchArticlesRequest(query="test", limit=0)
        with self.assertRaises(ValueError):
            self.models.SearchArticlesRequest(query="test", limit=15)

        req2 = self.models.GetArticleSummaryRequest(title="  Biology  ", language="  ES  ")
        self.assertEqual(req2.title, "Biology")
        self.assertEqual(req2.language, "es")

        with self.assertRaises(ValueError):
            self.models.GetArticleSummaryRequest(title="   ")

        req3 = self.models.GetRandomArticleRequest(language="  JA  ")
        self.assertEqual(req3.language, "ja")

    def test_hermetic_stubs_enforce_constraints(self):
        """Verify hermetic fallback stubs enforce constraints identically when pydantic is absent."""
        _, stub_models = load_app_modules(force_stubs=True)

        req = stub_models.SearchArticlesRequest(query="astronomy", limit=5)
        self.assertEqual(req.query, "astronomy")
        self.assertEqual(req.limit, 5)

        with self.assertRaises(ValueError):
            stub_models.SearchArticlesRequest(query="   ")
        with self.assertRaises(ValueError):
            stub_models.SearchArticlesRequest(query="test", limit=0)
        with self.assertRaises(ValueError):
            stub_models.SearchArticlesRequest(query="test", limit=20)
        with self.assertRaises(ValueError):
            stub_models.GetArticleSummaryRequest(title="   ")


if __name__ == "__main__":
    unittest.main()
