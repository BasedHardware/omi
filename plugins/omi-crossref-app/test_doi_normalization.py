"""Hermetic DOI normalization and Crossref request-boundary tests (#14523)."""

import asyncio
import importlib.util
import sys
import types
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch


class Framework:
    def __init__(self, *args, **kwargs):
        pass

    def get(self, *args, **kwargs):
        return lambda function: function

    post = get


class Response:
    def __init__(self, result=None, error=None, **kwargs):
        self.result = result
        self.error = error


def module(name, **attributes):
    value = types.ModuleType(name)
    value.__dict__.update(attributes)
    return value


stubs = {
    "fastapi": module("fastapi", FastAPI=Framework),
    "httpx": module("httpx", AsyncClient=object),
    "models": module(
        "models",
        AuthorWorksInput=Framework,
        ChatToolResponse=Response,
        GetWorkInput=Framework,
        SearchWorksInput=Framework,
    ),
}
spec = importlib.util.spec_from_file_location(
    "crossref_under_test", Path(__file__).with_name("main.py")
)
crossref = importlib.util.module_from_spec(spec)
with patch.dict(sys.modules, stubs):
    spec.loader.exec_module(crossref)


class NormalizeDoiTests(unittest.TestCase):
    def test_accepts_bare_doi(self):
        self.assertEqual(crossref.normalize_doi("10.5555/ABC.def"), "10.5555/ABC.def")

    def test_accepts_doi_prefix(self):
        self.assertEqual(crossref.normalize_doi(" doi:10.5555/ABC "), "10.5555/ABC")

    def test_accepts_doi_org_resolver(self):
        self.assertEqual(
            crossref.normalize_doi("https://doi.org/10.5555/ABC"), "10.5555/ABC"
        )

    def test_accepts_dx_doi_org_case_insensitively(self):
        self.assertEqual(
            crossref.normalize_doi("HTTPS://DX.DOI.ORG/10.5555/ABC"), "10.5555/ABC"
        )

    def test_strips_query_and_fragment(self):
        self.assertEqual(
            crossref.normalize_doi("https://doi.org/10.5555/ABC?utm=one#section"),
            "10.5555/ABC",
        )

    def test_decodes_resolver_path_once(self):
        self.assertEqual(
            crossref.normalize_doi("https://doi.org/10.5555/a%2Fb%23c"),
            "10.5555/a/b#c",
        )

    def test_does_not_decode_twice(self):
        self.assertIsNone(crossref.normalize_doi("https://doi.org/10.5555/a%252Fb"))

    def test_rejects_unrelated_host(self):
        self.assertIsNone(crossref.normalize_doi("https://example.com/10.5555/ABC"))

    def test_rejects_resolver_credentials(self):
        self.assertIsNone(crossref.normalize_doi("https://user:pass@doi.org/10.5555/ABC"))

    def test_rejects_wrong_scheme(self):
        self.assertIsNone(crossref.normalize_doi("ftp://doi.org/10.5555/ABC"))

    def test_rejects_missing_suffix(self):
        self.assertIsNone(crossref.normalize_doi("10.5555/"))

    def test_rejects_malformed_prefix(self):
        self.assertIsNone(crossref.normalize_doi("11.5555/ABC"))

    def test_rejects_whitespace_in_doi(self):
        self.assertIsNone(crossref.normalize_doi("10.5555/ABC DEF"))

    def test_rejects_repeated_dot(self):
        self.assertIsNone(crossref.normalize_doi("10.5555/ABC..DEF"))


class HttpBoundaryTests(unittest.TestCase):
    def invoke(self, value):
        request = AsyncMock(return_value={"message": {"DOI": "10.5555/ABC"}})
        with patch.object(crossref, "crossref_get", new=request):
            result = asyncio.run(
                crossref.get_crossref_work(SimpleNamespace(doi=value))
            )
        return result, request

    def test_bare_doi_is_quoted_as_one_path_segment(self):
        result, request = self.invoke("10.5555/a/b")
        self.assertIsNone(result.error)
        request.assert_awaited_once_with("/works/10.5555%2Fa%2Fb", {})

    def test_resolver_url_is_normalized_before_request(self):
        result, request = self.invoke("https://doi.org/10.5555/a%2Fb%23c?x=1#top")
        self.assertIsNone(result.error)
        request.assert_awaited_once_with("/works/10.5555%2Fa%2Fb%23c", {})

    def test_invalid_host_does_not_call_crossref(self):
        result, request = self.invoke("https://example.com/10.5555/ABC")
        self.assertEqual(result.error, "Invalid DOI format. Example: 10.1038/nphys1170")
        request.assert_not_awaited()

    def test_invalid_doi_does_not_call_crossref(self):
        result, request = self.invoke("not-a-doi")
        self.assertEqual(result.error, "Invalid DOI format. Example: 10.1038/nphys1170")
        request.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
