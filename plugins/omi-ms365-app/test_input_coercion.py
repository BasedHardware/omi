"""Hermetic tests for MS365 service input coercion and recipient normalization.

Verifies:
1. mail.send accepts single-string and comma/semicolon-separated emails without character slicing.
2. calendar.list_upcoming accepts string 'days' without timedelta TypeError and clamps safely.
3. calendar.create_event normalizes string attendees and handles string booleans for online.
4. calendar.find_free_slots normalizes string duration_minutes, within_days, and attendees.
5. sharepoint.upload_text_file correctly formats root and nested folder paths without double slashes.

Run: python3 plugins/omi-ms365-app/test_input_coercion.py
"""

from __future__ import annotations

import asyncio
import os
import sys
import types
import unittest

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

from services import calendar, mail, sharepoint


class MockGraphClient:
    def __init__(self, *, get_response=None, post_response=None, put_response=None):
        self.get_response = get_response or {}
        self.post_response = post_response or {}
        self.put_response = put_response or {}
        self.last_path = None
        self.last_params = None
        self.last_json = None
        self.last_bytes_path = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass

    async def get(self, path, params=None):
        self.last_path = path
        self.last_params = params
        return self.get_response

    async def get_all(self, path, params=None, max_items=500):
        self.last_path = path
        self.last_params = params
        return self.get_response.get("value", []) if isinstance(self.get_response, dict) else []

    async def post(self, path, json=None, expect_json=True):
        self.last_path = path
        self.last_json = json
        return self.post_response

    async def put_bytes(self, path, data, content_type="text/plain"):
        self.last_bytes_path = path
        return self.put_response


class MailInputCoercionTests(unittest.TestCase):
    def test_send_single_string_recipient_not_sliced(self):
        client = MockGraphClient()
        orig_client = mail.GraphClient
        mail.GraphClient = lambda user_id: client
        try:
            res = asyncio.run(
                mail.send("user1", to="alice@example.com", subject="Hi", body="Hello")
            )
            self.assertEqual(res["status"], "sent")
            self.assertEqual(res["to"], ["alice@example.com"])
            recipients = client.last_json["message"]["toRecipients"]
            # Must NOT slice 'alice@example.com' into 17 single-character recipients
            self.assertEqual(len(recipients), 1)
            self.assertEqual(recipients[0], {"emailAddress": {"address": "alice@example.com"}})
        finally:
            mail.GraphClient = orig_client

    def test_send_comma_and_semicolon_separated_recipients(self):
        client = MockGraphClient()
        orig_client = mail.GraphClient
        mail.GraphClient = lambda user_id: client
        try:
            asyncio.run(
                mail.send(
                    "user1",
                    to="alice@example.com, bob@example.com; charlie@example.com",
                    subject="Update",
                    body="Body",
                    cc="manager@example.com",
                )
            )
            to_recipients = client.last_json["message"]["toRecipients"]
            cc_recipients = client.last_json["message"]["ccRecipients"]
            self.assertEqual(
                to_recipients,
                [
                    {"emailAddress": {"address": "alice@example.com"}},
                    {"emailAddress": {"address": "bob@example.com"}},
                    {"emailAddress": {"address": "charlie@example.com"}},
                ],
            )
            self.assertEqual(
                cc_recipients,
                [{"emailAddress": {"address": "manager@example.com"}}],
            )
        finally:
            mail.GraphClient = orig_client

    def test_send_list_of_dict_recipients(self):
        client = MockGraphClient()
        orig_client = mail.GraphClient
        mail.GraphClient = lambda user_id: client
        try:
            asyncio.run(
                mail.send(
                    "user1",
                    to=[{"address": "alice@example.com"}, {"emailAddress": {"address": "bob@example.com"}}],
                    subject="Meeting",
                    body="Details",
                )
            )
            recipients = client.last_json["message"]["toRecipients"]
            self.assertEqual(len(recipients), 2)
            self.assertEqual(recipients[0], {"emailAddress": {"address": "alice@example.com"}})
            self.assertEqual(recipients[1], {"emailAddress": {"address": "bob@example.com"}})
        finally:
            mail.GraphClient = orig_client


