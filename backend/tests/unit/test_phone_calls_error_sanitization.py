"""Exception-sanitization guards for the phone calls router.

Upstream Twilio failures and internal errors must never be reflected to clients:
the HTTP response carries a generic message and the raw exception (with any
credentials it may embed) stays in server logs via exc_info.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from twilio.base.exceptions import TwilioRestException

import routers.phone_calls as phone_calls
from routers.phone_calls import router

TEST_UID = 'test-uid-security-audit'


@pytest.fixture()
def client():
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[phone_calls.auth.get_current_user_uid] = lambda: TEST_UID
    return TestClient(app)


@pytest.fixture(autouse=True)
def _stub_guards(monkeypatch):
    monkeypatch.setattr(phone_calls, 'check_call_access', MagicMock())
    monkeypatch.setattr(phone_calls, 'check_destination_allowed', MagicMock())
    monkeypatch.setattr(
        phone_calls,
        'get_quota_snapshot',
        MagicMock(return_value=SimpleNamespace(has_access=True, is_paid=True, max_duration_seconds=None)),
    )
    monkeypatch.setattr(
        phone_calls,
        'reserve_phone_call_quota',
        MagicMock(return_value=SimpleNamespace(has_access=True, is_paid=False, max_duration_seconds=None)),
    )


@pytest.fixture()
def logger(monkeypatch):
    mock = MagicMock()
    monkeypatch.setattr(phone_calls, 'logger', mock)
    return mock


def test_verify_phone_number_twilio_error_does_not_leak_raw_details(client, logger, monkeypatch):
    monkeypatch.setattr(phone_calls.phone_calls_db, 'get_phone_number_by_number', MagicMock(return_value=None))
    secret = 'twilio_auth_token_secret_12345'
    monkeypatch.setattr(
        phone_calls,
        'start_caller_id_verification',
        MagicMock(
            side_effect=TwilioRestException(
                msg=f'Upstream Twilio failure with secret {secret}', code=50001, status=500, uri=''
            )
        ),
    )

    response = client.post('/v1/phone/numbers/verify', json={'phone_number': '+15551234567'})

    assert response.status_code == 500
    detail = response.json()['detail']
    assert detail == 'Failed to start phone number verification'
    assert secret not in detail
    assert 'twilio' not in detail.lower()
    logger.error.assert_called_once()
    assert logger.error.call_args[1].get('exc_info') is True


def test_verify_phone_number_unexpected_error_does_not_leak_raw_details(client, logger, monkeypatch):
    monkeypatch.setattr(phone_calls.phone_calls_db, 'get_phone_number_by_number', MagicMock(return_value=None))
    password = 'super_secret_db_pass_987'
    monkeypatch.setattr(
        phone_calls,
        'start_caller_id_verification',
        MagicMock(side_effect=RuntimeError(f'Connection timeout to internal redis://user:{password}@host')),
    )

    response = client.post('/v1/phone/numbers/verify', json={'phone_number': '+15551234567'})

    assert response.status_code == 500
    detail = response.json()['detail']
    assert detail == 'Failed to start phone number verification'
    assert password not in detail
    logger.error.assert_called_once()
    assert logger.error.call_args[1].get('exc_info') is True


def test_get_phone_token_error_does_not_leak_raw_details(client, logger, monkeypatch):
    monkeypatch.setattr(
        phone_calls.phone_calls_db,
        'get_primary_phone_number',
        MagicMock(return_value={'id': 'pn-1', 'phone_number': '+15551234567'}),
    )
    api_secret = 'SK_twilio_api_secret_key_456'
    monkeypatch.setattr(
        phone_calls,
        'generate_access_token',
        MagicMock(side_effect=ValueError(f'Failed generating grant for key {api_secret}')),
    )

    response = client.post('/v1/phone/token')

    assert response.status_code == 500
    detail = response.json()['detail']
    assert detail == 'Failed to generate phone access token'
    assert api_secret not in detail
    assert 'Failed to generate token:' not in detail
    logger.error.assert_called_once()
    assert logger.error.call_args[1].get('exc_info') is True
