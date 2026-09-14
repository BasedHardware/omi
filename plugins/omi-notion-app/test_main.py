"""Hermetic production-handler tests; HTTP, framework and token storage are doubles."""
import asyncio
import importlib.util
import json
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import AsyncMock, Mock, patch

class Framework:
    def __init__(self, *args, **kwargs):
        pass
    def get(self, *args, **kwargs):
        return lambda function: function
    post = get

class Response:
    result = None
    error = None
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)

def module(name, **attributes):
    value = types.ModuleType(name)
    value.__dict__.update(attributes)
    return value

stubs = {
    "requests": module("requests", get=Mock(), post=Mock(), patch=Mock()),
    "dotenv": module("dotenv", load_dotenv=lambda: None),
    "fastapi": module("fastapi", FastAPI=Framework, Request=Framework, Query=Framework, HTTPException=Exception),
    "fastapi.responses": module("fastapi.responses", HTMLResponse=Framework, RedirectResponse=Framework, JSONResponse=Framework),
    "models": module("models", ChatToolResponse=Response),
    "db": module("db", **{name: Mock() for name in (
        "store_notion_tokens", "get_notion_tokens", "update_notion_tokens", "delete_notion_tokens",
        "store_oauth_state", "get_oauth_state", "delete_oauth_state", "store_user_setting", "get_user_setting",
    )}),
}
spec = importlib.util.spec_from_file_location("notion_under_test", Path(__file__).with_name("main.py"))
notion = importlib.util.module_from_spec(spec)
with patch.dict(sys.modules, stubs):
    spec.loader.exec_module(notion)

class PageReadTests(unittest.TestCase):
    def read(self, content_response, archived=False):
        metadata = Mock(status_code=200)
        metadata.json.return_value = {
            "properties": {"title": {"type": "title", "title": [{"plain_text": "Known title"}]}},
            "id": "test-page", "archived": archived,
            "url": "https://www.notion.so/test-page",
            "created_time": "2026-09-01T00:00:00.000Z",
            "last_edited_time": "2026-09-08T00:00:00.000Z",
        }
        request = Mock(json=AsyncMock(return_value={"uid": "test-user", "page_id": "test-page"}))
        with patch.object(notion, "get_valid_access_token", return_value="test-placeholder"), patch.object(notion, "log"), patch.object(notion.requests, "get", side_effect=[metadata, content_response]) as get:
            result = asyncio.run(notion.tool_get_page(request))
        self.assertEqual(get.call_count, 2)
        self.assertTrue(get.call_args.args[0].endswith("/blocks/test-page/children"))
        return result

    def test_failed_content_is_not_an_empty_success(self):
        for status in (403, 429, 500):
            for body in ("", "private upstream response"):
                with self.subTest(status=status, body=body):
                    result = self.read(Mock(status_code=status, text=body))
                    self.assertIsNone(result.result)
                    self.assertTrue(result.error.startswith(f"Failed to retrieve page content (HTTP {status}). Please try again."))
                    self.assertNotIn("private upstream response", result.error)

    def test_transport_failure_is_not_success(self):
        result = self.read(RuntimeError("private transport detail"))
        self.assertIsNone(result.result)
        self.assertTrue(result.error.startswith("Failed to retrieve page content. Please try again."))

    def test_content_errors_retain_known_metadata_without_success(self):
        # Separate metadata/content endpoints: errors must not erase a successful
        # metadata read, or claim that unavailable content is an empty page.
        for archived in (False, True):
            for status in (404, 403, 429, 500, None):
                with self.subTest(archived=archived, status=status):
                    response = (Mock(status_code=status, text="private upstream response")
                                if status else RuntimeError("private transport detail"))
                    result = self.read(response, archived=archived)
                    self.assertIsNone(result.result)
                    self.assertIn("Failed to retrieve page content", result.error)
                    if status:
                        self.assertIn(f"HTTP {status}", result.error)
                    self.assertIn("**Known title**", result.error)
                    self.assertIn("**Status:** Archived" if archived else "**Status:** Active", result.error)
                    self.assertIn("**URL:** https://www.notion.so/test-page", result.error)
                    self.assertIn("**Created:** 2026-09-01", result.error)
                    self.assertIn("**Last Edited:** 2026-09-08", result.error)
                    self.assertIn("**Page ID:** `test-page`", result.error)
                    self.assertNotIn("**Content:**", result.error)
                    self.assertNotIn("private", result.error)

    def test_successful_empty_and_nonempty_content(self):
        for text in ("", "Useful page content"):
            with self.subTest(text=text):
                response = Mock(status_code=200)
                response.json.return_value = {"results": [] if not text else [{"type": "paragraph", "paragraph": {"rich_text": [{"plain_text": text}]}}]}
                result = self.read(response)
                self.assertIsNone(result.error)
                self.assertIn("**Known title**", result.result)
                self.assertEqual("**Content:**" in result.result, bool(text))
                if text:
                    self.assertIn(text, result.result)

