"""Hermetic unit tests for error sanitization in the memory product router.

Verifies that:
1. Product memory search handlers catch ValueError and sanitize error details
   instead of reflecting raw str(exc) (which can leak user UIDs or document IDs).
2. The _sanitize_search_error helper maps parameter validation errors to generic,
   safe HTTP 400 responses and logs error type safely.
"""

from __future__ import annotations

import os
from pathlib import Path
import re
import sys
from types import ModuleType
import unittest
from unittest.mock import MagicMock

os.environ.setdefault("ENCRYPTION_SECRET", "01234567890123456789012345678901")

# Stubs for hermetic execution without GCP / Firebase / Redis libraries
google_mod = sys.modules.get("google") or ModuleType("google")
google_mod.__path__ = []
google_cloud = sys.modules.get("google.cloud") or ModuleType("google.cloud")
google_cloud.__path__ = []
google_cloud_firestore = sys.modules.get("google.cloud.firestore") or ModuleType("google.cloud.firestore")
google_cloud_firestore.transactional = lambda fn: fn
google_cloud_firestore_v1 = sys.modules.get("google.cloud.firestore_v1") or ModuleType("google.cloud.firestore_v1")
google_cloud_firestore_v1.FieldFilter = MagicMock()
google_cloud_firestore_v1.transactional = lambda fn: fn

google_api_core = sys.modules.get("google.api_core") or ModuleType("google.api_core")
google_api_core.__path__ = []
google_api_core_exceptions = sys.modules.get("google.api_core.exceptions") or ModuleType("google.api_core.exceptions")
for exc_name in ["InvalidArgument", "NotFound", "AlreadyExists", "Conflict", "GoogleAPICallError"]:
    if not hasattr(google_api_core_exceptions, exc_name):
        setattr(google_api_core_exceptions, exc_name, type(exc_name, (Exception,), {}))
google_api_core.exceptions = google_api_core_exceptions

sys.modules["google"] = google_mod
sys.modules["google.cloud"] = google_cloud
sys.modules["google.cloud.firestore"] = google_cloud_firestore
sys.modules["google.cloud.firestore_v1"] = google_cloud_firestore_v1
sys.modules["google.api_core"] = google_api_core
sys.modules["google.api_core.exceptions"] = google_api_core_exceptions

firebase_admin = sys.modules.get("firebase_admin") or ModuleType("firebase_admin")
firebase_admin.__path__ = []
firebase_admin_auth = sys.modules.get("firebase_admin.auth") or ModuleType("firebase_admin.auth")
for exc_name in ["CertificateFetchError", "ExpiredIdTokenError", "InvalidIdTokenError", "RevokedIdTokenError"]:
    if not hasattr(firebase_admin_auth, exc_name):
        setattr(firebase_admin_auth, exc_name, type(exc_name, (Exception,), {}))
sys.modules["firebase_admin"] = firebase_admin
sys.modules["firebase_admin.auth"] = firebase_admin_auth

sys.modules.setdefault("redis", MagicMock())
sys.modules.setdefault("cachetools", MagicMock())
prom = sys.modules.get("prometheus_client")
if prom is None or not hasattr(prom, "start_http_server"):
    sys.modules["prometheus_client"] = MagicMock()

from routers.memory_product import _sanitize_search_error

MEMORY_PRODUCT_SOURCE_FILE = Path(__file__).resolve().parents[2] / "routers" / "memory_product.py"


def _get_function_source(function_name: str) -> str:
    source = MEMORY_PRODUCT_SOURCE_FILE.read_text(encoding="utf-8")
    start = source.index(f"def {function_name}")
    match = re.search(r"\n(?:@router|def |async def )", source[start + 1 :])
    if match:
        return source[start : start + 1 + match.start()]
    return source[start:]


class MemoryProductErrorSanitizationTests(unittest.TestCase):
    def test_search_product_memory_sanitizes_value_errors(self):
        source = _get_function_source("search_product_memory")
        self.assertNotIn("detail=str(exc)", source)
        self.assertIn('_sanitize_search_error(exc, "Product memory search")', source)

    def test_search_vector_memory_sanitizes_value_errors(self):
        source = _get_function_source("search_vector_memory")
        self.assertNotIn("detail=str(exc)", source)
        self.assertIn('_sanitize_search_error(exc, "Vector memory search")', source)

    def test_search_archive_memory_sanitizes_value_errors(self):
        source = _get_function_source("search_archive_memory")
        self.assertNotIn("detail=str(exc)", source)
        self.assertIn('_sanitize_search_error(exc, "Archive memory search")', source)

    def test_sanitize_search_error_masks_internal_details(self):
        source = MEMORY_PRODUCT_SOURCE_FILE.read_text(encoding="utf-8")
        self.assertIn("def _sanitize_search_error", source)
        self.assertIn("type(exc).__name__", source)
        self.assertIn("Invalid search parameters", source)
        self.assertIn("Invalid limit parameter", source)
        self.assertIn("Invalid offset parameter", source)
        self.assertIn("Invalid as_of parameter", source)

    def test_sanitize_search_error_behavioral(self):
        # Mismatch error embedding sensitive UIDs must yield generic message with zero leaked IDs
        mismatch_err = ValueError("canonical memory uid mismatch: expected uid-secret-123, got uid-leak-456")
        http_exc = _sanitize_search_error(mismatch_err, "Product memory search")
        self.assertEqual(http_exc.status_code, 400)
        self.assertEqual(http_exc.detail, "Invalid search parameters")
        self.assertNotIn("uid-secret-123", http_exc.detail)
        self.assertNotIn("uid-leak-456", http_exc.detail)

        # Document ID mismatch error
        doc_err = ValueError("canonical lineage document id mismatch: requested doc-999, found doc-000")
        http_exc_doc = _sanitize_search_error(doc_err, "Vector memory search")
        self.assertEqual(http_exc_doc.status_code, 400)
        self.assertEqual(http_exc_doc.detail, "Invalid search parameters")
        self.assertNotIn("doc-999", http_exc_doc.detail)

        # Pagination & date param variants
        limit_err = _sanitize_search_error(ValueError("invalid limit value"), "test")
        self.assertEqual(limit_err.detail, "Invalid limit parameter")

        offset_err = _sanitize_search_error(ValueError("invalid offset value"), "test")
        self.assertEqual(offset_err.detail, "Invalid offset parameter")

        as_of_err = _sanitize_search_error(ValueError("as_of must be timezone-aware"), "test")
        self.assertEqual(as_of_err.detail, "Invalid as_of parameter")

    def test_no_raw_str_exc_leak_in_memory_product(self):
        source = MEMORY_PRODUCT_SOURCE_FILE.read_text(encoding="utf-8")
        self.assertNotIn("detail=str(exc)", source)
        self.assertNotIn("detail=str(e)", source)


if __name__ == "__main__":
    unittest.main()
