"""Hermetic regression tests for plugins/omi-semantic-scholar-app/main.py.

Standard library only: httpx, fastapi, and pydantic are replaced with minimal
stubs before importing the module under test so the suite runs without
site-packages (the manifest lane runs plain python3). The async chat-tool
handlers are invoked through asyncio.run with api_get stubbed to return canned
Graph API payloads, so no network access is required.

Covers BasedHardware/omi#13925: null/non-dict `data` and `papers` payloads,
mixed-type year/citationCount sort keys, null or non-dict `authors` entries,
unnormalized DOI/arXiv identifiers, and transport-level httpx errors that
surfaced as 500s / "Unexpected error" responses instead of clean tool errors.
"""

import asyncio
import os
import sys
import types
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

_STUBBED_MODULES = ("httpx", "fastapi", "pydantic")


def _install_module_stubs():
    httpx = types.ModuleType("httpx")

    class HTTPError(Exception):
        pass

    class HTTPStatusError(HTTPError):
        def __init__(self, message="", *, response=None):
            super().__init__(message)
            self.response = response

    class ConnectError(HTTPError):
        pass

    class TimeoutException(HTTPError):
        pass

    class _AsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def get(self, *args, **kwargs):
            raise AssertionError("tests must stub main.api_get; no network allowed")

    httpx.HTTPError = HTTPError
    httpx.HTTPStatusError = HTTPStatusError
    httpx.ConnectError = ConnectError
    httpx.TimeoutException = TimeoutException
    httpx.AsyncClient = _AsyncClient
    sys.modules["httpx"] = httpx

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

    pydantic = types.ModuleType("pydantic")

    def model_validator(*args, **kwargs):
        def decorator(fn):
            fn.__model_validator__ = True
            return fn

        return decorator

    class BaseModel:
        def __init__(self, **data):
            for key, value in data.items():
                setattr(self, key, value)
            for name in dir(type(self)):
                member = getattr(type(self), name, None)
                if getattr(member, "__model_validator__", False):
                    member(self)

    def Field(*args, **kwargs):
        if "default_factory" in kwargs:
            return kwargs["default_factory"]()
        return kwargs.get("default")

    pydantic.BaseModel = BaseModel
    pydantic.Field = Field
    pydantic.model_validator = model_validator
    sys.modules["pydantic"] = pydantic


_saved_modules = {name: sys.modules.get(name) for name in _STUBBED_MODULES}
_install_module_stubs()
try:
    import main  # noqa: E402
finally:
    for _name, _original in _saved_modules.items():
        if _original is None:
            sys.modules.pop(_name, None)
        else:
            sys.modules[_name] = _original
    del _name, _original, _saved_modules


def _run(coro):
    return asyncio.run(coro)


def _search(payload, **req_kwargs):
    req = main.SearchPapersRequest(query="attention", **req_kwargs)
    with mock.patch.object(main, "api_get", new=mock.AsyncMock(return_value=payload)):
        return _run(main.search_papers(req))


def _get_paper(payload, paper_id_or_doi="abc123"):
    req = main.GetPaperRequest(paper_id_or_doi=paper_id_or_doi)
    with mock.patch.object(main, "api_get", new=mock.AsyncMock(return_value=payload)):
        return _run(main.get_paper(req))


def _author_papers(payload, **req_kwargs):
    req = main.GetAuthorPapersRequest(author_id="42", **req_kwargs)
    with mock.patch.object(main, "api_get", new=mock.AsyncMock(return_value=payload)):
        return _run(main.get_author_papers(req))


def _search_error(exc):
    req = main.SearchPapersRequest(query="attention")
    with mock.patch.object(main, "api_get", new=mock.AsyncMock(side_effect=exc)):
        return _run(main.search_papers(req))


def _get_paper_error(exc):
    req = main.GetPaperRequest(paper_id_or_doi="abc123")
    with mock.patch.object(main, "api_get", new=mock.AsyncMock(side_effect=exc)):
        return _run(main.get_paper(req))


def _status_error(code):
    response = types.SimpleNamespace(status_code=code)
    return main.httpx.HTTPStatusError("boom", response=response)


_PAPER = {
    "title": "Attention Is All You Need",
    "year": 2017,
    "authors": [{"name": "Ashish Vaswani"}, {"name": "Noam Shazeer"}],
    "citationCount": 50000,
    "url": "https://www.semanticscholar.org/paper/x",
    "venue": "NeurIPS",
}


class FormatAuthorsTests(unittest.TestCase):
    def test_normal_author_list(self):
        self.assertEqual(main.format_authors([{"name": "Ada"}, {"name": "Alan"}]), "Ada, Alan")

    def test_null_authors_returns_unknown(self):
        self.assertEqual(main.format_authors(None), "Unknown")

    def test_non_list_authors_returns_unknown(self):
        self.assertEqual(main.format_authors("Ada"), "Unknown")
        self.assertEqual(main.format_authors({"name": "Ada"}), "Unknown")

    def test_non_dict_entries_are_skipped(self):
        self.assertEqual(main.format_authors(["oops", None, {"name": "Ada"}]), "Ada")

    def test_all_entries_invalid_returns_unknown(self):
        self.assertEqual(main.format_authors([{}, "x", None]), "Unknown")


