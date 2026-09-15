"""Hermetic regression suite for the Crossref Omi app (#13983).

Framework stubs stand in for fastapi/httpx/pydantic so the production module
imports and runs with zero third-party packages and no network. The pydantic
stub executes real field/model validators, and the httpx stub is a
controllable transport seam for the pooled and fallback client paths.
"""

import sys
import types
import unittest
from unittest.mock import patch


class DummyFastAPI:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.lifespan = kwargs.get("lifespan")
        self.state = types.SimpleNamespace()
        self.routes = []
        self.exception_handlers = {}

    def get(self, path, **_kwargs):
        return self._route("GET", path)

    def post(self, path, **_kwargs):
        return self._route("POST", path)

    def _route(self, method, path):
        def decorator(func):
            self.routes.append((method, path, func))
            return func

        return decorator

    def exception_handler(self, exc_class):
        def decorator(func):
            self.exception_handlers[exc_class] = func
            return func

        return decorator


class DummyRequestValidationError(Exception):
    def __init__(self, errors):
        super().__init__("request validation failed")
        self._errors = errors

    def errors(self):
        return self._errors


class DummyJSONResponse:
    def __init__(self, content=None, status_code=200, **_kwargs):
        self.content = content
        self.status_code = status_code


def _field_validator(*fields, mode="after"):
    def decorator(func):
        target = getattr(func, "__func__", func)
        target.__validator_config__ = ("field", fields, mode)
        return func

    return decorator


def _model_validator(*, mode="after"):
    def decorator(func):
        target = getattr(func, "__func__", func)
        target.__validator_config__ = ("model", None, mode)
        return func

    return decorator


class DummyBaseModel:
    """Minimal pydantic stand-in that runs registered validators for real."""

    def __init__(self, **kwargs):
        cls = type(self)
        annotations = {}
        field_validators = []
        model_validators = []
        for klass in reversed(cls.__mro__):
            annotations.update(getattr(klass, "__annotations__", {}))
            for member in vars(klass).values():
                func = getattr(member, "__func__", member)
                config = getattr(func, "__validator_config__", None)
                if not config:
                    continue
                kind, fields, mode = config
                if kind == "field":
                    field_validators.append((fields, member))
                elif mode == "after":
                    model_validators.append(member)

        for name in annotations:
            if name in kwargs:
                value = kwargs[name]
            elif hasattr(cls, name):
                value = getattr(cls, name)
            else:
                raise TypeError(f"{cls.__name__} missing required field: {name}")
            for fields, member in field_validators:
                if name in fields:
                    value = member.__get__(None, cls)(value)
            setattr(self, name, value)
        for member in model_validators:
            bound = member.__get__(self, cls)
            bound()

    def model_dump(self):
        return dict(self.__dict__)


class FakeHTTPError(Exception):
    pass


class FakeResponse:
    def __init__(self, payload=None, status_error=None):
        self._payload = payload
        self._status_error = status_error

    def raise_for_status(self):
        if self._status_error is not None:
            raise self._status_error

    def json(self):
        return self._payload


class FakeAsyncClient:
    """Controllable httpx.AsyncClient seam: records requests, never hits network."""

    instances = []
    responses = []
    get_error = None
    fail_init = False

    @classmethod
    def reset(cls):
        cls.instances = []
        cls.responses = []
        cls.get_error = None
        cls.fail_init = False

    def __init__(self, timeout=None, headers=None):
        if FakeAsyncClient.fail_init:
            raise RuntimeError("client init failed")
        self.timeout = timeout
        self.headers = headers or {}
        self.requests = []
        self.closed = False
        FakeAsyncClient.instances.append(self)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_exc):
        self.closed = True
        return False

    async def get(self, url, params=None):
        self.requests.append({"url": url, "params": params or {}})
        if FakeAsyncClient.get_error is not None:
            raise FakeAsyncClient.get_error
        return FakeAsyncClient.responses.pop(0)

    async def aclose(self):
        self.closed = True


