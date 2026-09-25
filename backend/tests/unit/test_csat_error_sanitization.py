"""Hermetic unit tests for error sanitization and fallback resilience in the CSAT router.

Verifies that:
1. CSAT router handles storage exceptions gracefully, returning sanitized 503 error responses
   without exposing raw database errors or tracebacks.
2. CSAT config retrieval falls back safely to default product configuration on storage or cache failures.
3. Strict validation on platform, score (1-5), and revision (>=0) prevents invalid intake.
4. Static check ensures no raw detail=str(exc) or internal error leakage in backend/routers/csat.py.
"""

from __future__ import annotations

from pathlib import Path
import re
import sys
import unittest
from unittest.mock import MagicMock, patch

BACKEND_DIR = (
    Path(__file__).resolve().parents[2]
    if "backend" in str(Path(__file__).resolve())
    else Path(__file__).resolve().parent
)
CSAT_ROUTER_FILE = BACKEND_DIR / "backend" / "routers" / "csat.py"
if not CSAT_ROUTER_FILE.exists():
    CSAT_ROUTER_FILE = BACKEND_DIR / "csat.py"


class CsatErrorSanitizationTests(unittest.TestCase):
    _stubbed_modules: dict = {}

    @classmethod
    def setUpClass(cls):
        stub_names = [
            "database",
            "database.csat",
            "utils",
            "utils.other",
            "utils.other.endpoints",
        ]
        for mod in stub_names:
            if mod not in sys.modules:
                mock_mod = MagicMock()
                cls._stubbed_modules[mod] = mock_mod
                sys.modules[mod] = mock_mod

        # Inject constants and functions into database.csat stub BEFORE router import
        csat_mock = MagicMock()
        csat_mock.PLATFORMS = {"macos", "windows", "ios", "android"}
        csat_mock.MAX_APP_VERSION_LENGTH = 32
        csat_mock.MAX_COMMENT_LENGTH = 500
        csat_mock.DEFAULT_TITLE = "How would you rate Omi Desktop?"
        csat_mock.DEFAULT_THANK_YOU_TEXT = "Thank you!"
        csat_mock.DEFAULT_REFER_CTA_TEXT = "Enjoying Omi? Give a friend a free month."
        csat_mock.DEFAULT_CONFIG = {
            "enabled": True,
            "title": csat_mock.DEFAULT_TITLE,
            "body": "",
            "thank_you_text": csat_mock.DEFAULT_THANK_YOU_TEXT,
            "refer_cta_text": csat_mock.DEFAULT_REFER_CTA_TEXT,
            "question_threshold": 3,
            "comment_max_score": 3,
            "revision": 0,
        }
        csat_mock.get_product_config = MagicMock(return_value=dict(csat_mock.DEFAULT_CONFIG))
        csat_mock.submit_rating = MagicMock(return_value=("macos_uid-csat-1", True))

        sys.modules["database"].csat = csat_mock
        sys.modules["database.csat"] = csat_mock

        if str(BACKEND_DIR) not in sys.path:
            sys.path.insert(0, str(BACKEND_DIR))

        # Reload router module to pick up the configured stubs
        if "csat" in sys.modules:
            del sys.modules["csat"]
        if "routers.csat" in sys.modules:
            del sys.modules["routers.csat"]

        try:
            from routers import csat as csat_router_mod
        except ImportError:
            import csat as csat_router_mod

        cls._router_mod = csat_router_mod
        cls._csat_mock = csat_mock

    @classmethod
    def tearDownClass(cls):
        for mod in cls._stubbed_modules:
            sys.modules.pop(mod, None)

    def setUp(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        self.app = FastAPI()
        self.app.include_router(self._router_mod.router)
        self.app.dependency_overrides[self._router_mod.auth.get_current_user_uid] = lambda: "uid-csat-1"
        self.client = TestClient(self.app)

    def test_static_zero_raw_exception_reflection(self):
        source = CSAT_ROUTER_FILE.read_text(encoding="utf-8")
        self.assertNotIn("detail=str(e)", source)
        self.assertNotIn("detail=str(exc)", source)
        self.assertNotIn("detail=f\"{e", source)
        self.assertNotIn("detail=f\"{exc", source)

    def test_get_config_success(self):
        self._csat_mock.get_product_config.side_effect = None
        self._csat_mock.get_product_config.return_value = {
            "enabled": True,
            "title": "Custom Title",
            "body": "",
            "thank_you_text": "Thanks!",
            "refer_cta_text": "Refer friends",
            "question_threshold": 4,
            "comment_max_score": 3,
            "revision": 1,
        }
        response = self.client.get("/v1/csat/config?platform=macos")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["title"], "Custom Title")
        self.assertEqual(data["question_threshold"], 4)

    def test_get_config_storage_failure_falls_back_to_defaults(self):
        self._csat_mock.get_product_config.side_effect = RuntimeError("Firestore connection reset")
        response = self.client.get("/v1/csat/config?platform=macos")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["enabled"])
        self.assertEqual(data["title"], self._csat_mock.DEFAULT_TITLE)
        self.assertNotIn("Firestore", response.text)

    def test_submit_rating_success(self):
        self._csat_mock.submit_rating.side_effect = None
        self._csat_mock.submit_rating.return_value = ("macos_uid-csat-1", True)
        payload = {
            "platform": "macos",
            "app_version": "1.0.0",
            "score": 5,
            "comment": "Super helpful!",
            "revision": 0,
        }
        response = self.client.post("/v1/csat/ratings", json=payload)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json(), {"id": "macos_uid-csat-1", "created": True})

    def test_submit_rating_conflict_returns_409(self):
        self._csat_mock.submit_rating.side_effect = None
        self._csat_mock.submit_rating.return_value = ("macos_uid-csat-1", False)
        payload = {
            "platform": "macos",
            "app_version": "1.0.0",
            "score": 4,
            "comment": "Updated comment",
            "revision": 0,
        }
        response = self.client.post("/v1/csat/ratings", json=payload)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json(), {"id": "macos_uid-csat-1", "created": False})

    def test_submit_rating_storage_failure_returns_sanitized_503(self):
        self._csat_mock.submit_rating.side_effect = RuntimeError("GoogleCloudError: 503 Deadline Exceeded")
        payload = {
            "platform": "macos",
            "app_version": "1.0.0",
            "score": 5,
            "comment": "Nice!",
            "revision": 0,
        }
        response = self.client.post("/v1/csat/ratings", json=payload)
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["detail"], "CSAT service temporarily unavailable")
        self.assertNotIn("GoogleCloudError", response.text)
        self.assertNotIn("Deadline Exceeded", response.text)

    def test_submit_rating_invalid_platform(self):
        response = self.client.post("/v1/csat/ratings", json={"platform": "web_browser", "score": 3})
        self.assertEqual(response.status_code, 400)
        self.assertIn("platform must be one of", response.json()["detail"])

    def test_submit_rating_score_out_of_bounds(self):
        for score in [0, 6, -1, 10]:
            response = self.client.post("/v1/csat/ratings", json={"platform": "macos", "score": score})
            self.assertEqual(response.status_code, 400)
            self.assertEqual(response.json()["detail"], "score must be between 1 and 5")

    def test_submit_rating_negative_revision(self):
        response = self.client.post("/v1/csat/ratings", json={"platform": "macos", "score": 4, "revision": -1})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "revision must be >= 0")


if __name__ == "__main__":
    unittest.main()
