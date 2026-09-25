"""Hermetic unit tests for error sanitization in Wrapped generation and router.

Verifies that:
1. _run_wrapped_generation logs exception type and writes generic error without str(e).
2. generate_wrapped_2025 in backend/utils/wrapped/generate_2025.py logs exception type
   and writes generic error without str(e) or raw tracebacks.
3. get_wrapped_status sanitizes any legacy exception or traceback strings stored in the DB
   via a strict allowlist.
"""

from __future__ import annotations

import os
from pathlib import Path
import re
import sys
from types import ModuleType
import unittest
from unittest.mock import MagicMock, patch

os.environ.setdefault("ENCRYPTION_SECRET", "01234567890123456789012345678901")

google_mod = sys.modules.get("google") or ModuleType("google")
google_mod.__path__ = []
google_cloud = sys.modules.get("google.cloud") or ModuleType("google.cloud")
google_cloud.__path__ = []
google_cloud_exceptions = sys.modules.get("google.cloud.exceptions") or ModuleType("google.cloud.exceptions")
google_cloud_exceptions.__getattr__ = lambda name: type(name, (Exception,), {})
google_cloud_firestore = sys.modules.get("google.cloud.firestore") or ModuleType("google.cloud.firestore")
google_cloud_firestore.transactional = lambda fn: fn
google_cloud_firestore_v1 = sys.modules.get("google.cloud.firestore_v1") or ModuleType("google.cloud.firestore_v1")
google_cloud_firestore_v1.FieldFilter = MagicMock()
google_cloud_firestore_v1.transactional = lambda fn: fn
google_cloud_storage = sys.modules.get("google.cloud.storage") or ModuleType("google.cloud.storage")
google_cloud.storage = google_cloud_storage

google_api_core = sys.modules.get("google.api_core") or ModuleType("google.api_core")
google_api_core.__path__ = []
google_api_core_exceptions = sys.modules.get("google.api_core.exceptions") or ModuleType("google.api_core.exceptions")
google_api_core_exceptions.__getattr__ = lambda name: type(name, (Exception,), {})
google_api_core.exceptions = google_api_core_exceptions

google_auth = sys.modules.get("google.auth") or ModuleType("google.auth")
google_auth_transport = sys.modules.get("google.auth.transport") or ModuleType("google.auth.transport")
google_auth_transport_requests = sys.modules.get("google.auth.transport.requests") or ModuleType(
    "google.auth.transport.requests"
)
google_auth_transport_requests.Request = MagicMock()
google_cloud_tasks_v2 = ModuleType("google.cloud.tasks_v2")
google_cloud_tasks_v2.CloudTasksClient = MagicMock()
google_oauth2 = ModuleType("google.oauth2")
google_oauth2.id_token = MagicMock()
google_oauth2.service_account = MagicMock()

sys.modules["google"] = google_mod
sys.modules["google.cloud"] = google_cloud
sys.modules["google.cloud.exceptions"] = google_cloud_exceptions
sys.modules["google.cloud.firestore"] = google_cloud_firestore
sys.modules["google.cloud.firestore_v1"] = google_cloud_firestore_v1
sys.modules["google.cloud.storage"] = google_cloud_storage
sys.modules["google.cloud.tasks_v2"] = google_cloud_tasks_v2
sys.modules["google.api_core"] = google_api_core
sys.modules["google.api_core.exceptions"] = google_api_core_exceptions
sys.modules["google.auth"] = google_auth
sys.modules["google.auth.transport"] = google_auth_transport
sys.modules["google.auth.transport.requests"] = google_auth_transport_requests
sys.modules["google.oauth2"] = google_oauth2
sys.modules["google.oauth2.id_token"] = google_oauth2.id_token
sys.modules["google.oauth2.service_account"] = google_oauth2.service_account
sys.modules.setdefault("google.protobuf", MagicMock())
sys.modules.setdefault("google.protobuf.duration_pb2", MagicMock())

firebase_admin = sys.modules.get("firebase_admin") or ModuleType("firebase_admin")
firebase_admin.__path__ = []
firebase_admin_auth = sys.modules.get("firebase_admin.auth") or ModuleType("firebase_admin.auth")
firebase_admin_auth.__getattr__ = lambda name: type(name, (Exception,), {})
sys.modules["firebase_admin"] = firebase_admin
sys.modules["firebase_admin.auth"] = firebase_admin_auth

