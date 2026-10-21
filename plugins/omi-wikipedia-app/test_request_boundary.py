"""Hermetic request-boundary tests for the Wikipedia app.

Covers the three ways caller-supplied values reached the outbound request
unvalidated: a language code interpolated into the hostname, an article title
interpolated into the REST path, and non-string tool arguments that raised
AttributeError instead of returning a tool error.
"""

import asyncio
import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlsplit


class Framework:
    def __init__(self, *args, **kwargs):
        pass

    def get(self, *args, **kwargs):
        return lambda function: function

    post = get


class Model:
    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)


class HTTPError(Exception):
    pass


class HTTPStatusError(HTTPError):
    def __init__(self, message="", response=None):
        super().__init__(message)
        self.response = response


def module(name, **attributes):
    value = types.ModuleType(name)
    value.__dict__.update(attributes)
    return value


fastapi_responses = module("fastapi.responses", HTMLResponse=lambda *a, **k: None)
stubs = {
    "fastapi": module("fastapi", FastAPI=Framework, responses=fastapi_responses),
    "fastapi.responses": fastapi_responses,
    "httpx": module(
        "httpx",
        AsyncClient=object,
        HTTPError=HTTPError,
        HTTPStatusError=HTTPStatusError,
    ),
    "pydantic": module("pydantic", BaseModel=Model),
}
spec = importlib.util.spec_from_file_location(
    "wikipedia_under_test", Path(__file__).with_name("main.py")
)
wikipedia = importlib.util.module_from_spec(spec)
with patch.dict(sys.modules, stubs):
    spec.loader.exec_module(wikipedia)


SUMMARY_PREFIX = "/api/rest_v1/page/summary/"


def run(coroutine):
    return asyncio.run(coroutine)


class LanguageValidationTests(unittest.TestCase):
    """The language code becomes a hostname label, so it must stay ASCII."""

    def test_accepts_real_wikipedia_subdomains(self):
        for code in ("en", "es", "simple", "zh-min-nan", "be-tarask", "roa-tara"):
            with self.subTest(code=code):
                self.assertEqual(wikipedia._safe_language(code), code)

    def test_uppercase_is_normalized(self):
        self.assertEqual(wikipedia._safe_language("EN"), "en")

    def test_sharp_s_does_not_idna_map_to_another_wiki(self):
        # "ß".encode("idna") is b"ss": the previous isalpha() check sent
        # the request to ss.wikipedia.org instead of the default wiki.
        self.assertEqual(wikipedia._safe_language("ß"), "en")

    def test_cyrillic_lookalike_does_not_become_a_punycode_host(self):
        # "мо".wikipedia.org IDNA-encodes to xn--l1ae.wikipedia.org.
        self.assertEqual(wikipedia._safe_language("мо"), "en")

    def test_fullwidth_letters_are_rejected(self):
        self.assertEqual(wikipedia._safe_language("ｅｎ"), "en")

    def test_letters_that_casefold_into_ascii_are_rejected(self):
        # str.lower() maps U+212A KELVIN SIGN to "k", so a non-ASCII value
        # could otherwise reach the pattern as an ASCII-looking code.
        for code in ("eK", "KK", "Ko"):
            with self.subTest(code=code):
                self.assertEqual(wikipedia._safe_language(code), "en")

    def test_hyphen_edges_and_empty_segments_are_rejected(self):
        for code in ("-en", "en-", "en--us", "-", "--"):
            with self.subTest(code=code):
                self.assertEqual(wikipedia._safe_language(code), "en")

    def test_overlong_code_is_rejected(self):
        self.assertEqual(wikipedia._safe_language("a" * 13), "en")

    def test_non_string_values_fall_back_instead_of_raising(self):
        for value in (123, 1.5, True, ["en"], {"lang": "en"}, None, b"en"):
            with self.subTest(value=value):
                self.assertEqual(wikipedia._safe_language(value), "en")