class PageWriteTests(unittest.TestCase):
    def write(self, content, create=False, fail_at=None, failure=None, **metadata):
        calls = []

        def send(method, url, **kwargs):
            # Accept the original json= seam as well as explicitly encoded data.
            wire = kwargs.get("data")
            if wire is None:
                wire = json.dumps(kwargs["json"], allow_nan=False).encode("utf-8")
            calls.append((method, url, wire, json.loads(wire)))
            if len(calls) == fail_at:
                if isinstance(failure, Exception):
                    raise failure
                return failure
            response = Mock(status_code=200)
            # The append endpoint returns newly created first-level blocks,
            # including object/id even without read-content capabilities.
            response.json.return_value = {"id": "created-page", "url": "https://www.notion.so/created-page"} if method == "POST" else {
                "object": "list", "type": "block", "block": {},
                "has_more": False, "next_cursor": None,
                "results": [{"object": "block", "id": f"00000000-0000-4000-8000-{len(calls) * 100 + index:012d}"}
                            for index in range(len(calls[-1][3]["children"]))],
            }
            return response

        body = {"uid": "test-user", "content": content}
        body.update({"title": "Test title", "parent_page_id": "parent-page"} if create else {"page_id": "existing-page"})
        body.update(metadata)
        request = Mock(json=AsyncMock(return_value=body))
        with patch.object(notion, "get_valid_access_token", return_value="test-placeholder"), patch.object(notion, "log") as log, patch.object(notion.requests, "post", side_effect=lambda *args, **kwargs: send("POST", *args, **kwargs)), patch.object(notion.requests, "patch", side_effect=lambda *args, **kwargs: send("PATCH", *args, **kwargs)):
            result = asyncio.run((notion.tool_create_page if create else notion.tool_append_content)(request))
        self.write_logs = log.call_args_list
        return result, calls

    def assert_valid_requests(self, calls):
        def check(value):
            if isinstance(value, list):
                self.assertLessEqual(len(value), 100)
                for item in value:
                    check(item)
            elif isinstance(value, dict):
                if "text" in value:
                    text = value["text"]["content"]
                    self.assertLessEqual(len(text), 2000)
                    self.assertLessEqual(len(text.encode("utf-16-le")) // 2, 2000)
                for item in value.values():
                    check(item)

        for method, url, wire, payload in calls:
            self.assertLessEqual(len(wire), 500000)
            self.assertEqual(json.loads(wire), payload)
            check(payload)

    def saved_paragraphs(self, calls):
        return ["".join(item["text"]["content"] for item in block["paragraph"]["rich_text"])
                for _, _, _, payload in calls for block in payload.get("children", [])]

    def test_small_inputs_keep_paragraphs_spacing_and_response(self):
        for create in (False, True):
            with self.subTest(create=create):
                result, calls = self.write(" first \n\n \t \nsecond", create=create)
                self.assertIsNone(result.error)
                self.assertEqual(len(calls), 1)
                self.assertEqual(self.saved_paragraphs(calls), [" first ", "second"])
                self.assert_valid_requests(calls)
                self.assertIn("**Page Created!**" if create else "Added 2 paragraph(s)", result.result)

    def test_text_item_boundaries_keep_one_paragraph(self):
        for create in (False, True):
            for length in (1999, 2000, 2001):
                with self.subTest(create=create, length=length):
                    content = "x" * length
                    result, calls = self.write(content, create=create)
                    self.assertIsNone(result.error)
                    self.assert_valid_requests(calls)
                    self.assertEqual(self.saved_paragraphs(calls), [content])

    def test_unicode_chunk_boundaries_preserve_whole_characters(self):
        for create in (False, True):
            for content in ("a" * 1999 + "😀" + "tail", "😀" * 2000):
                with self.subTest(create=create, length=len(content)):
                    result, calls = self.write(content, create=create)
                    self.assertIsNone(result.error)
                    self.assert_valid_requests(calls)
                    self.assertEqual(self.saved_paragraphs(calls), [content])

    def test_child_boundaries_and_batches_are_ordered(self):
        for create in (False, True):
            for count in (99, 100, 101, 201):
                with self.subTest(create=create, count=count):
                    paragraphs = [f"Paragraph {index}" for index in range(count)]
                    result, calls = self.write("\n".join(paragraphs), create=create)
                    self.assertIsNone(result.error)
                    self.assertEqual(len(calls), (count + 99) // 100)
                    self.assertEqual(self.saved_paragraphs(calls), paragraphs)
                    self.assert_valid_requests(calls)
                    expected_page = "created-page" if create else "existing-page"
                    for method, url, _, _ in calls[1:] if create else calls:
                        self.assertEqual(method, "PATCH")
                        self.assertTrue(url.endswith(f"/blocks/{expected_page}/children"))

    def test_oversized_single_paragraph_preserves_all_characters(self):
        # Exceed both 100 rich-text elements and one serialized request budget.
        for create in (False, True):
            for character in ("a", "😀"):
                with self.subTest(create=create, character=character):
                    content = character * 200001
                    result, calls = self.write(content, create=create)
                    self.assertIsNone(result.error)
                    self.assert_valid_requests(calls)
                    self.assertEqual("".join(self.saved_paragraphs(calls)), content)
                    self.assertGreater(len(self.saved_paragraphs(calls)), 1)

    def test_serialized_byte_budget_includes_escaping_and_create_metadata(self):
        for create in (False, True):
            for character in ("界", "😀", '"', "\\"):
                with self.subTest(create=create, character=character):
                    paragraphs = [character * 2000 + str(index) for index in range(100)]
                    # A substantial title exercises the full first-request budget.
                    metadata = {"title": "😀" * 2000, "database_id": "test-database"} if create else {}
                    result, calls = self.write("\n".join(paragraphs), create=create, **metadata)
                    self.assertIsNone(result.error)
                    self.assert_valid_requests(calls)
                    self.assertEqual(self.saved_paragraphs(calls), paragraphs)
                    if character in ("界", "😀"):
                        self.assertGreater(len(calls), 1)

    def test_create_metadata_can_require_an_empty_first_batch(self):
        content = "😀" * 40000
        result, calls = self.write(content, create=True, title="😀" * 2000)
        self.assertIsNone(result.error)
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0][3]["children"], [])
        self.assertEqual(self.saved_paragraphs(calls), [content])
        self.assert_valid_requests(calls)

    def test_empty_content_and_whitespace_only_input_keep_existing_behavior(self):
        for content in (None, "", " \n\t"):
            result, calls = self.write(content, create=True)
            self.assertIsNone(result.error)
            self.assertEqual(len(calls), 1)
            self.assertEqual("children" in calls[0][3], bool(content))
            self.assertEqual(self.saved_paragraphs(calls), [])
        result, calls = self.write(" \n\t")
        self.assertIsNone(result.error)
        self.assertEqual(calls[0][3], {"children": []})
        self.assertIn("Added 0 paragraph(s)", result.result)

    def test_later_batch_failure_reports_confirmed_progress_and_stops(self):
        failures = [Mock(status_code=429, text="private upstream response"), RuntimeError("private transport detail")]
        for payload in (None, {}, {"error": ""}):
            response = Mock(status_code=200)
            response.json.return_value = payload
            failures.append(response)
        for create in (False, True):
            for failure in failures:
                with self.subTest(create=create, failure=type(failure).__name__):
                    result, calls = self.write("\n".join(f"p{index}" for index in range(301)), create=create, fail_at=3, failure=failure)
                    self.assertEqual(len(calls), 3)
                    self.assertIsNone(result.result)
                    self.assertIn("200 of 301", result.error)
                    self.assertIn("created-page" if create else "existing-page", result.error)
                    self.assertIn("not confirmed", result.error)
                    self.assertIn("duplicate", result.error)
                    self.assertNotIn("private", result.error)
                    self.assert_valid_requests(calls)

    def test_failed_create_is_not_replayed(self):
        for failure in (Mock(status_code=400, text="private upstream response"), RuntimeError("private transport detail")):
            with self.subTest(failure=type(failure).__name__):
                result, calls = self.write("\n".join("x" for _ in range(101)), create=True, fail_at=1, failure=failure)
                self.assertEqual(len(calls), 1)
                self.assertIsNone(result.result)
                self.assertIn("not confirmed", result.error)
                self.assertIn("before retrying", result.error)
                self.assertNotIn("private", result.error)

    def test_malformed_append_success_does_not_confirm_the_batch(self):
        blocks = [{"object": "block", "id": f"00000000-0000-4000-8000-{index:012d}"} for index in range(100)]
        invalid_results = [
            {"foo": "bar"},
            {"object": "page", "id": "unrelated-page"},
            {"object": "page", "results": blocks},
            {"results": blocks},
            {"object": "list"},
        ]
        for results in (None, "private malformed results", {},
                        [None] * 100, ["block"] * 100, [{}] * 100,
                        [{"object": "page", "id": block["id"]} for block in blocks],
                        [{"object": "block", "id": None}] * 100,
                        [{"object": "block", "id": " "}] * 100,
                        [{"object": "block", "id": 123}] * 100):
            invalid_results.append({"object": "list", "results": results})

        for create, fail_at in ((False, 1), (False, 2), (True, 2)):
            for payload in invalid_results:
                with self.subTest(create=create, fail_at=fail_at, payload=payload):
                    response = Mock(status_code=200)
                    response.json.return_value = payload
                    result, calls = self.write("\n".join(f"p{index}" for index in range(301)), create=create, fail_at=fail_at, failure=response)
                    self.assertEqual(len(calls), fail_at)
                    self.assertIsNone(result.result)
                    self.assertIn(f"{(fail_at - 1) * 100} of 301", result.error)
                    self.assertIn("created-page" if create else "existing-page", result.error)
                    self.assertIn("not confirmed", result.error)
                    self.assertIn("may have been applied", result.error)
                    self.assertIn("duplicate", result.error)
                    self.assertNotIn("private", result.error)

    def test_paginated_append_response_acknowledges_the_submitted_batch(self):
        # The version-matched SDK permits a paginated list of partial blocks:
        # https://github.com/makenotion/notion-sdk-js/blob/v2.2.15/src/api-endpoints.ts
        for create in (False, True):
            with self.subTest(create=create):
                response = Mock(status_code=200)
                response.json.return_value = {
                    "object": "list", "type": "block", "block": {},
                    "has_more": True, "next_cursor": "opaque-cursor",
                    "results": [{"object": "block", "id": "00000000-0000-4000-8000-000000000001"}],
                }
                result, calls = self.write("\n".join(f"p{index}" for index in range(301)), create=create, fail_at=2, failure=response)
                self.assertIsNone(result.error)
                self.assertEqual(len(calls), 4)
                self.assertEqual([len(call[3]["children"]) for call in calls], [100, 100, 100, 1])
                self.assertEqual(self.saved_paragraphs(calls), [f"p{index}" for index in range(301)])
                self.assertIn("**Page Created!**" if create else "Added 301 paragraph(s)", result.result)

    def test_write_logs_omit_content_and_upstream_error_details(self):
        content = "private synthetic note contents"
        for failure in (Mock(status_code=400, text=content), RuntimeError(content)):
            with self.subTest(failure=type(failure).__name__):
                self.write(content, create=True, fail_at=1, failure=failure)
                self.assertNotIn(content, str(self.write_logs))

    def test_unusable_create_result_does_not_append_or_claim_success(self):
        for payload in (None, {}, {"error": ""}, {"url": "https://www.notion.so/unknown"}, {"id": ""}):
            with self.subTest(payload=payload):
                response = Mock(status_code=200)
                response.json.return_value = payload
                result, calls = self.write("\n".join("x" for _ in range(101)), create=True, fail_at=1, failure=response)
                self.assertEqual(len(calls), 1)
                self.assertIsNone(result.result)
                self.assertIn("not confirmed", result.error)

    def test_title_limits_are_validated_before_writing(self):
        result, calls = self.write("content", create=True, title="a" * 2001)
        self.assertIsNone(result.error)
        self.assert_valid_requests(calls)
        self.assertEqual("".join(item["text"]["content"] for item in calls[0][3]["properties"]["title"]["title"]), "a" * 2001)
        for title in ("a" * 200001, "😀" * 100000):
            result, calls = self.write("content", create=True, title=title)
            self.assertEqual(calls, [])
            self.assertIsNone(result.result)
            self.assertTrue(result.error)

if __name__ == "__main__":
    unittest.main(verbosity=2)
