"""Hermetic stdlib tests for the PubMed app (issue #13958).

Loads the production module with framework-only stubs so the real request
models, payload guards, and HTTP client pooling paths execute without
network access or third-party packages.
"""

from pathlib import Path
import sys
import types
import unittest
import unittest.mock


# --- Minimal functional stubs for pydantic / fastapi / httpx -----------------


class _FieldInfo:
    """Stand-in for pydantic.Field metadata."""

    def __init__(self, default, constraints):
        self.default = default
        self.required = default is ...
        self.min_length = constraints.get("min_length")
        self.max_length = constraints.get("max_length")
        self.ge = constraints.get("ge")
        self.le = constraints.get("le")


def _field(default=..., **constraints):
    return _FieldInfo(default, constraints)


def _field_validator(*field_names, mode="after"):
    def decorator(func):
        target = getattr(func, "__func__", func)
        configs = getattr(target, "_field_validator_configs", [])
        target._field_validator_configs = configs + [(field_names, mode)]
        return func

    return decorator


def _model_validator(mode="after"):
    def decorator(func):
        target = getattr(func, "__func__", func)
        target._model_validator_mode = mode
        return func

    return decorator


class _BaseModel:
    """Tiny functional subset of pydantic.BaseModel.

    Runs ``mode="before"`` validators before field constraint checks and
    ``mode="after"`` validators afterwards, matching pydantic v2 ordering.
    """

    def __init__(self, **kwargs):
        cls = type(self)
        annotations = {}
        validators = {}
        model_validators = []
        for klass in reversed(cls.__mro__):
            annotations.update(getattr(klass, "__annotations__", {}))
            for name, member in vars(klass).items():
                func = getattr(member, "__func__", member)
                for names, mode in getattr(func, "_field_validator_configs", []):
                    for field_name in names:
                        validators.setdefault(field_name, []).append((mode, name))
                if getattr(func, "_model_validator_mode", None) == "after":
                    model_validators.append(name)
        for field_name, annotation in annotations.items():
            info = getattr(cls, field_name, _FieldInfo(..., {}))
            if field_name in kwargs:
                value = kwargs[field_name]
            elif isinstance(info, _FieldInfo) and info.required:
                raise ValueError(f"{field_name}: field required")
            elif isinstance(info, _FieldInfo):
                value = info.default
            else:
                value = info
            for mode, validator_name in validators.get(field_name, []):
                if mode == "before":
                    value = getattr(cls, validator_name)(value)
            value = self._enforce(field_name, annotation, info, value)
            for mode, validator_name in validators.get(field_name, []):
                if mode == "after":
                    value = getattr(cls, validator_name)(value)
            setattr(self, field_name, value)
        for validator_name in model_validators:
            getattr(self, validator_name)()

    @staticmethod
    def _enforce(field_name, annotation, info, value):
        if annotation is str and not isinstance(value, str):
            raise ValueError(f"{field_name}: Input should be a valid string")
        if annotation is int and not isinstance(value, int):
            try:
                value = int(value)
            except (TypeError, ValueError):
                raise ValueError(f"{field_name}: Input should be a valid integer")
        if isinstance(info, _FieldInfo):
            if isinstance(value, str):
                if info.min_length is not None and len(value) < info.min_length:
                    raise ValueError(f"{field_name}: string shorter than {info.min_length}")
                if info.max_length is not None and len(value) > info.max_length:
                    raise ValueError(f"{field_name}: string longer than {info.max_length}")
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                if info.ge is not None and value < info.ge:
                    raise ValueError(f"{field_name}: less than {info.ge}")
                if info.le is not None and value > info.le:
                    raise ValueError(f"{field_name}: greater than {info.le}")
        return value

    def model_dump(self):
        return dict(vars(self))


class _StubHTTPError(Exception):
    pass


class _StubResponse:
    """Stand-in for httpx.Response (JSON body + text + status)."""

    def __init__(self, payload=None, status_code=200, text=""):
        self._payload = payload
        self.status_code = status_code
        self.text = text

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise _StubHTTPError(f"HTTP {self.status_code}")


