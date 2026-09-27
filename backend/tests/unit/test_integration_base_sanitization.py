"""Hermetic unit tests verifying exception sanitization in integration_base.py.

Ensures that internal database exceptions, token refresh errors, and value parsing
errors are never leaked to user-facing tool outputs or chat contexts.
"""

import importlib
import importlib.util
import os
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)


def _pkg(name):
    mod = sys.modules.get(name)
    if mod is None or not hasattr(mod, "__path__"):
        mod = types.ModuleType(name)
        mod.__path__ = []
        sys.modules[name] = mod
    return mod


def _mod(name):
    mod = sys.modules.get(name)
    if mod is None:
        mod = types.ModuleType(name)
        sys.modules[name] = mod
    return mod


def _load(module_name, rel_path):
    if module_name in sys.modules:
        return sys.modules[module_name]
    spec = importlib.util.spec_from_file_location(module_name, str(BACKEND_DIR / rel_path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return mod


for _p in [
    "database",
    "utils",
    "utils.retrieval",
    "utils.retrieval.tools",
]:
    _pkg(_p)

for _name, _attrs in {
    "database.users": ["get_integration"],
    "utils.retrieval.agentic": ["agent_config_context"],
}.items():
    _m = _mod(_name)
    for _a in _attrs:
        if not hasattr(_m, _a):
            setattr(_m, _a, MagicMock())

sys.path.insert(0, str(BACKEND_DIR))

integration_base = _load(
    "utils.retrieval.tools._test_integration_base",
    "utils/retrieval/tools/integration_base.py",
)


class TestIntegrationBaseSanitization(unittest.IsolatedAsyncioTestCase):
    """Verify all error return paths in integration_base sanitize internal exceptions."""

    def test_get_integration_checked_database_exception_sanitized(self):
        secret_leak = "postgres://admin:secret_pass_123@db.prod.internal:5432/omi"
        with patch.object(integration_base.users_db, "get_integration", side_effect=RuntimeError(secret_leak)):
            result, err = integration_base.get_integration_checked(
                "user_123",
                "google_calendar",
                "Google Calendar",
                "Not connected",
                "Error fetching Google Calendar integration",
            )
            self.assertIsNone(result)
            self.assertEqual(err, "Error fetching Google Calendar integration. Please try again later.")
            self.assertNotIn(secret_leak, err)

    def test_parse_iso_with_tz_invalid_format_sanitized(self):
        result, err = integration_base.parse_iso_with_tz(
            "start_time", "not-a-valid-iso-date", "in format YYYY-MM-DDTHH:MM:SS+HH:MM"
        )
        self.assertIsNone(result)
        self.assertEqual(
            err,
            "Error: Invalid start_time format. Expected in format YYYY-MM-DDTHH:MM:SS+HH:MM: not-a-valid-iso-date",
        )

    def test_retry_on_auth_unexpected_exception_sanitized(self):
        secret_leak = "internal_upstream_connection_failed_token_xyz"
        call_fn = MagicMock(side_effect=RuntimeError(secret_leak))
        refresh_fn = MagicMock()

        result, err = integration_base.retry_on_auth(
            call_fn,
            {"param": "val"},
            refresh_fn,
            "user_123",
            {"connected": True},
            "Token expired",
        )
        self.assertIsNone(result)
        self.assertEqual(err, "Error executing request. Please try again later.")
        self.assertNotIn(secret_leak, err)
        refresh_fn.assert_not_called()

    def test_retry_on_auth_refresh_second_failure_sanitized(self):
        secret_leak = "internal_auth_refresh_pipeline_broken_db_leak"
        call_fn = MagicMock(side_effect=[Exception("401 token may be expired"), RuntimeError(secret_leak)])
        refresh_fn = MagicMock(return_value="new_access_token")

        result, err = integration_base.retry_on_auth(
            call_fn,
            {"param": "val"},
            refresh_fn,
            "user_123",
            {"connected": True},
            "Token expired",
        )
        self.assertIsNone(result)
        self.assertEqual(err, "Error after token refresh. Please try again later.")
        self.assertNotIn(secret_leak, err)

    async def test_retry_on_auth_async_unexpected_exception_sanitized(self):
        secret_leak = "async_internal_timeout_socket_error_cluster_888"
        call_fn = AsyncMock(side_effect=RuntimeError(secret_leak))
        refresh_fn = AsyncMock()

        result, err = await integration_base.retry_on_auth_async(
            call_fn,
            {"param": "val"},
            refresh_fn,
            "user_123",
            {"connected": True},
            "Token expired",
        )
        self.assertIsNone(result)
        self.assertEqual(err, "Error executing request. Please try again later.")
        self.assertNotIn(secret_leak, err)
        refresh_fn.assert_not_called()

    async def test_retry_on_auth_async_refresh_second_failure_sanitized(self):
        secret_leak = "async_token_rotation_internal_failure_secret_credentials"
        call_fn = AsyncMock(side_effect=[Exception("Authentication failed 401"), RuntimeError(secret_leak)])
        refresh_fn = AsyncMock(return_value="new_async_token")

        result, err = await integration_base.retry_on_auth_async(
            call_fn,
            {"param": "val"},
            refresh_fn,
            "user_123",
            {"connected": True},
            "Token expired",
        )
        self.assertIsNone(result)
        self.assertEqual(err, "Error after token refresh. Please try again later.")
        self.assertNotIn(secret_leak, err)


if __name__ == "__main__":
    unittest.main()