def install_dependency_stubs():
    fastapi = types.ModuleType("fastapi")
    fastapi.FastAPI = DummyFastAPI
    fastapi.Request = object
    sys.modules.setdefault("fastapi", fastapi)

    fastapi_exceptions = types.ModuleType("fastapi.exceptions")
    fastapi_exceptions.RequestValidationError = DummyRequestValidationError
    sys.modules.setdefault("fastapi.exceptions", fastapi_exceptions)

    fastapi_responses = types.ModuleType("fastapi.responses")
    fastapi_responses.JSONResponse = DummyJSONResponse
    sys.modules.setdefault("fastapi.responses", fastapi_responses)

    pydantic = types.ModuleType("pydantic")
    pydantic.BaseModel = DummyBaseModel
    pydantic.field_validator = _field_validator
    pydantic.model_validator = _model_validator
    sys.modules.setdefault("pydantic", pydantic)

    httpx = types.ModuleType("httpx")
    httpx.AsyncClient = FakeAsyncClient
    httpx.HTTPError = FakeHTTPError
    sys.modules.setdefault("httpx", httpx)


install_dependency_stubs()
import main


def _payload_message(**overrides):
    message = {
        "title": ["Machine Learning"],
        "DOI": "10.1/test",
        "publisher": "Test Publisher",
        "URL": "https://doi.org/10.1/test",
        "abstract": "<jats:p>A study.</jats:p>",
        "issued": {"date-parts": [[2021, 3, 4]]},
    }
    message.update(overrides)
    return {"message": message}


class ModelValidationTests(unittest.TestCase):
    def test_search_input_strips_query_and_clamps_upper_bound(self):
        model = main.SearchWorksInput(query="  graph nets  ", max_results=500)
        self.assertEqual(model.query, "graph nets")
        self.assertEqual(model.max_results, 10)

    def test_search_input_clamps_low_and_non_numeric_max_results(self):
        self.assertEqual(
            main.SearchWorksInput(query="q", max_results=-3).max_results, 1
        )
        self.assertEqual(
            main.SearchWorksInput(query="q", max_results="junk").max_results, 5
        )

    def test_get_work_input_strips_doi(self):
        self.assertEqual(main.GetWorkInput(doi="  10.1/abc ").doi, "10.1/abc")

    def test_author_input_strips_and_clamps(self):
        model = main.AuthorWorksInput(author="  Ada Lovelace ", max_results=0)
        self.assertEqual(model.author, "Ada Lovelace")
        self.assertEqual(model.max_results, 1)

    def test_chat_tool_response_requires_exactly_one_field(self):
        with self.assertRaises(ValueError):
            main.ChatToolResponse()
        with self.assertRaises(ValueError):
            main.ChatToolResponse(result="ok", error="bad")
        self.assertEqual(main.ChatToolResponse(result="ok").result, "ok")
        self.assertEqual(main.ChatToolResponse(error="bad").error, "bad")


class ExtractionHelperTests(unittest.TestCase):
    def test_extract_year_survives_scalar_container(self):
        self.assertEqual(main.extract_year({"issued": "2020"}), "")

    def test_extract_year_survives_non_list_date_parts(self):
        item = {"issued": {"date-parts": "2020"}}
        self.assertEqual(main.extract_year(item), "")

    def test_extract_year_survives_non_list_first_entry(self):
        item = {"issued": {"date-parts": [2020]}}
        self.assertEqual(main.extract_year(item), "")

    def test_extract_year_reads_normal_and_rejects_non_dict_items(self):
        item = {"published-print": {"date-parts": [[2019, 5, 1]]}}
        self.assertEqual(main.extract_year(item), "2019")
        self.assertEqual(main.extract_year(None), "")
        self.assertEqual(main.extract_year("junk"), "")

    def test_extract_title_handles_scalar_list_and_missing(self):
        self.assertEqual(
            main._extract_title({"title": "Machine Learning"}), "Machine Learning"
        )
        self.assertEqual(main._extract_title({"title": ["A", "B"]}), "A")
        self.assertEqual(
            main._extract_title({"title": ["", "  ", "Second"]}), "Second"
        )
        self.assertEqual(main._extract_title({"title": []}), "Untitled")
        self.assertEqual(main._extract_title({}), "Untitled")
        self.assertEqual(main._extract_title(42), "Untitled")


class CrossrefGetTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        FakeAsyncClient.reset()
        main.app.state.http_client = None

    def tearDown(self):
        FakeAsyncClient.reset()
        main.app.state.http_client = None

    async def test_uses_pooled_client_without_closing_it(self):
        pooled = FakeAsyncClient()
        main.app.state.http_client = pooled
        FakeAsyncClient.responses = [FakeResponse({"message": {}})]

        result = await main.crossref_get("/works", {"query": "x"})

        self.assertEqual(result, {"message": {}})
        self.assertEqual(FakeAsyncClient.instances, [pooled])
        self.assertEqual(
            pooled.requests[0]["url"], "https://api.crossref.org/works"
        )
        self.assertFalse(pooled.closed)

    async def test_fallback_creates_identified_client_and_closes_it(self):
        FakeAsyncClient.responses = [FakeResponse({"ok": True})]

        result = await main.crossref_get("/works/10.1/x", {})

        self.assertEqual(result, {"ok": True})
        self.assertEqual(len(FakeAsyncClient.instances), 1)
        client = FakeAsyncClient.instances[0]
        self.assertTrue(client.closed)
        self.assertEqual(client.timeout, main.TIMEOUT)
        self.assertEqual(client.headers.get("User-Agent"), main.USER_AGENT)

    async def test_non_dict_json_payload_raises(self):
        FakeAsyncClient.responses = [FakeResponse(["unexpected", "list"])]
        with self.assertRaises(ValueError):
            await main.crossref_get("/works", {})

    async def test_http_error_status_propagates(self):
        FakeAsyncClient.responses = [
            FakeResponse(status_error=FakeHTTPError("500 Server Error"))
        ]
        with self.assertRaises(FakeHTTPError):
            await main.crossref_get("/works", {})


class LifespanTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        FakeAsyncClient.reset()
        main.app.state.http_client = None

    def tearDown(self):
        FakeAsyncClient.reset()
        main.app.state.http_client = None

    async def test_lifespan_installs_and_closes_pooled_client(self):
        self.assertIsNotNone(main.app.lifespan)
        async with main.app.lifespan(main.app):
            client = main.app.state.http_client
            self.assertIsInstance(client, FakeAsyncClient)
            self.assertEqual(client.headers.get("User-Agent"), main.USER_AGENT)
            self.assertFalse(client.closed)
        self.assertTrue(client.closed)
        self.assertIsNone(main.app.state.http_client)

    async def test_lifespan_falls_back_when_client_init_fails(self):
        FakeAsyncClient.fail_init = True
        async with main.app.lifespan(main.app):
            self.assertIsNone(main.app.state.http_client)
            FakeAsyncClient.fail_init = False
            FakeAsyncClient.responses = [FakeResponse({"ok": 1})]
            result = await main.crossref_get("/works", {})
            self.assertEqual(result, {"ok": 1})


class ValidationEnvelopeTests(unittest.IsolatedAsyncioTestCase):
    async def test_request_validation_error_returns_200_envelope(self):
        handler = main.app.exception_handlers.get(DummyRequestValidationError)
        self.assertIsNotNone(handler)
        exc = DummyRequestValidationError(
            [
                {"loc": ("body", "query"), "msg": "field required"},
                {"loc": ("body", "max_results"), "msg": "not an int"},
            ]
        )
        response = await handler(None, exc)
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.content["result"])
        self.assertIn("body.query", response.content["error"])
        self.assertIn("field required", response.content["error"])
        self.assertIn("max_results", response.content["error"])


class SearchHandlerTests(unittest.IsolatedAsyncioTestCase):
    async def test_search_rejects_short_query(self):
        response = await main.search_crossref_works(
            main.SearchWorksInput(query=" a ")
        )
        self.assertIsNone(response.result)
        self.assertIn("at least 2 characters", response.error)

    async def test_search_surfaces_request_failure_as_envelope(self):
        async def boom(_path, _params):
            raise RuntimeError("network down")

        with patch.object(main, "crossref_get", boom):
            response = await main.search_crossref_works(
                main.SearchWorksInput(query="science", max_results=3)
            )
        self.assertIsNone(response.result)
        self.assertIn("Crossref request failed", response.error)
        self.assertIn("network down", response.error)

    async def test_search_skips_non_dict_items_and_reads_string_titles(self):
        payload = {
            "message": {
                "items": [
                    42,
                    "junk",
                    {
                        "title": "Machine Learning",
                        "DOI": "10.1/a",
                        "issued": {"date-parts": [[2021]]},
                    },
                ]
            }
        }

        async def fake(_path, _params):
            return payload

        with patch.object(main, "crossref_get", fake):
            response = await main.search_crossref_works(
                main.SearchWorksInput(query="ml", max_results=9)
            )
        self.assertIsNone(response.error)
        self.assertIn("1. Machine Learning (2021)", response.result)
        self.assertIn("DOI: 10.1/a", response.result)

    async def test_search_reports_no_results_for_non_dict_message(self):
        async def fake(_path, _params):
            return {"message": "oops"}

        with patch.object(main, "crossref_get", fake):
            response = await main.search_crossref_works(
                main.SearchWorksInput(query="ml")
            )
        self.assertIsNone(response.error)
        self.assertIn("No Crossref results found", response.result)

    async def test_search_reports_no_results_for_non_dict_payload(self):
        async def fake(_path, _params):
            return ["not", "a", "dict"]

        with patch.object(main, "crossref_get", fake):
            response = await main.search_crossref_works(
                main.SearchWorksInput(query="ml")
            )
        self.assertIsNone(response.error)
        self.assertIn("No Crossref results found", response.result)


