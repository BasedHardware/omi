"""Hermetic unit tests for error sanitization and service resilience in the Mobile Feedback router.

Verifies that:
1. Mobile feedback router handles Firestore database and service connectivity exceptions gracefully,
   returning sanitized 503 error responses without exposing internal error details or stack traces.
2. Telemetry failures (PostHog/product events) never crash user-facing HTTP 201 receipt responses.
3. Input validation rejects empty feedback_id or target_id with clean 422 Unprocessable Entity.
4. Static check ensures no raw detail=str(exc) or internal error leakage in backend/routers/mobile_feedback.py.
"""

from __future__ import annotations

from enum import Enum
import logging
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
from typing import Any, Literal, Optional
import unittest
from unittest.mock import MagicMock, patch

from pydantic import BaseModel, Field

_candidates = [
    Path(__file__).resolve().parents[2] / "routers" / "mobile_feedback.py",
    Path(__file__).resolve().parents[1] / "routers" / "mobile_feedback.py",
    Path(__file__).resolve().parent / "mobile_feedback.py",
    Path("routers/mobile_feedback.py").resolve(),
    Path("backend/routers/mobile_feedback.py").resolve(),
    Path("mobile_feedback.py").resolve(),
]
FEEDBACK_ROUTER_FILE = next((p for p in _candidates if p.exists()), None)
BACKEND_DIR = (
    Path(__file__).resolve().parents[2]
    if len(Path(__file__).resolve().parents) >= 3
    else Path(__file__).resolve().parent
)
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


# Define real Pydantic models for testing router registration
class _FeedbackSurface(str, Enum):
    conversation_summary = "conversation_summary"
    recording_quality = "recording_quality"


class _FeedbackTargetKind(str, Enum):
    conversation = "conversation"
    recording = "recording"


class _MobileFeedbackKind(str, Enum):
    summary_helpfulness = "summary_helpfulness"
    recording_quality = "recording_quality"


class _MobileFeedbackReceipt(BaseModel):
    schema_version: Literal["mobile_feedback_receipt.v1"] = "mobile_feedback_receipt.v1"
    feedback_id: str
    event_id: str
    created: bool
    persisted: Literal[True] = True


class _MobileFeedbackRequest(BaseModel):
    schema_version: Literal["mobile_feedback.v1"] = "mobile_feedback.v1"
    feedback_id: str = Field(min_length=1, max_length=128)
    kind: _MobileFeedbackKind
    target_kind: Optional[str] = None
    target_id: str
    value: int = -1
    reason: Optional[Any] = None
    comment: Optional[str] = None
    app_version: Optional[str] = None
    app_build: Optional[str] = None
    platform: Optional[str] = None
    client_app_namespace: Optional[str] = None
    client_app_profile: Optional[str] = None
    correlation_id: Optional[str] = None


class _MockFeedbackIdempotencyConflict(Exception):
    pass


class _MockFeedbackPersistenceError(Exception):
    pass


