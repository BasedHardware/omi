"""Regression tests for CWE-209 sanitization in backend/routers/api_key_management.py.

Issue #18939 — the API key management router must never reflect raw internal exception
details, raw API tokens, or caller PII back to external clients in HTTP 422 responses.

Tests verify:
1. Static analysis: no raw ``detail=str(exc)`` appears in api_key_management.py.
2. Behavioral tests: ApiKeyValidationError with token or PII is masked via sanitize().
3. Behavioral tests: safe caller domain messages remain intact.
4. Auditing: validation errors are logged as warnings server-side.
"""

import ast
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

from fastapi import HTTPException

# ---------------------------------------------------------------------------
# Minimal environment bootstrap
# ---------------------------------------------------------------------------
os.environ.setdefault("ENCRYPTION_SECRET", "test-secret-key-for-unit-tests")

_BACKEND = os.path.join(os.path.dirname(__file__), os.pardir, os.pardir)
if os.path.isdir(_BACKEND) and os.path.abspath(_BACKEND) not in sys.path:
    sys.path.insert(0, os.path.abspath(_BACKEND))

_ROUTER_PATH = os.path.join(
    os.path.dirname(__file__), os.pardir, os.pardir, "routers", "api_key_management.py"
)


# ---------------------------------------------------------------------------
# 1) Static analysis
# ---------------------------------------------------------------------------


class TestApiKeyManagementSourceSanitization(unittest.TestCase):
    """Static analysis: no raw detail=str(exc) in api_key_management.py."""

    def test_no_raw_str_exc_in_detail(self):
        """detail=str(exc) must never appear in api_key_management.py."""
        with open(_ROUTER_PATH, "r", encoding="utf-8") as fh:
            source = fh.read()
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.keyword) and node.arg == "detail":
                src_fragment = ast.get_source_segment(source, node.value)
                self.assertNotIn(
                    "str(exc)",
                    src_fragment or "",
                    "Found raw detail=str(exc) in api_key_management router — CWE-209 leak",
                )
                self.assertNotIn(
                    "str(e)",
                    src_fragment or "",
                    "Found raw detail=str(e) in api_key_management router — CWE-209 leak",
                )


# ---------------------------------------------------------------------------
# 2) Behavioral tests
# ---------------------------------------------------------------------------


class TestApiKeyManagementSanitizationBehavior(unittest.TestCase):
    """Behavioral tests: tokens and PII are masked in 422 responses."""

    def setUp(self):
        from routers import api_key_management as routes

        self.routes = routes

    @patch("routers.api_key_management.logger")
    def test_create_mcp_key_sanitizes_token_in_validation_error(self, mock_logger):
        """MCP key creation masks token-like strings in validation error details."""
        from database.api_key_metadata import ApiKeyValidationError

        leak_message = "Token omi_mcp_12345678901234567890123456789012 is invalid"
        mock_create = MagicMock(side_effect=ApiKeyValidationError(leak_message))

        with patch.object(self.routes.mcp_api_key_db, "create_mcp_key", mock_create):
            payload = self.routes.McpApiKeyCreate(name="test-key")
            with self.assertRaises(HTTPException) as cm:
                self.routes.create_mcp_key(payload, uid="user-123")

            self.assertEqual(cm.exception.status_code, 422)
            # Full raw token must NEVER be present in client-facing detail
            self.assertNotIn("omi_mcp_12345678901234567890123456789012", cm.exception.detail)
            # Masked token format must be used
            self.assertIn("***", cm.exception.detail)
            mock_logger.warning.assert_called()

    @patch("routers.api_key_management.logger")
    def test_create_developer_key_sanitizes_pii_and_token(self, mock_logger):
        """Developer key creation masks tokens and emails in validation error details."""
        from database.api_key_metadata import ApiKeyValidationError

        leak_message = "Key omi_dev_abcdef1234567890abcdef1234567890 for john.doe@example.com failed"
        mock_create = MagicMock(side_effect=ApiKeyValidationError(leak_message))

        with patch.object(self.routes.dev_api_key_db, "create_dev_key", mock_create):
            payload = self.routes.DevApiKeyCreate(name="dev-key")
            with self.assertRaises(HTTPException) as cm:
                self.routes.create_developer_key(payload, uid="user-123")

            self.assertEqual(cm.exception.status_code, 422)
            self.assertNotIn("omi_dev_abcdef1234567890abcdef1234567890", cm.exception.detail)
            self.assertNotIn("john.doe@example.com", cm.exception.detail)
            self.assertIn("j***e@example.com", cm.exception.detail)
            mock_logger.warning.assert_called()

    def test_create_mcp_key_preserves_safe_validation_detail(self):
        """Safe domain messages without tokens pass through unchanged."""
        from database.api_key_metadata import ApiKeyValidationError

        safe_message = "API key name must not contain a raw API key"
        mock_create = MagicMock(side_effect=ApiKeyValidationError(safe_message))

        with patch.object(self.routes.mcp_api_key_db, "create_mcp_key", mock_create):
            payload = self.routes.McpApiKeyCreate(name="safe-name")
            with self.assertRaises(HTTPException) as cm:
                self.routes.create_mcp_key(payload, uid="user-123")

            self.assertEqual(cm.exception.status_code, 422)
            self.assertEqual(cm.exception.detail, safe_message)

    def test_create_developer_key_preserves_safe_validation_detail(self):
        """Safe domain messages without tokens pass through unchanged."""
        from database.api_key_metadata import ApiKeyValidationError

        safe_message = "API key name must not contain a raw API key"
        mock_create = MagicMock(side_effect=ApiKeyValidationError(safe_message))

        with patch.object(self.routes.dev_api_key_db, "create_dev_key", mock_create):
            payload = self.routes.DevApiKeyCreate(name="safe-name")
            with self.assertRaises(HTTPException) as cm:
                self.routes.create_developer_key(payload, uid="user-123")

            self.assertEqual(cm.exception.status_code, 422)
            self.assertEqual(cm.exception.detail, safe_message)


if __name__ == "__main__":
    unittest.main()