class GetWorkHandlerTests(unittest.IsolatedAsyncioTestCase):
    async def test_get_work_rejects_invalid_doi(self):
        response = await main.get_crossref_work(
            main.GetWorkInput(doi="noseparator")
        )
        self.assertIsNone(response.result)
        self.assertIn("Invalid DOI format", response.error)

        response = await main.get_crossref_work(
            main.GetWorkInput(doi="10..1234/x")
        )
        self.assertIsNone(response.result)
        self.assertIn("Invalid DOI value", response.error)

    async def test_get_work_formats_full_message(self):
        async def fake(_path, _params):
            return _payload_message()

        with patch.object(main, "crossref_get", fake):
            response = await main.get_crossref_work(
                main.GetWorkInput(doi="10.1/test")
            )
        self.assertIsNone(response.error)
        self.assertIn("Title: Machine Learning", response.result)
        self.assertIn("DOI: 10.1/test", response.result)
        self.assertIn("Year: 2021", response.result)
        self.assertIn("Publisher: Test Publisher", response.result)
        self.assertIn("Abstract: A study.", response.result)

    async def test_get_work_survives_non_dict_message(self):
        async def fake(_path, _params):
            return {"message": "oops"}

        with patch.object(main, "crossref_get", fake):
            response = await main.get_crossref_work(
                main.GetWorkInput(doi="10.1/test")
            )
        self.assertIsNone(response.error)
        self.assertIn("Title: Untitled", response.result)

    async def test_get_work_surfaces_request_failure(self):
        async def boom(_path, _params):
            raise FakeHTTPError("404 Not Found")

        with patch.object(main, "crossref_get", boom):
            response = await main.get_crossref_work(
                main.GetWorkInput(doi="10.1/missing")
            )
        self.assertIsNone(response.result)
        self.assertIn("Crossref request failed", response.error)


class AuthorWorksHandlerTests(unittest.IsolatedAsyncioTestCase):
    async def test_author_rejects_short_name(self):
        response = await main.get_crossref_works_by_author(
            main.AuthorWorksInput(author=" x ")
        )
        self.assertIsNone(response.result)
        self.assertIn("at least 2 characters", response.error)

    async def test_author_clamps_and_strips_before_request(self):
        captured = {}

        async def fake(_path, params):
            captured.update(params)
            return {"message": {"items": []}}

        with patch.object(main, "crossref_get", fake):
            await main.get_crossref_works_by_author(
                main.AuthorWorksInput(author="  Ada  ", max_results=999)
            )
        self.assertEqual(captured["query.author"], "Ada")
        self.assertEqual(captured["rows"], 10)

    async def test_author_skips_non_dict_items(self):
        async def fake(_path, _params):
            return {
                "message": {
                    "items": [
                        None,
                        {"title": ["Paper"], "DOI": "10.1/p"},
                    ]
                }
            }

        with patch.object(main, "crossref_get", fake):
            response = await main.get_crossref_works_by_author(
                main.AuthorWorksInput(author="Ada")
            )
        self.assertIsNone(response.error)
        self.assertIn("1. Paper ()", response.result)


class EndpointSurfaceTests(unittest.TestCase):
    def test_health_and_tool_manifests(self):
        import asyncio

        self.assertEqual(asyncio.run(main.health()), {"status": "ok"})
        manifest = asyncio.run(main.get_omi_tools_manifest())
        names = {tool["name"] for tool in manifest["tools"]}
        self.assertEqual(
            names,
            {
                "search_crossref_works",
                "get_crossref_work",
                "get_crossref_works_by_author",
            },
        )
        self.assertTrue(
            all(tool["auth_required"] is False for tool in manifest["tools"])
        )
        routes = {(method, path) for method, path, _ in main.app.routes}
        self.assertIn(("POST", "/tools/search_crossref_works"), routes)
        self.assertIn(("POST", "/tools/get_crossref_work"), routes)
        self.assertIn(("POST", "/tools/get_crossref_works_by_author"), routes)


if __name__ == "__main__":
    unittest.main()
