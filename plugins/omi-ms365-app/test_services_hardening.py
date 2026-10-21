"""Hermetic regression tests for MS365 services defensive hardening.

Standard library only: runs under python3 -S with zero external dependencies.
Stubs httpx and services.auth before module import.
Covers defensive null guards, non-dict payloads, recipient extraction,
and RFC 7231 Retry-After parsing across mail, teams, sharepoint,
calendar, and graph_client services.
"""

from __future__ import annotations

import asyncio
import os
import sys
import types
import unittest
from datetime import datetime, timezone, timedelta

# Ensure local plugin directory is on path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def _install_module_stubs():
    if "httpx" not in sys.modules:
        httpx = types.ModuleType("httpx")

        class _AsyncClient:
            def __init__(self, *args, **kwargs):
                pass

            async def aclose(self):
                pass

        httpx.AsyncClient = _AsyncClient
        sys.modules["httpx"] = httpx

    if "services.auth" not in sys.modules:
        auth = types.ModuleType("services.auth")

        async def get_access_token(user_id):
            return "mock-token"

        class AuthError(Exception):
            pass

        auth.get_access_token = get_access_token
        auth.AuthError = AuthError
        sys.modules["services.auth"] = auth


_install_module_stubs()

from services import mail, teams, sharepoint, calendar
from services.graph_client import GraphClient, GraphError, _parse_retry_after


class MockGraphClient:
    """Mock for GraphClient context manager that returns pre-configured responses."""

    def __init__(self, get_response=None, post_response=None, get_bytes_response=b"", put_bytes_response=None):
        self.get_response = get_response
        self.post_response = post_response
        self.get_bytes_response = get_bytes_response
        self.put_bytes_response = put_bytes_response
        self.last_get_params = None
        self.last_post_json = None
        self.last_path = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    async def get(self, path, params=None, **kwargs):
        self.last_path = path
        self.last_get_params = params
        return self.get_response

    async def post(self, path, json=None, **kwargs):
        self.last_path = path
        self.last_post_json = json
        return self.post_response

    async def get_bytes(self, path, **kwargs):
        self.last_path = path
        return self.get_bytes_response

    async def put_bytes(self, path, data, content_type=None):
        self.last_path = path
        return self.put_bytes_response


class MailHardeningTests(unittest.TestCase):
    def test_slim_message_guards_non_dict(self):
        self.assertEqual(mail._slim_message(None), {})
        self.assertEqual(mail._slim_message("not a dict"), {})

    def test_extract_recipients_null_and_malformed(self):
        self.assertEqual(mail._extract_recipients(None), [])
        self.assertEqual(mail._extract_recipients("invalid"), [])
        self.assertEqual(mail._extract_recipients([None, 123]), [])

        recipients = [
            {"emailAddress": {"address": "user1@example.com", "name": "User 1"}},
            {"emailAddress": "user2@example.com"},
            {"otherField": "no-address"},
        ]
        extracted = mail._extract_recipients(recipients)
        self.assertEqual(len(extracted), 2)
        self.assertEqual(extracted[0], {"address": "user1@example.com", "name": "User 1"})
        self.assertEqual(extracted[1], {"address": "user2@example.com"})

    def test_read_null_recipients(self):
        mock_msg = {
            "id": "msg-123",
            "subject": "Test Subject",
            "from": {"emailAddress": {"address": "sender@example.com"}},
            "receivedDateTime": "2026-09-16T10:00:00Z",
            "bodyPreview": "Preview",
            "isRead": True,
            "hasAttachments": False,
            "webLink": "https://outlook.office.com/msg-123",
            "body": {"content": "Hello World", "contentType": "Text"},
            "toRecipients": None,
            "ccRecipients": None,
        }
        mock_client = MockGraphClient(get_response=mock_msg)
        original_client = mail.GraphClient
        mail.GraphClient = lambda user_id: mock_client
        try:
            res = asyncio.run(mail.read("user1", "msg-123"))
            self.assertEqual(res["id"], "msg-123")
            self.assertEqual(res["to"], [])
            self.assertEqual(res["cc"], [])
            self.assertEqual(res["body"], "Hello World")
        finally:
            mail.GraphClient = original_client

    def test_list_recent_null_value(self):
        mock_client = MockGraphClient(get_response={"value": None})
        original_client = mail.GraphClient
        mail.GraphClient = lambda user_id: mock_client
        try:
            res = asyncio.run(mail.list_recent("user1", limit=10))
            self.assertEqual(res, [])
        finally:
            mail.GraphClient = original_client

    def test_list_recent_non_dict_items_filtered(self):
        mock_client = MockGraphClient(get_response={"value": [None, "malformed", {"id": "valid-msg"}]})
        original_client = mail.GraphClient
        mail.GraphClient = lambda user_id: mock_client
        try:
            res = asyncio.run(mail.list_recent("user1", limit=10))
            self.assertEqual(len(res), 1)
            self.assertEqual(res[0]["id"], "valid-msg")
        finally:
            mail.GraphClient = original_client

    def test_search_strips_quotes(self):
        mock_client = MockGraphClient(get_response={"value": []})
        original_client = mail.GraphClient
        mail.GraphClient = lambda user_id: mock_client
        try:
            asyncio.run(mail.search("user1", query='urgent "project"', limit=10))
            self.assertEqual(mock_client.last_get_params["$search"], '"urgent project"')
        finally:
            mail.GraphClient = original_client


