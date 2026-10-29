"""Regression tests for input validation and error boundaries in backend/routers/conversation_mutations.py.

Issue #19094 — durable conversation sync mutations router must validate conversation_id,
map operation ValueError/TypeError to 400, catch unexpected persistence errors with
sanitized 500 responses, and align failure telemetry.
"""

import ast
from datetime import datetime, timezone
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# Minimal environment bootstrap
# ---------------------------------------------------------------------------
os.environ.setdefault("ENCRYPTION_SECRET", "test-secret-key-for-unit-tests")

_BACKEND = os.path.join(os.path.dirname(__file__), os.pardir, os.pardir)
if os.path.isdir(_BACKEND) and os.path.abspath(_BACKEND) not in sys.path:
    sys.path.insert(0, os.path.abspath(_BACKEND))

_ROUTER_PATH = os.path.join(
    os.path.dirname(__file__), os.pardir, os.pardir, "routers", "conversation_mutations.py"
)


# ---------------------------------------------------------------------------
# 1) Static Analysis
# ---------------------------------------------------------------------------


class TestConversationMutationsSourceSanitization(unittest.TestCase):
    """Static analysis: source checks on conversation_mutations.py."""

    def test_no_raw_str_exc_in_detail(self):
        """detail=str(exc) must never appear in conversation_mutations router."""
        with open(_ROUTER_PATH, "r", encoding="utf-8") as fh:
            source = fh.read()
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.keyword) and node.arg == "detail":
                src_fragment = ast.get_source_segment(source, node.value)
                self.assertNotIn(
                    "str(exc)",
                    src_fragment or "",
                    "Found raw detail=str(exc) in conversation_mutations router — CWE-209 leak",
                )
                self.assertNotIn(
                    "str(e)",
                    src_fragment or "",
                    "Found raw detail=str(e) in conversation_mutations router — CWE-209 leak",
                )

    def test_generic_exception_boundary_exists(self):
        """apply_conversation_sync_mutation must have a generic except Exception guard."""
        with open(_ROUTER_PATH, "r", encoding="utf-8") as fh:
            source = fh.read()
        tree = ast.parse(source)
        found_generic_except = False
        for node in ast.walk(tree):
            if isinstance(node, ast.ExceptHandler):
                if node.type is None or (isinstance(node.type, ast.Name) and node.type.id == "Exception"):
                    found_generic_except = True
                    break
        self.assertTrue(
            found_generic_except,
            "apply_conversation_sync_mutation must include a generic 'except Exception' error boundary",
        )


# ---------------------------------------------------------------------------
# 2) Behavioral Tests
# ---------------------------------------------------------------------------


def _make_app():
    from routers import conversation_mutations as router_module
    from utils.other import endpoints as auth

    app = FastAPI()
    app.dependency_overrides[auth.get_current_user_uid] = lambda: "user-123"
    app.include_router(router_module.router)
    return app


def _valid_payload():
    return {
        "client_mutation_id": "mut_12345",
        "base_revision": datetime.now(timezone.utc).isoformat(),
        "operation": {
            "type": "set_title",
            "title": "Strategy Discussion",
        },
    }


def _dummy_response():
    return {
        "status": "ok",
        "client_mutation_id": "mut_12345",
        "conversation_id": "conv_abc123",
        "conversation": {
            "revision": datetime.now(timezone.utc).isoformat(),
            "title": "Strategy Discussion",
            "starred": False,
            "folder_id": None,
            "visibility": "private",
        },
    }


class TestConversationMutationsValidationAndBoundaries(unittest.TestCase):
    """Behavioral tests for input validation, error handling, and telemetry."""

    def setUp(self):
        from routers import conversation_mutations as router_module
        self.router_module = router_module

    def test_whitespace_conversation_id_returns_400(self):
        """Empty or whitespace-only conversation_id returns HTTP 400."""
        app = _make_app()
        client = TestClient(app)
        for bad_id in ["%20", "%20%20%20", "   "]:
            resp = client.post(
                f"/v1/conversations/{bad_id}/mutations",
                json=_valid_payload(),
            )
            self.assertEqual(resp.status_code, 400)
            self.assertIn("conversation_id", resp.json().get("detail", "").lower())

    @patch("routers.conversation_mutations.record_product_event")
    def test_operation_value_error_returns_400(self, mock_record_event):
        """ValueError in operation handling returns HTTP 400 with error telemetry."""
        with patch.object(
            self.router_module.mutations_db,
            "apply_conversation_sync_mutation",
            side_effect=ValueError("Invalid operation type: unknown_op"),
        ):
            app = _make_app()
            client = TestClient(app)
            resp = client.post(
                "/v1/conversations/conv_123/mutations",
                json=_valid_payload(),
            )
            self.assertEqual(resp.status_code, 400)
            mock_record_event.assert_called_with(
                "conversation_sync_mutation",
                request=unittest.mock.ANY,
                outcome="error",
            )

    @patch("routers.conversation_mutations.record_product_event")
    def test_operation_type_error_returns_400(self, mock_record_event):
        """TypeError in operation handling returns HTTP 400 with error telemetry."""
        with patch.object(
            self.router_module.mutations_db,
            "apply_conversation_sync_mutation",
            side_effect=TypeError("Unexpected operation field types"),
        ):
            app = _make_app()
            client = TestClient(app)
            resp = client.post(
                "/v1/conversations/conv_123/mutations",
                json=_valid_payload(),
            )
            self.assertEqual(resp.status_code, 400)
            mock_record_event.assert_called_with(
                "conversation_sync_mutation",
                request=unittest.mock.ANY,
                outcome="error",
            )

    @patch("routers.conversation_mutations.record_product_event")
    @patch("routers.conversation_mutations.logger")
    def test_database_internal_error_returns_500_sanitized(self, mock_logger, mock_record_event):
        """Unexpected internal errors return HTTP 500 without leaking stack traces."""
        leak_msg = "Firestore transport reset at collection users/user-123/conversations/conv_123"
        with patch.object(
            self.router_module.mutations_db,
            "apply_conversation_sync_mutation",
            side_effect=RuntimeError(leak_msg),
        ):
            app = _make_app()
            client = TestClient(app)
            resp = client.post(
                "/v1/conversations/conv_123/mutations",
                json=_valid_payload(),
            )
            self.assertEqual(resp.status_code, 500)
            body = resp.json()
            self.assertNotIn("users/user-123", body.get("detail", ""))
            self.assertNotIn("Firestore transport", body.get("detail", ""))
            self.assertEqual(body.get("detail"), "Failed to apply conversation mutation")
            mock_record_event.assert_called_with(
                "conversation_sync_mutation",
                request=unittest.mock.ANY,
                outcome="error",
            )
            mock_logger.error.assert_called()

    @patch("routers.conversation_mutations.record_product_event")
    def test_success_applied_records_telemetry(self, mock_record_event):
        """Happy path applies mutation and records outcome='applied'."""
        with patch.object(
            self.router_module.mutations_db,
            "apply_conversation_sync_mutation",
            return_value=(_dummy_response(), False),
        ):
            app = _make_app()
            client = TestClient(app)
            resp = client.post(
                "/v1/conversations/conv_123/mutations",
                json=_valid_payload(),
            )
            self.assertEqual(resp.status_code, 200)
            mock_record_event.assert_called_with(
                "conversation_sync_mutation",
                request=unittest.mock.ANY,
                outcome="applied",
            )


if __name__ == "__main__":
    unittest.main()
