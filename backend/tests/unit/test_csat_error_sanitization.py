"""Regression tests for CWE-209 sanitization in backend/routers/csat.py.

Issue #18868 — the CSAT router must never leak internal Firestore document
keys, collection paths, or runtime call stacks to external callers.

The tests in this file verify:
1. No raw ``detail=str(exc)`` patterns appear in the router source.
2. ``submit_csat_rating`` returns 503 (not 500) with a sanitized detail on
   database failures.
3. ``get_csat_config`` falls back to DEFAULT_CONFIG on unexpected exceptions
   rather than propagating a 500.
4. Input validation rejects invalid platforms, scores, and revisions.
"""

import ast
import importlib
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# Minimal environment bootstrap
# ---------------------------------------------------------------------------
os.environ["ENCRYPTION_SECRET"] = "12345678901234567890123456789012"

# Make backend/ importable
_BACKEND = os.path.join(os.path.dirname(__file__), os.pardir, os.pardir)
if os.path.isdir(_BACKEND) and os.path.abspath(_BACKEND) not in sys.path:
    sys.path.insert(0, os.path.abspath(_BACKEND))

# ---------------------------------------------------------------------------
# 1) Source-level checks
# ---------------------------------------------------------------------------

_ROUTER_PATH = os.path.join(
    os.path.dirname(__file__), os.pardir, os.pardir, "routers", "csat.py"
)


class TestCsatSourceSanitization(unittest.TestCase):
    """Static analysis: no raw str(exc) leaks in csat router."""

    def test_no_raw_str_exc_in_detail(self):
        """detail=str(exc) must never appear in csat.py."""
        with open(_ROUTER_PATH, "r", encoding="utf-8") as fh:
            source = fh.read()
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.keyword) and node.arg == "detail":
                src_fragment = ast.get_source_segment(source, node.value)
                self.assertNotIn(
                    "str(exc)",
                    src_fragment or "",
                    "Found raw detail=str(exc) in csat router — CWE-209 leak",
                )
                self.assertNotIn(
                    "str(e)",
                    src_fragment or "",
                    "Found raw detail=str(e) in csat router — CWE-209 leak",
                )

    def test_submit_uses_503_not_500(self):
        """submit_csat_rating must return 503, not 500, on DB failure."""
        with open(_ROUTER_PATH, "r", encoding="utf-8") as fh:
            source = fh.read()
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Raise):
                continue
            exc_node = node.exc
            if not isinstance(exc_node, ast.Call):
                continue
            for kw in exc_node.keywords:
                if kw.arg == "status_code" and isinstance(kw.value, ast.Constant):
                    self.assertNotEqual(
                        kw.value.value,
                        500,
                        "submit_csat_rating must use 503, not 500, for DB errors",
                    )

    def test_config_endpoint_has_exception_guard(self):
        """get_csat_config must have a try/except guard."""
        with open(_ROUTER_PATH, "r", encoding="utf-8") as fh:
            source = fh.read()
        tree = ast.parse(source)
        found_guard = False
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "get_csat_config":
                for child in ast.walk(node):
                    if isinstance(child, ast.Try):
                        found_guard = True
                        break
                break
        self.assertTrue(
            found_guard,
            "get_csat_config() must wrap the Firestore call with try/except",
        )


# ---------------------------------------------------------------------------
# 2) Behavioural tests — use TestClient with proper dependency overrides
# ---------------------------------------------------------------------------


def _make_test_app():
    """Build a FastAPI app with auth bypassed and csat router mounted."""
    from fastapi import FastAPI

    from utils.other import endpoints as auth
    import routers.csat as csat_mod

    app = FastAPI()
    app.dependency_overrides[auth.get_current_user_uid] = lambda: "test-uid"
    app.dependency_overrides[csat_mod.auth.get_current_user_uid] = lambda: "test-uid"
    app.include_router(csat_mod.router)
    return app


