"""Hermetic unit tests for omi-ms365-app services hardening.

Covers null guards, malformed response handling, clamp bounds, and Retry-After parsing.
Requires zero external network access and runs with pure Python standard library.
"""
from __future__ import annotations

import asyncio
from pathlib import Path
import sys
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

# Ensure plugins/omi-ms365-app is on sys.path
APP_DIR = Path(__file__).resolve().parent
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

# Mock httpx and services.auth if not present to ensure standard library hermeticity
if "httpx" not in sys.modules:
    try:
        import httpx
    except ImportError:
        mock_httpx = MagicMock()
        mock_httpx.AsyncClient = MagicMock
        sys.modules["httpx"] = mock_httpx

if "services.auth" not in sys.modules:
    mock_auth = MagicMock()
    mock_auth.get_access_token = AsyncMock(return_value="mock-access-token")
    sys.modules["services.auth"] = mock_auth

from services import calendar, graph_client, mail, sharepoint, teams
from services.graph_client import _parse_retry_after


class TestGraphClientHardening(unittest.TestCase):
    def test_parse_retry_after_none_or_empty(self):
        self.assertEqual(_parse_retry_after(None, default=2), 2)
        self.assertEqual(_parse_retry_after("", default=5), 5)
        self.assertEqual(_parse_retry_after("   ", default=3), 3)

    def test_parse_retry_after_integer(self):
        self.assertEqual(_parse_retry_after("10"), 10)
        self.assertEqual(_parse_retry_after(" 0 "), 0)
        self.assertEqual(_parse_retry_after("-5", default=2), 0)

    def test_parse_retry_after_http_date(self):
        future_date = "Wed, 21 Oct 2099 07:28:00 GMT"
        parsed = _parse_retry_after(future_date, default=2)
        self.assertGreater(parsed, 1000)

        past_date = "Wed, 21 Oct 2000 07:28:00 GMT"
        self.assertEqual(_parse_retry_after(past_date, default=2), 0)

    def test_parse_retry_after_invalid_fallback(self):
        self.assertEqual(_parse_retry_after("not-a-valid-value", default=7), 7)
        self.assertEqual(_parse_retry_after("###@@@", default=4), 4)


class TestMailHardening(unittest.TestCase):
    def test_slim_message_null_and_malformed(self):
        self.assertEqual(mail._slim_message(None), {})
        self.assertEqual(mail._slim_message("invalid-type"), {})
        self.assertEqual(mail._slim_message(123), {})

        # Empty dict returns None for fields
        slim = mail._slim_message({})
        self.assertIsNone(slim["id"])
        self.assertIsNone(slim["subject"])
        self.assertEqual(slim["from"], {})
        self.assertIsNone(slim["is_read"])

        # Dict with malformed nested from
        slim2 = mail._slim_message({"from": "string-not-dict"})
        self.assertEqual(slim2["from"], {})

        slim3 = mail._slim_message({"from": {"emailAddress": None}})
        self.assertEqual(slim3["from"], {})

        slim4 = mail._slim_message({"from": {"emailAddress": {"address": "test@example.com", "name": "Test"}}})
        self.assertEqual(slim4["from"], {"address": "test@example.com", "name": "Test"})

    def test_extract_recipients(self):
        self.assertEqual(mail._extract_recipients(None), [])
        self.assertEqual(mail._extract_recipients("invalid"), [])
        self.assertEqual(mail._extract_recipients([None, "bad", 456]), [])

        recips = mail._extract_recipients([
            {"emailAddress": {"name": "Alice", "address": "alice@example.com"}},
            {"emailAddress": None},
            {"emailAddress": {"address": "bob@example.com"}},
            "string-item",
        ])
        self.assertEqual(len(recips), 2)
        self.assertEqual(recips[0]["name"], "Alice")
        self.assertEqual(recips[0]["address"], "alice@example.com")
        self.assertEqual(recips[1]["address"], "bob@example.com")

    def test_list_recent_and_search_null_value(self):
        async def run():
            with patch("services.mail.GraphClient") as mock_gc_cls:
                mock_gc = AsyncMock()
                mock_gc.__aenter__.return_value = mock_gc
                mock_gc.get.return_value = {"value": None}
                mock_gc_cls.return_value = mock_gc

                res = await mail.list_recent("u1", limit=100)
                self.assertEqual(res, [])

                # Verify limit was clamped to 50
                mock_gc.get.assert_called_once()
                call_params = mock_gc.get.call_args[1]["params"]
                self.assertEqual(call_params["$top"], 50)

                mock_gc.get.return_value = {
                    "value": [
                        None,
                        "string-val",
                        {"id": "msg1", "subject": "Hello", "isRead": True},
                    ]
                }
                res2 = await mail.search("u1", query="test")
                self.assertEqual(len(res2), 1)
                self.assertEqual(res2[0]["id"], "msg1")

        asyncio.run(run())

    def test_read_null_fields(self):
        async def run():
            with patch("services.mail.GraphClient") as mock_gc_cls:
                mock_gc = AsyncMock()
                mock_gc.__aenter__.return_value = mock_gc
                mock_gc.get.return_value = {
                    "id": "msg1",
                    "subject": None,
                    "body": None,
                    "toRecipients": None,
                    "ccRecipients": None,
                    "from": None,
                }
                mock_gc_cls.return_value = mock_gc

                res = await mail.read("u1", "msg1")
                self.assertEqual(res["id"], "msg1")
                self.assertIsNone(res["subject"])
                self.assertIsNone(res["body"])
                self.assertEqual(res["to"], [])
                self.assertEqual(res["cc"], [])
                self.assertEqual(res["from"], {})

        asyncio.run(run())


