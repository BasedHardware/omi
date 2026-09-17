"""Hermetic unit tests for Notion app identifier hygiene and page disambiguation."""
import asyncio
import importlib.util
import json
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import AsyncMock, Mock, patch

APP_DIR = Path(__file__).resolve().parent
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))


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
    "requests": module("requests", get=Mock(), post=Mock(), patch=Mock(), delete=Mock()),
    "dotenv": module("dotenv", load_dotenv=lambda: None),
    "fastapi": module("fastapi", FastAPI=Framework, Request=Framework, Query=Framework, HTTPException=Exception),
    "fastapi.responses": module(
        "fastapi.responses",
        HTMLResponse=Framework,
        RedirectResponse=Framework,
        JSONResponse=Framework,
    ),
    "models": module("models", ChatToolResponse=Response),
    "db": module("db", **{
        name: Mock() for name in (
            "store_notion_tokens", "get_notion_tokens", "update_notion_tokens", "delete_notion_tokens",
            "store_oauth_state", "get_oauth_state", "delete_oauth_state", "store_user_setting", "get_user_setting",
        )
    }),
}

spec = importlib.util.spec_from_file_location("notion_under_test", Path(__file__).with_name("main.py"))
notion = importlib.util.module_from_spec(spec)
with patch.dict(sys.modules, stubs):
    spec.loader.exec_module(notion)


class NotionIdentifierSanitizationTests(unittest.TestCase):
    """Test suite for sanitize_notion_id."""

    def test_raw_32_hex_normalized(self):
        raw = "8a99478f6b214f1b857c2b28cf9c9a29"
        expected = "8a99478f-6b21-4f1b-857c-2b28cf9c9a29"
        self.assertEqual(notion.sanitize_notion_id(raw), expected)
        self.assertEqual(notion.sanitize_notion_id(raw.upper()), expected)

    def test_hyphenated_uuid(self):
        uuid_str = "8a99478f-6b21-4f1b-857c-2b28cf9c9a29"
        self.assertEqual(notion.sanitize_notion_id(uuid_str), uuid_str)
        self.assertEqual(notion.sanitize_notion_id(uuid_str.upper()), uuid_str)

    def test_prefixes_and_wrapping_stripped(self):
        base_id = "8a99478f-6b21-4f1b-857c-2b28cf9c9a29"
        cases = [
            f"page:{base_id}",
            f"page/{base_id}",
            f"p:{base_id}",
            f"database:{base_id}",
            f"db:{base_id}",
            f"block:{base_id}",
            f"#{base_id}",
            f"`{base_id}`",
            f"'{base_id}'",
            f'"{base_id}"',
            f"<{base_id}>",
            f"  {base_id}  \n",
        ]
        for c in cases:
            with self.subTest(case=c):
                self.assertEqual(notion.sanitize_notion_id(c), base_id)

    def test_notion_urls_parsed(self):
        expected = "8a99478f-6b21-4f1b-857c-2b28cf9c9a29"
        hex_part = "8a99478f6b214f1b857c2b28cf9c9a29"
        urls = [
            f"https://www.notion.so/workspace/My-Page-Title-{hex_part}",
            f"https://notion.so/{hex_part}?pvs=4",
            f"https://notion.so/workspace/{expected}#block-1234",
            f"https://team.notion.site/Weekly-Update-{hex_part}?pvs=4&utm_source=app",
            f"http://notion.so/{hex_part}",
        ]
        for url in urls:
            with self.subTest(url=url):
                self.assertEqual(notion.sanitize_notion_id(url), expected)

    def test_natural_language_titles_return_none(self):
        titles = [
            "Meeting Notes",
            "Sprint 42 Retrospective",
            "Daily Standup",
            "Notes",
            "Project Roadmap 2026",
            "12345",
            "short-id",
        ]
        for title in titles:
            with self.subTest(title=title):
                self.assertIsNone(notion.sanitize_notion_id(title))

    def test_non_hex_urls_return_none(self):
        urls = [
            "https://notion.so/pricing",
            "https://notion.so/login",
            "https://www.notion.so/product",
            "https://notion.site/about",
            "https://notion.so/",
        ]
        for u in urls:
            with self.subTest(url=u):
                self.assertIsNone(notion.sanitize_notion_id(u))

    def test_dirty_and_empty_types(self):
        for val in (None, "", "   ", "\t\n", 123, {}, [], True, False):
            with self.subTest(val=val):
                self.assertIsNone(notion.sanitize_notion_id(val))


