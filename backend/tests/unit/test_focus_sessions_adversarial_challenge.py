"""Adversarial stress and verification harness for Focus Sessions read boundary.

Tests extreme malicious, malformed, corrupted, and adversarial inputs against:
1. FocusSession.deserialize_many_safe
2. GET /v1/focus-sessions router boundary
3. database.focus_sessions get_focus_sessions resilience
4. Non-PII logging guarantees under hostile data
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

try:
    import email.message  # noqa: F401
    import anyio.from_thread  # noqa: F401
except ImportError:
    pass


import pytest

from testing.import_isolation import AutoMockModule, stub_modules

# Mark the entire module as slow so it does not run in the fast PR unit lane
pytestmark = pytest.mark.slow

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


class _ExplodingId:
    """An object whose __str__ raises an exception to challenge logging robustness."""

    def __str__(self):
        raise RuntimeError("Exploding __str__")

    def __repr__(self):
        raise RuntimeError("Exploding __repr__")


class _ExplodingMapping(dict):
    """A dictionary whose get() method raises an unexpected exception."""

    def get(self, key, default=None):
        raise RuntimeError(f"Exploding get('{key}')")


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


class TestAdversarialDeserializationInputs(unittest.TestCase):
    """Adversarial stress testing against FocusSession.deserialize_many_safe."""

    def test_deserialize_many_safe_extreme_poisoned_inputs(self):
        """Inject an exhaustive battery of malformed records."""
        now = datetime.now(timezone.utc)
        valid_record_1 = {
            "id": "valid-clean-1",
            "status": "focused",
            "app_or_site": "Terminal",
            "description": "Standard clean task",
            "message": "Focus mode",
            "created_at": now,
            "duration_seconds": 1200,
        }
        valid_record_2 = {
            "id": "valid-clean-2",
            "status": "distracted",
            "app_or_site": "HackerNews",
            "description": "Reading articles",
            "message": None,
            "created_at": now.isoformat(),
            "duration_seconds": 0,
        }

        adversarial_inputs = [
            # 1. Negative durations (must fail Pydantic ge=0 check and be safely skipped)
            {
                "id": "bad-neg-duration-1",
                "status": "focused",
                "app_or_site": "App",
                "description": "Negative duration",
                "created_at": now,
                "duration_seconds": -1,
            },
            {
                "id": "bad-neg-duration-huge",
                "status": "focused",
                "app_or_site": "App",
                "description": "Huge negative duration",
                "created_at": now,
                "duration_seconds": -999999999999,
            },
            # 2. Corrupted status and description
            {
                "id": "bad-status-none",
                "status": None,
                "app_or_site": "App",
                "description": "None status",
                "created_at": now,
            },
            {
                "id": "bad-desc-none",
                "status": "focused",
                "app_or_site": "App",
                "description": None,
                "created_at": now,
            },
            # 3. Corrupted timestamps
            {
                "id": "bad-time-future-overflow",
                "status": "focused",
                "app_or_site": "App",
                "description": "Year 99999",
                "created_at": "99999-12-31T23:59:59Z",
            },
            {
                "id": "bad-time-empty-str",
                "status": "focused",
                "app_or_site": "App",
                "description": "Empty timestamp",
                "created_at": "",
            },
            {
                "id": "bad-time-garbage",
                "status": "focused",
                "app_or_site": "App",
                "description": "Garbage timestamp",
                "created_at": "\x00\x01\x02!@#$%^&*()_+",
            },
            {
                "id": "bad-time-boolean",
                "status": "focused",
                "app_or_site": "App",
                "description": "Boolean timestamp",
                "created_at": False,
            },
            {
                "id": "bad-time-nested-dict",
                "status": "focused",
                "app_or_site": "App",
                "description": "Nested dict timestamp",
                "created_at": {"epoch": 1700000000},
            },
            # 4. NaN / Infinity in duration_seconds
            {
                "id": "bad-duration-nan",
                "status": "focused",
                "app_or_site": "App",
                "description": "NaN duration",
                "created_at": now,
                "duration_seconds": float("nan"),
            },
            {
                "id": "bad-duration-inf",
                "status": "focused",
                "app_or_site": "App",
                "description": "Inf duration",
                "created_at": now,
                "duration_seconds": float("inf"),
            },
            # 5. Non-dict types
            None,
            "",
            "   ",
            123456789,
            999.999,
            True,
            False,
            [],
            [1, 2, 3],
            set(),
            tuple(),
            object(),
            # 6. Missing required fields
            {},
            {"status": "focused"},
            {"app_or_site": "Xcode"},
            {"description": "desc"},
            # 7. Ultra-large fields (stress memory/parser)
            {
                "id": "huge-payload-session",
                "status": "focused",
                "app_or_site": "A" * 10000,
                "description": "B" * 50000,
                "message": "C" * 10000,
                "created_at": now,
                "duration_seconds": 100,
            },
            # 8. Unicode & Injection strings in ID and other fields
            {
                "id": "id\nCRLF_INJECTION: true\r\nHeader: fake",
                "status": "focused",
                "app_or_site": "App\x00NullByte",
                "description": "Normal desc",
                "created_at": now,
                "duration_seconds": 50,
            },
        ]

        # Combine valid records with adversarial payload
        test_payload = [valid_record_1] + adversarial_inputs + [valid_record_2]

        error_calls = []

        def on_err(rec, exc):
            error_calls.append((rec, exc))

        results = FocusSession.deserialize_many_safe(test_payload, on_error=on_err)

        # Both valid clean records must be successfully extracted
        result_ids = [r.id for r in results]
        self.assertIn("valid-clean-1", result_ids)
        self.assertIn("valid-clean-2", result_ids)
        self.assertIn("huge-payload-session", result_ids)
        self.assertIn("id\nCRLF_INJECTION: true\r\nHeader: fake", result_ids)

        # Ensure no unhandled exceptions were thrown and errors were captured
        self.assertGreater(len(error_calls), 15)

    def test_deserialize_many_safe_with_empty_or_none_generator(self):
        """Generator input, empty iterable, or mixed generator should behave deterministically."""
        self.assertEqual(FocusSession.deserialize_many_safe([]), [])
        self.assertEqual(FocusSession.deserialize_many_safe(()), [])

        def gen():
            yield None
            yield 123
            yield {"bad": "record"}

        self.assertEqual(FocusSession.deserialize_many_safe(gen()), [])

    def test_deserialize_many_safe_exploding_fixtures(self):
        """Pass exploding poison fixtures to FocusSession.deserialize_many_safe to verify robustness."""
        now = datetime.now(timezone.utc)
        exploding_id_record = {
            "id": _ExplodingId(),
            "status": "focused",
            "app_or_site": "Xcode",
            "description": "Exploding ID desc",
            "created_at": now,
        }
        exploding_mapping_record = _ExplodingMapping(
            {
                "id": "exploding-map-01",
                "status": "focused",
                "app_or_site": "Slack",
                "description": None,  # triggers ValidationError to exercise poison skip and on_error
                "created_at": now,
            }
        )
        valid_survivor = {
            "id": "valid-survivor-1",
            "status": "focused",
            "app_or_site": "Terminal",
            "description": "Clean survivor",
            "created_at": now,
        }

        errors = []
        parsed = FocusSession.deserialize_many_safe(
            [exploding_id_record, exploding_mapping_record, valid_survivor],
            on_error=lambda rec, exc: errors.append((rec, exc)),
        )

        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0].id, "valid-survivor-1")
        self.assertEqual(len(errors), 2)


class TestAdversarialRouterBoundary(unittest.TestCase):
    """Adversarial stress testing against GET /v1/focus-sessions router."""

    def setUp(self):
        self.app = FastAPI()
        self.app.include_router(focus_sessions_router.router)
        self.test_uid = "user_adv_test_uid_444"
        self.app.dependency_overrides[auth.get_current_user_uid] = lambda: self.test_uid
        self.client = TestClient(self.app)

    def tearDown(self):
        self.app.dependency_overrides.clear()

    def test_router_never_raises_500_under_massive_adversarial_stream(self):
        """FastAPI must return 200 and never 500 when database produces hostile rows."""
        now = datetime.now(timezone.utc)
        hostile_db_data = [
            None,
            "corrupted_primitive_str",
            1234567,
            [],
            {},
            {
                "id": "doc-neg-duration",
                "status": "focused",
                "app_or_site": "App",
                "description": "d",
                "created_at": now,
                "duration_seconds": -500,
            },
            {"id": "doc-missing-all"},
            {"id": None, "status": "focused", "app_or_site": "App", "description": "d", "created_at": now},
            {
                "id": "doc-invalid-date",
                "status": "focused",
                "app_or_site": "App",
                "description": "d",
                "created_at": "not-valid-iso",
            },
            # Valid item in between
            {
                "id": "valid-doc-survivor-1",
                "status": "focused",
                "app_or_site": "VSCode",
                "description": "Survived intact",
                "message": None,
                "created_at": now.isoformat(),
                "duration_seconds": 60,
            },
            # More hostile data
            {
                "id": "doc-type-conflict",
                "status": ["focused"],
                "app_or_site": 999,
                "description": None,
                "created_at": None,
            },
            {
                "id": "doc-bad-unicode",
                "status": "focused",
                "app_or_site": "App",
                "description": "d",
                "created_at": "9999-99-99T99:99:99Z",
            },
            # Valid item 2
            {
                "id": "valid-doc-survivor-2",
                "status": "distracted",
                "app_or_site": "Twitter",
                "description": "Survived intact too",
                "message": "Quick break",
                "created_at": now.isoformat(),
                "duration_seconds": 300,
            },
        ]

        with patch.object(focus_sessions_db, "get_focus_sessions", return_value=hostile_db_data):
            response = self.client.get("/v1/focus-sessions")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data), 2)
        self.assertEqual(data[0]["id"], "valid-doc-survivor-1")
        self.assertEqual(data[1]["id"], "valid-doc-survivor-2")
        self.assertEqual(data[0]["status"], "focused")
        self.assertEqual(data[1]["status"], "distracted")

    def test_router_survives_exploding_fixtures_without_crash(self):
        """Pass exploding __str__ and get() poison fixtures through router without 500 or logger crash."""
        now = datetime.now(timezone.utc)
        exploding_id_record = {
            "id": _ExplodingId(),
            "status": "focused",
            "app_or_site": "Xcode",
            "description": "Exploding ID desc",
            "created_at": now,
        }
        exploding_mapping_record = _ExplodingMapping(
            {
                "id": "exploding-map-01",
                "status": "focused",
                "app_or_site": "Slack",
                "description": None,  # triggers ValidationError to exercise poison skip and error logging
                "created_at": now,
            }
        )
        valid_survivor = {
            "id": "valid-survivor-1",
            "status": "focused",
            "app_or_site": "Terminal",
            "description": "Clean survivor",
            "created_at": now.isoformat(),
        }

        with patch.object(
            focus_sessions_db,
            "get_focus_sessions",
            return_value=[exploding_id_record, exploding_mapping_record, valid_survivor],
        ):
            response = self.client.get("/v1/focus-sessions")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["id"], "valid-survivor-1")


class TestAdversarialPIILogging(unittest.TestCase):
    """Adversarial stress testing against logging leaks."""

    def setUp(self):
        self.app = FastAPI()
        self.app.include_router(focus_sessions_router.router)
        self.secret_token = "eyJhGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.SECRET_TOKEN_VALUE"
        self.patient_diagnosis = "Patient has severe confidential medical diagnosis 12345"
        self.credit_card = "4532-0150-1234-5678"
        self.user_secret_uid = "usr_super_secret_pii_identity_777"
        self.app.dependency_overrides[auth.get_current_user_uid] = lambda: self.user_secret_uid
        self.client = TestClient(self.app)

    def tearDown(self):
        self.app.dependency_overrides.clear()

    def test_pii_and_auth_tokens_strictly_absent_from_logs(self):
        """All user secrets embedded in poisoned documents must NOT leak into logs."""
        poisoned_records = [
            # Poisoned record containing PII in message and description
            {
                "id": "poison-pii-1",
                "status": "focused",
                "app_or_site": "HospitalPortal",
                "description": self.patient_diagnosis,
                "message": f"Authorization: Bearer {self.secret_token}",
                "created_at": "invalid_date_triggers_error",
            },
            # Poisoned record with PII in extra unexpected keys and invalid field type
            {
                "id": "poison-pii-2",
                "status": "distracted",
                "app_or_site": "BankingSite",
                "description": None,  # triggers ValidationError
                "credit_card_raw": self.credit_card,
                "created_at": datetime.now(timezone.utc),
            },
            # Poisoned record with PII in app_or_site and invalid description
            {
                "id": "poison-pii-3",
                "status": "focused",
                "app_or_site": f"https://mybank.com/user?card={self.credit_card}",
                "description": None,  # triggers ValidationError
                "created_at": datetime.now(timezone.utc),
            },
        ]

        with self.assertLogs("routers.focus_sessions", level="WARNING") as captured_logs:
            with patch.object(focus_sessions_db, "get_focus_sessions", return_value=poisoned_records):
                response = self.client.get("/v1/focus-sessions")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), [])

        full_logs = "\n".join(captured_logs.output)

        # Assert no sensitive contents leaked
        self.assertNotIn(self.secret_token, full_logs)
        self.assertNotIn(self.patient_diagnosis, full_logs)
        self.assertNotIn(self.credit_card, full_logs)
        self.assertNotIn(self.user_secret_uid, full_logs)
        self.assertNotIn("Bearer", full_logs)
        self.assertNotIn("HospitalPortal", full_logs)
        self.assertNotIn("BankingSite", full_logs)

        # Assert only doc id and exception class name are present
        for log_line in captured_logs.output:
            self.assertIn("Skipping malformed focus session", log_line)
            # Verify structure: "Skipping malformed focus session <doc_id>: <exc_class>"
            self.assertTrue(
                "ValidationError" in log_line or "TypeError" in log_line,
                f"Unexpected log line format: {log_line}",
            )


class TestDatabaseStreamHostileResilience(unittest.TestCase):
    """Adversarial testing on database.focus_sessions.get_focus_sessions."""

    def test_database_stream_handles_hostile_snapshots(self):
        """Snapshots with NaN, Inf, None data, or stream disruptions must not crash get_focus_sessions."""
        now = datetime(2026, 10, 3, 10, 0, tzinfo=timezone.utc)
        hostile_snapshots = [
            _FakeSnapshot(
                "snap-hostile-nan",
                {
                    "status": "focused",
                    "app_or_site": "Xcode",
                    "description": "iOS Development",
                    "created_at": now,
                    "duration_seconds": float("nan"),
                },
            ),
            _FakeSnapshot(
                "snap-hostile-inf",
                {
                    "status": "focused",
                    "app_or_site": "Xcode",
                    "description": "iOS Development",
                    "created_at": now,
                    "duration_seconds": float("inf"),
                },
            ),
            _FakeSnapshot("snap-stream-crash", None, exc=ConnectionResetError("Socket broken")),
            _FakeSnapshot(
                "snap-valid-intact",
                {
                    "status": "focused",
                    "app_or_site": "Safari",
                    "description": "Reading Docs",
                    "created_at": now,
                    "duration_seconds": 600,
                },
            ),
        ]

        mock_col = MagicMock()
        mock_query = MagicMock()
        mock_col.order_by.return_value = mock_query
        mock_query.where.return_value = mock_query
        mock_query.offset.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.stream.return_value = hostile_snapshots

        with patch.object(focus_sessions_db, "_user_col", return_value=mock_col):
            results = focus_sessions_db.get_focus_sessions("adversarial_test_uid")

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["id"], "snap-valid-intact")
        self.assertEqual(results[0]["duration_seconds"], 600)


if __name__ == "__main__":
    unittest.main()
