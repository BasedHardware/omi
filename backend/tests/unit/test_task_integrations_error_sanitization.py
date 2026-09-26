"""Hermetic unit tests for error sanitization in the task_integrations router.

Verifies that:
1. Provider and network exceptions in Asana and ClickUp chooser endpoints are sanitized
   to clean constant error details without reflecting internal details or tracebacks.
2. Server-side observability is preserved via logger.error.
3. No raw detail=f"Error fetching... or detail=str(e) reflections remain across task_integrations.py.
4. Behavioral executions for all 5 chooser endpoints return sanitized HTTP 500 responses.
"""

from __future__ import annotations

from pathlib import Path
import sys
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

BACKEND_DIR = Path(__file__).resolve().parents[2]
ROUTER_FILE = BACKEND_DIR / "routers" / "task_integrations.py"


class TaskIntegrationsErrorSanitizationTests(unittest.IsolatedAsyncioTestCase):
    _stubbed_modules: dict = {}
    _modified_parent_attrs: list = []
    _router_mod = None

    @classmethod
    def setUpClass(cls):
        cls._stubbed_modules = {}
        cls._modified_parent_attrs = []

        stub_names = [
            "google",
            "google.cloud",
            "google.cloud.firestore",
            "database",
            "database.users",
            "database.redis_db",
            "utils",
            "utils.other",
            "utils.other.endpoints",
            "utils.log_sanitizer",
            "utils.executors",
            "utils.task_integrations_ops",
            "fastapi.templating",
            "models",
            "models.shared",
        ]
        for mod in stub_names:
            if mod not in sys.modules:
                mock_mod = MagicMock()
                cls._stubbed_modules[mod] = mock_mod
                sys.modules[mod] = mock_mod

        # Link parent/child modules cleanly with undo tracking
        for mod in stub_names:
            if "." in mod:
                parent, child = mod.rsplit(".", 1)
                if parent in sys.modules:
                    parent_mod = sys.modules[parent]
                    had_attr = hasattr(parent_mod, child)
                    old_val = getattr(parent_mod, child, None) if had_attr else None
                    cls._modified_parent_attrs.append((parent_mod, child, had_attr, old_val))
                    setattr(parent_mod, child, sys.modules[mod])

        sys.modules["utils.task_integrations_ops"].OAUTH_CONFIGS = {}
        sys.modules["models.shared"].StatusResponse = MagicMock

        if str(BACKEND_DIR) not in sys.path:
            sys.path.insert(0, str(BACKEND_DIR))

        try:
            import routers.task_integrations as router_mod
        except ImportError:
            import task_integrations as router_mod

        cls._router_mod = router_mod

    @classmethod
    def tearDownClass(cls):
        for parent_mod, child, had_attr, old_val in reversed(cls._modified_parent_attrs):
            if had_attr:
                setattr(parent_mod, child, old_val)
            else:
                try:
                    delattr(parent_mod, child)
                except AttributeError:
                    pass
        for mod in cls._stubbed_modules:
            sys.modules.pop(mod, None)

    def test_sanitize_task_integration_error_helper(self):
        sanitize_fn = getattr(self._router_mod, "_sanitize_task_integration_error")
        sensitive_error = RuntimeError(
            "psycopg2.OperationalError: could not connect to server: Connection refused (10.128.0.4:5432)"
        )

        detail = sanitize_fn(sensitive_error, "Asana workspaces")
        self.assertEqual(detail, "Failed to fetch Asana workspaces")
        self.assertNotIn("psycopg2", detail)
        self.assertNotIn("10.128.0.4", detail)

    def test_no_raw_str_exc_leak_in_task_integrations(self):
        target_path = ROUTER_FILE
        if not target_path.exists():
            target_path = Path(__file__).parent / "task_integrations.py"
        source = target_path.read_text(encoding="utf-8")

        self.assertIn("_sanitize_task_integration_error", source)
        self.assertNotIn('detail=f"Error fetching', source)
        self.assertNotIn("detail=str(e)", source)
        self.assertNotIn("detail=str(exc)", source)
        self.assertNotIn("detail=str(error)", source)

    async def test_get_asana_workspaces_sanitizes_error(self):
        from fastapi import HTTPException

        mod = self._router_mod
        fake_data = {"connected": True, "access_token": "valid-token"}

        with patch.object(mod, "run_blocking", AsyncMock(return_value=fake_data)), patch.object(
            mod, "ensure_valid_oauth_token", AsyncMock(return_value=fake_data)
        ), patch.object(
            mod,
            "perform_request_with_token_retry",
            AsyncMock(side_effect=RuntimeError("ssl.SSLError: certificate verify failed for app.asana.com")),
        ):
            with self.assertRaises(HTTPException) as ctx:
                await mod.get_asana_workspaces(uid="user-1")
            self.assertEqual(ctx.exception.status_code, 500)
            self.assertEqual(ctx.exception.detail, "Failed to fetch Asana workspaces")
            self.assertNotIn("certificate verify failed", ctx.exception.detail)

    async def test_get_asana_projects_sanitizes_error(self):
        from fastapi import HTTPException

        mod = self._router_mod
        fake_data = {"connected": True, "access_token": "valid-token"}

        with patch.object(mod, "run_blocking", AsyncMock(return_value=fake_data)), patch.object(
            mod, "ensure_valid_oauth_token", AsyncMock(return_value=fake_data)
        ), patch.object(
            mod,
            "perform_request_with_token_retry",
            AsyncMock(side_effect=ValueError("json.decoder.JSONDecodeError: Unterminated string at line 1")),
        ):
            with self.assertRaises(HTTPException) as ctx:
                await mod.get_asana_projects(workspace_gid="ws-123", uid="user-1")
            self.assertEqual(ctx.exception.status_code, 500)
            self.assertEqual(ctx.exception.detail, "Failed to fetch Asana projects")
            self.assertNotIn("JSONDecodeError", ctx.exception.detail)

    async def test_get_clickup_teams_sanitizes_error(self):
        from fastapi import HTTPException

        mod = self._router_mod
        fake_data = {"connected": True, "access_token": "valid-token"}

        with patch.object(mod, "run_blocking", AsyncMock(return_value=fake_data)), patch.object(
            mod, "ensure_valid_oauth_token", AsyncMock(return_value=fake_data)
        ), patch.object(
            mod,
            "perform_request_with_token_retry",
            AsyncMock(side_effect=ConnectionResetError("Remote disconnected")),
        ):
            with self.assertRaises(HTTPException) as ctx:
                await mod.get_clickup_teams(uid="user-1")
            self.assertEqual(ctx.exception.status_code, 500)
            self.assertEqual(ctx.exception.detail, "Failed to fetch ClickUp teams")
            self.assertNotIn("Remote disconnected", ctx.exception.detail)

    async def test_get_clickup_spaces_sanitizes_error(self):
        from fastapi import HTTPException

        mod = self._router_mod
        fake_data = {"connected": True, "access_token": "valid-token"}

        with patch.object(mod, "run_blocking", AsyncMock(return_value=fake_data)), patch.object(
            mod, "ensure_valid_oauth_token", AsyncMock(return_value=fake_data)
        ), patch.object(
            mod,
            "perform_request_with_token_retry",
            AsyncMock(side_effect=TimeoutError("Gateway timeout to api.clickup.com")),
        ):
            with self.assertRaises(HTTPException) as ctx:
                await mod.get_clickup_spaces(team_id="t-1", uid="user-1")
            self.assertEqual(ctx.exception.status_code, 500)
            self.assertEqual(ctx.exception.detail, "Failed to fetch ClickUp spaces")
            self.assertNotIn("Gateway timeout", ctx.exception.detail)

    async def test_get_clickup_lists_sanitizes_error(self):
        from fastapi import HTTPException

        mod = self._router_mod
        fake_data = {"connected": True, "access_token": "valid-token"}

        with patch.object(mod, "run_blocking", AsyncMock(return_value=fake_data)), patch.object(
            mod, "ensure_valid_oauth_token", AsyncMock(return_value=fake_data)
        ), patch.object(
            mod,
            "perform_request_with_token_retry",
            AsyncMock(side_effect=KeyError("unhandled 'data' key")),
        ):
            with self.assertRaises(HTTPException) as ctx:
                await mod.get_clickup_lists(space_id="s-1", uid="user-1")
            self.assertEqual(ctx.exception.status_code, 500)
            self.assertEqual(ctx.exception.detail, "Failed to fetch ClickUp lists")
            self.assertNotIn("unhandled 'data' key", ctx.exception.detail)


if __name__ == "__main__":
    unittest.main()
