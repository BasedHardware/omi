"""Hermetic unit tests for DuckDuckGo Instant Answers & Search Omi integration.

No third-party runtime dependencies required. Runs deterministically under
both standard library `python3 -S` and `pytest`.
"""

import asyncio
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import AsyncMock, patch


def load_app():
    class DummyState:
        pass

    class DummyFastAPI:
        def __init__(self, **kwargs):
            self.routes = []
            self.lifespan = kwargs.get("lifespan")
            self.state = DummyState()

        def get(self, path, **kwargs):
            return self._route("GET", path, kwargs.get("response_model"))

        def post(self, path, **kwargs):
            return self._route("POST", path, kwargs.get("response_model"))

        def exception_handler(self, exc_class):
            def decorator(func):
                return func

            return decorator

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

        def model_dump(self):
            return {k: v for k, v in self.__dict__.items() if not k.startswith("_")}

    def Field(default=None, **_kwargs):
        return default

    def field_validator(*_args, **_kwargs):
        def decorator(func):
            return func

        return decorator

    class HTTPError(Exception):
        pass

    class HTTPStatusError(HTTPError):
        def __init__(self, message=None, response=None):
            super().__init__(message)
            self.response = response or types.SimpleNamespace(status_code=500, text="Internal Server Error")

    class TimeoutException(HTTPError):
        pass

    class DummyAsyncClient:
        def __init__(self, *args, **kwargs):
            self.is_closed = False

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            self.is_closed = True

        async def aclose(self):
            self.is_closed = True

        async def get(self, url, params=None):
            raise NotImplementedError

    fastapi = types.ModuleType("fastapi")
    fastapi.FastAPI = DummyFastAPI
    fastapi.Request = object
    fastapi_responses = types.ModuleType("fastapi.responses")
    fastapi_responses.HTMLResponse = str
    fastapi_responses.JSONResponse = dict
    fastapi_exceptions = types.ModuleType("fastapi.exceptions")

    class RequestValidationError(Exception):
        pass

    fastapi_exceptions.RequestValidationError = RequestValidationError

    pydantic = types.ModuleType("pydantic")
    pydantic.BaseModel = DummyBaseModel
    pydantic.Field = Field
    pydantic.field_validator = field_validator

    httpx = types.ModuleType("httpx")
    httpx.HTTPError = HTTPError
    httpx.HTTPStatusError = HTTPStatusError
    httpx.TimeoutException = TimeoutException
    httpx.AsyncClient = DummyAsyncClient

    models_spec = importlib.util.spec_from_file_location("models", Path(__file__).with_name("models.py"))
    models_mod = importlib.util.module_from_spec(models_spec)

    main_spec = importlib.util.spec_from_file_location("duckduckgo_app_hermetic", Path(__file__).with_name("main.py"))
    main_mod = importlib.util.module_from_spec(main_spec)

    with patch.dict(
        sys.modules,
        {
            "fastapi": fastapi,
            "fastapi.responses": fastapi_responses,
            "fastapi.exceptions": fastapi_exceptions,
            "pydantic": pydantic,
            "httpx": httpx,
            "models": models_mod,
        },
    ):
        models_spec.loader.exec_module(models_mod)
        main_spec.loader.exec_module(main_mod)
    return main_mod, models_mod


main, models = load_app()


def _run(coro):
    return asyncio.run(coro)


class RouteRegistrationTests(unittest.TestCase):
    def test_routes_registered_with_correct_methods_and_paths(self):
        registered = {(r["method"], r["path"]): r for r in main.app.routes}
        expected_endpoints = {
            ("GET", "/"),
            ("GET", "/health"),
            ("GET", "/privacy"),
            ("GET", "/manifest.json"),
            ("GET", "/.well-known/ai-plugin.json"),
            ("POST", "/tools/instant_answer"),
            ("POST", "/tools/search_topics"),
            ("POST", "/tools/define_term"),
        }
        for endpoint in expected_endpoints:
            self.assertIn(endpoint, registered, f"Endpoint {endpoint} was not registered")