class PageTitleDisambiguationTests(unittest.TestCase):
    """Test suite for disambiguate_page_by_title."""

    def _mock_page(self, page_id: str, title: str, archived: bool = False):
        return {
            "object": "page",
            "id": page_id,
            "archived": archived,
            "properties": {
                "title": {
                    "type": "title",
                    "title": [{"plain_text": title}]
                }
            },
            "url": f"https://www.notion.so/{page_id}"
        }

    def test_exact_title_match_success(self):
        target_page = self._mock_page("page-uuid-1", "Meeting Notes")
        search_res = {"results": [target_page, self._mock_page("page-uuid-2", "General Notes")]}

        with patch.object(notion, "notion_api_request", return_value=search_res):
            resolved_id, page, err = notion.disambiguate_page_by_title("user-1", "meeting notes")

        self.assertIsNone(err)
        self.assertEqual(resolved_id, "page-uuid-1")
        self.assertEqual(page["id"], "page-uuid-1")

    def test_multiple_exact_matches_blocked_with_candidates(self):
        p1 = self._mock_page("page-uuid-1", "Project Plan")
        p2 = self._mock_page("page-uuid-2", "Project Plan")
        search_res = {"results": [p1, p2]}

        with patch.object(notion, "notion_api_request", return_value=search_res):
            resolved_id, page, err = notion.disambiguate_page_by_title("user-1", "Project Plan")

        self.assertIsNone(resolved_id)
        self.assertIsNone(page)
        self.assertIn("Multiple pages match 'Project Plan'", err)
        self.assertIn("page-uuid-1", err)
        self.assertIn("page-uuid-2", err)
        self.assertIn("Please specify the exact Page ID", err)

    def test_partial_match_when_no_exact_match(self):
        target_page = self._mock_page("page-uuid-roadmap", "2026 Q3 Product Roadmap")
        search_res = {"results": [target_page, self._mock_page("page-uuid-other", "Customer Feedback")]}

        with patch.object(notion, "notion_api_request", return_value=search_res):
            resolved_id, page, err = notion.disambiguate_page_by_title("user-1", "Product Roadmap")

        self.assertIsNone(err)
        self.assertEqual(resolved_id, "page-uuid-roadmap")

    def test_multiple_partial_matches_blocked(self):
        p1 = self._mock_page("page-uuid-1", "Sprint 10 Review")
        p2 = self._mock_page("page-uuid-2", "Sprint 11 Review")
        search_res = {"results": [p1, p2]}

        with patch.object(notion, "notion_api_request", return_value=search_res):
            resolved_id, page, err = notion.disambiguate_page_by_title("user-1", "Sprint")

        self.assertIsNone(resolved_id)
        self.assertIn("Multiple pages match 'Sprint'", err)
        self.assertIn("page-uuid-1", err)
        self.assertIn("page-uuid-2", err)

    def test_no_matches_returns_diagnostic_error(self):
        search_res = {"results": []}

        with patch.object(notion, "notion_api_request", return_value=search_res):
            resolved_id, page, err = notion.disambiguate_page_by_title("user-1", "NonExistent")

        self.assertIsNone(resolved_id)
        self.assertIn("No page found matching 'NonExistent'", err)

    def test_search_failure_propagates_clean_error(self):
        with patch.object(notion, "notion_api_request", return_value={"error": "Rate limit exceeded"}):
            resolved_id, page, err = notion.disambiguate_page_by_title("user-1", "Notes")

        self.assertIsNone(resolved_id)
        self.assertIn("Search failed while resolving page 'Notes': Rate limit exceeded", err)

    def test_unicode_nfd_nfc_and_invisible_characters(self):
        # NFD vs NFC normalized match
        nfc_page = self._mock_page("page-cafe-1", "Café")
        search_res = {"results": [nfc_page]}
        with patch.object(notion, "notion_api_request", return_value=search_res):
            resolved_id, page, err = notion.disambiguate_page_by_title("user-1", "Cafe\u0301")
        self.assertIsNone(err)
        self.assertEqual(resolved_id, "page-cafe-1")

        # Zero-width spaces stripped
        zw_page = self._mock_page("page-zw-1", "Meeting\u200bNotes")
        search_res = {"results": [zw_page]}
        with patch.object(notion, "notion_api_request", return_value=search_res):
            resolved_id, page, err = notion.disambiguate_page_by_title("user-1", "Meeting Notes")
        self.assertIsNone(err)
        self.assertEqual(resolved_id, "page-zw-1")

    def test_archived_pages_ignored_without_revival(self):
        archived_page = self._mock_page("archived-1", "Old Notes", archived=True)
        search_res = {"results": [archived_page]}
        with patch.object(notion, "notion_api_request", return_value=search_res):
            resolved_id, page, err = notion.disambiguate_page_by_title("user-1", "Old Notes")
        self.assertIsNone(resolved_id)
        self.assertIn("No active page found matching 'Old Notes'", err)

    def test_word_boundary_prevents_substring_drift(self):
        email_page = self._mock_page("page-email-1", "Email Marketing Guide")
        search_res = {"results": [email_page]}
        with patch.object(notion, "notion_api_request", return_value=search_res):
            resolved_id, page, err = notion.disambiguate_page_by_title("user-1", "AI")
        # 'AI' has length < 3 and does not match as word boundary in 'Email Marketing Guide'
        self.assertIsNone(resolved_id)
        self.assertIn("No page found matching 'AI'", err)


