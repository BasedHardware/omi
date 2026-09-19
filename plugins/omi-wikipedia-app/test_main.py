"""Hermetic regression tests for plugins/omi-wikipedia-app.

Covers the malformed-payload hardening: every outbound request carries an
explicit timeout, non-dict API payloads return clean chat-tool errors instead
of raising AttributeError/TypeError, and missing/None nested fields degrade
gracefully. Well-formed responses must still render exactly as before.

All third-party calls are patched at the ``main._request_json`` seam, so the
suite performs no network I/O.

Run with pytest:
    python -m pytest plugins/omi-wikipedia-app/test_main.py -q
or directly:
    python plugins/omi-wikipedia-app/test_main.py
"""

import asyncio
from pathlib import Path
import sys
import unittest
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

import httpx  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import main  # noqa: E402
from main import (  # noqa: E402
    DEFAULT_LANGUAGE,
    REQUEST_TIMEOUT_SECONDS,
    USER_AGENT,
    _clean_snippet,
    _format_summary,
    app,
)


class _FakeResponse:
    """Minimal httpx.Response stand-in for _request_json seam tests."""

    def __init__(self, payload=None, json_exc=None, status_code=200):
        self._payload = payload
        self._json_exc = json_exc
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("boom", request=None, response=self)

    def json(self):
        if self._json_exc is not None:
            raise self._json_exc
        return self._payload


class _FakeAsyncClient:
    """Records constructor/get kwargs so the explicit timeout is observable."""

    last_init_kwargs: dict = {}
    last_get_kwargs: dict = {}
    response: _FakeResponse = _FakeResponse(payload={})

    def __init__(self, **kwargs):
        type(self).last_init_kwargs = kwargs

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def get(self, url, **kwargs):
        type(self).last_get_kwargs = kwargs
        return type(self).response


class RequestJsonTimeoutTests(unittest.TestCase):
    def setUp(self):
        self.client_patch = patch("main.httpx.AsyncClient", _FakeAsyncClient)
        self.client_patch.start()
        self.addCleanup(self.client_patch.stop)

    def test_module_timeout_constant_is_set(self):
        self.assertEqual(REQUEST_TIMEOUT_SECONDS, 10)

    def test_client_and_call_both_carry_explicit_timeout(self):
        _FakeAsyncClient.response = _FakeResponse(payload={"ok": True})
        result = _run(main._request_json("https://en.wikipedia.org/w/api.php", {"action": "query"}))

        self.assertEqual(result, {"ok": True})
        self.assertEqual(_FakeAsyncClient.last_init_kwargs.get("timeout"), REQUEST_TIMEOUT_SECONDS)
        self.assertEqual(_FakeAsyncClient.last_get_kwargs.get("timeout"), REQUEST_TIMEOUT_SECONDS)
        self.assertEqual(_FakeAsyncClient.last_init_kwargs.get("headers", {}).get("User-Agent"), USER_AGENT)

    def test_invalid_json_raises_httpx_http_error(self):
        _FakeAsyncClient.response = _FakeResponse(json_exc=ValueError("not json"))
        with self.assertRaises(httpx.HTTPError):
            _run(main._request_json("https://en.wikipedia.org/w/api.php"))

    def test_non_dict_payload_is_returned_untouched(self):
        _FakeAsyncClient.response = _FakeResponse(payload=["not", "a", "dict"])
        self.assertEqual(_run(main._request_json("https://en.wikipedia.org/w/api.php")), ["not", "a", "dict"])


class SearchArticlesMalformedPayloadTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def _post(self, body):
        return self.client.post("/tools/search_articles", json=body)

    def test_missing_query_still_errors(self):
        resp = self._post({})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["error"], "Missing required field: query")

    def test_non_string_query_errors_cleanly(self):
        resp = self._post({"query": ["python"]})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["error"], "Missing required field: query")

    def test_non_dict_top_level_payload_errors_cleanly(self):
        with patch("main._request_json", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = ["unexpected"]
            resp = self._post({"query": "python"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["result"], None)
        self.assertIn("unexpected response", resp.json()["error"])

    def test_non_dict_query_section_errors_cleanly(self):
        with patch("main._request_json", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = {"query": "not-a-dict"}
            resp = self._post({"query": "python"})
        self.assertIsNone(resp.json()["result"])
        self.assertIn("unexpected response", resp.json()["error"])

    def test_search_field_of_wrong_type_errors_cleanly(self):
        with patch("main._request_json", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = {"query": {"search": "python, but a string"}}
            resp = self._post({"query": "python"})
        self.assertIsNone(resp.json()["result"])
        self.assertIn("unexpected response", resp.json()["error"])

    def test_null_search_field_reads_as_no_results(self):
        with patch("main._request_json", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = {"query": {"search": None}}
            resp = self._post({"query": "python"})
        self.assertEqual(resp.json()["error"], None)
        self.assertIn("No Wikipedia articles found", resp.json()["result"])

    def test_non_dict_entries_are_skipped_not_crashed(self):
        with patch("main._request_json", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = {
                "query": {
                    "search": [
                        "a bare string",
                        None,
                        42,
                        {"title": "Valid", "snippet": "<b>ok</b>"},
                    ]
                }
            }
            resp = self._post({"query": "python"})
        data = resp.json()
        self.assertIsNone(data["error"])
        self.assertIn("1. Valid", data["result"])
        self.assertNotIn("a bare string", data["result"])

    def test_entries_with_missing_or_null_title_use_untitled(self):
        with patch("main._request_json", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = {
                "query": {"search": [{"snippet": "no title"}, {"title": None}, {"title": 7, "snippet": "n"}]}
            }
            resp = self._post({"query": "python"})
        result = resp.json()["result"]
        self.assertIsNone(resp.json()["error"])
        self.assertEqual([line for line in result.splitlines() if line.startswith(("1. ", "2. ", "3. "))],
                         ["1. Untitled", "2. Untitled", "3. Untitled"])

    def test_null_and_non_string_snippet_is_tolerated(self):
        with patch("main._request_json", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = {
                "query": {"search": [{"title": "A", "snippet": None}, {"title": "B", "snippet": ["x"]}]}
            }
            resp = self._post({"query": "python"})
        data = resp.json()
        self.assertIsNone(data["error"])
        self.assertIn("1. A", data["result"])
        self.assertIn("2. B", data["result"])

    def test_well_formed_search_output_is_unchanged(self):
        with patch("main._request_json", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = {
                "query": {
                    "search": [
                        {"title": "Python", "snippet": "<span class=\"searchmatch\">Python</span> is &amp; lang"}
                    ]
                }
            }
            resp = self._post({"query": "python", "language": "en", "limit": 3})
        data = resp.json()
        self.assertIsNone(data["error"])
        self.assertEqual(
            data["result"],
            "Wikipedia search results for 'python':\n\n1. Python\n   Python is & lang\n   https://en.wikipedia.org/wiki/Python",
        )

    def test_well_formed_empty_search_is_unchanged(self):
        with patch("main._request_json", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = {"query": {"search": []}}
            resp = self._post({"query": "python"})
        self.assertEqual(resp.json()["error"], None)
        self.assertEqual(resp.json()["result"], "No Wikipedia articles found for 'python'.")

    def test_invalid_json_from_upstream_returns_clean_error(self):
        with patch("main.httpx.AsyncClient", _FakeAsyncClient):
            _FakeAsyncClient.response = _FakeResponse(json_exc=ValueError("bad json"))
            resp = self._post({"query": "python"})
        data = resp.json()
        self.assertIsNone(data["result"])
        self.assertIn("invalid JSON response", data["error"])


class GetArticleSummaryMalformedPayloadTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def _post(self, body):
        return self.client.post("/tools/get_article_summary", json=body)

    def test_missing_title_still_errors(self):
        resp = self._post({})
        self.assertEqual(resp.json()["error"], "Missing required field: title")

    def test_non_string_title_errors_cleanly(self):
        resp = self._post({"title": {"nested": "value"}})
        self.assertEqual(resp.json()["error"], "Missing required field: title")

    def test_non_dict_payload_errors_cleanly(self):
        with patch("main._request_json", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = ["not", "a", "dict"]
            resp = self._post({"title": "Python"})
        data = resp.json()
        self.assertIsNone(data["result"])
        self.assertIn("No Wikipedia article found", data["error"])

    def test_content_urls_missing_falls_back_to_article_url(self):
        with patch("main._request_json", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = {"title": "Python", "extract": "A language."}
            resp = self._post({"title": "Python", "language": "en"})
        data = resp.json()
        self.assertIsNone(data["error"])
        self.assertIn("https://en.wikipedia.org/wiki/Python", data["result"])

    def test_content_urls_wrong_types_fall_back(self):
        variants = [
            {"content_urls": "https://example.com"},
            {"content_urls": {"desktop": "https://example.com"}},
            {"content_urls": {"desktop": {"page": None}}},
            {"content_urls": {"desktop": {"page": ["list"]}}},
        ]
        for payload in variants:
            with self.subTest(payload=payload):
                with patch("main._request_json", new_callable=AsyncMock) as mock_req:
                    mock_req.return_value = {"title": "Python", "extract": "x", **payload}
                    resp = self._post({"title": "Python", "language": "en"})
                data = resp.json()
                self.assertIsNone(data["error"])
                self.assertIn("https://en.wikipedia.org/wiki/Python", data["result"])

    def test_missing_and_null_fields_use_defaults(self):
        with patch("main._request_json", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = {"title": None, "extract": None, "description": None}
            resp = self._post({"title": "Python"})
        data = resp.json()
        self.assertIsNone(data["error"])
        self.assertIn("Untitled", data["result"])
        self.assertIn("No summary was returned for this article.", data["result"])

    def test_non_string_description_is_ignored(self):
        with patch("main._request_json", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = {"title": "Python", "extract": "x", "description": ["nope"]}
            resp = self._post({"title": "Python"})
        data = resp.json()
        self.assertIsNone(data["error"])
        self.assertNotIn("nope", data["result"])

    def test_non_string_title_in_payload_is_not_stringified(self):
        with patch("main._request_json", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = {"title": 42, "extract": "x"}
            resp = self._post({"title": "Python"})
        data = resp.json()
        self.assertIsNone(data["error"])
        self.assertIn("Untitled", data["result"])

    def test_disambiguation_path_is_unchanged_for_valid_payload(self):
        with patch("main._request_json", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = {"type": "disambiguation", "title": "Mercury", "extract": "Could mean..."}
            resp = self._post({"title": "Mercury"})
        data = resp.json()
        self.assertIsNone(data["error"])
        self.assertIn("This is a disambiguation page.", data["result"])

    def test_well_formed_summary_output_is_unchanged(self):
        with patch("main._request_json", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = {
                "title": "Python",
                "description": "Programming language",
                "extract": "Python is a language.",
                "content_urls": {"desktop": {"page": "https://en.wikipedia.org/wiki/Python_(programming)"}},
            }
            resp = self._post({"title": "Python"})
        self.assertEqual(
            resp.json()["result"],
            "Python\nProgramming language\n\nPython is a language.\n\nhttps://en.wikipedia.org/wiki/Python_(programming)",
        )


class GetRandomArticleMalformedPayloadTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def _post(self, body=None):
        return self.client.post("/tools/get_random_article", json=body or {})

    def test_non_dict_top_level_payload_errors_cleanly(self):
        with patch("main._request_json", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = "not a dict"
            resp = self._post()
        data = resp.json()
        self.assertIsNone(data["result"])
        self.assertIn("unexpected response", data["error"])

    def test_non_dict_query_section_errors_cleanly(self):
        with patch("main._request_json", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = {"query": 5}
            resp = self._post()
        data = resp.json()
        self.assertIsNone(data["result"])
        self.assertIn("unexpected response", data["error"])

    def test_null_query_section_reads_as_no_article(self):
        with patch("main._request_json", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = {"query": None}
            resp = self._post()
        data = resp.json()
        self.assertIsNone(data["error"])
        self.assertEqual(data["result"], "No random Wikipedia article was returned.")

    def test_random_field_of_wrong_type_errors_cleanly(self):
        with patch("main._request_json", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = {"query": {"random": {"title": "Python"}}}
            resp = self._post()
        data = resp.json()
        self.assertIsNone(data["result"])
        self.assertIn("unexpected response", data["error"])

    def test_null_random_field_reads_as_no_article(self):
        with patch("main._request_json", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = {"query": {"random": None}}
            resp = self._post()
        data = resp.json()
        self.assertIsNone(data["error"])
        self.assertEqual(data["result"], "No random Wikipedia article was returned.")

    def test_non_dict_random_entries_read_as_no_article(self):
        with patch("main._request_json", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = {"query": {"random": ["bare", None, 3]}}
            resp = self._post()
        data = resp.json()
        self.assertIsNone(data["error"])
        self.assertEqual(data["result"], "No random Wikipedia article was returned.")

    def test_missing_title_reads_as_without_title(self):
        with patch("main._request_json", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = {"query": {"random": [{"id": 1, "title": None}]}}
            resp = self._post()
        data = resp.json()
        self.assertIsNone(data["error"])
        self.assertEqual(data["result"], "Wikipedia returned a random article without a title.")

    def test_non_dict_summary_payload_errors_cleanly(self):
        with patch("main._request_json", new_callable=AsyncMock) as mock_req:
            mock_req.side_effect = [{"query": {"random": [{"title": "Python"}]}}, ["nope"]]
            resp = self._post()
        data = resp.json()
        self.assertIsNone(data["result"])
        self.assertIn("unexpected response", data["error"])

    def test_well_formed_random_output_is_unchanged(self):
        with patch("main._request_json", new_callable=AsyncMock) as mock_req:
            mock_req.side_effect = [
                {"query": {"random": [{"title": "Python"}]}},
                {"title": "Python", "extract": "A language."},
            ]
            resp = self._post({"language": "en"})
        data = resp.json()
        self.assertIsNone(data["error"])
        self.assertEqual(
            data["result"],
            "Random Wikipedia article:\n\nPython\n\nA language.\n\nhttps://en.wikipedia.org/wiki/Python",
        )


class HelperTests(unittest.TestCase):
    def test_clean_snippet_tolerates_non_strings(self):
        self.assertEqual(_clean_snippet(None), "")
        self.assertEqual(_clean_snippet(123), "")
        self.assertEqual(_clean_snippet(["x"]), "")
        self.assertEqual(_clean_snippet("<b>a</b>  b"), "a b")

    def test_format_summary_tolerates_non_dict(self):
        rendered = _format_summary(["nope"], DEFAULT_LANGUAGE)
        self.assertIn("Untitled", rendered)
        self.assertIn("No summary was returned for this article.", rendered)


def _run(coro):
    return asyncio.run(coro)


if __name__ == "__main__":
    unittest.main()