class CalendarInputCoercionTests(unittest.TestCase):
    def test_list_upcoming_coerces_string_days_without_type_error(self):
        client = MockGraphClient(get_response={"value": []})
        orig_client = calendar.GraphClient
        calendar.GraphClient = lambda user_id: client
        try:
            # String 'days' must not raise TypeError: unsupported type for timedelta days component: str
            res = asyncio.run(calendar.list_upcoming("user1", days="7", limit="20"))
            self.assertEqual(res, [])
            self.assertIn("startDateTime", client.last_params)
            self.assertIn("endDateTime", client.last_params)
        finally:
            calendar.GraphClient = orig_client

    def test_list_upcoming_clamps_invalid_or_negative_days(self):
        client = MockGraphClient(get_response={"value": []})
        orig_client = calendar.GraphClient
        calendar.GraphClient = lambda user_id: client
        try:
            asyncio.run(calendar.list_upcoming("user1", days=-5))
            self.assertIn("startDateTime", client.last_params)
            asyncio.run(calendar.list_upcoming("user1", days="invalid"))
            self.assertIn("startDateTime", client.last_params)
        finally:
            calendar.GraphClient = orig_client

    def test_create_event_normalizes_string_attendees_and_boolean_online(self):
        client = MockGraphClient(post_response={"id": "evt-1"})
        orig_client = calendar.GraphClient
        calendar.GraphClient = lambda user_id: client
        try:
            asyncio.run(
                calendar.create_event(
                    "user1",
                    subject="Sync",
                    start_iso="2026-09-20T10:00:00Z",
                    end_iso="2026-09-20T10:30:00Z",
                    attendees="lead@example.com, dev@example.com",
                    online="false",
                )
            )
            payload = client.last_json
            self.assertFalse(payload["isOnlineMeeting"])
            self.assertIsNone(payload["onlineMeetingProvider"])
            attendees = payload["attendees"]
            self.assertEqual(len(attendees), 2)
            self.assertEqual(attendees[0]["emailAddress"]["address"], "lead@example.com")
            self.assertEqual(attendees[1]["emailAddress"]["address"], "dev@example.com")
        finally:
            calendar.GraphClient = orig_client

    def test_find_free_slots_coerces_string_durations_and_attendees(self):
        client = MockGraphClient(post_response={"meetingTimeSuggestions": []})
        orig_client = calendar.GraphClient
        calendar.GraphClient = lambda user_id: client
        try:
            # String duration and within_days should not raise TypeError
            res = asyncio.run(
                calendar.find_free_slots(
                    "user1",
                    duration_minutes="45",
                    attendees="colleague@example.com",
                    within_days="10",
                )
            )
            self.assertEqual(res, [])
            payload = client.last_json
            self.assertEqual(payload["meetingDuration"], "PT45M")
            self.assertEqual(len(payload["attendees"]), 1)
            self.assertEqual(
                payload["attendees"][0]["emailAddress"]["address"],
                "colleague@example.com",
            )
        finally:
            calendar.GraphClient = orig_client


class SharePointInputCoercionTests(unittest.TestCase):
    def test_upload_text_file_empty_or_root_folder_path(self):
        client = MockGraphClient(put_response={"id": "item1", "name": "notes.txt"})
        orig_client = sharepoint.GraphClient
        sharepoint.GraphClient = lambda user_id: client
        try:
            # Empty folder path should not create double slash //
            asyncio.run(sharepoint.upload_text_file("user1", folder_path="", filename="notes.txt", content="hi"))
            self.assertEqual(client.last_bytes_path, "/me/drive/root:/notes.txt:/content")

            # Slash-only folder path
            asyncio.run(sharepoint.upload_text_file("user1", folder_path="/", filename="notes.txt", content="hi"))
            self.assertEqual(client.last_bytes_path, "/me/drive/root:/notes.txt:/content")

            # Normal folder path
            asyncio.run(sharepoint.upload_text_file("user1", folder_path="Notes/Work", filename="notes.txt", content="hi"))
            self.assertEqual(client.last_bytes_path, "/me/drive/root:/Notes/Work/notes.txt:/content")
        finally:
            sharepoint.GraphClient = orig_client


if __name__ == "__main__":
    unittest.main()