class FormatYearTests(unittest.TestCase):
    def test_int_year(self):
        self.assertEqual(main.format_year(2023), "2023")

    def test_numeric_string_year(self):
        self.assertEqual(main.format_year("2023"), "2023")

    def test_none_year(self):
        self.assertEqual(main.format_year(None), "Unknown")

    def test_garbage_year(self):
        self.assertEqual(main.format_year("n/a"), "Unknown")
        self.assertEqual(main.format_year(True), "Unknown")


class NormalizeIdentifierTests(unittest.TestCase):
    def test_raw_doi_gets_doi_prefix(self):
        self.assertEqual(main.normalize_identifier("10.1038/nature12373"), "DOI:10.1038/nature12373")

    def test_doi_url_https(self):
        self.assertEqual(
            main.normalize_identifier("https://doi.org/10.1038/nature12373"),
            "DOI:10.1038/nature12373",
        )

    def test_doi_url_http_and_trailing_slash(self):
        self.assertEqual(
            main.normalize_identifier("http://doi.org/10.1109/5.771073/"),
            "DOI:10.1109/5.771073",
        )

    def test_doi_prefix_any_case(self):
        self.assertEqual(main.normalize_identifier("doi:10.1/x"), "DOI:10.1/x")
        self.assertEqual(main.normalize_identifier("Doi: 10.1/x"), "DOI:10.1/x")

    def test_arxiv_abs_url(self):
        self.assertEqual(
            main.normalize_identifier("https://arxiv.org/abs/1706.03762"),
            "ARXIV:1706.03762",
        )

    def test_arxiv_pdf_url_strips_pdf_suffix(self):
        self.assertEqual(
            main.normalize_identifier("https://arxiv.org/pdf/1706.03762.pdf"),
            "ARXIV:1706.03762",
        )

    def test_arxiv_prefix_any_case(self):
        self.assertEqual(main.normalize_identifier("arxiv:1706.03762v5"), "ARXIV:1706.03762v5")

    def test_other_namespaces_canonicalized(self):
        self.assertEqual(main.normalize_identifier("pmid:19872477"), "PMID:19872477")
        self.assertEqual(main.normalize_identifier("pmcid:2323296"), "PMCID:2323296")
        self.assertEqual(main.normalize_identifier("corpusid:215416146"), "CorpusId:215416146")

    def test_plain_s2_id_passes_through(self):
        self.assertEqual(
            main.normalize_identifier("649def34f8be52c8b66281af98ae884c09aef38b"),
            "649def34f8be52c8b66281af98ae884c09aef38b",
        )

    def test_surrounding_whitespace_stripped(self):
        self.assertEqual(main.normalize_identifier("  10.1038/nature12373  "), "DOI:10.1038/nature12373")


class PaperSortKeyTests(unittest.TestCase):
    def test_mixed_type_years_and_citations_sort_descending(self):
        papers = [
            {"title": "b", "year": 2021, "citationCount": "9"},
            {"title": "a", "year": "2023", "citationCount": 5},
            {"title": "c", "year": None, "citationCount": None},
        ]
        ordered = sorted(papers, key=main._paper_sort_key, reverse=True)
        self.assertEqual([p["title"] for p in ordered], ["a", "b", "c"])

    def test_non_dict_paper_sorts_last(self):
        self.assertEqual(main._paper_sort_key("nope"), (0, 0))


class SearchPapersHandlerTests(unittest.TestCase):
    def test_happy_path_renders_papers(self):
        resp = _search({"data": [_PAPER]})
        self.assertIsNotNone(resp.result)
        self.assertIn("Attention Is All You Need", resp.result)
        self.assertIn("Ashish Vaswani", resp.result)

    def test_null_data_returns_no_papers_found(self):
        resp = _search({"data": None})
        self.assertEqual(resp.result, "No papers found.")

    def test_missing_data_key_returns_no_papers_found(self):
        resp = _search({"total": 0})
        self.assertEqual(resp.result, "No papers found.")

    def test_non_list_data_returns_no_papers_found(self):
        resp = _search({"data": {"a": 1}})
        self.assertEqual(resp.result, "No papers found.")

    def test_non_dict_payload_returns_no_papers_found(self):
        resp = _search([{"title": "x"}])
        self.assertEqual(resp.result, "No papers found.")

    def test_non_dict_paper_entries_are_skipped(self):
        resp = _search({"data": [None, "oops", _PAPER]})
        self.assertIsNotNone(resp.result)
        self.assertIn("Attention Is All You Need", resp.result)

    def test_null_authors_and_string_year_render_cleanly(self):
        paper = dict(_PAPER, authors=None, year="2023", citationCount=None)
        resp = _search({"data": [paper]})
        self.assertIsNotNone(resp.result)
        self.assertIn("Authors: Unknown", resp.result)
        self.assertIn("Year: 2023", resp.result)
        self.assertIn("Citations: 0", resp.result)

    def test_http_status_error_reports_status_code(self):
        resp = _search_error(_status_error(429))
        self.assertEqual(resp.error, "Semantic Scholar API error: 429")

    def test_transport_error_reports_clean_message(self):
        resp = _search_error(main.httpx.ConnectError("connection refused"))
        self.assertIsNotNone(resp.error)
        self.assertIn("Semantic Scholar request failed", resp.error)


