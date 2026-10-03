"""Hermetic unit tests for focus_sessions read-boundary poison-document hardening.

Verifies that malformed, legacy, non-dict, or exception-raising Firestore documents
are safely logged (without PII) and skipped at both the database layer and router layer,
preventing FastAPI ResponseValidationError (HTTP 500) crashes.
"""

from __future__ import annotations

import importlib.abc
import importlib.machinery
import logging
import os
import sys
import types
import unittest
from datetime import datetime, timezone
from typing import Any
from unittest.mock import MagicMock, patch

try:
    import email.message  # noqa: F401
    import anyio.from_thread  # noqa: F401
except ImportError:
    pass



# Configure safe test environment
os.environ.setdefault("OPENAI_API_KEY", "sk-test-not-real")
os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)

# Ensure backend root is in sys.path
_BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

from testing.import_isolation import AutoMockModule, stub_modules

# Hermetic isolation stubs for external cloud and telemetry packages
_STUB_MODULES = [
    "google",
    "google.api_core",
    "google.api_core.exceptions",
    "google.cloud",
    "google.cloud.firestore",
    "google.cloud.firestore_v1",
    "google.cloud.firestore_v1.base_query",
    "google.cloud.storage",
    "firebase_admin",
    "firebase_admin.auth",
    "firebase_admin.firestore",
    "redis",
    "sentry_sdk",
    "requests",
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
    "prometheus_client",
    "database._client",
    "utils.other.storage",
]

_fakes = {}
for _name in _STUB_MODULES:
    _m = AutoMockModule(_name)
    _m.__path__ = []
    _fakes[_name] = _m

with stub_modules(_fakes):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    import database.focus_sessions as focus_sessions_db
    from models.focus_session import FocusSession
    import routers.focus_sessions as focus_sessions_router
    from utils.other import endpoints as auth



class _FakeSnapshot:
    """Mock Firestore DocumentSnapshot."""

    def __init__(self, doc_id: str, data: Any, exc: Exception | None = None):
        self.id = doc_id
        self._data = data
        self._exc = exc

    def to_dict(self) -> Any:
        if self._exc is not None:
            raise self._exc
        return self._data


class TestFocusSessionModelDeserialization(unittest.TestCase):
    """Unit tests for FocusSession.deserialize_many_safe."""

    def test_deserialize_many_safe_skips_malformed_and_non_dict_records(self):
        """Malformed or non-dict records must be skipped while valid records parse completely."""
        now = datetime.now(timezone.utc)
        records = [
            # Valid record 1
            {
                "id": "valid-1",
                "status": "focused",
                "app_or_site": "VS Code",
                "description": "Deep coding session",
                "created_at": now,
                "duration_seconds": 1800,
            },
            # Missing required 'status'
            {
                "id": "bad-missing-status",
                "app_or_site": "Browser",
                "description": "Missing status field",
                "created_at": now,
            },
            # Missing required 'id'
            {
                "status": "distracted",
                "app_or_site": "Twitter",
                "description": "Missing ID field",
                "created_at": now,
            },
            # Missing required 'created_at'
            {
                "id": "bad-missing-date",
                "status": "focused",
                "app_or_site": "Terminal",
                "description": "Missing created_at field",
            },
            # Corrupted created_at type (cannot be parsed as datetime)
            {
                "id": "bad-corrupt-date",
                "status": "focused",
                "app_or_site": "Terminal",
                "description": "Invalid date type",
                "created_at": {"not": "a date"},
            },
            # Non-dict / non-Mapping items
            None,
            "corrupted-string-row",
            12345,
            ["list", "item"],
            # Valid record 2
            {
                "id": "valid-2",
                "status": "distracted",
                "app_or_site": "YouTube",
                "description": "Watching conference talks",
                "created_at": now.isoformat(),
                "duration_seconds": 600,
            },
        ]

        errors_captured: list[tuple[Any, Exception]] = []

        def _on_error(record: Any, exc: Exception) -> None:
            errors_captured.append((record, exc))

        parsed = FocusSession.deserialize_many_safe(records, on_error=_on_error)

        # Only the two valid records should be returned
        self.assertEqual(len(parsed), 2)
        self.assertEqual([s.id for s in parsed], ["valid-1", "valid-2"])
        self.assertEqual(parsed[0].status, "focused")
        self.assertEqual(parsed[0].duration_seconds, 1800)
        self.assertEqual(parsed[1].status, "distracted")
        self.assertEqual(parsed[1].duration_seconds, 600)

        # 8 malformed/non-dict items should trigger on_error
        self.assertEqual(len(errors_captured), 8)
        # Verify non-dict items raised TypeError
        type_errors = [e for r, e in errors_captured if isinstance(e, TypeError)]
        self.assertEqual(len(type_errors), 4)


