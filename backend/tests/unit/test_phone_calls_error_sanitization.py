import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
from backend.routers.phone_calls import PhoneCallsRouter
from twilio.base.exceptions import TwilioRestException

@pytest.fixture
def client():
    router = PhoneCallsRouter()
    return TestClient(router)

def test_verify_phone_number_twilio_error(client):
    with patch.object(PhoneCallsRouter, 'verify_phone_number') as mock_method:
        mock_method.side_effect = TwilioRestException("Test error")
        with pytest.raises(HTTPException) as exc_info:
            client.get("/verify?phone=123")
        assert exc_info.value.detail == "Failed to start phone number verification"

def test_get_phone_token_twilio_error(client):
    with patch.object(PhoneCallsRouter, 'get_phone_token') as mock_method:
        mock_method.side_effect = TwilioRestException("Test error")
        with pytest.raises(HTTPException) as exc_info:
            client.get("/token?phone=123")
        assert exc_info.value.detail == "Failed to generate phone access token"

def test_generic_exception_handling(client, caplog):
    with patch.object(PhoneCallsRouter, 'verify_phone_number') as mock_method:
        mock_method.side_effect = Exception("Generic error")
        with pytest.raises(HTTPException) as exc_info:
            client.get("/verify?phone=123")
        assert "Internal server error" in exc_info.value.detail
        assert "Generic error" not in caplog.text