class _FakeClient:
    """Records GET requests; routes canned responses by endpoint basename.

    ``routes`` maps the last URL path segment (e.g. "esearch.fcgi") to a
    _StubResponse or an Exception to raise.
    """

    created = []
    routes = {}

    def __init__(self, *args, routes=None, **kwargs):
        self.kwargs = kwargs
        self.routes = dict(routes or {})
        self.requests = []
        _FakeClient.created.append(self)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def get(self, url, params=None):
        self.requests.append((url, params))
        endpoint = url.rsplit("/", 1)[-1]
        table = self.routes or _FakeClient.routes
        if endpoint not in table:
            raise AssertionError(f"unexpected GET {url}")
        item = table[endpoint]
        if isinstance(item, Exception):
            raise item
        return item


class _StubFastAPI:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.state = types.SimpleNamespace()

    def _route(self, method, path):
        def decorator(func):
            return func

        return decorator

    def get(self, path, **kwargs):
        return self._route("GET", path)

    def post(self, path, **kwargs):
        return self._route("POST", path)

    def exception_handler(self, exc_class):
        return lambda func: func


class _StubJSONResponse:
    def __init__(self, status_code=200, content=None, **kwargs):
        self.status_code = status_code
        self.content = content


def _install_stubs():
    httpx = types.ModuleType("httpx")
    httpx.TimeoutException = type("TimeoutException", (_StubHTTPError,), {})
    httpx.HTTPError = _StubHTTPError
    httpx.AsyncClient = _FakeClient

    fastapi = types.ModuleType("fastapi")
    fastapi.FastAPI = _StubFastAPI
    fastapi.Request = type("Request", (), {})
    exceptions = types.ModuleType("fastapi.exceptions")
    exceptions.RequestValidationError = type("RequestValidationError", (Exception,), {})
    fastapi.exceptions = exceptions
    responses = types.ModuleType("fastapi.responses")
    responses.HTMLResponse = str
    responses.JSONResponse = _StubJSONResponse
    fastapi.responses = responses

    pydantic = types.ModuleType("pydantic")
    pydantic.BaseModel = _BaseModel
    pydantic.Field = _field
    pydantic.field_validator = _field_validator
    pydantic.model_validator = _model_validator

    sys.modules.update(
        {
            "httpx": httpx,
            "fastapi": fastapi,
            "fastapi.exceptions": exceptions,
            "fastapi.responses": responses,
            "pydantic": pydantic,
        }
    )


_install_stubs()
sys.path.insert(0, str(Path(__file__).resolve().parent))

import main  # noqa: E402
import models  # noqa: E402


EFETCH_XML = """<?xml version="1.0"?>
<PubmedArticleSet>
  <PubmedArticle><MedlineCitation><Article><Abstract>
    <AbstractText>Detailed abstract text.</AbstractText>
  </Abstract></Article></MedlineCitation></PubmedArticle>
</PubmedArticleSet>
"""


def _search_routes(**overrides):
    routes = {
        "esearch.fcgi": _StubResponse({"esearchresult": {"idlist": ["111", "222"]}}),
        "esummary.fcgi": _StubResponse(
            {
                "result": {
                    "111": {
                        "title": "First Study",
                        "fulljournalname": "Nature",
                        "pubdate": "2021",
                    },
                    "222": {"title": "Second Study", "source": "Cell", "pubdate": "2022"},
                }
            }
        ),
    }
    routes.update(overrides)
    return routes


def _related_routes(**overrides):
    routes = _search_routes()
    routes["elink.fcgi"] = _StubResponse(
        {"linksets": [{"linksetdbs": [{"links": ["333", "111"]}]}]}
    )
    routes["esummary.fcgi"] = _StubResponse(
        {"result": {"333": {"title": "Related Study", "source": "BMJ", "pubdate": "2020"}}}
    )
    routes.update(overrides)
    return routes


# --- Request model tests ------------------------------------------------------


