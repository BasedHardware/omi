from __future__ import annotations

import os
import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# Ensure ENCRYPTION_SECRET is set for hermetic test execution
os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)

# Stub twilio if not installed in current environment
if "twilio" not in sys.modules:

    def _make_pkg(name: str) -> ModuleType:
        m = ModuleType(name)
        m.__path__ = []  # type: ignore[attr-defined]
        return m

    _twilio = _make_pkg("twilio")
    _twilio_base = _make_pkg("twilio.base")
    _twilio_base_exc = ModuleType("twilio.base.exceptions")

    class TwilioRestException(Exception):
        def __init__(self, msg: str = "Twilio error", code: int = 0, status: int = 500, uri: str = ""):
            super().__init__(msg)
            self.code = code
            self.status = status
            self.uri = uri
            self.msg = msg

    _twilio_base_exc.TwilioRestException = TwilioRestException
    _twilio_jwt = _make_pkg("twilio.jwt")
    _twilio_jwt_token = _make_pkg("twilio.jwt.access_token")
    _twilio_jwt_token.AccessToken = MagicMock()
    _twilio_jwt_grants = _make_pkg("twilio.jwt.access_token.grants")
    _twilio_jwt_grants.VoiceGrant = MagicMock()
    _twilio_rest = _make_pkg("twilio.rest")
    _twilio_rest.Client = MagicMock()
    _twilio_twiml = _make_pkg("twilio.twiml")
    _twilio_twiml_vr = _make_pkg("twilio.twiml.voice_response")
    _twilio_twiml_vr.Dial = MagicMock()
    _twilio_twiml_vr.VoiceResponse = MagicMock()
    _twilio_rv = _make_pkg("twilio.request_validator")
    _twilio_rv.RequestValidator = MagicMock()

    for _name, _mod in [
        ("twilio", _twilio),
        ("twilio.base", _twilio_base),
        ("twilio.base.exceptions", _twilio_base_exc),
        ("twilio.jwt", _twilio_jwt),
        ("twilio.jwt.access_token", _twilio_jwt_token),
        ("twilio.jwt.access_token.grants", _twilio_jwt_grants),
        ("twilio.rest", _twilio_rest),
        ("twilio.twiml", _twilio_twiml),
        ("twilio.twiml.voice_response", _twilio_twiml_vr),
        ("twilio.request_validator", _twilio_rv),
    ]:
        sys.modules.setdefault(_name, _mod)

from routers.phone_calls import router
from twilio.base.exceptions import TwilioRestException
from utils.other import endpoints as auth

TEST_UID = "test-uid-security-audit"


@pytest.fixture(autouse=True)
def _stub_phone_call_plan_guards(monkeypatch):
    monkeypatch.setattr("routers.phone_calls.check_call_access", MagicMock())
    monkeypatch.setattr(
        "routers.phone_calls.get_quota_snapshot",
        MagicMock(return_value=SimpleNamespace(has_access=True, is_paid=True, max_duration_seconds=None)),
    )
    monkeypatch.setattr(
        "routers.phone_calls.reserve_phone_call_quota",
        MagicMock(return_value=SimpleNamespace(has_access=True, is_paid=False, max_duration_seconds=None)),
    )
    monkeypatch.setattr("routers.phone_calls.check_destination_allowed", MagicMock())


def _make_app():
    app = FastAPI()
    app.include_router(router)
    return app


@pytest.fixture()
def client():
    app = _make_app()
    app.dependency_overrides[auth.get_current_user_uid] = lambda: TEST_UID
    return TestClient(app)


class TestPhoneCallsErrorSanitization:
    @patch("routers.phone_calls.logger")
    @patch("routers.phone_calls.phone_calls_db")
    @patch("routers.phone_calls.start_caller_id_verification")
    def test_verify_phone_number_twilio_rest_exception_does_not_leak_raw_details(
        self, mock_start, mock_db, mock_logger, client
    ):
        mock_db.get_phone_number_by_number.return_value = None
        secret_leak = "twilio_auth_token_secret_12345"
        mock_start.side_effect = TwilioRestException(
            msg=f"Upstream Twilio failure with secret {secret_leak}",
            code=50001,
            status=500,
        )

        resp = client.post("/v1/phone/numbers/verify", json={"phone_number": "+15551234567"})

        assert resp.status_code == 500
        data = resp.json()
        assert data["detail"] == "Failed to start phone number verification"
        assert secret_leak not in data["detail"]
        assert "twilio" not in data["detail"].lower()
        mock_logger.error.assert_called_once()
        assert mock_logger.error.call_args[1].get("exc_info") is True

    @patch("routers.phone_calls.logger")
    @patch("routers.phone_calls.phone_calls_db")
    @patch("routers.phone_calls.start_caller_id_verification")
    def test_verify_phone_number_unexpected_exception_does_not_leak_raw_details(
        self, mock_start, mock_db, mock_logger, client
    ):
        mock_db.get_phone_number_by_number.return_value = None
        db_password = "super_secret_db_pass_987"
        mock_start.side_effect = RuntimeError(f"Connection timeout to internal redis://user:{db_password}@host")

        resp = client.post("/v1/phone/numbers/verify", json={"phone_number": "+15551234567"})

        assert resp.status_code == 500
        data = resp.json()
        assert data["detail"] == "Failed to start phone number verification"
        assert db_password not in data["detail"]
        mock_logger.error.assert_called_once()
        assert mock_logger.error.call_args[1].get("exc_info") is True

    @patch("routers.phone_calls.logger")
    @patch("routers.phone_calls.phone_calls_db")
    @patch("routers.phone_calls.generate_access_token")
    def test_get_phone_token_exception_does_not_leak_raw_details(self, mock_generate, mock_db, mock_logger, client):
        mock_db.get_primary_phone_number.return_value = {
            "id": "pn-1",
            "phone_number": "+15551234567",
        }
        api_secret = "SK_twilio_api_secret_key_456"
        mock_generate.side_effect = ValueError(f"Failed generating grant for key {api_secret}")

        resp = client.post("/v1/phone/token")

        assert resp.status_code == 500
        data = resp.json()
        assert data["detail"] == "Failed to generate phone access token"
        assert api_secret not in data["detail"]
        assert "Failed to generate token:" not in data["detail"]
        mock_logger.error.assert_called_once()
        assert mock_logger.error.call_args[1].get("exc_info") is True