class TeamsHardeningTests(unittest.TestCase):
    def test_list_recent_chats_null_value(self):
        mock_client = MockGraphClient(get_response={"value": None})
        original_client = teams.GraphClient
        teams.GraphClient = lambda user_id: mock_client
        try:
            res = asyncio.run(teams.list_recent_chats("user1", limit=15))
            self.assertEqual(res, [])
        finally:
            teams.GraphClient = original_client

    def test_list_recent_chats_non_dict_items(self):
        mock_client = MockGraphClient(get_response={"value": [None, {"id": "chat-1", "topic": "Sprint"}]})
        original_client = teams.GraphClient
        teams.GraphClient = lambda user_id: mock_client
        try:
            res = asyncio.run(teams.list_recent_chats("user1", limit=15))
            self.assertEqual(len(res), 1)
            self.assertEqual(res[0]["id"], "chat-1")
            self.assertEqual(res[0]["topic"], "Sprint")
        finally:
            teams.GraphClient = original_client

    def test_list_my_teams_null_value(self):
        mock_client = MockGraphClient(get_response={"value": None})
        original_client = teams.GraphClient
        teams.GraphClient = lambda user_id: mock_client
        try:
            res = asyncio.run(teams.list_my_teams("user1"))
            self.assertEqual(res, [])
        finally:
            teams.GraphClient = original_client

    def test_create_online_meeting_non_dict_response(self):
        mock_client = MockGraphClient(post_response="unexpected string")
        original_client = teams.GraphClient
        teams.GraphClient = lambda user_id: mock_client
        try:
            res = asyncio.run(teams.create_online_meeting("user1", "Standup", "2026-09-16T10:00:00Z", "2026-09-16T10:30:00Z"))
            self.assertEqual(res["subject"], "Standup")
            self.assertIsNone(res["id"])
        finally:
            teams.GraphClient = original_client


class SharePointHardeningTests(unittest.TestCase):
    def test_slim_item_non_dict(self):
        self.assertEqual(sharepoint._slim_item(None), {})
        self.assertEqual(sharepoint._slim_item("string"), {})

    def test_list_recent_files_null_value(self):
        mock_client = MockGraphClient(get_response={"value": None})
        original_client = sharepoint.GraphClient
        sharepoint.GraphClient = lambda user_id: mock_client
        try:
            res = asyncio.run(sharepoint.list_recent_files("user1", limit=15))
            self.assertEqual(res, [])
        finally:
            sharepoint.GraphClient = original_client

    def test_search_files_escapes_single_quotes(self):
        mock_client = MockGraphClient(get_response={"value": []})
        original_client = sharepoint.GraphClient
        sharepoint.GraphClient = lambda user_id: mock_client
        try:
            asyncio.run(sharepoint.search_files("user1", query="O'Reilly Report", limit=15))
            self.assertIn("O''Reilly Report", mock_client.last_path)
        finally:
            sharepoint.GraphClient = original_client

    def test_read_file_text_binary_fallback(self):
        mock_client = MockGraphClient(
            get_response={"id": "f1", "name": "data.bin"},
            get_bytes_response=b"\xff\xfe\x00\x80\x90",
        )
        original_client = sharepoint.GraphClient
        sharepoint.GraphClient = lambda user_id: mock_client
        try:
            res = asyncio.run(sharepoint.read_file_text("user1", "f1"))
            self.assertEqual(res["id"], "f1")
            self.assertIn("<binary 5 bytes>", res["content"])
        finally:
            sharepoint.GraphClient = original_client