class MobileFeedbackErrorSanitizationTests(unittest.TestCase):
    _stubbed_modules: dict = {}

    @classmethod
    def setUpClass(cls):
        # Setup models.feedback if not already loaded with real models
        if "models.feedback" not in sys.modules:
            models_mod = ModuleType("models")
            feedback_models = ModuleType("models.feedback")
            feedback_models.FeedbackSurface = _FeedbackSurface
            feedback_models.FeedbackTargetKind = _FeedbackTargetKind
            feedback_models.MobileFeedbackKind = _MobileFeedbackKind
            feedback_models.MobileFeedbackReceipt = _MobileFeedbackReceipt
            feedback_models.MobileFeedbackRequest = _MobileFeedbackRequest
            models_mod.feedback = feedback_models
            sys.modules["models"] = models_mod
            sys.modules["models.feedback"] = feedback_models

        stub_names = [
            "database",
            "database.conversations",
            "database.feedback",
            "database.recording_sessions",
            "utils",
            "utils.other",
            "utils.other.endpoints",
            "utils.product_metrics",
            "utils.product_telemetry",
        ]
        for mod in stub_names:
            if mod not in sys.modules:
                mock_mod = MagicMock()
                cls._stubbed_modules[mod] = mock_mod
                sys.modules[mod] = mock_mod

        # Ensure parent-child relationships for stubs
        sys.modules["database"].conversations = sys.modules["database.conversations"]
        sys.modules["database"].feedback = sys.modules["database.feedback"]
        sys.modules["database"].recording_sessions = sys.modules["database.recording_sessions"]
        sys.modules["utils"].other = sys.modules["utils.other"]
        sys.modules["utils.other"].endpoints = sys.modules["utils.other.endpoints"]
        sys.modules["utils"].product_metrics = sys.modules["utils.product_metrics"]
        sys.modules["utils"].product_telemetry = sys.modules["utils.product_telemetry"]

        # Ensure custom exception classes inherit from Exception
        if not hasattr(sys.modules["database.feedback"], "FeedbackIdempotencyConflict") or not isinstance(
            sys.modules["database.feedback"].FeedbackIdempotencyConflict, type
        ):
            sys.modules["database.feedback"].FeedbackIdempotencyConflict = _MockFeedbackIdempotencyConflict
        if not hasattr(sys.modules["database.feedback"], "FeedbackPersistenceError") or not isinstance(
            sys.modules["database.feedback"].FeedbackPersistenceError, type
        ):
            sys.modules["database.feedback"].FeedbackPersistenceError = _MockFeedbackPersistenceError

    def setUp(self):
        # Fresh router import
        if "mobile_feedback" in sys.modules:
            del sys.modules["mobile_feedback"]
        if "routers.mobile_feedback" in sys.modules:
            del sys.modules["routers.mobile_feedback"]
        if "backend.routers.mobile_feedback" in sys.modules:
            del sys.modules["backend.routers.mobile_feedback"]

        try:
            from routers import mobile_feedback as mf_mod
        except ModuleNotFoundError:
            try:
                from backend.routers import mobile_feedback as mf_mod
            except ModuleNotFoundError:
                import mobile_feedback as mf_mod

        self.mf = mf_mod

        # Reset all mocks in stubbed modules
        self.mf.conversations_db.get_conversation = MagicMock(return_value={"id": "conv-default"})
        self.mf.recording_sessions_db.get_recording_session = MagicMock(return_value=None)
        self.mf.feedback_db.record_feedback_event_idempotent = MagicMock(return_value=("event-default", True))
        self.mf.emit_product_event = MagicMock()

    def test_static_analysis_no_unhandled_raw_exception_detail_leak(self):
        """Ensure backend/routers/mobile_feedback.py contains zero raw exception detail leaks."""
        self.assertIsNotNone(FEEDBACK_ROUTER_FILE, "mobile_feedback.py file must be locatable")
        content = FEEDBACK_ROUTER_FILE.read_text(encoding="utf-8")
        self.assertNotIn("detail=str(e)", content)
        self.assertNotIn("detail=str(exc)", content)
        self.assertNotIn("detail=str(err)", content)
        self.assertNotIn("detail=str(error)", content)

    def test_submit_mobile_feedback_empty_feedback_id_raises_422(self):
        """Whitespace or empty feedback_id must raise 422 with clear message."""
        from fastapi import HTTPException

        payload = _MobileFeedbackRequest(
            feedback_id="   ",
            target_id="conv-1",
            kind=_MobileFeedbackKind.summary_helpfulness,
        )

        with self.assertRaises(HTTPException) as ctx:
            self.mf.submit_mobile_feedback(payload=payload, uid="user-123")
        self.assertEqual(ctx.exception.status_code, 422)
        self.assertIn("feedback_id cannot be empty", ctx.exception.detail)

    def test_submit_mobile_feedback_empty_target_id_raises_422(self):
        """Whitespace or empty target_id must raise 422 with clear message."""
        from fastapi import HTTPException

        payload = _MobileFeedbackRequest(
            feedback_id="f-123",
            target_id="   ",
            kind=_MobileFeedbackKind.summary_helpfulness,
        )

        with self.assertRaises(HTTPException) as ctx:
            self.mf.submit_mobile_feedback(payload=payload, uid="user-123")
        self.assertEqual(ctx.exception.status_code, 422)
        self.assertIn("target_id cannot be empty", ctx.exception.detail)

    def test_submit_mobile_feedback_summary_db_error_raises_503(self):
        """Database exception when fetching conversation must raise sanitized 503."""
        from fastapi import HTTPException

        payload = _MobileFeedbackRequest(
            feedback_id="f-123",
            target_id="conv-1",
            kind=_MobileFeedbackKind.summary_helpfulness,
            target_kind="conversation",
        )

        self.mf.conversations_db.get_conversation.side_effect = RuntimeError("Firestore connection timeout")

        with self.assertRaises(HTTPException) as ctx:
            self.mf.submit_mobile_feedback(payload=payload, uid="user-123")
        self.assertEqual(ctx.exception.status_code, 503)
        self.assertEqual(ctx.exception.detail, "Conversation service temporarily unavailable")

    def test_submit_mobile_feedback_recording_lookup_db_error_raises_503(self):
        """Database error fetching recording session must raise sanitized 503."""
        from fastapi import HTTPException

        payload = _MobileFeedbackRequest(
            feedback_id="f-123",
            target_id="rec-1",
            kind=_MobileFeedbackKind.recording_quality,
            target_kind="recording",
        )

        self.mf.recording_sessions_db.get_recording_session.side_effect = RuntimeError("Disk IO Error")

        with self.assertRaises(HTTPException) as ctx:
            self.mf.submit_mobile_feedback(payload=payload, uid="user-123")
        self.assertEqual(ctx.exception.status_code, 503)
        self.assertEqual(ctx.exception.detail, "Recording ownership is temporarily unavailable")

    def test_submit_mobile_feedback_fallback_conversation_db_error_raises_503(self):
        """Database error during legacy fallback conversation lookup must raise sanitized 503."""
        from fastapi import HTTPException

        payload = _MobileFeedbackRequest(
            feedback_id="f-123",
            target_id="conv-1",
            kind=_MobileFeedbackKind.recording_quality,
            target_kind=None,
        )

        self.mf.recording_sessions_db.get_recording_session.return_value = None
        self.mf.conversations_db.get_conversation.side_effect = RuntimeError("Firestore unavailable")

        with self.assertRaises(HTTPException) as ctx:
            self.mf.submit_mobile_feedback(payload=payload, uid="user-123")
        self.assertEqual(ctx.exception.status_code, 503)
        self.assertEqual(ctx.exception.detail, "Conversation service temporarily unavailable")

    def test_submit_mobile_feedback_related_conversation_error_proceeds_gracefully(self):
        """Failure to fetch provenance for a related conversation logs a warning and does not crash."""
        payload = _MobileFeedbackRequest(
            feedback_id="f-123",
            target_id="rec-1",
            kind=_MobileFeedbackKind.recording_quality,
            target_kind="recording",
            value=1,
            app_version="1.0.0",
            app_build="100",
            platform="ios",
            client_app_namespace="com.test",
            client_app_profile="prod",
            correlation_id="c-1",
        )

        self.mf.recording_sessions_db.get_recording_session.return_value = {"conversation_id": "conv-rel"}
        self.mf.conversations_db.get_conversation.side_effect = RuntimeError("Related conv lookup failed")
        self.mf.feedback_db.record_feedback_event_idempotent.return_value = ("event-123", True)

        receipt = self.mf.submit_mobile_feedback(payload=payload, uid="user-123")
        self.assertEqual(receipt.event_id, "event-123")
        self.assertTrue(receipt.created)

    def test_submit_mobile_feedback_persistence_db_error_raises_503(self):
        """Generic database persistence exception must be caught and return 503."""
        from fastapi import HTTPException

        payload = _MobileFeedbackRequest(
            feedback_id="f-123",
            target_id="conv-1",
            kind=_MobileFeedbackKind.summary_helpfulness,
            target_kind="conversation",
            value=-1,
        )

        self.mf.conversations_db.get_conversation.return_value = {"id": "conv-1"}
        self.mf.feedback_db.record_feedback_event_idempotent.side_effect = RuntimeError("GoogleCloudError: 503 DB busy")

        with self.assertRaises(HTTPException) as ctx:
            self.mf.submit_mobile_feedback(payload=payload, uid="user-123")
        self.assertEqual(ctx.exception.status_code, 503)
        self.assertIn("Feedback could not be durably stored", ctx.exception.detail)

    def test_submit_mobile_feedback_idempotency_conflict_raises_409(self):
        """Idempotency conflict must return HTTP 409."""
        from fastapi import HTTPException

        payload = _MobileFeedbackRequest(
            feedback_id="f-conflict",
            target_id="conv-1",
            kind=_MobileFeedbackKind.summary_helpfulness,
            target_kind="conversation",
            value=1,
        )

        self.mf.conversations_db.get_conversation.return_value = {"id": "conv-1"}
        conflict_instance = self.mf.feedback_db.FeedbackIdempotencyConflict("conflict")
        self.mf.feedback_db.record_feedback_event_idempotent.side_effect = conflict_instance

        with self.assertRaises(HTTPException) as ctx:
            self.mf.submit_mobile_feedback(payload=payload, uid="user-123")
        self.assertEqual(ctx.exception.status_code, 409)
        self.assertIn("feedback_id was already used for a different event", ctx.exception.detail)

    def test_submit_mobile_feedback_telemetry_failure_does_not_crash_receipt(self):
        """Telemetry failure during emit_product_event must be suppressed so HTTP 201 receipt succeeds."""
        payload = _MobileFeedbackRequest(
            feedback_id="f-123",
            target_id="conv-1",
            kind=_MobileFeedbackKind.summary_helpfulness,
            target_kind="conversation",
            value=1,
        )

        self.mf.conversations_db.get_conversation.return_value = {"id": "conv-1"}
        self.mf.feedback_db.record_feedback_event_idempotent.return_value = ("event-999", True)
        self.mf.emit_product_event.side_effect = ConnectionError("PostHog endpoint unreachable")

        receipt = self.mf.submit_mobile_feedback(payload=payload, uid="user-123")
        self.assertEqual(receipt.event_id, "event-999")
        self.assertTrue(receipt.created)


if __name__ == "__main__":
    unittest.main()
