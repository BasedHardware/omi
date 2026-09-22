import asyncio
from pathlib import Path
import sys
import unittest
from unittest.mock import MagicMock

backend_dir = str(Path(__file__).resolve().parent.parent.parent)
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from testing.import_isolation import AutoMockModule, load_module_fresh, stub_modules


class TestIntegrationBaseSanitization(unittest.TestCase):
    def setUp(self):
        self._stub_cm = stub_modules({
            "database": AutoMockModule("database"),
            "database.users": AutoMockModule("database.users"),
            "utils.retrieval.agentic": AutoMockModule("utils.retrieval.agentic"),
        })
        self._stub_cm.__enter__()
        tools_path = str(Path(backend_dir) / "utils" / "retrieval" / "tools" / "integration_base.py")
        self.integration_base = load_module_fresh("utils.retrieval.tools.integration_base", tools_path)

    def tearDown(self):
        self._stub_cm.__exit__(None, None, None)

    def test_get_integration_checked_exception_does_not_leak_details(self):
        import database.users as users_db
        users_db.get_integration = MagicMock(
            side_effect=RuntimeError("psycopg2.OperationalError: password=secret_password connection timeout")
        )

        integration, err = self.integration_base.get_integration_checked(
            uid="u123",
            key="google_calendar",
            connection_name="Google Calendar",
            not_connected_msg="Not connected",
            error_prefix="Google Calendar error",
        )
        self.assertIsNone(integration)
        self.assertIsNotNone(err)
        self.assertNotIn("secret_password", err)
        self.assertNotIn("psycopg2", err)
        self.assertEqual(err, "Google Calendar error: Failed to fetch integration details")

    def test_parse_iso_with_tz_sanitizes_value_error(self):
        dt, err = self.integration_base.parse_iso_with_tz(
            field_name="start_time",
            value="invalid-iso-string-12345",
            tz_required_msg="YYYY-MM-DDTHH:MM:SS+HH:MM",
        )
        self.assertIsNone(dt)
        self.assertIsNotNone(err)
        self.assertEqual(
            err,
            "Error: Invalid start_time format. Expected YYYY-MM-DDTHH:MM:SS+HH:MM: invalid-iso-string-12345",
        )
        self.assertNotIn("Invalid isoformat string", err)

    def test_retry_on_auth_non_auth_exception_does_not_leak_details(self):
        def failing_call(**kwargs):
            raise RuntimeError("Database connection string: postgres://user:super_secret@internal.db:5432/app")

        res, err = self.integration_base.retry_on_auth(
            call_fn=failing_call,
            call_kwargs={},
            refresh_fn=lambda uid, integ: "new_token",
            uid="u1",
            integration={},
            expired_msg="Token expired",
        )
        self.assertIsNone(res)
        self.assertEqual(err, "Error: Request failed")
        self.assertNotIn("super_secret", err)

    def test_retry_on_auth_refresh_failure_does_not_leak_details(self):
        call_count = [0]

        def failing_call(**kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                raise Exception("401 token may be expired")
            raise RuntimeError("Internal backend error: token=bearer_xyz_12345")

        res, err = self.integration_base.retry_on_auth(
            call_fn=failing_call,
            call_kwargs={"access_token": "old"},
            refresh_fn=lambda uid, integ: "new_token",
            uid="u1",
            integration={},
            expired_msg="Token expired",
        )
        self.assertIsNone(res)
        self.assertEqual(err, "Error: Request failed after token refresh")
        self.assertNotIn("bearer_xyz_12345", err)

    def test_retry_on_auth_async_non_auth_exception_does_not_leak_details(self):
        async def failing_call(**kwargs):
            raise RuntimeError("Secret credentials: api_key=sk-live-1234567890")

        async def dummy_refresh(uid, integ):
            return "new"

        res, err = asyncio.run(
            self.integration_base.retry_on_auth_async(
                call_fn=failing_call,
                call_kwargs={},
                refresh_fn=dummy_refresh,
                uid="u1",
                integration={},
                expired_msg="Token expired",
            )
        )
        self.assertIsNone(res)
        self.assertEqual(err, "Error: Request failed")
        self.assertNotIn("sk-live-1234567890", err)

    def test_retry_on_auth_async_refresh_failure_does_not_leak_details(self):
        call_count = [0]

        async def failing_call(**kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                raise Exception("Authentication failed")
            raise RuntimeError("Internal crash with token=leak_999")

        async def dummy_refresh(uid, integ):
            return "new"

        res, err = asyncio.run(
            self.integration_base.retry_on_auth_async(
                call_fn=failing_call,
                call_kwargs={"access_token": "old"},
                refresh_fn=dummy_refresh,
                uid="u1",
                integration={},
                expired_msg="Token expired",
            )
        )
        self.assertIsNone(res)
        self.assertEqual(err, "Error: Request failed after token refresh")
        self.assertNotIn("leak_999", err)


if __name__ == "__main__":
    unittest.main()