class GetPaperHandlerTests(unittest.TestCase):
    def test_happy_path(self):
        resp = _get_paper(dict(_PAPER, abstract="We propose..."))
        self.assertIsNotNone(resp.result)
        self.assertIn("Title: Attention Is All You Need", resp.result)
        self.assertIn("Year: 2017", resp.result)

    def test_null_authors_and_string_year(self):
        resp = _get_paper(dict(_PAPER, authors=None, year="2023"))
        self.assertIsNotNone(resp.result)
        self.assertIn("Authors: Unknown", resp.result)
        self.assertIn("Year: 2023", resp.result)

    def test_non_dict_payload_returns_not_found(self):
        resp = _get_paper([{"title": "x"}])
        self.assertEqual(resp.error, "Paper not found.")

    def test_404_returns_not_found(self):
        resp = _get_paper_error(_status_error(404))
        self.assertEqual(resp.error, "Paper not found.")

    def test_transport_error_reports_clean_message(self):
        resp = _get_paper_error(main.httpx.TimeoutException("timed out"))
        self.assertIsNotNone(resp.error)
        self.assertIn("Semantic Scholar request failed", resp.error)

    def test_raw_doi_is_normalized_before_request(self):
        req = main.GetPaperRequest(paper_id_or_doi="10.1038/nature12373")
        with mock.patch.object(main, "api_get", new=mock.AsyncMock(return_value=dict(_PAPER))) as api:
            resp = _run(main.get_paper(req))
        self.assertEqual(api.call_args[0][0], "/paper/DOI:10.1038%2Fnature12373")
        self.assertIsNotNone(resp.result)

    def test_arxiv_url_is_normalized_before_request(self):
        req = main.GetPaperRequest(paper_id_or_doi="https://arxiv.org/abs/1706.03762")
        with mock.patch.object(main, "api_get", new=mock.AsyncMock(return_value=dict(_PAPER))) as api:
            resp = _run(main.get_paper(req))
        self.assertEqual(api.call_args[0][0], "/paper/ARXIV:1706.03762")
        self.assertIsNotNone(resp.result)


class GetAuthorPapersHandlerTests(unittest.TestCase):
    def test_happy_path(self):
        resp = _author_papers({"name": "Ada", "papers": [dict(_PAPER)]})
        self.assertIsNotNone(resp.result)
        self.assertIn("Recent papers by Ada:", resp.result)
        self.assertIn("Attention Is All You Need", resp.result)

    def test_mixed_type_years_sort_without_crashing(self):
        papers = [
            {"title": "old", "year": 2019, "citationCount": 3},
            {"title": "new", "year": "2023", "citationCount": "7"},
            {"title": "undated", "year": None, "citationCount": None},
        ]
        resp = _author_papers({"name": "Ada", "papers": papers}, max_results=10)
        self.assertIsNotNone(resp.result)
        self.assertLess(resp.result.index("new"), resp.result.index("old"))
        self.assertLess(resp.result.index("old"), resp.result.index("undated"))

    def test_null_papers_returns_no_papers(self):
        resp = _author_papers({"name": "Ada", "papers": None})
        self.assertEqual(resp.result, "No papers found for author Ada.")

    def test_non_list_papers_returns_no_papers(self):
        resp = _author_papers({"name": "Ada", "papers": {"a": 1}})
        self.assertEqual(resp.result, "No papers found for author Ada.")

    def test_non_dict_payload_falls_back_to_author_id(self):
        resp = _author_papers(["x"])
        self.assertEqual(resp.result, "No papers found for author 42.")

    def test_non_dict_paper_entries_are_skipped(self):
        resp = _author_papers({"name": "Ada", "papers": [None, dict(_PAPER)]})
        self.assertIsNotNone(resp.result)
        self.assertIn("Attention Is All You Need", resp.result)

    def test_max_results_is_respected(self):
        papers = [dict(_PAPER, title=f"P{i}", year=2000 + i) for i in range(8)]
        resp = _author_papers({"name": "Ada", "papers": papers}, max_results=3)
        self.assertIsNotNone(resp.result)
        self.assertIn("P7", resp.result)
        self.assertNotIn("P0", resp.result)

    def test_404_returns_author_not_found(self):
        req = main.GetAuthorPapersRequest(author_id="42")
        with mock.patch.object(main, "api_get", new=mock.AsyncMock(side_effect=_status_error(404))):
            resp = _run(main.get_author_papers(req))
        self.assertEqual(resp.error, "Author not found.")


class ResponseContractTests(unittest.TestCase):
    def test_response_requires_result_or_error(self):
        with self.assertRaises(ValueError):
            main.ChatToolResponse()


if __name__ == "__main__":
    unittest.main()