class TestTeamsHardening(unittest.TestCase):
    def test_list_recent_chats_null_and_clamp(self):
        async def run():
            with patch("services.teams.GraphClient") as mock_gc_cls:
                mock_gc = AsyncMock()
                mock_gc.__aenter__.return_value = mock_gc
                mock_gc.get.return_value = {
                    "value": [
                        None,
                        {"id": "chat1", "topic": "General", "chatType": "group"},
                        "invalid-chat",
                    ]
                }
                mock_gc_cls.return_value = mock_gc

                chats = await teams.list_recent_chats("u1", limit=0)
                # limit clamped to 1
                mock_gc.get.assert_called_once()
                self.assertEqual(mock_gc.get.call_args[1]["params"]["$top"], 1)
                self.assertEqual(len(chats), 1)
                self.assertEqual(chats[0]["id"], "chat1")

        asyncio.run(run())

    def test_list_my_teams_null_value(self):
        async def run():
            with patch("services.teams.GraphClient") as mock_gc_cls:
                mock_gc = AsyncMock()
                mock_gc.__aenter__.return_value = mock_gc
                mock_gc.get.return_value = {"value": None}
                mock_gc_cls.return_value = mock_gc

                res = await teams.list_my_teams("u1")
                self.assertEqual(res, [])

        asyncio.run(run())

    def test_send_chat_message_and_create_meeting_non_dict_response(self):
        async def run():
            with patch("services.teams.GraphClient") as mock_gc_cls:
                mock_gc = AsyncMock()
                mock_gc.__aenter__.return_value = mock_gc
                mock_gc.post.return_value = "non-dict-string-response"
                mock_gc_cls.return_value = mock_gc

                msg = await teams.send_chat_message("u1", "chat1", "hello")
                self.assertIsNone(msg["id"])
                self.assertEqual(msg["status"], "sent")

                mtg = await teams.create_online_meeting("u1", "Meeting 1", "2026-10-01T10:00:00Z", "2026-10-01T11:00:00Z")
                self.assertIsNone(mtg["id"])
                self.assertIsNone(mtg["join_url"])

        asyncio.run(run())


