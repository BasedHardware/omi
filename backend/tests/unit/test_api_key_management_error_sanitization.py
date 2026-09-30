"""Hermetic unit tests for error sanitization in the api_key_management router.

Verifies that:
1. All exception handlers in api_key_management.py sanitize error details via _sanitize_api_key_error.
2. The _sanitize_api_key_error helper logs internal diagnostic information and returns
   clean, constant fallback messages to callers without exposing database internals or tracebacks.
3. No raw detail=str(exc) or detail=str(e) leaks remain in api_key_management.py (tripwire check).
4. Behavioral executions for ApiKeyValidationError return sanitized HTTP 422 responses,
   and unexpected backend exceptions return HTTP 500 without leaking stack traces.
"""

from __future__ import annotations

from pathlib import Path
import re
import sys
import unittest
from unittest.mock import MagicMock, patch

BACKEND_DIR = Path(__file__).resolve().parents[2]
API_KEY_ROUTER_FILE = BACKEND_DIR / "routers" / "api_key_management.py"

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


def _get_function_source(router_path: Path, function_name: str) -> str:
    source = router_path.read_text(encoding="utf-8")
    start = source.index(f"def {function_name}")
    match = re.search(r"\n(?:@|def |async def |class )", source[start + 1 :])
    if match:
        return source[start : start + 1 + match.start()]
    return source[start:]


