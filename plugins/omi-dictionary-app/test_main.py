"""Hermetic HTTP contract tests; the dictionary provider is replaced by MockTransport."""

import unittest
from copy import deepcopy
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient
from pydantic import ValidationError

from main import API_BASE, app
from models import ChatToolResponse

# Small synthetic entries follow the provider's documented response shape:
# https://dictionaryapi.dev/ and its entries/en/hello example.
ENTRIES = [
    {
        "word": "example",
        "phonetics": [
            {
                "text": "/example/",
                "audio": "https://example.org/example.mp3",
                "sourceUrl": "https://example.org/audio-source",
                "license": {"name": "CC BY", "url": "https://example.org/audio-license"},
            }
        ],
        "meanings": [
            {
                "partOfSpeech": "noun",
                "synonyms": ["sample"],
                "definitions": [
                    {"definition": "A first sample meaning.", "example": "Here is an example."},
                    {"definition": "A second sample meaning."},
                ],
            }
        ],
        "sourceUrls": ["https://example.org/dictionary"],
        "license": {"name": "CC BY-SA", "url": "https://example.org/text-license"},
    },
    {"word": "example", "meanings": [{"partOfSpeech": "verb", "definitions": [{"definition": "A third meaning."}]}]},
]


class DictionaryToolsTest(unittest.TestCase):
    def setUp(self):
        self.requests = []
        self.response = httpx.Response(200, json=ENTRIES)
        self.failure = None

        def upstream(request):
            self.requests.append(request)
            if self.failure:
                raise self.failure
            return self.response

        client_type = httpx.AsyncClient
        self.patcher = patch(
            "main.httpx.AsyncClient",
            side_effect=lambda **kwargs: client_type(transport=httpx.MockTransport(upstream), **kwargs),
        )
        self.patcher.start()
        self.addCleanup(self.patcher.stop)
        self.client = self.enterContext(TestClient(app))

    def call_tool(self, name="get_word_definition", **body):
        response = self.client.post(f"/tools/{name}", json=body or {"word": "example"})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertNotEqual(data["result"] is None, data["error"] is None)
        return data

    def test_definition_limits_meanings_and_preserves_attribution(self):
        data = self.call_tool(word=" EXAMPLE ", max_definitions=2, uid="private-user")
        self.assertIsNone(data["error"])
        for expected in [
            "first sample",
            "second sample",
            "Here is an example",
            "sample",
            "https://example.org/dictionary",
            "https://example.org/text-license",
        ]:
            self.assertIn(expected, data["result"])
        self.assertNotIn("third meaning", data["result"])
        self.assertEqual(str(self.requests[0].url), API_BASE + "example")
        self.assertEqual(self.requests[0].content, b"")
        self.assertNotIn("private-user", str(self.requests[0].headers))

    def test_pronunciation_keeps_audio_source_and_license(self):
        data = self.call_tool("get_word_pronunciation")
        for expected in [
            "/example/",
            "https://example.org/example.mp3",
            "https://example.org/audio-source",
            "https://example.org/audio-license",
        ]:
            self.assertIn(expected, data["result"])
        self.assertEqual(len(self.requests), 1)  # Audio is linked, never downloaded.

    def test_missing_pronunciation_is_reported_without_inventing_it(self):
        self.response = httpx.Response(200, json=[{"word": "example"}])
        self.assertIn("No phonetic spelling or audio", self.call_tool("get_word_pronunciation")["error"])

    def test_non_http_audio_is_not_returned(self):
        self.response = httpx.Response(200, json=[{"word": "example", "phonetics": [{"audio": "javascript:alert(1)"}]}])
        self.assertNotIn("javascript:", self.call_tool("get_word_pronunciation")["error"])

    def test_urls_with_userinfo_are_not_returned(self):
        for url in [
            "https://:private-password@example.org/audio",
            "https://user@example.org/audio",
            "https://@example.org/audio",
        ]:
            with self.subTest(url=url):
                entries = deepcopy(ENTRIES)
                entries[0]["sourceUrls"] = [url]
                entries[0]["license"]["url"] = url
                phonetic = entries[0]["phonetics"][0]
                phonetic["audio"] = phonetic["sourceUrl"] = phonetic["license"]["url"] = url
                self.response = httpx.Response(200, json=entries)
                for tool in ["get_word_definition", "get_word_pronunciation"]:
                    result = self.call_tool(tool)["result"]
                    self.assertNotIn(url, result)
                    self.assertNotIn("private-password", result)

    def test_response_requires_exactly_one_outcome(self):
        for fields in [{}, {"result": "found", "error": "failed"}]:
            with self.subTest(fields=fields), self.assertRaises(ValidationError):
                ChatToolResponse(**fields)
        self.assertEqual(ChatToolResponse(result="found").result, "found")
        self.assertEqual(ChatToolResponse(error="failed").error, "failed")

    def test_provider_errors_use_the_tool_error_contract(self):
        for status, message in [(404, "No entry found"), (429, "too many requests"), (503, "unavailable")]:
            with self.subTest(status=status):
                self.response = httpx.Response(status, text="private upstream details")
                data = self.call_tool()
                self.assertIn(message, data["error"])
                self.assertNotIn("private upstream details", data["error"])
        self.failure = httpx.ReadTimeout("private transport details")
        error = self.call_tool()["error"]
        self.assertIn("timed out", error)
        self.assertNotIn("private transport details", error)

    def test_malformed_provider_data_does_not_become_a_definition(self):
        for content in [b"not json", b"{}", b"[{}]", b"[]"]:
            with self.subTest(content=content):
                self.response = httpx.Response(200, content=content)
                self.assertIsNotNone(self.call_tool()["error"])

    def test_invalid_input_does_not_contact_provider(self):
        for body in [
            {"word": " "},
            {"word": "../admin"},
            {"word": "a" * 81},
            {"word": "example", "max_definitions": 6},
            {"uid": "private-user"},
        ]:
            with self.subTest(body=body):
                data = self.call_tool(**body)
                self.assertIsNotNone(data["error"])
                self.assertNotIn("private-user", data["error"])
        self.assertEqual(self.requests, [])

    def test_manifest_routes_and_schema_match_the_requests(self):
        manifest = self.client.get("/.well-known/omi-tools.json").json()
        self.assertEqual(manifest["schema_version"], "1.0")
        self.assertEqual(len(manifest["tools"]), 2)
        for tool in manifest["tools"]:
            self.assertEqual(tool["method"], "POST")
            self.assertEqual(tool["parameters"]["required"], ["word"])
            response = self.client.post(tool["endpoint"], json={"word": "example"})
            self.assertIsNotNone(response.json()["result"])
        self.assertEqual(self.client.get("/health").json()["status"], "ok")
        self.assertIn("Omi English Dictionary", self.client.get("/").text)


if __name__ == "__main__":
    unittest.main()
