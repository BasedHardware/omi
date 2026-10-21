"""Unit tests for safe chat session deserialization and validation in /v2/chat-sessions.

Verifies that legacy or malformed Firestore chat_session documents (missing required
fields, corrupted timestamps, or missing IDs) are cleanly skipped rather than causing
FastAPI ResponseValidationError (HTTP 500) for the user.
Also verifies that blank/whitespace titles are rejected on update.
"""

import importlib.abc
import importlib.machinery
import os
import sys
import types
import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from pydantic import ValidationError

os.environ.setdefault("OPENAI_API_KEY", "sk-test-not-real")
os.environ.setdefault("ENCRYPTION_SECRET", "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv")

_STUB = (
    "database",
    "utils",
    "firebase_admin",
    "google",
    "pinecone",
    "typesense",
    "opuslib",
    "pydub",
    "pusher",
    "modal",
    "ulid",
    "langchain",
    "langchain_core",
    "stripe",
    "openai",
    "anthropic",
    "redis",
    "sentry_sdk",
    "requests",
)


def _is_stubbed_name(name):
    return any(name == p or name.startswith(p + ".") for p in _STUB)


def _snapshot():
    return {name: module for name, module in sys.modules.items() if _is_stubbed_name(name)}


def _clear():
    for name in list(sys.modules):
        if _is_stubbed_name(name):
            sys.modules.pop(name, None)


def _restore(snapshot):
    for name in list(sys.modules):
        if _is_stubbed_name(name) and name not in snapshot:
            sys.modules.pop(name, None)
    sys.modules.update(snapshot)


class _AutoMock(types.ModuleType):
    __path__ = []

    def __getattr__(self, name):
        if name.startswith("__") and name.endswith("__"):
            raise AttributeError(name)
        m = MagicMock()
        setattr(self, name, m)
        return m


class _Finder(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    def find_spec(self, name, path=None, target=None):
        if _is_stubbed_name(name):
            return importlib.machinery.ModuleSpec(name, self, is_package=True)
        return None

    def create_module(self, spec):
        return _AutoMock(spec.name)

    def exec_module(self, module):
        pass


_finder = _Finder()
_snap = _snapshot()
_clear()
sys.meta_path.insert(0, _finder)
try:
    from models.chat_session import ChatSessionResponse
    from routers import chat_sessions as chat_sessions_mod
    from routers.chat_sessions import CreateChatSessionRequest, UpdateChatSessionRequest
finally:
    sys.meta_path.remove(_finder)
    _restore(_snap)


class TestChatSessionsSafeDeserialization(unittest.TestCase):
    def setUp(self):
        self.now = datetime.now(timezone.utc)
        self.good_session_1 = {
            "id": "session-valid-1",
            "title": "General Chat",
            "preview": "Hello there",
            "created_at": self.now,
            "updated_at": self.now,
            "message_count": 5,
            "starred": False,
        }
        self.good_session_2 = {
            "id": "session-valid-2",
            "title": "Project Brainstorm",
            "preview": "Let's plan",
            "created_at": self.now,
            "updated_at": self.now,
            "message_count": 12,
            "starred": True,
        }

    def test_deserialize_many_safe_skips_malformed(self):
        """ChatSessionResponse.deserialize_many_safe must skip malformed rows without crashing."""
        records = [
            self.good_session_1,
            {"title": "Missing ID", "message_count": 1},  # missing required id
            None,  # non-dict record
            "string_record",  # non-dict
            {
                "id": "bad-dates",
                "title": "Broken Dates",
                "created_at": "invalid_date_format",
                "updated_at": "invalid_date_format",
            },
            self.good_session_2,
        ]

        skipped = []
        parsed = ChatSessionResponse.deserialize_many_safe(
            records, on_error=lambda rec, exc: skipped.append((rec, type(exc).__name__))
        )

        self.assertEqual(len(parsed), 2)
        self.assertEqual([s.id for s in parsed], ["session-valid-1", "session-valid-2"])
        self.assertEqual(len(skipped), 4)

    def test_get_chat_sessions_skips_corrupt_records(self):
        """GET /v2/chat-sessions must drop corrupt records and return valid ones without 500."""
        mock_records = [
            dict(self.good_session_1),
            {"id": "corrupt-1", "created_at": "invalid_date", "updated_at": "invalid_date"},
            {"title": "No ID record"},
            dict(self.good_session_2),
        ]

        with patch.object(chat_sessions_mod.chat_db, "get_chat_sessions", return_value=mock_records):
            result = chat_sessions_mod.get_chat_sessions(
                app_id=None, limit=50, offset=0, starred=None, uid="test-user"
            )

        self.assertEqual(len(result), 2)
        self.assertEqual([s.id for s in result], ["session-valid-1", "session-valid-2"])

    def test_get_chat_sessions_empty_list(self):
        """Empty list from db returns empty list."""
        with patch.object(chat_sessions_mod.chat_db, "get_chat_sessions", return_value=[]):
            result = chat_sessions_mod.get_chat_sessions(
                app_id=None, limit=50, offset=0, starred=None, uid="test-user"
            )
        self.assertEqual(result, [])

    def test_get_chat_session_by_id_graceful_on_corrupt_doc(self):
        """GET /v2/chat-sessions/{id} raises 404 rather than 500 if stored doc is corrupt."""
        corrupt_doc = {
            "id": "sess-broken",
            "created_at": "not-a-datetime",
            "updated_at": "not-a-datetime",
        }
        with patch.object(chat_sessions_mod.chat_db, "get_chat_session_by_id", return_value=corrupt_doc):
            with self.assertRaises(chat_sessions_mod.HTTPException) as ctx:
                chat_sessions_mod.get_chat_session("sess-broken", uid="test-user")
            self.assertEqual(ctx.exception.status_code, 404)
            self.assertEqual(ctx.exception.detail, "Chat session not found")

    def test_update_chat_session_request_rejects_blank_title(self):
        """UpdateChatSessionRequest must reject whitespace-only titles with 422."""
        with self.assertRaises(ValidationError):
            UpdateChatSessionRequest(title="   ")

        # Valid title is stripped
        req = UpdateChatSessionRequest(title="  Clean Title  ")
        self.assertEqual(req.title, "Clean Title")

        # Title None is allowed for starring updates
        req_star = UpdateChatSessionRequest(starred=True)
        self.assertIsNone(req_star.title)
        self.assertTrue(req_star.starred)

    def test_create_chat_session_request_strips_title(self):
        """CreateChatSessionRequest strips whitespace or sets None if blank."""
        req = CreateChatSessionRequest(title="  New Session  ")
        self.assertEqual(req.title, "New Session")

        req_blank = CreateChatSessionRequest(title="   ")
        self.assertIsNone(req_blank.title)


if __name__ == "__main__":
    unittest.main()