class TitleEncodingTests(unittest.TestCase):
    """The title becomes one REST path segment and must not escape it."""

    def test_spaces_become_underscores(self):
        self.assertEqual(wikipedia._encode_title("Ada Lovelace"), "Ada_Lovelace")

    def test_path_separators_are_percent_encoded(self):
        self.assertEqual(
            wikipedia._encode_title("Wikipedia:Village pump/Technical"),
            "Wikipedia%3AVillage_pump%2FTechnical",
        )

    def test_traversal_cannot_leave_the_summary_segment(self):
        encoded = wikipedia._encode_title("../../../../w/api.php")
        self.assertNotIn("/", encoded)
        self.assertEqual(encoded, "..%2F..%2F..%2F..%2Fw%2Fapi.php")

    def test_query_and_fragment_characters_are_encoded(self):
        encoded = wikipedia._encode_title("A?b#c&d")
        for character in "?#&":
            self.assertNotIn(character, encoded)


class RequestBoundaryTests(unittest.TestCase):
    """Drive the real endpoints with a recording transport."""

    def _capture(self, coroutine_factory, response):
        seen = {}

        async def fake_request_json(url, params=None):
            seen["url"] = url
            seen["params"] = params
            return response

        with patch.object(wikipedia, "_request_json", fake_request_json):
            result = run(coroutine_factory())
        return seen, result

    def test_summary_request_stays_inside_the_summary_path(self):
        seen, result = self._capture(
            lambda: wikipedia.get_article_summary(
                {"title": "../../../../w/api.php", "language": "en"}
            ),
            {"title": "X", "extract": "Y"},
        )
        path = urlsplit(seen["url"]).path
        self.assertTrue(path.startswith(SUMMARY_PREFIX), path)
        self.assertNotIn("/../", path)
        self.assertEqual(path[len(SUMMARY_PREFIX):].count("/"), 0)
        self.assertIsNone(result.error)

    def test_summary_host_falls_back_for_a_rejected_language(self):
        seen, _ = self._capture(
            lambda: wikipedia.get_article_summary(
                {"title": "Ada Lovelace", "language": "мо"}
            ),
            {"title": "X", "extract": "Y"},
        )
        self.assertEqual(urlsplit(seen["url"]).hostname, "en.wikipedia.org")

    def test_search_host_falls_back_for_a_rejected_language(self):
        seen, _ = self._capture(
            lambda: wikipedia.search_articles({"query": "ada", "language": "ß"}),
            {"query": {"search": []}},
        )
        self.assertEqual(urlsplit(seen["url"]).hostname, "en.wikipedia.org")


class NonStringArgumentTests(unittest.TestCase):
    """Flat tool envelopes can carry any JSON type; none may raise."""

    def test_numeric_query_returns_a_tool_error(self):
        result = run(wikipedia.search_articles({"query": 2026}))
        self.assertEqual(result.error, "Missing required field: query")

    def test_structured_query_returns_a_tool_error(self):
        for value in ([1, 2], {"q": "x"}, None, True):
            with self.subTest(value=value):
                result = run(wikipedia.search_articles({"query": value}))
                self.assertEqual(result.error, "Missing required field: query")

    def test_numeric_title_returns_a_tool_error(self):
        result = run(wikipedia.get_article_summary({"title": 42}))
        self.assertEqual(result.error, "Missing required field: title")

    def test_overlong_title_is_rejected_before_the_request(self):
        result = run(wikipedia.get_article_summary({"title": "A" * 256}))
        self.assertEqual(result.error, "Article title is too long.")

    def test_limit_ignores_booleans_and_junk(self):
        for value in (True, False, "abc", None, [], {}):
            with self.subTest(value=value):
                self.assertEqual(wikipedia._safe_limit(value), 5)

    def test_limit_is_clamped(self):
        self.assertEqual(wikipedia._safe_limit(0), 1)
        self.assertEqual(wikipedia._safe_limit(99), wikipedia.MAX_LIMIT)
        self.assertEqual(wikipedia._safe_limit("3"), 3)


if __name__ == "__main__":
    unittest.main()