class TestSharepointHardening(unittest.TestCase):
    def test_slim_item_null_and_malformed(self):
        self.assertEqual(sharepoint._slim_item(None), {})
        self.assertEqual(sharepoint._slim_item("invalid"), {})
        self.assertEqual(sharepoint._slim_item(999), {})

        item = sharepoint._slim_item({})
        self.assertIsNone(item["id"])
        self.assertFalse(item["folder"])
        self.assertIsNone(item["mime"])

        folder_item = sharepoint._slim_item({"folder": {}})
        self.assertTrue(folder_item["folder"])

        file_item = sharepoint._slim_item({"file": {"mimeType": "application/pdf"}})
        self.assertFalse(file_item["folder"])
        self.assertEqual(file_item["mime"], "application/pdf")

    def test_list_recent_and_search_files_null_value(self):
        async def run():
            with patch("services.sharepoint.GraphClient") as mock_gc_cls:
                mock_gc = AsyncMock()
                mock_gc.__aenter__.return_value = mock_gc
                mock_gc.get.return_value = {"value": None}
                mock_gc_cls.return_value = mock_gc

                res = await sharepoint.list_recent_files("u1", limit=999)
                self.assertEqual(res, [])
                self.assertEqual(mock_gc.get.call_args[1]["params"]["$top"], 50)

                mock_gc.get.return_value = {"value": [None, "bad", {"id": "f1", "name": "doc.txt"}]}
                res2 = await sharepoint.search_files("u1", "query")
                self.assertEqual(len(res2), 1)
                self.assertEqual(res2[0]["id"], "f1")

        asyncio.run(run())


class TestCalendarHardening(unittest.TestCase):
    def test_slim_event_null_and_malformed(self):
        self.assertEqual(calendar._slim_event(None), {})
        self.assertEqual(calendar._slim_event(42), {})
        self.assertEqual(calendar._slim_event("string"), {})

        ev = calendar._slim_event({})
        self.assertIsNone(ev["id"])
        self.assertIsNone(ev["subject"])
        self.assertIsNone(ev["start"])
        self.assertIsNone(ev["end"])
        self.assertIsNone(ev["location"])
        self.assertIsNone(ev["organizer"])
        self.assertIsNone(ev["join_url"])

        ev2 = calendar._slim_event({
            "id": "e1",
            "subject": "Sync",
            "start": {"dateTime": "2026-09-17T10:00:00Z"},
            "end": {"dateTime": "2026-09-17T10:30:00Z"},
            "location": {"displayName": "Room 1"},
            "organizer": {"emailAddress": {"name": "Bob", "address": "bob@omi.me"}},
            "onlineMeeting": {"joinUrl": "https://teams.microsoft.com/l/meetup"},
        })
        self.assertEqual(ev2["id"], "e1")
        self.assertEqual(ev2["subject"], "Sync")
        self.assertEqual(ev2["start"], "2026-09-17T10:00:00Z")
        self.assertEqual(ev2["location"], "Room 1")
        self.assertEqual(ev2["organizer"], "bob@omi.me")
        self.assertEqual(ev2["join_url"], "https://teams.microsoft.com/l/meetup")

    def test_list_upcoming_null_value(self):
        async def run():
            with patch("services.calendar.GraphClient") as mock_gc_cls:
                mock_gc = AsyncMock()
                mock_gc.__aenter__.return_value = mock_gc
                mock_gc.get.return_value = {"value": None}
                mock_gc_cls.return_value = mock_gc

                res = await calendar.list_upcoming("u1")
                self.assertEqual(res, [])

        asyncio.run(run())

    def test_find_free_slots_null_and_malformed_suggestions(self):
        async def run():
            with patch("services.calendar.GraphClient") as mock_gc_cls:
                mock_gc = AsyncMock()
                mock_gc.__aenter__.return_value = mock_gc
                mock_gc.post.return_value = {"meetingTimeSuggestions": None}
                mock_gc_cls.return_value = mock_gc

                res = await calendar.find_free_slots("u1", duration_minutes=30, attendees=["colleague@example.com"])
                self.assertEqual(res, [])

                # Malformed suggestion items
                mock_gc.post.return_value = {
                    "meetingTimeSuggestions": [
                        None,
                        "string",
                        {},  # missing meetingTimeSlot
                        {"meetingTimeSlot": None},
                        {"meetingTimeSlot": {"start": None, "end": None}},
                        {
                            "meetingTimeSlot": {
                                "start": {"dateTime": "2026-09-17T09:00:00.0000000"},
                                "end": {"dateTime": "2026-09-17T09:30:00.0000000"},
                            },
                            "confidence": 100.0,
                        },
                    ]
                }
                res2 = await calendar.find_free_slots("u1", duration_minutes=30, attendees=["colleague@example.com"])
                self.assertEqual(len(res2), 1)
                self.assertEqual(res2[0]["start"], "2026-09-17T09:00:00.0000000")
                self.assertEqual(res2[0]["end"], "2026-09-17T09:30:00.0000000")
                self.assertEqual(res2[0]["confidence"], 100.0)

        asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