class TestCsatSubmitBehavior(unittest.TestCase):
    """submit_csat_rating must return sanitized 503 on DB failure."""

    @patch("routers.csat.csat")
    def test_submit_db_failure_returns_503(self, mock_csat_db):
        """Firestore crash → HTTP 503, sanitized detail, no stack."""
        mock_csat_db.PLATFORMS = {"macos", "windows", "ios", "android"}
        mock_csat_db.MAX_APP_VERSION_LENGTH = 32
        mock_csat_db.MAX_COMMENT_LENGTH = 500
        mock_csat_db.submit_rating.side_effect = RuntimeError(
            "Firestore doc csat_ratings/macos_u123 unavailable"
        )

        from fastapi.testclient import TestClient

        app = _make_test_app()
        client = TestClient(app)
        resp = client.post(
            "/v1/csat/ratings",
            json={
                "platform": "macos",
                "app_version": "1.0",
                "score": 4,
                "comment": "Great!",
                "revision": 1,
            },
        )
        self.assertEqual(resp.status_code, 503)
        body = resp.json()
        self.assertNotIn("csat_ratings", body.get("detail", ""))
        self.assertNotIn("macos_u123", body.get("detail", ""))

    @patch("routers.csat.csat")
    def test_submit_success_returns_201(self, mock_csat_db):
        """Happy path — rating created → 201."""
        mock_csat_db.PLATFORMS = {"macos", "windows", "ios", "android"}
        mock_csat_db.MAX_APP_VERSION_LENGTH = 32
        mock_csat_db.MAX_COMMENT_LENGTH = 500
        mock_csat_db.submit_rating.return_value = ("macos_uid1", True)

        from fastapi.testclient import TestClient

        app = _make_test_app()
        client = TestClient(app)
        resp = client.post(
            "/v1/csat/ratings",
            json={
                "platform": "macos",
                "app_version": "1.0",
                "score": 5,
                "revision": 0,
            },
        )
        self.assertEqual(resp.status_code, 201)

    @patch("routers.csat.csat")
    def test_submit_duplicate_returns_409(self, mock_csat_db):
        """Duplicate rating → 409 conflict, no leak."""
        mock_csat_db.PLATFORMS = {"macos", "windows", "ios", "android"}
        mock_csat_db.MAX_APP_VERSION_LENGTH = 32
        mock_csat_db.MAX_COMMENT_LENGTH = 500
        mock_csat_db.submit_rating.return_value = ("macos_uid1", False)

        from fastapi.testclient import TestClient

        app = _make_test_app()
        client = TestClient(app)
        resp = client.post(
            "/v1/csat/ratings",
            json={
                "platform": "macos",
                "app_version": "1.0",
                "score": 3,
                "revision": 0,
            },
        )
        self.assertEqual(resp.status_code, 409)


class TestCsatConfigBehavior(unittest.TestCase):
    """get_csat_config must fall back to DEFAULT_CONFIG on failure."""

    @patch("routers.csat.csat")
    def test_config_fallback_on_exception(self, mock_csat_db):
        """DB failure → 200 with DEFAULT_CONFIG, never 500."""
        mock_csat_db.get_product_config.side_effect = RuntimeError(
            "Firestore collection csat_config unavailable"
        )
        mock_csat_db.DEFAULT_CONFIG = {
            "enabled": True,
            "title": "How would you rate Omi Desktop?",
            "body": "",
            "thank_you_text": "Thank you!",
            "refer_cta_text": "Enjoying Omi? Give a friend a free month.",
            "question_threshold": 3,
            "comment_max_score": 3,
            "revision": 0,
        }

        from fastapi.testclient import TestClient

        app = _make_test_app()
        client = TestClient(app)
        resp = client.get("/v1/csat/config?platform=macos")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertNotIn("csat_config", str(body))
        self.assertTrue(body["enabled"])

    @patch("routers.csat.csat")
    def test_config_success_returns_200(self, mock_csat_db):
        """Happy path — config fetched → 200."""
        mock_csat_db.get_product_config.return_value = {
            "enabled": True,
            "title": "Rate us!",
            "body": "Please rate",
            "thank_you_text": "Thanks!",
            "refer_cta_text": "Share!",
            "question_threshold": 5,
            "comment_max_score": 3,
            "revision": 2,
        }

        from fastapi.testclient import TestClient

        app = _make_test_app()
        client = TestClient(app)
        resp = client.get("/v1/csat/config?platform=macos")
        self.assertEqual(resp.status_code, 200)


class TestCsatInputValidation(unittest.TestCase):
    """Input validation: bad platform, score, revision get 400."""

    @patch("routers.csat.csat")
    def test_invalid_platform_returns_400(self, mock_csat_db):
        mock_csat_db.PLATFORMS = {"macos", "windows", "ios", "android"}

        from fastapi.testclient import TestClient

        app = _make_test_app()
        client = TestClient(app)
        resp = client.post(
            "/v1/csat/ratings",
            json={
                "platform": "linux",
                "app_version": "1.0",
                "score": 3,
                "revision": 0,
            },
        )
        self.assertEqual(resp.status_code, 400)

    @patch("routers.csat.csat")
    def test_score_out_of_range_returns_400(self, mock_csat_db):
        mock_csat_db.PLATFORMS = {"macos", "windows", "ios", "android"}

        from fastapi.testclient import TestClient

        app = _make_test_app()
        client = TestClient(app)
        resp = client.post(
            "/v1/csat/ratings",
            json={
                "platform": "macos",
                "app_version": "1.0",
                "score": 10,
                "revision": 0,
            },
        )
        self.assertEqual(resp.status_code, 400)

    @patch("routers.csat.csat")
    def test_negative_revision_returns_400(self, mock_csat_db):
        mock_csat_db.PLATFORMS = {"macos", "windows", "ios", "android"}

        from fastapi.testclient import TestClient

        app = _make_test_app()
        client = TestClient(app)
        resp = client.post(
            "/v1/csat/ratings",
            json={
                "platform": "macos",
                "app_version": "1.0",
                "score": 3,
                "revision": -1,
            },
        )
        self.assertEqual(resp.status_code, 400)


if __name__ == "__main__":
    unittest.main()