sys.modules.setdefault("redis", MagicMock())
sys.modules.setdefault("cachetools", MagicMock())
prom = sys.modules.get("prometheus_client")
if prom is None or not hasattr(prom, "start_http_server"):
    sys.modules["prometheus_client"] = MagicMock()

# Stub generate_wrapped_2025 to keep router tests fast and hermetic
generate_mock = ModuleType("utils.wrapped.generate_2025")
generate_mock.generate_wrapped_2025 = MagicMock()
sys.modules["utils.wrapped.generate_2025"] = generate_mock

WRAPPED_ROUTER_FILE = Path(__file__).resolve().parents[2] / "routers" / "wrapped.py"
WRAPPED_GEN_FILE = Path(__file__).resolve().parents[2] / "utils" / "wrapped" / "generate_2025.py"


def _get_function_source(file_path: Path, function_name: str) -> str:
    source = file_path.read_text(encoding="utf-8")
    start = source.index(f"def {function_name}")
    match = re.search(r"\n(?:@router|def |async def )", source[start + 1 :])
    if match:
        return source[start : start + 1 + match.start()]
    return source[start:]


class WrappedErrorSanitizationTests(unittest.TestCase):
    def test_run_wrapped_generation_sanitizes_errors(self):
        source = _get_function_source(WRAPPED_ROUTER_FILE, "_run_wrapped_generation")
        self.assertNotIn("error=str(e)", source)
        self.assertNotIn("logger.error(f\"Error in wrapped generation for user {uid}: {e}\")", source)
        self.assertIn("type(e).__name__", source)
        self.assertIn('error="Failed to generate Wrapped. Please try again later."', source)

    def test_get_wrapped_status_allowlist_behavior(self):
        from routers import wrapped as wrapped_router
        from database.wrapped import WrappedStatus

        # 1. Raw traceback in DB -> masked to generic
        with patch.object(wrapped_router.wrapped_db, "get_wrapped", return_value={
            "status": WrappedStatus.ERROR,
            "error": "Traceback (most recent call last):\n  File 'app.py', line 10\nRuntimeError: /var/secrets/key.json",
        }):
            resp = wrapped_router.get_wrapped_status(year=2025, uid="u1")
            self.assertEqual(resp.error, "Failed to generate Wrapped. Please try again later.")
            self.assertNotIn("/var/secrets", resp.error)

        # 2. Custom internal error string without standard traceback keywords -> also masked by allowlist
        with patch.object(wrapped_router.wrapped_db, "get_wrapped", return_value={
            "status": WrappedStatus.ERROR,
            "error": "custom database connection failed at postgres://user:pass@10.0.0.5:5432/omi",
        }):
            resp = wrapped_router.get_wrapped_status(year=2025, uid="u1")
            self.assertEqual(resp.error, "Failed to generate Wrapped. Please try again later.")
            self.assertNotIn("postgres://", resp.error)

        # 3. Known sanitized message -> returned as-is
        with patch.object(wrapped_router.wrapped_db, "get_wrapped", return_value={
            "status": WrappedStatus.ERROR,
            "error": "Failed to generate Wrapped. Please try again later.",
        }):
            resp = wrapped_router.get_wrapped_status(year=2025, uid="u1")
            self.assertEqual(resp.error, "Failed to generate Wrapped. Please try again later.")

        # 4. No error
        with patch.object(wrapped_router.wrapped_db, "get_wrapped", return_value={
            "status": WrappedStatus.DONE,
            "error": None,
        }):
            resp = wrapped_router.get_wrapped_status(year=2025, uid="u1")
            self.assertIsNone(resp.error)

    def test_generate_wrapped_2025_sanitizes_errors(self):
        source = _get_function_source(WRAPPED_GEN_FILE, "generate_wrapped_2025")
        self.assertNotIn("error=str(e)", source)
        self.assertNotIn("traceback.print_exc()", source)
        self.assertIn("type(e).__name__", source)
        self.assertIn('error="Failed to generate Wrapped. Please try again later."', source)


if __name__ == "__main__":
    unittest.main()