class ApiKeyManagementErrorSanitizationTests(unittest.TestCase):
    _stubbed_modules: dict = {}
    _sanitize_fn = None
    _router_mod = None

    @classmethod
    def setUpClass(cls):
        # Only stub external database and observability side-effects, leaving pure models untouched
        stub_names = [
            "database",
            "database.dev_api_key",
            "database.mcp_api_key",
            "utils.dev_cache",
            "utils.observability",
            "utils.observability.api_keys",
        ]
        for mod in stub_names:
            if mod not in sys.modules:
                mock_mod = MagicMock()
                cls._stubbed_modules[mod] = mock_mod
                sys.modules[mod] = mock_mod

        try:
            from routers.api_key_management import (
                _sanitize_api_key_error,
                create_developer_key,
                create_mcp_key,
            )
            import routers.api_key_management as api_key_mod
        except ImportError:
            import api_key_management as api_key_mod
            from api_key_management import (
                _sanitize_api_key_error,
                create_developer_key,
                create_mcp_key,
            )

        from database.api_key_metadata import ApiKeyValidationError, ApiKeyRevocationUnavailableError
        from models.mcp_api_key import McpApiKeyCreate
        from models.dev_api_key import DevApiKeyCreate

        cls._sanitize_fn = staticmethod(_sanitize_api_key_error)
        cls._router_mod = api_key_mod
        cls._ApiKeyValidationError = ApiKeyValidationError
        cls._ApiKeyRevocationUnavailableError = ApiKeyRevocationUnavailableError
        cls._McpApiKeyCreate = McpApiKeyCreate
        cls._DevApiKeyCreate = DevApiKeyCreate

    @classmethod
    def tearDownClass(cls):
        for mod in cls._stubbed_modules:
            sys.modules.pop(mod, None)

    def test_sanitize_api_key_error_behavior(self):
        fallback = "Invalid API key parameters"
        sanitize = self._sanitize_fn

        # 1. Any ValueError strictly returns safe fallback key
        self.assertEqual(
            sanitize(ValueError("clean_error_code"), fallback),
            fallback,
        )

        # 2. Raw traceback filtered to fallback
        self.assertEqual(
            sanitize(
                ValueError("Traceback (most recent call last):\n  File 'x.py', line 1\nZeroDivisionError"),
                fallback,
            ),
            fallback,
        )

        # 3. Firestore / internal paths filtered to fallback
        self.assertEqual(
            sanitize(
                self._ApiKeyValidationError(
                    "google.cloud.exceptions.Conflict: 409 Document in firestore users/123/keys/456"
                ),
                fallback,
            ),
            fallback,
        )

        # 4. Multiline error text filtered to fallback
        self.assertEqual(
            sanitize(ValueError("line 1\nline 2 sensitive redis info"), fallback),
            fallback,
        )

        # 5. Empty exception detail falls back cleanly
        self.assertEqual(
            sanitize(RuntimeError(""), fallback),
            fallback,
        )

    def test_static_tripwire_no_raw_str_exc_leak(self):
        target_path = API_KEY_ROUTER_FILE
        if not target_path.exists():
            target_path = Path(__file__).parent / "api_key_management.py"
        source = target_path.read_text(encoding="utf-8")

        self.assertNotIn("detail=str(exc)", source)
        self.assertNotIn("detail=str(e)", source)
        self.assertNotIn("detail=str(error)", source)
        self.assertIn("_sanitize_api_key_error", source)

    def test_source_handlers_route_through_sanitizer(self):
        target_path = API_KEY_ROUTER_FILE
        if not target_path.exists():
            target_path = Path(__file__).parent / "api_key_management.py"

        source_mcp = _get_function_source(target_path, "create_mcp_key")
        self.assertIn("_sanitize_api_key_error", source_mcp)
        self.assertIn("API key name must not contain a raw API key", source_mcp)
        self.assertIn("Invalid MCP API key app_id", source_mcp)
        self.assertIn("Invalid API key parameters", source_mcp)
        self.assertIn("Failed to create API key", source_mcp)

        source_dev = _get_function_source(target_path, "create_developer_key")
        self.assertIn("_sanitize_api_key_error", source_dev)
        self.assertIn("API key name must not contain a raw API key", source_dev)
        self.assertIn("Invalid API key parameters", source_dev)
        self.assertIn("Failed to create API key", source_dev)

    def test_create_mcp_key_sanitized_exceptions(self):
        from fastapi import HTTPException

        router_mod = self._router_mod
        create_mcp_key = router_mod.create_mcp_key
        mock_req = self._McpApiKeyCreate(name="valid_name")

        # 1. ApiKeyValidationError containing raw API key -> HTTP 422
        with patch.object(
            router_mod.mcp_api_key_db,
            "create_mcp_key",
            side_effect=self._ApiKeyValidationError(
                "API key name must not contain a raw API key: omi_mcp_abcd1234efgh"
            ),
        ):
            with self.assertRaises(HTTPException) as ctx:
                create_mcp_key(mock_req, uid="user-1")
            self.assertEqual(ctx.exception.status_code, 422)
            self.assertEqual(ctx.exception.detail, "API key name must not contain a raw API key")

        # 2. ApiKeyValidationError containing app_id error -> HTTP 422
        with patch.object(
            router_mod.mcp_api_key_db,
            "create_mcp_key",
            side_effect=self._ApiKeyValidationError("Invalid MCP API key app_id: internal_sensitive_id"),
        ):
            with self.assertRaises(HTTPException) as ctx:
                create_mcp_key(mock_req, uid="user-1")
            self.assertEqual(ctx.exception.status_code, 422)
            self.assertEqual(ctx.exception.detail, "Invalid MCP API key app_id")

        # 3. Unexpected server-side fault -> HTTP 500
        with patch.object(
            router_mod.mcp_api_key_db,
            "create_mcp_key",
            side_effect=RuntimeError("internal formatting failure in key generator"),
        ):
            with self.assertRaises(HTTPException) as ctx:
                create_mcp_key(mock_req, uid="user-1")
            self.assertEqual(ctx.exception.status_code, 500)
            self.assertEqual(ctx.exception.detail, "Failed to create API key")

    def test_create_developer_key_sanitized_exceptions(self):
        from fastapi import HTTPException

        router_mod = self._router_mod
        create_developer_key = router_mod.create_developer_key
        mock_req = self._DevApiKeyCreate(name="valid_dev_key", scopes=None)

        # 1. ApiKeyValidationError containing raw API key -> HTTP 422
        with patch.object(
            router_mod.dev_api_key_db,
            "create_dev_key",
            side_effect=self._ApiKeyValidationError(
                "API key name must not contain a raw API key: omi_dev_9876543210ab"
            ),
        ):
            with self.assertRaises(HTTPException) as ctx:
                create_developer_key(mock_req, uid="user-1")
            self.assertEqual(ctx.exception.status_code, 422)
            self.assertEqual(ctx.exception.detail, "API key name must not contain a raw API key")

        # 2. Generic ApiKeyValidationError -> HTTP 422
        with patch.object(
            router_mod.dev_api_key_db,
            "create_dev_key",
            side_effect=self._ApiKeyValidationError("internal metadata schema validation failure"),
        ):
            with self.assertRaises(HTTPException) as ctx:
                create_developer_key(mock_req, uid="user-1")
            self.assertEqual(ctx.exception.status_code, 422)
            self.assertEqual(ctx.exception.detail, "Invalid API key parameters")

        # 3. Unexpected server-side fault -> HTTP 500
        with patch.object(
            router_mod.dev_api_key_db,
            "create_dev_key",
            side_effect=Exception("firestore transaction failure"),
        ):
            with self.assertRaises(HTTPException) as ctx:
                create_developer_key(mock_req, uid="user-1")
            self.assertEqual(ctx.exception.status_code, 500)
            self.assertEqual(ctx.exception.detail, "Failed to create API key")


if __name__ == "__main__":
    unittest.main()
