"""Unit tests for phone_calls router exception detail sanitization.

Verifies that Twilio verification errors and token generation exceptions
do not leak Twilio Account SIDs, auth tokens, or internal socket traces in HTTP 500 response details.
"""

from unittest.mock import MagicMock, patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest
from twilio.base.exceptions import TwilioRestException

from routers.phone_calls import router
from utils.other import endpoints as auth

TEST_UID = "test-uid-phone-user"


@pytest.fixture()
def client():
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[auth.get_current_user_uid] = lambda: TEST_UID
    return TestClient(app)


def test_verify_phone_number_masks_twilio_rest_exception(client, monkeypatch):
    """TwilioRestException must not leak SID or internal message in 500 detail."""
    leak_text = (
        "Twilio API error: Account SID AC1234567890abcdef auth failed on uri https://api.twilio.com/2010-04-01/Accounts"
    )

    monkeypatch.setattr("routers.phone_calls.get_verified_phone_number", lambda uid: None)

    exc = TwilioRestException(status=500, uri="https://api.twilio.com", msg=leak_text)
    exc.code = 20001

    with patch("routers.phone_calls.start_caller_id_verification", side_effect=exc):
        response = client.post("/v1/phone/numbers/verify", json={"phone_number": "+14155552671"})

    assert response.status_code == 500
    data = response.json()
    assert data["detail"] == "Failed to start verification. Please try again."
    assert "AC1234567890" not in data["detail"]
    assert "twilio.com" not in data["detail"]


def test_verify_phone_number_masks_generic_exception(client, monkeypatch):
    """Generic exception must not leak internal traceback/network details."""
    leak_text = "Timeout connecting to twilio-edge-gateway.internal:443"

    monkeypatch.setattr("routers.phone_calls.get_verified_phone_number", lambda uid: None)

    with patch("routers.phone_calls.start_caller_id_verification", side_effect=RuntimeError(leak_text)):
        response = client.post("/v1/phone/numbers/verify", json={"phone_number": "+14155552671"})

    assert response.status_code == 500
    data = response.json()
    assert data["detail"] == "Failed to start verification. Please try again."
    assert "twilio-edge-gateway" not in data["detail"]


def test_get_phone_token_masks_token_generation_exception(client, monkeypatch):
    """generate_access_token failure must return static 500 without signing keys or internal paths."""
    leak_text = "Failed to sign JWT with API Key SK998877665544332211: private key corrupted"

    fake_phone = MagicMock()
    fake_phone.phone_number = "+14155552671"
    monkeypatch.setattr("routers.phone_calls.get_verified_phone_number", lambda uid: fake_phone)

    with patch("routers.phone_calls.generate_access_token", side_effect=RuntimeError(leak_text)):
        response = client.post("/v1/phone/token")

    assert response.status_code == 500
    data = response.json()
    assert data["detail"] == "Failed to generate phone access token. Please try again."
    assert "SK99887766" not in data["detail"]
    assert "private key" not in data["detail"]
