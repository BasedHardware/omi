"""
Hermetic regression and unit tests for plugins/omi-pubmed-app.

The suite runs with the Python standard library only. Lightweight stubs replace
FastAPI, httpx, and Pydantic before importing the application, and every API
response is supplied by in-memory async mocks.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
import importlib
import logging
import os
import sys
import types
import unittest
from unittest.mock import AsyncMock, patch
from urllib.parse import parse_qs, urlsplit

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def _install_dependency_stubs():
    saved = {name: sys.modules.get(name) for name in ("httpx", "fastapi", "fastapi.responses", "pydantic")}

    httpx_mod = types.ModuleType("httpx")

    class HTTPError(Exception):
        pass

    class HTTPStatusError(HTTPError):
        def __init__(self, message="", *, request=None, response=None):
            super().__init__(message)
            self.request = request
            self.response = response

    class Request:
        def __init__(self, method="GET", url=""):
            self.method = method
            self.url = url

    class Response:
        def __init__(self, status_code=200, json_data=None, text_data=""):
            self.status_code = status_code
            self._json_data = json_data if json_data is not None else {}
            self.text = text_data

        def json(self):
            if isinstance(self._json_data, Exception):
                raise self._json_data
            return self._json_data

        def raise_for_status(self):
            if self.status_code >= 400:
                raise HTTPStatusError(f"HTTP {self.status_code}", response=self)

    class AsyncClient:
        def __init__(self, *args, **kwargs):
            self.timeout = kwargs.get("timeout")
            self.headers = kwargs.get("headers", {})
            self.is_closed = False

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            await self.aclose()
            return False

        async def aclose(self):
            self.is_closed = True

        async def get(self, url, params=None):
            raise AssertionError("Tests must stub get() on the client")

    httpx_mod.HTTPError = HTTPError
    httpx_mod.HTTPStatusError = HTTPStatusError
    httpx_mod.Request = Request
    httpx_mod.Response = Response
    httpx_mod.AsyncClient = AsyncClient
    sys.modules["httpx"] = httpx_mod

    fastapi_mod = types.ModuleType("fastapi")

    class FastAPI:
        def __init__(self, **kwargs):
            self.title = kwargs.get("title", "")
            self.description = kwargs.get("description", "")
            self.version = kwargs.get("version", "")
            self.lifespan = kwargs.get("lifespan")
            self.routes = []

        def get(self, path, **kwargs):
            def decorator(func):
                self.routes.append(("GET", path, func))
                return func
            return decorator

        def post(self, path, **kwargs):
            def decorator(func):
                self.routes.append(("POST", path, func))
                return func
            return decorator

    class FastAPIRequest:
        def __init__(self, json_data=None):
            self._json_data = json_data

        async def json(self):
            if isinstance(self._json_data, Exception):
                raise self._json_data
            return self._json_data

    fastapi_mod.FastAPI = FastAPI
    fastapi_mod.Request = FastAPIRequest
    sys.modules["fastapi"] = fastapi_mod

    fastapi_responses = types.ModuleType("fastapi.responses")

    class HTMLResponse:
        def __init__(self, content="", status_code=200):
            self.content = content
            self.status_code = status_code

    fastapi_responses.HTMLResponse = HTMLResponse
    sys.modules["fastapi.responses"] = fastapi_responses

    pydantic_mod = types.ModuleType("pydantic")

    class BaseModel:
        def __init__(self, **kwargs):
            for k, v in kwargs.items():
                setattr(self, k, v)

        def __getattr__(self, name):
            return None

        def model_dump(self):
            return self.__dict__.copy()

    pydantic_mod.BaseModel = BaseModel
    sys.modules["pydantic"] = pydantic_mod

    return saved


_saved_modules = _install_dependency_stubs()
try:
    if "main" in sys.modules:
        del sys.modules["main"]
    import main
finally:
    for _name, _original in _saved_modules.items():
        if _original is None:
            sys.modules.pop(_name, None)
        else:
            sys.modules[_name] = _original


def _run(coro):
    return asyncio.run(coro)


class MockResponse:
    def __init__(self, json_data=None, text_data="", status_code=200):
        self._json_data = json_data if json_data is not None else {}
        self.text = text_data
        self.status_code = status_code

    def json(self):
        if isinstance(self._json_data, Exception):
            raise self._json_data
        return self._json_data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise main.httpx.HTTPStatusError(f"HTTP {self.status_code}", response=self)


def make_request(json_data=None):
    class FakeRequest:
        async def json(self):
            if isinstance(json_data, Exception):
                raise json_data
            return json_data

    return FakeRequest()


class NormalizationAndHelperTests(unittest.TestCase):
    def test_normalize_pmid_bare_numbers(self):
        self.assertEqual(main._normalize_pmid("12345678"), "12345678")
        self.assertEqual(main._normalize_pmid("  987654321  "), "987654321")
        self.assertEqual(main._normalize_pmid("1"), "1")
        self.assertEqual(main._normalize_pmid("123456789012"), "123456789012")

    def test_normalize_pmid_prefixes(self):
        self.assertEqual(main._normalize_pmid("PMID: 34567890"), "34567890")
        self.assertEqual(main._normalize_pmid("pmid:34567890"), "34567890")
        self.assertEqual(main._normalize_pmid("PMID 34567890"), "34567890")
        self.assertEqual(main._normalize_pmid("pmid 34567890"), "34567890")
        self.assertEqual(main._normalize_pmid("PMID:34567890"), "34567890")

    def test_normalize_pmid_urls(self):
        self.assertEqual(
            main._normalize_pmid("https://pubmed.ncbi.nlm.nih.gov/34567890/"),
            "34567890",
        )
        self.assertEqual(
            main._normalize_pmid("https://pubmed.ncbi.nlm.nih.gov/34567890"),
            "34567890",
        )
        self.assertEqual(
            main._normalize_pmid("http://pubmed.ncbi.nlm.nih.gov/34567890/"),
            "34567890",
        )
        self.assertEqual(
            main._normalize_pmid("https://www.ncbi.nlm.nih.gov/pubmed/34567890/"),
            "34567890",
        )
        self.assertEqual(
            main._normalize_pmid("https://www.ncbi.nlm.nih.gov/pubmed/34567890"),
            "34567890",
        )
        self.assertEqual(
            main._normalize_pmid("pubmed.ncbi.nlm.nih.gov/34567890"),
            "34567890",
        )

    def test_normalize_pmid_invalid(self):
        self.assertIsNone(main._normalize_pmid(""))
        self.assertIsNone(main._normalize_pmid("   "))
        self.assertIsNone(main._normalize_pmid(None))
        self.assertIsNone(main._normalize_pmid(12345))
        self.assertIsNone(main._normalize_pmid("abc"))
        self.assertIsNone(main._normalize_pmid("pmid:abc"))
        self.assertIsNone(main._normalize_pmid("123456789012345678"))  # >12 digits
        self.assertIsNone(main._normalize_pmid("https://example.com/34567890"))

    def test_clamp_max_results(self):
        self.assertEqual(main._clamp_max_results(5), 5)
        self.assertEqual(main._clamp_max_results("7"), 7)
        self.assertEqual(main._clamp_max_results(0), 1)
        self.assertEqual(main._clamp_max_results(-3), 1)
        self.assertEqual(main._clamp_max_results(20), 10)
        self.assertEqual(main._clamp_max_results("invalid", default=5), 5)
        self.assertEqual(main._clamp_max_results(None, default=5), 5)

    def test_extract_article_fields(self):
        record = {
            "title": "Clinical &amp; Molecular Study",
            "pubdate": "2026 Sep 18",
            "source": "Nature Medicine",
            "elocationid": "10.1038/s41591-026-001",
            "authors": [
                {"name": "Alice Smith"},
                {"name": "Bob Jones"},
                "Charlie Brown",
            ],
            "abstract": "Key findings regarding genomic markers.",
        }
        res = main._extract_article_fields(record)
        self.assertEqual(res["title"], "Clinical & Molecular Study")
        self.assertEqual(res["pubdate"], "2026 Sep 18")
        self.assertEqual(res["source"], "Nature Medicine")
        self.assertEqual(res["doi"], "10.1038/s41591-026-001")
        self.assertEqual(res["authors"], ["Alice Smith", "Bob Jones", "Charlie Brown"])
        self.assertEqual(res["abstract"], "Key findings regarding genomic markers.")

    def test_extract_article_fields_malformed(self):
        res = main._extract_article_fields({})
        self.assertEqual(res["title"], "Untitled")
        self.assertEqual(res["authors"], [])
        self.assertEqual(res["abstract"], "")

        res_none = main._extract_article_fields(None)
        self.assertEqual(res_none["title"], "Untitled")
        self.assertEqual(res_none["authors"], [])

    def test_extract_abstract_from_efetch_xml(self):
        # Unlabeled abstract
        xml1 = """<?xml version="1.0"?>
        <PubmedArticleSet>
          <PubmedArticle>
            <MedlineCitation>
              <Article>
                <Abstract>
                  <AbstractText>This paper studies sleep.</AbstractText>
                </Abstract>
              </Article>
            </MedlineCitation>
          </PubmedArticle>
        </PubmedArticleSet>
        """
        self.assertEqual(main._extract_abstract_from_efetch_xml(xml1), "This paper studies sleep.")

        # Labeled sections
        xml2 = """<?xml version="1.0"?>
        <PubmedArticleSet>
          <PubmedArticle>
            <MedlineCitation>
              <Article>
                <Abstract>
                  <AbstractText Label="BACKGROUND">Prior work.</AbstractText>
                  <AbstractText Label="METHODS">We measured X.</AbstractText>
                </Abstract>
              </Article>
            </MedlineCitation>
          </PubmedArticle>
        </PubmedArticleSet>
        """
        out = main._extract_abstract_from_efetch_xml(xml2)
        self.assertIn("BACKGROUND: Prior work.", out)
        self.assertIn("METHODS: We measured X.", out)

        # Bad / empty XML
        self.assertEqual(main._extract_abstract_from_efetch_xml(""), "")
        self.assertEqual(main._extract_abstract_from_efetch_xml(None), "")
        self.assertEqual(main._extract_abstract_from_efetch_xml("<invalid xml"), "")
        self.assertEqual(main._extract_abstract_from_efetch_xml("<PubmedArticleSet></PubmedArticleSet>"), "")

    def test_select_related_pmids(self):
        links = ["19304878", "14630660", "22909249", "20739307", "31278684"]
        self.assertEqual(main._select_related_pmids(links, "19304878", 1), ["14630660"])
        self.assertEqual(main._select_related_pmids(links, "19304878", 5), ["14630660", "22909249", "20739307", "31278684"])

        # When source is not first
        links2 = ["14630660", "19304878", "22909249"]
        self.assertEqual(main._select_related_pmids(links2, "19304878", 5), ["14630660", "22909249"])

        # Source only
        self.assertEqual(main._select_related_pmids(["19304878"], "19304878", 5), [])

        # Non-list input
        self.assertEqual(main._select_related_pmids(None, "19304878", 5), [])
        self.assertEqual(main._select_related_pmids("not a list", "19304878", 5), [])

        # Integer IDs in links
        links3 = [19304878, 14630660, 22909249]
        self.assertEqual(main._select_related_pmids(links3, "19304878", 5), ["14630660", "22909249"])


class LifespanAndClientTests(unittest.TestCase):
    def test_client_lifecycle_and_reuse(self):
        async def run_test():
            main._pubmed_client = None
            client1 = await main._get_pubmed_client()
            self.assertIsNotNone(client1)
            self.assertFalse(client1.is_closed)

            # Same instance reused
            client2 = await main._get_pubmed_client()
            self.assertIs(client1, client2)

            # If closed, recreated
            await client1.aclose()
            self.assertTrue(client1.is_closed)
            client3 = await main._get_pubmed_client()
            self.assertIsNot(client1, client3)
            self.assertFalse(client3.is_closed)
            await client3.aclose()

        _run(run_test())

    def test_lifespan_context(self):
        async def run_lifespan():
            main._pubmed_client = None
            async with main.lifespan(main.app):
                self.assertIsNotNone(main._pubmed_client)
                self.assertFalse(main._pubmed_client.is_closed)
            self.assertTrue(main._pubmed_client.is_closed)

        _run(run_lifespan())


class EndpointTests(unittest.TestCase):
    def setUp(self):
        self.mock_client = AsyncMock()
        self.mock_client.is_closed = False
        main._pubmed_client = self.mock_client

    def tearDown(self):
        main._pubmed_client = None

    def test_health_endpoint(self):
        res = _run(main.health())
        self.assertEqual(res, {"status": "ok"})

    def test_home_endpoint(self):
        res = _run(main.home())
        self.assertIn("Omi PubMed App", res.content)

    def test_manifest_endpoints(self):
        m1 = _run(main.manifest())
        tools = m1.get("tools", [])
        self.assertEqual(len(tools), 3)
        names = [t["name"] for t in tools]
        self.assertIn("search_pubmed", names)
        self.assertIn("get_pubmed_article", names)
        self.assertIn("get_related_pubmed", names)

        m2 = _run(main.manifest_alias())
        self.assertEqual(m1, m2)

    def test_search_pubmed_success(self):
        mock_esearch = MockResponse(json_data={"esearchresult": {"idlist": ["123456", "789012"]}})
        mock_esummary = MockResponse(json_data={
            "result": {
                "uids": ["123456", "789012"],
                "123456": {"title": "Study A", "fulljournalname": "Journal One", "pubdate": "2026 Jan"},
                "789012": {"title": "Study B", "source": "Journal Two", "pubdate": "2026 Feb"},
            }
        })
        self.mock_client.get.side_effect = [mock_esearch, mock_esummary]

        req = make_request({"query": "genomics", "max_results": 2})
        resp = _run(main.search_pubmed(req))
        self.assertIsNone(resp.error)
        self.assertIn("Top PubMed results for: genomics", resp.result)
        self.assertIn("1. PMID 123456: Study A (Journal One, 2026 Jan)", resp.result)
        self.assertIn("2. PMID 789012: Study B (Journal Two, 2026 Feb)", resp.result)

    def test_search_pubmed_empty_query(self):
        req = make_request({"query": "   "})
        resp = _run(main.search_pubmed(req))
        self.assertEqual(resp.error, "query is required")

    def test_search_pubmed_invalid_payload(self):
        req = make_request("not a dict")
        resp = _run(main.search_pubmed(req))
        self.assertEqual(resp.error, "Request body must be a JSON object")

    def test_search_pubmed_no_results(self):
        mock_esearch = MockResponse(json_data={"esearchresult": {"idlist": []}})
        self.mock_client.get.return_value = mock_esearch

        req = make_request({"query": "nonexistentterm12345"})
        resp = _run(main.search_pubmed(req))
        self.assertIn("No PubMed results found for: nonexistentterm12345", resp.result)

    def test_search_pubmed_exception_sanitization(self):
        self.mock_client.get.side_effect = RuntimeError("sensitive internal cluster database error: /db/pubmed.sqlite")
        req = make_request({"query": "test query"})
        resp = _run(main.search_pubmed(req))
        self.assertEqual(resp.error, "PubMed search failed. Please try again later.")
        self.assertNotIn("sensitive internal cluster", str(resp.error))

    def test_get_pubmed_article_success_bare_pmid(self):
        mock_esummary = MockResponse(json_data={
            "result": {
                "uids": ["12345678"],
                "12345678": {
                    "title": "Quantum Biology Discovery",
                    "pubdate": "2026 Mar",
                    "source": "Science",
                    "elocationid": "10.1126/science.123",
                    "authors": [{"name": "Dr. Smith"}],
                }
            }
        })
        mock_efetch = MockResponse(text_data="""<PubmedArticleSet><PubmedArticle><MedlineCitation><Article>
            <Abstract><AbstractText Label="RESULTS">Found significant quantum effects.</AbstractText></Abstract>
        </Article></MedlineCitation></PubmedArticle></PubmedArticleSet>""")
        self.mock_client.get.side_effect = [mock_esummary, mock_efetch]

        req = make_request({"pmid": "12345678"})
        resp = _run(main.get_pubmed_article(req))
        self.assertIsNone(resp.error)
        self.assertIn("PMID 12345678", resp.result)
        self.assertIn("Title: Quantum Biology Discovery", resp.result)
        self.assertIn("Authors: Dr. Smith", resp.result)
        self.assertIn("Abstract: RESULTS: Found significant quantum effects.", resp.result)

    def test_get_pubmed_article_success_with_url(self):
        mock_esummary = MockResponse(json_data={
            "result": {
                "uids": ["12345678"],
                "12345678": {
                    "title": "Quantum Biology Discovery",
                    "pubdate": "2026 Mar",
                    "source": "Science",
                    "elocationid": "10.1126/science.123",
                    "authors": [{"name": "Dr. Smith"}],
                }
            }
        })
        mock_efetch = MockResponse(text_data="")
        self.mock_client.get.side_effect = [mock_esummary, mock_efetch]

        req = make_request({"pmid": "https://pubmed.ncbi.nlm.nih.gov/12345678/"})
        resp = _run(main.get_pubmed_article(req))
        self.assertIsNone(resp.error)
        self.assertIn("PMID 12345678", resp.result)

    def test_get_pubmed_article_success_with_prefix(self):
        mock_esummary = MockResponse(json_data={
            "result": {
                "uids": ["12345678"],
                "12345678": {
                    "title": "Quantum Biology Discovery",
                    "pubdate": "2026 Mar",
                    "source": "Science",
                    "elocationid": "10.1126/science.123",
                    "authors": [{"name": "Dr. Smith"}],
                }
            }
        })
        mock_efetch = MockResponse(text_data="")
        self.mock_client.get.side_effect = [mock_esummary, mock_efetch]

        req = make_request({"pmid": "PMID: 12345678"})
        resp = _run(main.get_pubmed_article(req))
        self.assertIsNone(resp.error)
        self.assertIn("PMID 12345678", resp.result)

    def test_get_pubmed_article_empty_id(self):
        req = make_request({"pmid": "   "})
        resp = _run(main.get_pubmed_article(req))
        self.assertEqual(resp.error, "pmid is required")

    def test_get_pubmed_article_invalid_id(self):
        req = make_request({"pmid": "invalid-pmid!"})
        resp = _run(main.get_pubmed_article(req))
        self.assertEqual(resp.error, "pmid must be a numeric PubMed ID")

    def test_get_pubmed_article_nonexistent(self):
        mock_esummary = MockResponse(json_data={
            "result": {
                "uids": ["999999999"],
                "999999999": {"uid": "999999999", "error": "cannot get document summary"}
            }
        })
        self.mock_client.get.return_value = mock_esummary

        req = make_request({"pmid": "999999999"})
        resp = _run(main.get_pubmed_article(req))
        self.assertEqual(resp.error, "No PubMed record found for PMID 999999999")

    def test_get_pubmed_article_exception_sanitization(self):
        self.mock_client.get.side_effect = RuntimeError("network connection timeout to backend: http://internal-vault:8200")
        req = make_request({"pmid": "12345678"})
        resp = _run(main.get_pubmed_article(req))
        self.assertEqual(resp.error, "Failed to fetch PubMed article. Please try again later.")
        self.assertNotIn("internal-vault", str(resp.error))

    def test_get_related_pubmed_success(self):
        mock_elink = MockResponse(json_data={
            "linksets": [{
                "linksetdbs": [{
                    "links": ["100", "200", "300"]
                }]
            }]
        })
        mock_esummary = MockResponse(json_data={
            "result": {
                "uids": ["200", "300"],
                "200": {"title": "Related Paper 1", "source": "J Cell Biol", "pubdate": "2025"},
                "300": {"title": "Related Paper 2", "source": "Nature", "pubdate": "2026"},
            }
        })
        self.mock_client.get.side_effect = [mock_elink, mock_esummary]

        req = make_request({"pmid": "100", "max_results": 2})
        resp = _run(main.get_related_pubmed(req))
        self.assertIsNone(resp.error)
        self.assertIn("Related PubMed articles for PMID 100:", resp.result)
        self.assertIn("1. PMID 200: Related Paper 1 (J Cell Biol, 2025)", resp.result)
        self.assertIn("2. PMID 300: Related Paper 2 (Nature, 2026)", resp.result)

    def test_get_related_pubmed_no_links(self):
        mock_elink = MockResponse(json_data={"linksets": []})
        self.mock_client.get.return_value = mock_elink

        req = make_request({"pmid": "12345"})
        resp = _run(main.get_related_pubmed(req))
        self.assertIn("No related articles found for PMID 12345", resp.result)

    def test_get_related_pubmed_invalid_pmid(self):
        req = make_request({"pmid": "invalid-id!"})
        resp = _run(main.get_related_pubmed(req))
        self.assertEqual(resp.error, "pmid must be a numeric PubMed ID")

    def test_get_related_pubmed_exception_sanitization(self):
        self.mock_client.get.side_effect = RuntimeError("sensitive proxy credentials leaked in http://user:pass@proxy.corp")
        req = make_request({"pmid": "12345"})
        resp = _run(main.get_related_pubmed(req))
        self.assertEqual(resp.error, "Failed to fetch related PubMed articles. Please try again later.")
        self.assertNotIn("user:pass", str(resp.error))


class DefensiveParsingTests(unittest.TestCase):
    def test_search_ids_defensive_against_non_dict_and_none(self):
        async def run_checks():
            client = AsyncMock()
            # Non-dict JSON
            client.get.return_value = MockResponse(json_data="string response")
            self.assertEqual(await main._search_ids(client, "test"), [])

            # None esearchresult
            client.get.return_value = MockResponse(json_data={"esearchresult": None})
            self.assertEqual(await main._search_ids(client, "test"), [])

            # Non-list idlist
            client.get.return_value = MockResponse(json_data={"esearchresult": {"idlist": None}})
            self.assertEqual(await main._search_ids(client, "test"), [])

        _run(run_checks())

    def test_fetch_summaries_defensive_against_non_dict(self):
        async def run_checks():
            client = AsyncMock()
            # Empty IDs
            self.assertEqual(await main._fetch_summaries(client, []), {})

            # Non-dict JSON
            client.get.return_value = MockResponse(json_data=None)
            self.assertEqual(await main._fetch_summaries(client, ["123"]), {})

            # None result key
            client.get.return_value = MockResponse(json_data={"result": None})
            self.assertEqual(await main._fetch_summaries(client, ["123"]), {})

        _run(run_checks())


if __name__ == "__main__":
    unittest.main()