class HelperFunctionTests(unittest.TestCase):
    def test_clean_text_strips_html_and_unescapes(self):
        self.assertEqual(main._clean_text("<b>Hello</b> &amp; World!"), "Hello & World!")
        self.assertEqual(main._clean_text("<i>Test &lt;123&gt;</i>"), "Test <123>")
        self.assertEqual(main._clean_text(""), "")
        self.assertEqual(main._clean_text(None), "")
        self.assertEqual(main._clean_text("   Spaces   "), "Spaces")

    def test_extract_related_topics_flat(self):
        raw = [
            {"Text": "Apple Inc. — American tech company", "FirstURL": "https://duckduckgo.com/Apple_Inc"},
            {"Text": "Apple (fruit) — Pome fruit", "FirstURL": "https://duckduckgo.com/Apple"},
        ]
        extracted = main._extract_related_topics(raw, max_count=5)
        self.assertEqual(len(extracted), 2)
        self.assertEqual(extracted[0]["text"], "Apple Inc. — American tech company")
        self.assertEqual(extracted[0]["url"], "https://duckduckgo.com/Apple_Inc")

    def test_extract_related_topics_nested(self):
        raw = [
            {
                "Name": "Computers",
                "Topics": [
                    {"Text": "Apple I — Early computer", "FirstURL": "https://duckduckgo.com/Apple_I"},
                    {"Text": "Apple II — 8-bit computer", "FirstURL": "https://duckduckgo.com/Apple_II"},
                ],
            },
            {"Text": "Apple Corps — Multimedia company", "FirstURL": "https://duckduckgo.com/Apple_Corps"},
        ]
        extracted = main._extract_related_topics(raw, max_count=2)
        self.assertEqual(len(extracted), 2)
        self.assertEqual(extracted[0]["text"], "Apple I — Early computer")
        self.assertEqual(extracted[1]["text"], "Apple II — 8-bit computer")

    def test_extract_related_topics_invalid_input(self):
        self.assertEqual(main._extract_related_topics(None), [])
        self.assertEqual(main._extract_related_topics("not a list"), [])
        self.assertEqual(main._extract_related_topics([None, 123, {}]), [])


