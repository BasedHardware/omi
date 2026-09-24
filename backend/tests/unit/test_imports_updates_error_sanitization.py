"""Hermetic unit tests for error sanitization in imports and updates routers.

Verifies that:
1. Appcast generation errors in updates router do not leak XML generator, file path,
   or storage exception details into HTTP 500 responses.
2. Limitless ZIP file save errors in imports router do not leak temp filesystem paths
   or OS error details into HTTP 500 responses or database job records.
"""

from __future__ import annotations

import os
import sys
from types import ModuleType
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

os.environ.setdefault("ENCRYPTION_SECRET", "01234567890123456789012345678901")

# Stub external dependencies if not present in the environment
google_mod = ModuleType("google")
google_mod.__path__ = []
google_cloud = ModuleType("google.cloud")
google_cloud.__path__ = []
google_cloud_firestore = ModuleType("google.cloud.firestore")
google_cloud_firestore.transactional = lambda fn: fn
google_cloud_firestore_v1 = ModuleType("google.cloud.firestore_v1")
google_cloud_firestore_v1.FieldFilter = MagicMock()
google_cloud_firestore_v1.transactional = lambda fn: fn
google_api_core = sys.modules.get("google.api_core") or ModuleType("google.api_core")
google_api_core.__path__ = []
google_api_core_exceptions = sys.modules.get("google.api_core.exceptions") or ModuleType("google.api_core.exceptions")
for exc_name in ["InvalidArgument", "NotFound", "AlreadyExists", "Conflict", "GoogleAPICallError"]:
    if not hasattr(google_api_core_exceptions, exc_name):
        setattr(google_api_core_exceptions, exc_name, type(exc_name, (Exception,), {}))

google_cloud_exceptions = sys.modules.get("google.cloud.exceptions") or ModuleType("google.cloud.exceptions")
google_cloud_exceptions.NotFound = type("NotFound", (Exception,), {})
google_auth = sys.modules.get("google.auth") or ModuleType("google.auth")
google_auth_transport = sys.modules.get("google.auth.transport") or ModuleType("google.auth.transport")
google_auth_transport_requests = sys.modules.get("google.auth.transport.requests") or ModuleType(
    "google.auth.transport.requests"
)
google_auth_transport_requests.Request = MagicMock()

google_cloud_tasks_v2 = ModuleType("google.cloud.tasks_v2")
google_cloud.tasks_v2 = google_cloud_tasks_v2
google_oauth2 = ModuleType("google.oauth2")
google_oauth2.id_token = MagicMock()

sys.modules["google"] = google_mod
sys.modules["google.cloud"] = google_cloud
sys.modules["google.cloud.tasks_v2"] = google_cloud_tasks_v2
sys.modules["google.cloud.exceptions"] = google_cloud_exceptions
sys.modules["google.cloud.firestore"] = google_cloud_firestore
sys.modules["google.cloud.firestore_v1"] = google_cloud_firestore_v1
sys.modules["google.api_core"] = google_api_core
sys.modules["google.api_core.exceptions"] = google_api_core_exceptions
sys.modules["google.auth"] = google_auth
sys.modules["google.auth.transport"] = google_auth_transport
sys.modules["google.auth.transport.requests"] = google_auth_transport_requests
sys.modules["google.oauth2"] = google_oauth2
sys.modules["google.oauth2.id_token"] = google_oauth2.id_token
sys.modules.setdefault("google.protobuf", MagicMock())
sys.modules.setdefault("google.protobuf.duration_pb2", MagicMock())
sys.modules.setdefault("redis", MagicMock())
sys.modules.setdefault("firebase_admin", MagicMock())
sys.modules.setdefault("firebase_admin.auth", MagicMock())
sys.modules.setdefault("prometheus_client", MagicMock())
sys.modules.setdefault("cachetools", MagicMock())

limitless_mock = ModuleType("utils.imports.limitless")
limitless_mock.create_import_job = MagicMock()
limitless_mock.process_limitless_import = MagicMock()
sys.modules["utils.imports.limitless"] = limitless_mock

from fastapi import HTTPException

SECRET_PATH = "/srv/omi/storage/appcasts/private_key.pem"
FILESYSTEM_PATH = "/tmp/omi_imports_secret_user_dir/upload.zip"
LEAK_MARKERS = ("/srv/omi", "private_key", "/tmp/omi_imports", "RuntimeError", "Traceback")


class ImportsUpdatesErrorSanitizationTests(unittest.IsolatedAsyncioTestCase):
    async def test_appcast_generation_error_sanitized(self):
        from routers import updates

        dummy_release = {
            "version": "1.0.0",
            "build": "100",
            "published_at": "2026-09-24T00:00:00Z",
            "channel": "stable",
            "ed_signature": "sig",
        }

        with (
            patch.object(updates, "_get_live_desktop_releases", return_value=[dummy_release]),
            patch.object(updates, "_parse_desktop_version", return_value={"version": "1.0.0", "build": "100"}),
            patch.object(updates, "_get_installer_download_url", return_value="https://test/app.dmg"),
            patch.object(updates, "_generate_appcast_xml", side_effect=RuntimeError(SECRET_PATH)),
        ):
            with self.assertRaises(HTTPException) as ctx:
                await updates.get_desktop_appcast_xml(
                    platform="macos",
                    identity="stable",
                )

            self.assertEqual(ctx.exception.status_code, 500)
            self.assertEqual(ctx.exception.detail, "Error generating appcast. Please try again.")
            for marker in LEAK_MARKERS:
                self.assertNotIn(marker, str(ctx.exception.detail))

    async def test_import_file_save_error_sanitized(self):
        from routers import imports
        from models.import_job import ImportJobStatus

        file_mock = AsyncMock()
        file_mock.filename = "notes.zip"
        file_mock.read.side_effect = RuntimeError(f"Permission denied: {FILESYSTEM_PATH}")

        job_mock = MagicMock()
        job_mock.id = "job-123"

        update_job_mock = MagicMock()

        async def fake_run_blocking(executor, func, *args, **kwargs):
            if func == imports.create_import_job:
                return job_mock
            elif func == imports.import_jobs_db.update_import_job:
                return update_job_mock(*args, **kwargs)
            elif func == open:
                f_mock = MagicMock()
                f_mock.write = MagicMock()
                return f_mock
            return func(*args, **kwargs)

        with (
            patch("routers.imports.run_blocking", side_effect=fake_run_blocking),
            patch("routers.imports.os.makedirs"),
        ):
            with self.assertRaises(HTTPException) as ctx:
                await imports.import_limitless_data(
                    file=file_mock,
                    language="en",
                    uid="user_123",
                )

            self.assertEqual(ctx.exception.status_code, 500)
            self.assertEqual(ctx.exception.detail, "Failed to save uploaded file. Please try again.")
            for marker in LEAK_MARKERS:
                self.assertNotIn(marker, str(ctx.exception.detail))

            # Verify database record also received sanitized error string
            update_job_mock.assert_called_once()
            args, _ = update_job_mock.call_args
            self.assertEqual(args[0], "job-123")
            self.assertEqual(args[1]["status"], ImportJobStatus.failed.value)
            self.assertEqual(args[1]["error"], "Failed to save uploaded file.")
            for marker in LEAK_MARKERS:
                self.assertNotIn(marker, args[1]["error"])


if __name__ == "__main__":
    unittest.main()