class RequestModelTests(unittest.TestCase):
    def test_search_query_whitespace_stripped(self):
        req = models.SearchPubmedRequest(query="  cancer immunotherapy  ")
        self.assertEqual(req.query, "cancer immunotherapy")

    def test_search_query_blank_rejected(self):
        with self.assertRaises(ValueError):
            models.SearchPubmedRequest(query="   ")

    def test_search_query_missing_rejected(self):
        with self.assertRaises(ValueError):
            models.SearchPubmedRequest()

    def test_search_query_non_string_rejected(self):
        with self.assertRaises(ValueError):
            models.SearchPubmedRequest(query={"bad": "type"})

    def test_max_results_clamped_into_bounds(self):
        self.assertEqual(models.SearchPubmedRequest(query="x", max_results=0).max_results, 1)
        self.assertEqual(models.SearchPubmedRequest(query="x", max_results=99).max_results, 10)
        self.assertEqual(models.SearchPubmedRequest(query="x", max_results=4).max_results, 4)

    def test_max_results_unparsable_and_null_default(self):
        self.assertEqual(models.SearchPubmedRequest(query="x", max_results="abc").max_results, 5)
        self.assertEqual(models.SearchPubmedRequest(query="x", max_results=None).max_results, 5)

    def test_article_pmid_whitespace_stripped(self):
        req = models.GetPubmedArticleRequest(pmid="  12345678 ")
        self.assertEqual(req.pmid, "12345678")

    def test_article_pmid_non_numeric_rejected(self):
        for bad in ["abc", "12x4", "", "1234567890123"]:
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                models.GetPubmedArticleRequest(pmid=bad)

    def test_related_request_validates_and_clamps(self):
        req = models.GetRelatedPubmedRequest(pmid=" 42 ", max_results=50)
        self.assertEqual(req.pmid, "42")
        self.assertEqual(req.max_results, 10)
        with self.assertRaises(ValueError):
            models.GetRelatedPubmedRequest(pmid="nope")

    def test_chat_tool_response_requires_exactly_one_field(self):
        with self.assertRaises(ValueError):
            models.ChatToolResponse()
        with self.assertRaises(ValueError):
            models.ChatToolResponse(result="a", error="b")
        self.assertEqual(models.ChatToolResponse(error="e").error, "e")


# --- Defensive parsing tests ---------------------------------------------------


class PayloadGuardTests(unittest.TestCase):
    def test_extract_article_fields_mixed_author_types(self):
        record = {
            "title": "Study",
            "authors": [
                {"name": "Alice A"},
                "Scalar Author",
                None,
                7,
                {"name": ""},
                {"name": "Bob B"},
            ],
        }
        fields = main._extract_article_fields(record)
        self.assertEqual(fields["authors"], ["Alice A", "Scalar Author", "Bob B"])

    def test_extract_article_fields_non_dict_record(self):
        fields = main._extract_article_fields("corrupted")
        self.assertEqual(fields["title"], "Untitled")
        self.assertEqual(fields["authors"], [])
        self.assertEqual(fields["abstract"], "")

    def test_extract_article_fields_non_list_authors(self):
        for bad_authors in [{"name": "x"}, "oops", None, 42]:
            with self.subTest(bad_authors=bad_authors):
                fields = main._extract_article_fields({"title": "T", "authors": bad_authors})
                self.assertEqual(fields["authors"], [])


# --- Endpoint + client pooling tests -------------------------------------------


class EndpointTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        _FakeClient.created = []
        _FakeClient.routes = {}
        if hasattr(main.app.state, "http_client"):
            del main.app.state.http_client

    def _use_client(self, routes):
        client = _FakeClient(routes=routes)
        main.app.state.http_client = client
        _FakeClient.created = []
        return client

    async def test_search_pubmed_reuses_lifespan_client(self):
        client = self._use_client(_search_routes())
        response = await main.search_pubmed(models.SearchPubmedRequest(query="cancer"))
        self.assertIsNone(response.error)
        self.assertIn("1. PMID 111: First Study (Nature, 2021)", response.result)
        self.assertIn("2. PMID 222: Second Study (Cell, 2022)", response.result)
        endpoints = [url.rsplit("/", 1)[-1] for url, _ in client.requests]
        self.assertEqual(endpoints, ["esearch.fcgi", "esummary.fcgi"])
        self.assertEqual(_FakeClient.created, [])

    async def test_search_pubmed_falls_back_to_transient_client(self):
        _FakeClient.routes = _search_routes()
        response = await main.search_pubmed(models.SearchPubmedRequest(query="cancer"))
        self.assertIsNone(response.error)
        self.assertIn("PMID 111", response.result)
        self.assertEqual(len(_FakeClient.created), 1)

    async def test_search_pubmed_non_dict_esearch_payload(self):
        self._use_client({"esearch.fcgi": _StubResponse(["corrupted"])})
        response = await main.search_pubmed(models.SearchPubmedRequest(query="cancer"))
        self.assertIsNone(response.error)
        self.assertEqual(response.result, "No PubMed results found for: cancer")

    async def test_search_pubmed_non_dict_esearchresult_and_idlist(self):
        for payload in [
            {"esearchresult": "oops"},
            {"esearchresult": {"idlist": "not-a-list"}},
            {"esearchresult": {"idlist": None}},
        ]:
            with self.subTest(payload=payload):
                self._use_client({"esearch.fcgi": _StubResponse(payload)})
                response = await main.search_pubmed(models.SearchPubmedRequest(query="x"))
                self.assertIsNone(response.error)
                self.assertEqual(response.result, "No PubMed results found for: x")

    async def test_search_pubmed_non_dict_summary_row_falls_back(self):
        routes = _search_routes()
        routes["esummary.fcgi"] = _StubResponse(
            {"result": {"111": "corrupted-row", "222": {"title": "Good", "source": "Cell", "pubdate": "2022"}}}
        )
        self._use_client(routes)
        response = await main.search_pubmed(models.SearchPubmedRequest(query="cancer"))
        self.assertIsNone(response.error)
        self.assertIn("1. PMID 111: Untitled (, )", response.result)
        self.assertIn("2. PMID 222: Good (Cell, 2022)", response.result)

    async def test_search_pubmed_upstream_error_returns_clean_error(self):
        self._use_client({"esearch.fcgi": _StubHTTPError("boom")})
        response = await main.search_pubmed(models.SearchPubmedRequest(query="cancer"))
        self.assertIsNone(response.result)
        self.assertIn("PubMed search failed", response.error)

    async def test_get_pubmed_article_happy_path_with_abstract(self):
        routes = {
            "esummary.fcgi": _StubResponse(
                {
                    "result": {
                        "123": {
                            "title": "Deep Study",
                            "authors": [{"name": "A"}],
                            "source": "Lancet",
                            "pubdate": "2020",
                            "elocationid": "doi:10.1/x",
                        }
                    }
                }
            ),
            "efetch.fcgi": _StubResponse(text=EFETCH_XML),
        }
        self._use_client(routes)
        response = await main.get_pubmed_article(models.GetPubmedArticleRequest(pmid="123"))
        self.assertIsNone(response.error)
        self.assertIn("PMID 123", response.result)
        self.assertIn("Title: Deep Study", response.result)
        self.assertIn("Abstract: Detailed abstract text.", response.result)

    async def test_get_pubmed_article_missing_record(self):
        self._use_client({"esummary.fcgi": _StubResponse({"result": {}})})
        response = await main.get_pubmed_article(models.GetPubmedArticleRequest(pmid="999"))
        self.assertIsNone(response.result)
        self.assertEqual(response.error, "No PubMed record found for PMID 999")

    async def test_get_pubmed_article_non_dict_summary_record(self):
        self._use_client({"esummary.fcgi": _StubResponse({"result": {"999": "oops"}})})
        response = await main.get_pubmed_article(models.GetPubmedArticleRequest(pmid="999"))
        self.assertIsNone(response.result)
        self.assertEqual(response.error, "No PubMed record found for PMID 999")

    async def test_get_related_pubmed_happy_path(self):
        self._use_client(_related_routes())
        response = await main.get_related_pubmed(models.GetRelatedPubmedRequest(pmid="111"))
        self.assertIsNone(response.error)
        self.assertIn("Related PubMed articles for PMID 111:", response.result)
        self.assertIn("PMID 333: Related Study", response.result)

    async def test_get_related_pubmed_malformed_linksets(self):
        for payload in [
            {"linksets": "oops"},
            {"linksets": []},
            {"linksets": ["junk"]},
            {"linksets": [{"linksetdbs": "oops"}]},
            {"linksets": [{"linksetdbs": [[]]}]},
            {"linksets": [{"linksetdbs": [{"links": "oops"}]}]},
            "totally-corrupted",
        ]:
            with self.subTest(payload=payload):
                self._use_client({"elink.fcgi": _StubResponse(payload)})
                response = await main.get_related_pubmed(models.GetRelatedPubmedRequest(pmid="111"))
                self.assertIsNone(response.error)
                self.assertEqual(response.result, "No related articles found for PMID 111")

    async def test_get_related_pubmed_non_dict_summary_row(self):
        routes = _related_routes()
        routes["esummary.fcgi"] = _StubResponse({"result": {"333": 7, "111": {"title": "Ok"}}})
        self._use_client(routes)
        response = await main.get_related_pubmed(models.GetRelatedPubmedRequest(pmid="111"))
        self.assertIsNone(response.error)
        self.assertIn("PMID 333: Untitled", response.result)


if __name__ == "__main__":
    unittest.main()