class ToolEndpointsTests(unittest.TestCase):
    def setUp(self):
        self.sample_abstract_data = {
            "Heading": "Quantum Computing",
            "AbstractText": "Quantum computing is a multidisciplinary field comprising aspects of computer science, physics, and mathematics that utilizes quantum mechanics to solve complex problems faster than on classical computers.",
            "AbstractSource": "Wikipedia",
            "AbstractURL": "https://en.wikipedia.org/wiki/Quantum_computing",
            "Answer": "",
            "Definition": "",
            "RelatedTopics": [],
            "Results": [],
        }

        self.sample_calc_data = {
            "Heading": "",
            "AbstractText": "",
            "Answer": "42",
            "AnswerType": "calc",
            "Definition": "",
            "RelatedTopics": [],
            "Results": [],
        }

        self.sample_definition_data = {
            "Heading": "Serendipity",
            "AbstractText": "",
            "Answer": "",
            "Definition": "The faculty of making happy and unexpected discoveries by accident.",
            "DefinitionSource": "Wiktionary",
            "DefinitionURL": "https://en.wiktionary.org/wiki/serendipity",
            "RelatedTopics": [],
            "Results": [],
        }

        self.sample_disambig_data = {
            "Heading": "Python",
            "AbstractText": "",
            "Answer": "",
            "Definition": "",
            "RelatedTopics": [
                {"Text": "Python (programming language) — High-level language", "FirstURL": "https://duckduckgo.com/Python_lang"},
                {"Text": "Python (genus) — Genus of nonvenomous snakes", "FirstURL": "https://duckduckgo.com/Python_genus"},
            ],
            "Results": [],
        }

    def test_instant_answer_abstract(self):
        with patch.object(main, "_query_duckduckgo", new=AsyncMock(return_value=self.sample_abstract_data)):
            req = models.InstantAnswerRequest(query="quantum computing", include_sources=True)
            res = _run(main.instant_answer(req))
            self.assertIsNone(res.error)
            self.assertIn("### Quantum Computing", res.result)
            self.assertIn("multidisciplinary field", res.result)
            self.assertIn("Source: Wikipedia (https://en.wikipedia.org/wiki/Quantum_computing)", res.result)

    def test_instant_answer_abstract_without_sources(self):
        with patch.object(main, "_query_duckduckgo", new=AsyncMock(return_value=self.sample_abstract_data)):
            req = models.InstantAnswerRequest(query="quantum computing", include_sources=False)
            res = _run(main.instant_answer(req))
            self.assertIsNone(res.error)
            self.assertIn("### Quantum Computing", res.result)
            self.assertNotIn("Source: Wikipedia", res.result)

    def test_instant_answer_calculation(self):
        with patch.object(main, "_query_duckduckgo", new=AsyncMock(return_value=self.sample_calc_data)):
            req = models.InstantAnswerRequest(query="6 * 7")
            res = _run(main.instant_answer(req))
            self.assertIsNone(res.error)
            self.assertIn("**calc**: 42", res.result)

    def test_instant_answer_definition(self):
        with patch.object(main, "_query_duckduckgo", new=AsyncMock(return_value=self.sample_definition_data)):
            req = models.InstantAnswerRequest(query="define serendipity")
            res = _run(main.instant_answer(req))
            self.assertIsNone(res.error)
            self.assertIn("### Definition: Serendipity", res.result)
            self.assertIn("unexpected discoveries", res.result)
            self.assertIn("Source: Wiktionary", res.result)

    def test_instant_answer_disambiguation(self):
        with patch.object(main, "_query_duckduckgo", new=AsyncMock(return_value=self.sample_disambig_data)):
            req = models.InstantAnswerRequest(query="python")
            res = _run(main.instant_answer(req))
            self.assertIsNone(res.error)
            self.assertIn("### Topics matching 'python':", res.result)
            self.assertIn("Python (programming language)", res.result)
            self.assertIn("https://duckduckgo.com/Python_lang", res.result)

    def test_instant_answer_no_results(self):
        empty_data = {"Heading": "", "AbstractText": "", "Answer": "", "Definition": "", "RelatedTopics": [], "Results": []}
        with patch.object(main, "_query_duckduckgo", new=AsyncMock(return_value=empty_data)):
            req = models.InstantAnswerRequest(query="randomnonexistenttopic12345")
            res = _run(main.instant_answer(req))
            self.assertIsNone(res.error)
            self.assertIn("No instant answer or detailed summary was found", res.result)

    def test_instant_answer_upstream_error(self):
        with patch.object(main, "_query_duckduckgo", new=AsyncMock(return_value={"error": "API unreachable"})):
            req = models.InstantAnswerRequest(query="test")
            res = _run(main.instant_answer(req))
            self.assertEqual(res.error, "API unreachable")
            self.assertIsNone(res.result)

    def test_search_topics_success(self):
        with patch.object(main, "_query_duckduckgo", new=AsyncMock(return_value=self.sample_disambig_data)):
            req = models.SearchTopicsRequest(query="python", limit=2)
            res = _run(main.search_topics(req))
            self.assertIsNone(res.error)
            self.assertIn("### Related Topics for 'python':", res.result)
            self.assertIn("1. Python (programming language) — High-level language", res.result)
            self.assertIn("[Link](https://duckduckgo.com/Python_lang)", res.result)

    def test_search_topics_fallback_to_abstract(self):
        with patch.object(main, "_query_duckduckgo", new=AsyncMock(return_value=self.sample_abstract_data)):
            req = models.SearchTopicsRequest(query="quantum computing")
            res = _run(main.search_topics(req))
            self.assertIsNone(res.error)
            self.assertIn("**Quantum Computing**: Quantum computing is a multidisciplinary field", res.result)

    def test_search_topics_empty(self):
        empty_data = {"Heading": "", "AbstractText": "", "Answer": "", "Definition": "", "RelatedTopics": [], "Results": []}
        with patch.object(main, "_query_duckduckgo", new=AsyncMock(return_value=empty_data)):
            req = models.SearchTopicsRequest(query="xyz987")
            res = _run(main.search_topics(req))
            self.assertIsNone(res.error)
            self.assertIn("No related topics or disambiguations found", res.result)

    def test_define_term_success(self):
        with patch.object(main, "_query_duckduckgo", new=AsyncMock(return_value=self.sample_definition_data)):
            req = models.DefineTermRequest(term="serendipity")
            res = _run(main.define_term(req))
            self.assertIsNone(res.error)
            self.assertIn("**Serendipity** (via Wiktionary):", res.result)
            self.assertIn("faculty of making happy", res.result)
            self.assertIn("Reference: https://en.wiktionary.org/wiki/serendipity", res.result)

    def test_define_term_fallback_to_abstract(self):
        with patch.object(main, "_query_duckduckgo", new=AsyncMock(return_value=self.sample_abstract_data)):
            req = models.DefineTermRequest(term="quantum computing")
            res = _run(main.define_term(req))
            self.assertIsNone(res.error)
            self.assertIn("**Quantum Computing** (via Wikipedia):", res.result)
            self.assertIn("Reference: https://en.wikipedia.org/wiki/Quantum_computing", res.result)

    def test_define_term_not_found(self):
        empty_data = {"Heading": "", "AbstractText": "", "Answer": "", "Definition": "", "RelatedTopics": [], "Results": []}
        with patch.object(main, "_query_duckduckgo", new=AsyncMock(return_value=empty_data)):
            req = models.DefineTermRequest(term="flabbergasted")
            res = _run(main.define_term(req))
            self.assertIsNone(res.error)
            self.assertIn("No dictionary definition found for 'flabbergasted'", res.result)


class MetadataEndpointsTests(unittest.TestCase):
    def test_index_html(self):
        html_content = _run(main.index())
        self.assertIn("DuckDuckGo Instant Answers for Omi", html_content)
        self.assertIn("POST /tools/instant_answer", html_content)

    def test_health_json(self):
        data = _run(main.health())
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["service"], "omi-duckduckgo-app")

    def test_privacy_json(self):
        data = _run(main.privacy())
        self.assertIn("privacy_policy", data)

    def test_manifest_json(self):
        data = _run(main.plugin_manifest())
        self.assertEqual(data["schema_version"], "v1")
        self.assertEqual(data["name_for_model"], "duckduckgo_answers")


if __name__ == "__main__":
    unittest.main()