class ToolEndpointsIntegrationTests(unittest.TestCase):
    """Test suite for tool endpoints with title disambiguation and URL support."""

    PAGE_UUID = "8a99478f-6b21-4f1b-857c-2b28cf9c9a29"
    PAGE_HEX = "8a99478f6b214f1b857c2b28cf9c9a29"

    def _mock_page_obj(self, page_id=PAGE_UUID, title="Architecture Spec"):
        return {
            "object": "page",
            "id": page_id,
            "properties": {
                "title": {"type": "title", "title": [{"plain_text": title}]}
            },
            "url": f"https://www.notion.so/{page_id}",
            "created_time": "2026-09-01T00:00:00.000Z",
            "last_edited_time": "2026-09-17T00:00:00.000Z",
            "archived": False,
        }

    def test_tool_get_page_via_notion_url(self):
        url = f"https://www.notion.so/workspace/Architecture-Spec-{self.PAGE_HEX}?pvs=4"
        request = Mock(json=AsyncMock(return_value={"uid": "user-1", "page_id": url}))

        page_data = self._mock_page_obj()
        blocks_data = {"results": [{"object": "block", "type": "paragraph", "paragraph": {"rich_text": [{"plain_text": "Content"}]}}]}

        with patch.object(notion, "get_valid_access_token", return_value="token"), \
             patch.object(notion, "notion_api_request", side_effect=lambda uid, method, endpoint, **kwargs: (
                 page_data if endpoint.endswith(self.PAGE_UUID) else None
             )), \
             patch.object(notion, "fetch_page_blocks", return_value=blocks_data):
            response = asyncio.run(notion.tool_get_page(request))

        self.assertIsNone(response.error)
        self.assertIn("**Architecture Spec**", response.result)
        self.assertIn(f"**Page ID:** `{self.PAGE_UUID}`", response.result)

    def test_tool_get_page_via_page_title(self):
        request = Mock(json=AsyncMock(return_value={"uid": "user-1", "page_id": "Architecture Spec"}))

        page_data = self._mock_page_obj()
        search_res = {"results": [page_data]}
        blocks_data = {"results": []}

        with patch.object(notion, "get_valid_access_token", return_value="token"), \
             patch.object(notion, "notion_api_request", side_effect=lambda uid, method, endpoint, **kwargs: (
                 search_res if endpoint == "/search" else page_data
             )), \
             patch.object(notion, "fetch_page_blocks", return_value=blocks_data):
            response = asyncio.run(notion.tool_get_page(request))

        self.assertIsNone(response.error)
        self.assertIn("**Architecture Spec**", response.result)
        self.assertIn(f"**Page ID:** `{self.PAGE_UUID}`", response.result)

    def test_tool_get_page_multiple_titles_blocked(self):
        request = Mock(json=AsyncMock(return_value={"uid": "user-1", "page_id": "Meeting Notes"}))

        p1 = self._mock_page_obj("id-1", "Meeting Notes")
        p2 = self._mock_page_obj("id-2", "Meeting Notes")
        search_res = {"results": [p1, p2]}

        with patch.object(notion, "get_valid_access_token", return_value="token"), \
             patch.object(notion, "notion_api_request", return_value=search_res):
            response = asyncio.run(notion.tool_get_page(request))

        self.assertIsNone(response.result)
        self.assertIn("Multiple pages match 'Meeting Notes'", response.error)

    def test_tool_create_page_whitespace_title_rejected(self):
        for blank_title in ("", "   ", "\t\n"):
            with self.subTest(title=blank_title):
                request = Mock(json=AsyncMock(return_value={"uid": "user-1", "title": blank_title}))
                response = asyncio.run(notion.tool_create_page(request))
                self.assertIsNone(response.result)
                self.assertIn("Page title is required and cannot be whitespace only", response.error)

    def test_tool_create_page_adaptive_database_title_property(self):
        db_id = "database-uuid-123"
        request = Mock(json=AsyncMock(return_value={
            "uid": "user-1",
            "title": "New Task Item",
            "database_id": f"https://notion.so/{db_id}"
        }))

        # Database schema has title property named 'Task' instead of default 'Name'
        db_schema = {
            "object": "database",
            "id": db_id,
            "properties": {
                "Task": {"type": "title"},
                "Priority": {"type": "select"}
            }
        }

        sent_post_payload = {}

        def mock_request(uid, method, endpoint, **kwargs):
            nonlocal sent_post_payload
            if method == "GET" and endpoint == f"/databases/{db_id}":
                return db_schema
            if method == "POST" and endpoint == "/pages":
                sent_post_payload = kwargs.get("json_data", {})
                return {"id": "new-page-id", "url": "https://notion.so/new-page-id"}
            return None

        with patch.object(notion, "get_valid_access_token", return_value="token"), \
             patch.object(notion, "notion_api_request", side_effect=mock_request):
            response = asyncio.run(notion.tool_create_page(request))

        self.assertIsNone(response.error)
        self.assertIn("**Page Created!**", response.result)
        # Verify the dynamic property key 'Task' was used instead of 'Name'
        self.assertIn("Task", sent_post_payload.get("properties", {}))
        self.assertNotIn("Name", sent_post_payload.get("properties", {}))
        self.assertEqual(
            sent_post_payload["properties"]["Task"]["title"][0]["text"]["content"],
            "New Task Item"
        )
        self.assertEqual(sent_post_payload["parent"], {"database_id": db_id})

    def test_tool_update_page_whitespace_title_rejected(self):
        request = Mock(json=AsyncMock(return_value={
            "uid": "user-1",
            "page_id": self.PAGE_UUID,
            "title": "   "
        }))
        with patch.object(notion, "get_valid_access_token", return_value="token"):
            response = asyncio.run(notion.tool_update_page(request))
        self.assertIsNone(response.result)
        self.assertIn("Page title cannot be empty or whitespace only", response.error)

    def test_tool_update_page_with_notion_url(self):
        url = f"https://notion.so/{self.PAGE_HEX}?pvs=4"
        request = Mock(json=AsyncMock(return_value={
            "uid": "user-1",
            "page_id": url,
            "archived": True
        }))

        patch_called = False

        def mock_request(uid, method, endpoint, **kwargs):
            nonlocal patch_called
            if method == "PATCH" and endpoint == f"/pages/{self.PAGE_UUID}":
                patch_called = True
                return {"id": self.PAGE_UUID}
            return None

        with patch.object(notion, "get_valid_access_token", return_value="token"), \
             patch.object(notion, "notion_api_request", side_effect=mock_request):
            response = asyncio.run(notion.tool_update_page(request))

        self.assertTrue(patch_called)
        self.assertIsNone(response.error)
        self.assertIn("Archived: True", response.result)

    def test_tool_append_content_with_notion_url(self):
        url = f"https://notion.so/workspace/Page-{self.PAGE_HEX}"
        request = Mock(json=AsyncMock(return_value={
            "uid": "user-1",
            "page_id": url,
            "content": "Followup action item"
        }))

        append_called = False

        def mock_request(uid, method, endpoint, **kwargs):
            nonlocal append_called
            if method == "PATCH" and endpoint == f"/blocks/{self.PAGE_UUID}/children":
                append_called = True
                return {
                    "object": "list",
                    "results": [{"object": "block", "id": "block-new-1"}]
                }
            return None

        with patch.object(notion, "get_valid_access_token", return_value="token"), \
             patch.object(notion, "notion_api_request", side_effect=mock_request):
            response = asyncio.run(notion.tool_append_content(request))

        self.assertTrue(append_called)
        self.assertIsNone(response.error)
        self.assertIn("Added 1 paragraph(s)", response.result)

    def test_tool_query_database_with_notion_url(self):
        db_hex = "a1b2c3d4e5f64a7b8c9d0e1f2a3b4c5d"
        db_uuid = "a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d"
        url = f"https://notion.so/{db_hex}?v=123"
        request = Mock(json=AsyncMock(return_value={
            "uid": "user-1",
            "database_id": url
        }))

        query_called = False

        def mock_request(uid, method, endpoint, **kwargs):
            nonlocal query_called
            if method == "POST" and endpoint == f"/databases/{db_uuid}/query":
                query_called = True
                return {"results": []}
            return None

        with patch.object(notion, "get_valid_access_token", return_value="token"), \
             patch.object(notion, "notion_api_request", side_effect=mock_request):
            response = asyncio.run(notion.tool_query_database(request))

        self.assertTrue(query_called)
        self.assertIsNone(response.error)
        self.assertIn("No entries found in this database", response.result)

    def test_tool_get_page_word_title_ambiguity_propagated(self):
        request = Mock(json=AsyncMock(return_value={"uid": "user-1", "page_id": "Notes"}))

        p1 = self._mock_page_obj("notes-id-1", "Notes")
        p2 = self._mock_page_obj("notes-id-2", "Notes")
        search_res = {"results": [p1, p2]}

        with patch.object(notion, "get_valid_access_token", return_value="token"), \
             patch.object(notion, "notion_api_request", side_effect=lambda uid, method, endpoint, **kwargs: (
                 search_res if endpoint == "/search" else {"error": "object_not_found"}
             )):
            response = asyncio.run(notion.tool_get_page(request))

        self.assertIsNone(response.result)
        self.assertIn("Multiple pages match 'Notes'", response.error)
        self.assertIn("notes-id-1", response.error)
        self.assertIn("notes-id-2", response.error)

    def test_tool_update_page_single_word_title_disambiguated(self):
        request = Mock(json=AsyncMock(return_value={
            "uid": "user-1",
            "page_id": "Roadmap",
            "title": "2026 Strategy",
            "archived": "false"
        }))

        roadmap_page = self._mock_page_obj(self.PAGE_UUID, "Roadmap")
        search_res = {"results": [roadmap_page]}
        patch_payload = {}

        def mock_request(uid, method, endpoint, **kwargs):
            nonlocal patch_payload
            if method == "GET" and endpoint == "/pages/Roadmap":
                return {"error": "object_not_found"}
            if method == "POST" and endpoint == "/search":
                return search_res
            if method == "GET" and endpoint == f"/pages/{self.PAGE_UUID}":
                return roadmap_page
            if method == "PATCH" and endpoint == f"/pages/{self.PAGE_UUID}":
                patch_payload = kwargs.get("json_data", {})
                return {"id": self.PAGE_UUID}
            return None

        with patch.object(notion, "get_valid_access_token", return_value="token"), \
             patch.object(notion, "notion_api_request", side_effect=mock_request):
            response = asyncio.run(notion.tool_update_page(request))

        self.assertIsNone(response.error)
        self.assertIn("Page Updated!", response.result)
        self.assertIn("Title: 2026 Strategy", response.result)
        self.assertIn("Archived: False", response.result)
        self.assertFalse(patch_payload.get("archived"))
        self.assertEqual(patch_payload["properties"]["title"]["title"][0]["text"]["content"], "2026 Strategy")

    def test_tool_append_content_single_word_title_disambiguated(self):
        request = Mock(json=AsyncMock(return_value={
            "uid": "user-1",
            "page_id": "Roadmap",
            "content": "Q4 objectives"
        }))

        roadmap_page = self._mock_page_obj(self.PAGE_UUID, "Roadmap")
        search_res = {"results": [roadmap_page]}
        append_called = False

        def mock_request(uid, method, endpoint, **kwargs):
            nonlocal append_called
            if method == "PATCH" and endpoint == "/blocks/Roadmap/children":
                return {"error": "HTTP 404", "status_code": 404}
            if method == "POST" and endpoint == "/search":
                return search_res
            if method == "PATCH" and endpoint == f"/blocks/{self.PAGE_UUID}/children":
                append_called = True
                return {
                    "object": "list",
                    "results": [{"object": "block", "id": "block-new-1"}]
                }
            return None

        with patch.object(notion, "get_valid_access_token", return_value="token"), \
             patch.object(notion, "notion_api_request", side_effect=mock_request):
            response = asyncio.run(notion.tool_append_content(request))

        self.assertTrue(append_called)
        self.assertIsNone(response.error)
        self.assertIn("Added 1 paragraph(s)", response.result)

    def test_notion_url_with_modal_peek_page_id(self):
        # When opening a page from a database view in Notion web, the URL contains ?p=<page_id>
        db_hex = "78a69ec407a142e0989f66085a6a6e5b"
        page_hex = "94d7dfaa2da84a569df495eb48ba5381"
        url = f"https://www.notion.so/workspace/Tasks-{db_hex}?p={page_hex}&pm=s"
        extracted = notion.sanitize_notion_id(url)
        self.assertEqual(extracted, "94d7dfaa-2da8-4a56-9df4-95eb48ba5381")

    def test_cjk_language_substring_disambiguation(self):
        page_obj = self._mock_page_obj(self.PAGE_UUID, "2026年技术架构方案")
        search_res = {"results": [page_obj]}
        with patch.object(notion, "notion_api_request", return_value=search_res):
            # Query with non-spaced CJK substring (length 4 >= 2)
            resolved_id, resolved_page, err = notion.disambiguate_page_by_title("user-1", "技术架构")
            self.assertEqual(resolved_id, self.PAGE_UUID)
            self.assertIsNone(err)

    def test_clean_target_id_dirty_types_blocked(self):
        self.assertIsNone(notion._clean_target_id(True))
        self.assertIsNone(notion._clean_target_id(False))
        self.assertIsNone(notion._clean_target_id(None))
        self.assertIsNone(notion._clean_target_id(["invalid"]))
        self.assertIsNone(notion._clean_target_id({"bad": "dict"}))

    def test_tool_update_page_invalid_boolean_string_rejected(self):
        request = Mock(json=AsyncMock(return_value={
            "uid": "user-1",
            "page_id": self.PAGE_UUID,
            "archived": "maybe_archive"
        }))
        with patch.object(notion, "get_valid_access_token", return_value="token"):
            response = asyncio.run(notion.tool_update_page(request))
        self.assertIsNone(response.result)
        self.assertIn("Invalid boolean value for archived", response.error)

    def test_tool_query_database_none_max_results_safe(self):
        request = Mock(json=AsyncMock(return_value={
            "uid": "user-1",
            "database_id": self.PAGE_UUID,
            "max_results": None
        }))
        with patch.object(notion, "get_valid_access_token", return_value="token"), \
             patch.object(notion, "notion_api_request", return_value={"results": []}):
            response = asyncio.run(notion.tool_query_database(request))
        self.assertIsNone(response.error)
        self.assertIn("No entries found", response.result)


if __name__ == "__main__":
    unittest.main(verbosity=2)

