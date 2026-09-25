"""Hermetic unit tests for error sanitization and service resilience in the Referrals router.

Verifies that:
1. Referrals router handles Firebase auth and Firestore transaction exceptions gracefully,
   returning sanitized 503 error responses without exposing internal error details or stack traces.
2. Telemetry failures (PostHog errors) never crash user-facing HTTP responses.
3. Input validation rejects empty or whitespace referral codes with clean 400 Bad Request.
4. Static check ensures no raw detail=str(exc) or internal error leakage in backend/routers/referrals.py.
"""

from __future__ import annotations

from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

_candidates = [
    Path(__file__).resolve().parents[2] / "routers" / "referrals.py",
    Path(__file__).resolve().parent / "referrals.py",
    Path("routers/referrals.py").resolve(),
    Path("backend/routers/referrals.py").resolve(),
    Path("referrals.py").resolve(),
]
REFERRALS_ROUTER_FILE = next((p for p in _candidates if p.exists()), None)
BACKEND_DIR = (
    Path(__file__).resolve().parents[2]
    if len(Path(__file__).resolve().parents) >= 3
    else Path(__file__).resolve().parent
)


class ReferralsErrorSanitizationTests(unittest.TestCase):
    _stubbed_modules: dict = {}

    @classmethod
    def setUpClass(cls):
        stub_names = [
            "database",
            "database.referrals",
            "firebase_admin",
            "firebase_admin.auth",
            "utils",
            "utils.integration_telemetry",
            "utils.other",
            "utils.other.endpoints",
            "utils.referrals",
        ]
        for mod in stub_names:
            if mod not in sys.modules:
                mock_mod = MagicMock()
                cls._stubbed_modules[mod] = mock_mod
                sys.modules[mod] = mock_mod

        # Ensure parent-child relationships for stubs
        sys.modules["database"].referrals = sys.modules["database.referrals"]
        sys.modules["firebase_admin"].auth = sys.modules["firebase_admin.auth"]
        sys.modules["utils"].integration_telemetry = sys.modules["utils.integration_telemetry"]
        sys.modules["utils"].referrals = sys.modules["utils.referrals"]

        # Configure utils.referrals constants
        ref_mock = sys.modules["utils.referrals"]
        ref_mock.REFERRAL_COOKIE_MAX_AGE_SECONDS = 2592000
        ref_mock.REFERRAL_COOKIE_NAME = "omi_referral_code"
        ref_mock.REFERRAL_PROGRAM = "desktop_operator_month_v1"
        ref_mock.REFERRAL_TRIAL_DAYS = 30

        class StubReferralCodeError(Exception):
            pass

        ref_mock.ReferralCodeError = StubReferralCodeError
        cls._StubReferralCodeError = StubReferralCodeError

        ref_mock.referral_link = MagicMock(return_value="https://omi.me/r/ref1.testcode")
        ref_mock.referral_signup_url = MagicMock(return_value="https://app.omi.me/login?referral=ref1.testcode")
        ref_mock.referrer_uid_from_code = MagicMock(return_value="referrer-123")
        ref_mock.is_new_referral_account = MagicMock(return_value=True)

        sys.modules["database.referrals"].claim_referral_trial = MagicMock(return_value=(True, "granted"))
        sys.modules["firebase_admin.auth"].get_user = MagicMock(
            return_value=SimpleNamespace(user_metadata=SimpleNamespace(creation_timestamp=1700000000000))
        )

        if str(BACKEND_DIR) not in sys.path:
            sys.path.insert(0, str(BACKEND_DIR))

        if "referrals" in sys.modules:
            del sys.modules["referrals"]
        if "routers.referrals" in sys.modules:
            del sys.modules["routers.referrals"]

        try:
            from routers import referrals as referrals_router_mod
        except ImportError:
            import referrals as referrals_router_mod

        cls._router_mod = referrals_router_mod
        cls._ref_mock = ref_mock

    @classmethod
    def tearDownClass(cls):
        for mod in cls._stubbed_modules:
            sys.modules.pop(mod, None)

    def setUp(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        self.app = FastAPI()
        self.app.include_router(self._router_mod.router)
        self.app.dependency_overrides[self._router_mod.auth.get_current_user_uid] = lambda: "uid-claimant-1"
        self.client = TestClient(self.app)

    def test_static_zero_raw_exception_reflection(self):
        self.assertIsNotNone(REFERRALS_ROUTER_FILE, "referrals.py router file must be resolved")
        source = REFERRALS_ROUTER_FILE.read_text(encoding="utf-8")
        self.assertNotIn("detail=str(e)", source)
        self.assertNotIn("detail=str(exc)", source)
        self.assertNotIn("detail=str(error)", source)
        self.assertNotIn("detail=f\"{e", source)
        self.assertNotIn("detail=f\"{exc", source)
        self.assertNotIn("detail=f\"{error", source)

    def test_get_referral_link_success(self):
        self._ref_mock.referral_link.side_effect = None
        self._ref_mock.referral_link.return_value = "https://omi.me/r/ref1.unique"
        response = self.client.get("/v1/users/me/referral")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["referral_url"], "https://omi.me/r/ref1.unique")

    def test_get_referral_link_telemetry_failure_does_not_crash_response(self):
        self._ref_mock.referral_link.side_effect = None
        self._ref_mock.referral_link.return_value = "https://omi.me/r/ref1.unique"
        with patch.object(self._router_mod, "emit_posthog_event", side_effect=RuntimeError("Posthog network timeout")):
            response = self.client.get("/v1/users/me/referral")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["referral_url"], "https://omi.me/r/ref1.unique")

    def test_get_referral_link_signing_failure_returns_sanitized_503(self):
        self._ref_mock.referral_link.side_effect = self._StubReferralCodeError("encryption_key_unreachable")
        response = self.client.get("/v1/users/me/referral")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["detail"], "Referral links are temporarily unavailable")
        self.assertNotIn("encryption_key", response.text)

    def test_capture_referral_success_redirects(self):
        self._ref_mock.referrer_uid_from_code.side_effect = None
        self._ref_mock.referrer_uid_from_code.return_value = "referrer-123"
        self._ref_mock.referral_signup_url.return_value = "https://app.omi.me/login?referral=code123"
        response = self.client.get("/r/code123", follow_redirects=False)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["location"], "https://app.omi.me/login?referral=code123")
        self.assertIn("omi_referral_code=code123", response.headers["set-cookie"])

    def test_capture_referral_telemetry_failure_does_not_break_redirect(self):
        self._ref_mock.referrer_uid_from_code.side_effect = None
        self._ref_mock.referrer_uid_from_code.return_value = "referrer-123"
        self._ref_mock.referral_signup_url.return_value = "https://app.omi.me/login?referral=code123"
        with patch.object(self._router_mod, "emit_posthog_event", side_effect=RuntimeError("Posthog unavailable")):
            response = self.client.get("/r/code123", follow_redirects=False)
            self.assertEqual(response.status_code, 302)
            self.assertEqual(response.headers["location"], "https://app.omi.me/login?referral=code123")

    def test_capture_referral_invalid_code_returns_404(self):
        self._ref_mock.referrer_uid_from_code.side_effect = self._StubReferralCodeError("invalid_signature")
        response = self.client.get("/r/invalid_code", follow_redirects=False)
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["detail"], "Referral link not found")
        self.assertNotIn("invalid_signature", response.text)

    def test_claim_referral_empty_code_returns_400(self):
        for empty_code in ["", "   ", "\t\n"]:
            response = self.client.post("/v1/users/me/referral/claim", json={"code": empty_code})
            self.assertEqual(response.status_code, 400)
            self.assertEqual(response.json()["detail"], "Referral code cannot be empty")

    def test_claim_referral_auth_metadata_failure_returns_sanitized_503(self):
        self._ref_mock.referrer_uid_from_code.side_effect = None
        self._ref_mock.referrer_uid_from_code.return_value = "referrer-123"
        with patch.object(
            self._router_mod.firebase_admin.auth,
            "get_user",
            side_effect=RuntimeError("Firebase Auth internal connection timeout"),
        ):
            response = self.client.post("/v1/users/me/referral/claim", json={"code": "valid-code"})
            self.assertEqual(response.status_code, 503)
            self.assertEqual(response.json()["detail"], "User authentication metadata temporarily unavailable")
            self.assertNotIn("Firebase Auth", response.text)

    def test_claim_referral_transaction_storage_failure_returns_sanitized_503(self):
        self._ref_mock.referrer_uid_from_code.side_effect = None
        self._ref_mock.referrer_uid_from_code.return_value = "referrer-123"
        with patch.object(
            self._router_mod,
            "claim_referral_trial",
            side_effect=RuntimeError("GoogleCloudError: 503 Firestore Transaction Contention"),
        ):
            response = self.client.post("/v1/users/me/referral/claim", json={"code": "valid-code"})
            self.assertEqual(response.status_code, 503)
            self.assertEqual(response.json()["detail"], "Referral claim service temporarily unavailable")
            self.assertNotIn("Firestore Transaction", response.text)

    def test_claim_referral_telemetry_failure_does_not_break_success_response(self):
        self._ref_mock.referrer_uid_from_code.side_effect = None
        self._ref_mock.referrer_uid_from_code.return_value = "referrer-123"
        with patch.object(self._router_mod, "claim_referral_trial", return_value=(True, "granted")):
            with patch.object(self._router_mod, "emit_posthog_event", side_effect=RuntimeError("Posthog drop")):
                response = self.client.post("/v1/users/me/referral/claim", json={"code": "valid-code"})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json(), {"claimed": True, "trial_days": 30})


if __name__ == "__main__":
    unittest.main()