class CalendarHardeningTests(unittest.TestCase):
    def test_slim_event_non_dict(self):
        self.assertEqual(calendar._slim_event(None), {})
        self.assertEqual(calendar._slim_event("string"), {})

    def test_find_free_slots_null_suggestions(self):
        mock_client = MockGraphClient(post_response={"meetingTimeSuggestions": None})
        original_client = calendar.GraphClient
        calendar.GraphClient = lambda user_id: mock_client
        try:
            res = asyncio.run(calendar.find_free_slots("user1", 30, ["alice@example.com"]))
            self.assertEqual(res, [])
        finally:
            calendar.GraphClient = original_client

    def test_find_free_slots_guarded_nested_slots(self):
        mock_client = MockGraphClient(
            post_response={
                "meetingTimeSuggestions": [
                    None,
                    {"confidence": 50.0},  # Missing meetingTimeSlot
                    {
                        "confidence": 100.0,
                        "meetingTimeSlot": {
                            "start": {"dateTime": "2026-09-16T14:00:00Z"},
                            "end": {"dateTime": "2026-09-16T14:30:00Z"},
                        },
                    },
                ]
            }
        )
        original_client = calendar.GraphClient
        calendar.GraphClient = lambda user_id: mock_client
        try:
            res = asyncio.run(calendar.find_free_slots("user1", 30, ["alice@example.com"]))
            self.assertEqual(len(res), 2)
            self.assertIsNone(res[0]["start"])
            self.assertEqual(res[0]["confidence"], 50.0)
            self.assertEqual(res[1]["start"], "2026-09-16T14:00:00Z")
            self.assertEqual(res[1]["end"], "2026-09-16T14:30:00Z")
            self.assertEqual(res[1]["confidence"], 100.0)
        finally:
            calendar.GraphClient = original_client


class GraphClientRetryAfterTests(unittest.TestCase):
    def test_parse_retry_after_integer(self):
        self.assertEqual(_parse_retry_after("120"), 120)
        self.assertEqual(_parse_retry_after("5"), 5)

    def test_parse_retry_after_none_or_empty(self):
        self.assertEqual(_parse_retry_after(None), 2)
        self.assertEqual(_parse_retry_after(""), 2)

    def test_parse_retry_after_http_date(self):
        future = datetime.now(timezone.utc) + timedelta(seconds=60)
        http_date = future.strftime("%a, %d %b %Y %H:%M:%S GMT")
        parsed = _parse_retry_after(http_date)
        # Should be approximately 58-62 seconds
        self.assertTrue(50 <= parsed <= 70)

    def test_parse_retry_after_invalid_string(self):
        self.assertEqual(_parse_retry_after("not-a-number-or-date"), 2)


class LimitCoercionAndKqlTests(unittest.TestCase):
    def test_non_numeric_limit_falls_back_to_default(self):
        captured_params = {}

        class MockGraph:
            def __init__(self, user_id):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

            async def get(self, endpoint, params=None):
                captured_params[endpoint] = params
                return {"value": []}

            async def get_all(self, endpoint, params=None, max_items=None):
                captured_params[endpoint] = {"params": params, "max_items": max_items}
                return []

        orig_mail_g = mail.GraphClient
        orig_cal_g = calendar.GraphClient
        orig_sp_g = sharepoint.GraphClient
        orig_teams_g = teams.GraphClient

        mail.GraphClient = MockGraph
        calendar.GraphClient = MockGraph
        sharepoint.GraphClient = MockGraph
        teams.GraphClient = MockGraph
        try:
            asyncio.run(mail.list_recent("u1", limit="ten"))
            self.assertEqual(captured_params["/me/messages"]["$top"], 10)

            asyncio.run(mail.search("u1", "test", limit="invalid"))
            self.assertEqual(captured_params["/me/messages"]["$top"], 10)

            asyncio.run(calendar.list_upcoming("u1", days=1, limit="many"))
            self.assertEqual(captured_params["/me/calendarView"]["max_items"], calendar.MAX_EVENTS)

            asyncio.run(sharepoint.list_recent_files("u1", limit="bad"))
            self.assertEqual(captured_params["/me/drive/recent"]["$top"], 15)

            asyncio.run(teams.list_recent_chats("u1", limit="none"))
            self.assertEqual(captured_params["/me/chats"]["$top"], 15)
        finally:
            mail.GraphClient = orig_mail_g
            calendar.GraphClient = orig_cal_g
            sharepoint.GraphClient = orig_sp_g
            teams.GraphClient = orig_teams_g

    def test_mail_search_strips_double_quotes_from_kql_query(self):
        captured_params = {}

        class MockGraph:
            def __init__(self, user_id):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                pass

            async def get(self, endpoint, params=None):
                captured_params.update(params or {})
                return {"value": []}

        orig_mail_g = mail.GraphClient
        mail.GraphClient = MockGraph
        try:
            asyncio.run(mail.search("u1", 'quarterly "Q3" report'))
            self.assertEqual(captured_params["$search"], '"quarterly Q3 report"')
        finally:
            mail.GraphClient = orig_mail_g


if __name__ == "__main__":
    unittest.main()