class TestFocusSessionsRouterBoundary(unittest.TestCase):
    """Hermetic router boundary tests for GET /v1/focus-sessions."""

    def setUp(self):
        self.app = FastAPI()
        self.app.include_router(focus_sessions_router.router)
        self.test_uid = "user_boundary_test_987"
        self.app.dependency_overrides[auth.get_current_user_uid] = lambda: self.test_uid
        self.client = TestClient(self.app)

    def tearDown(self):
        self.app.dependency_overrides.clear()

    def test_get_focus_sessions_returns_200_and_filters_poisoned_docs(self):
        """Poisoned stored records must not raise ResponseValidationError HTTP 500."""
        now_iso = datetime.now(timezone.utc).isoformat()
        db_raw_data = [
            # Valid session 1
            {
                "id": "fs-good-1",
                "status": "focused",
                "app_or_site": "PyCharm",
                "description": "Writing tests",
                "message": "Concentrated",
                "created_at": now_iso,
                "duration_seconds": 1500,
            },
            # Poisoned: missing description
            {
                "id": "fs-bad-no-desc",
                "status": "focused",
                "app_or_site": "PyCharm",
                "created_at": now_iso,
            },
            # Poisoned: invalid datetime string
            {
                "id": "fs-bad-date",
                "status": "focused",
                "app_or_site": "PyCharm",
                "description": "Invalid timestamp format",
                "created_at": "invalid-iso-timestamp-never-parse",
            },
            # Poisoned: non-dict
            None,
            "corrupted_raw_string",
            # Valid session 2
            {
                "id": "fs-good-2",
                "status": "distracted",
                "app_or_site": "Reddit",
                "description": "Browsing news",
                "message": None,
                "created_at": now_iso,
                "duration_seconds": 300,
            },
        ]

        with patch.object(focus_sessions_db, "get_focus_sessions", return_value=db_raw_data):
            response = self.client.get("/v1/focus-sessions")

        self.assertEqual(response.status_code, 200)
        json_data = response.json()
        self.assertIsInstance(json_data, list)
        self.assertEqual(len(json_data), 2)
        self.assertEqual([item["id"] for item in json_data], ["fs-good-1", "fs-good-2"])
        self.assertEqual(json_data[0]["app_or_site"], "PyCharm")
        self.assertEqual(json_data[1]["app_or_site"], "Reddit")


class TestFocusSessionsNonPIILogging(unittest.TestCase):
    """Logging verification to ensure zero PII leaks."""

    def setUp(self):
        self.app = FastAPI()
        self.app.include_router(focus_sessions_router.router)
        self.test_uid = "secret_uid_pii_alpha_999"
        self.app.dependency_overrides[auth.get_current_user_uid] = lambda: self.test_uid
        self.client = TestClient(self.app)

    def tearDown(self):
        self.app.dependency_overrides.clear()

    def test_router_logging_strict_non_pii(self):
        """Skipped session warnings must only log document ID and exception class name."""
        sensitive_desc = "Patient medical diagnosis and consultation record secret"
        sensitive_msg = "Top secret authentication token: bearer_xyz123abc"
        poisoned_records = [
            {
                "id": "doc-poison-77",
                "status": "focused",
                "app_or_site": "SecretApp",
                "description": sensitive_desc,
                "message": sensitive_msg,
                "created_at": {"invalid": "object"},  # Validation error
            },
            None,  # Non-dict
        ]

        with self.assertLogs("routers.focus_sessions", level="WARNING") as captured_logs:
            with patch.object(focus_sessions_db, "get_focus_sessions", return_value=poisoned_records):
                response = self.client.get("/v1/focus-sessions")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), [])

        # Check log lines for exact non-PII format
        log_text = "\n".join(captured_logs.output)
        self.assertIn("Skipping malformed focus session doc-poison-77:", log_text)
        self.assertIn("Skipping malformed focus session unknown:", log_text)

        # Strictly assert NO PII, auth headers, or raw content was logged
        self.assertNotIn(self.test_uid, log_text)
        self.assertNotIn(sensitive_desc, log_text)
        self.assertNotIn(sensitive_msg, log_text)
        self.assertNotIn("bearer_xyz123abc", log_text)
        self.assertNotIn("SecretApp", log_text)



class TestDatabaseGetFocusSessionsStreamResilience(unittest.TestCase):
    """Database stream snapshot exception handling and malformed doc skipping."""

    def test_database_get_focus_sessions_stream_exception_resilience(self):
        """Corrupted snapshots, snapshot exceptions, and empty/non-dict docs must be skipped."""
        now = datetime(2026, 10, 3, 10, 0, tzinfo=timezone.utc)
        snapshots = [
            # Valid snapshot 1
            _FakeSnapshot(
                "snap-1",
                {
                    "status": "focused",
                    "app_or_site": "Xcode",
                    "description": "iOS Development",
                    "created_at": now,
                    "duration_seconds": 1200,
                },
            ),
            # Snapshot whose to_dict() raises RuntimeError
            _FakeSnapshot("snap-broken-stream", None, exc=RuntimeError("Firestore stream socket dropped")),
            # Snapshot whose to_dict() returns None
            _FakeSnapshot("snap-none", None),
            # Snapshot whose to_dict() returns empty dict
            _FakeSnapshot("snap-empty", {}),
            # Snapshot whose to_dict() returns non-dict
            _FakeSnapshot("snap-string", "raw_string_not_dict"),
            # Valid snapshot 2
            _FakeSnapshot(
                "snap-2",
                {
                    "status": "distracted",
                    "app_or_site": "Slack",
                    "description": "Checking channels",
                    "created_at": now,
                    "duration_seconds": 300,
                },
            ),
        ]

        mock_col = MagicMock()
        mock_query = MagicMock()
        mock_col.order_by.return_value = mock_query
        mock_query.where.return_value = mock_query
        mock_query.offset.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.stream.return_value = snapshots

        with self.assertLogs("database.focus_sessions", level="WARNING") as captured_logs:
            with patch.object(focus_sessions_db, "_user_col", return_value=mock_col):
                results = focus_sessions_db.get_focus_sessions("user_resilience_test")

        # Must cleanly return only the 2 valid docs
        self.assertEqual(len(results), 2)
        self.assertEqual([r["id"] for r in results], ["snap-1", "snap-2"])
        self.assertEqual(results[0]["status"], "focused")
        self.assertEqual(results[1]["status"], "distracted")

        # Must log non-PII warnings for bad snapshots
        log_text = "\n".join(captured_logs.output)
        self.assertIn("Skipping malformed focus session snap-broken-stream: RuntimeError", log_text)
        self.assertIn("Skipping malformed focus session snap-none: EmptyOrNonDictDocument", log_text)
        self.assertIn("Skipping malformed focus session snap-empty: EmptyOrNonDictDocument", log_text)
        self.assertIn("Skipping malformed focus session snap-string: EmptyOrNonDictDocument", log_text)

        # Ensure no user credentials or user ID in database logs
        self.assertNotIn("user_resilience_test", log_text)


if __name__ == "__main__":
    unittest.main()
