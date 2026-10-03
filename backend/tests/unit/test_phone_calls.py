import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from routers.phone_calls import router, _redact_phone, E164_PATTERN
from utils.other import endpoints as auth

TEST_UID = 'test-uid-123'
TEST_UID_OTHER = 'test-uid-other'


@pytest.fixture(autouse=True)
def _stub_phone_call_plan_guards(monkeypatch):
    monkeypatch.setattr('routers.phone_calls.check_call_access', MagicMock())
    monkeypatch.setattr(
        'routers.phone_calls.get_quota_snapshot',
        MagicMock(return_value=SimpleNamespace(has_access=True, is_paid=True, max_duration_seconds=None)),
    )
    monkeypatch.setattr(
        'routers.phone_calls.reserve_phone_call_quota',
        MagicMock(return_value=SimpleNamespace(has_access=True, is_paid=False, max_duration_seconds=None)),
    )
    monkeypatch.setattr('routers.phone_calls.check_destination_allowed', MagicMock())
    from utils.other.endpoints import cached

    cached.clear()


def _make_app():
    app = FastAPI()
    app.include_router(router)
    return app


@pytest.fixture()
def client():
    app = _make_app()
    app.dependency_overrides[auth.get_current_user_uid] = lambda: TEST_UID
    return TestClient(app)


@pytest.fixture()
def client_other_uid():
    app = _make_app()
    app.dependency_overrides[auth.get_current_user_uid] = lambda: TEST_UID_OTHER
    return TestClient(app)


# ---------------------------------------------------------------------------
# Helper: _redact_phone
# ---------------------------------------------------------------------------


def test_redact_phone_normal():
    assert _redact_phone('+15551234567') == '+1***4567'


def test_redact_phone_short():
    assert _redact_phone('123') == '***'


# ---------------------------------------------------------------------------
# Helper: E164_PATTERN
# ---------------------------------------------------------------------------


def test_e164_pattern_valid():
    assert E164_PATTERN.match('+15551234567')
    assert E164_PATTERN.match('+442071234567')
    assert E164_PATTERN.match('+81312345678')


def test_e164_pattern_invalid():
    assert not E164_PATTERN.match('15551234567')  # no +
    assert not E164_PATTERN.match('+0551234567')  # leading zero
    assert not E164_PATTERN.match('+1')  # too short
    assert not E164_PATTERN.match('not-a-number')


# ---------------------------------------------------------------------------
# POST /v1/phone/numbers/verify
# ---------------------------------------------------------------------------


@patch('routers.phone_calls.phone_calls_db')
@patch('routers.phone_calls.start_caller_id_verification')
def test_verify_phone_number_success(mock_start, mock_db, client):
    mock_db.get_phone_number_by_number.return_value = None
    mock_db.set_pending_verification.return_value = None
    mock_start.return_value = {
        'verification_sid': 'CA123',
        'phone_number': '+15551234567',
        'validation_code': '123456',
        'status': 'pending',
    }

    resp = client.post('/v1/phone/numbers/verify', json={'phone_number': '+15551234567'})
    assert resp.status_code == 200
    data = resp.json()
    assert data['verification_sid'] == 'CA123'
    assert data['status'] == 'pending'
    mock_db.set_pending_verification.assert_called_once_with(TEST_UID, '+15551234567')


@patch('routers.phone_calls.phone_calls_db')
def test_verify_phone_number_invalid_format(mock_db, client):
    resp = client.post('/v1/phone/numbers/verify', json={'phone_number': '5551234567'})
    assert resp.status_code == 400
    assert 'E.164' in resp.json()['detail']


@patch('routers.phone_calls.phone_calls_db')
def test_verify_phone_number_already_verified_locally(mock_db, client):
    mock_db.get_phone_number_by_number.return_value = {'id': 'abc', 'phone_number': '+15551234567'}

    resp = client.post('/v1/phone/numbers/verify', json={'phone_number': '+15551234567'})
    assert resp.status_code == 409
    assert 'already verified' in resp.json()['detail']


@patch('routers.phone_calls.phone_calls_db')
@patch('routers.phone_calls.get_caller_id')
@patch('routers.phone_calls.start_caller_id_verification')
def test_verify_phone_number_already_verified_in_twilio(mock_start, mock_get_cid, mock_db, client):
    """User cannot claim a number that's already verified in Twilio by another user."""
    from twilio.base.exceptions import TwilioRestException

    mock_db.get_phone_number_by_number.return_value = None
    mock_start.side_effect = TwilioRestException(status=400, uri='', code=21450, msg='already exists')
    mock_get_cid.return_value = {'sid': 'PN123', 'phone_number': '+15551234567'}  # Number exists in Twilio

    resp = client.post('/v1/phone/numbers/verify', json={'phone_number': '+15551234567'})
    assert resp.status_code == 409
    assert 'already registered' in resp.json()['detail']
    mock_db.upsert_phone_number.assert_not_called()


# ---------------------------------------------------------------------------
# POST /v1/phone/numbers/verify/check
# ---------------------------------------------------------------------------


@patch('routers.phone_calls.phone_calls_db')
@patch('routers.phone_calls.check_caller_id_verified')
def test_check_verification_not_verified(mock_check, mock_db, client):
    mock_db.get_phone_number_by_number.return_value = None
    mock_db.get_pending_verification_uid.return_value = TEST_UID
    mock_check.return_value = False

    resp = client.post('/v1/phone/numbers/verify/check', json={'phone_number': '+15551234567'})
    assert resp.status_code == 200
    assert resp.json()['verified'] is False


@patch('routers.phone_calls.phone_calls_db')
@patch('routers.phone_calls.get_caller_id')
@patch('routers.phone_calls.check_caller_id_verified')
def test_check_verification_success(mock_check, mock_get_cid, mock_db, client):
    mock_db.get_phone_number_by_number.return_value = None
    mock_db.get_pending_verification_uid.return_value = TEST_UID
    mock_check.return_value = True
    mock_get_cid.return_value = {'sid': 'PN123', 'friendly_name': 'Test'}
    mock_db.get_phone_numbers.return_value = []
    mock_db.upsert_phone_number.return_value = None
    mock_db.delete_pending_verification.return_value = None

    resp = client.post('/v1/phone/numbers/verify/check', json={'phone_number': '+15551234567'})
    assert resp.status_code == 200
    data = resp.json()
    assert data['verified'] is True
    assert data['phone_number_id'] is not None
    mock_db.delete_pending_verification.assert_called_once_with('+15551234567')


@patch('routers.phone_calls.phone_calls_db')
@patch('routers.phone_calls.check_caller_id_verified')
def test_check_verification_wrong_user(mock_check, mock_db, client):
    """User B cannot claim a number whose verification was initiated by User A."""
    mock_db.get_phone_number_by_number.return_value = None
    mock_db.get_pending_verification_uid.return_value = TEST_UID_OTHER  # different uid
    mock_check.return_value = True  # number IS verified in Twilio

    resp = client.post('/v1/phone/numbers/verify/check', json={'phone_number': '+15551234567'})
    assert resp.status_code == 200
    assert resp.json()['verified'] is False
    # Should NOT have stored anything
    mock_db.upsert_phone_number.assert_not_called()


@patch('routers.phone_calls.phone_calls_db')
@patch('routers.phone_calls.check_caller_id_verified')
def test_check_verification_no_pending_record(mock_check, mock_db, client):
    """Cannot claim a number if no pending verification exists (expired or never started)."""
    mock_db.get_phone_number_by_number.return_value = None
    mock_db.get_pending_verification_uid.return_value = None  # No pending record
    mock_check.return_value = True  # Number IS verified in Twilio

    resp = client.post('/v1/phone/numbers/verify/check', json={'phone_number': '+15551234567'})
    assert resp.status_code == 200
    assert resp.json()['verified'] is False
    mock_db.upsert_phone_number.assert_not_called()


@patch('routers.phone_calls.phone_calls_db')
@patch('routers.phone_calls.start_caller_id_verification')
def test_verify_phone_number_sanitizes_twilio_exception(mock_start, mock_db, client):
    from twilio.base.exceptions import TwilioRestException

    mock_db.get_phone_number_by_number.return_value = None
    sensitive_token = "dummy_secret_auth_token_9876543210"
    mock_start.side_effect = TwilioRestException(
        status=500,
        uri="https://api.twilio.com",
        code=50000,
        msg=f"Internal Twilio failure with credentials {sensitive_token}",
    )

    with patch('routers.phone_calls.logger.error') as mock_logger:
        resp = client.post('/v1/phone/numbers/verify', json={'phone_number': '+15551234567'})
        assert resp.status_code == 500
        assert resp.json()['detail'] == "Failed to start verification. Please try again later."
        assert sensitive_token not in resp.text
        mock_logger.assert_called_once()
        log_msg = mock_logger.call_args[0][0]
        assert sensitive_token not in log_msg  # sanitized by sanitize()


@patch('routers.phone_calls.phone_calls_db')
@patch('routers.phone_calls.start_caller_id_verification')
def test_verify_phone_number_sanitizes_generic_exception(mock_start, mock_db, client):
    mock_db.get_phone_number_by_number.return_value = None
    sensitive_db_url = "postgres://root:supersecretpass123@db.internal:5432/omi"
    mock_start.side_effect = RuntimeError(f"Database error at {sensitive_db_url}")

    with patch('routers.phone_calls.logger.error') as mock_logger:
        resp = client.post('/v1/phone/numbers/verify', json={'phone_number': '+15551234567'})
        assert resp.status_code == 500
        assert resp.json()['detail'] == "Failed to start verification. Please try again later."
        assert "supersecretpass123" not in resp.text
        mock_logger.assert_called_once()


# ---------------------------------------------------------------------------
# POST /v1/phone/token
# ---------------------------------------------------------------------------


@patch('routers.phone_calls.phone_calls_db')
@patch('routers.phone_calls.generate_access_token')
def test_get_phone_token_sanitizes_exception(mock_generate, mock_db, client):
    mock_db.get_primary_phone_number.return_value = {'phone_number': '+15551234567'}
    sensitive_key = "dummy_service_account_secret_12345678"
    mock_generate.side_effect = RuntimeError(f"Twilio token generation crashed with auth {sensitive_key}")

    with patch('routers.phone_calls.logger.error') as mock_logger:
        resp = client.post('/v1/phone/token')
        assert resp.status_code == 500
        assert resp.json()['detail'] == "Failed to generate token. Please try again later."
        assert sensitive_key not in resp.text
        mock_logger.assert_called_once()
        log_msg = mock_logger.call_args[0][0]
        assert sensitive_key not in log_msg


# ---------------------------------------------------------------------------
# POST /v1/phone/twiml
# ---------------------------------------------------------------------------


def test_twiml_rejects_oversized_urlencoded_body(client):
    body = b'payload=' + (b'x' * (5 * 1024 * 1024))

    resp = client.post(
        '/v1/phone/twiml',
        content=body,
        headers={'Content-Type': 'application/x-www-form-urlencoded'},
    )

    assert resp.status_code == 400
    assert resp.json()['detail'] == 'Form body exceeded maximum size of 5242880 bytes.'


@patch('routers.phone_calls.validate_twilio_signature', return_value=True)
@patch('routers.phone_calls.phone_calls_db')
def test_twiml_no_destination(mock_db, mock_sig, client):
    resp = client.post('/v1/phone/twiml', data={'To': '', 'From': 'client:test-uid', 'CallId': 'C1'})
    assert resp.status_code == 200
    assert 'No destination number' in resp.text


@patch('routers.phone_calls.validate_twilio_signature', return_value=True)
@patch('routers.phone_calls.check_caller_id_verified', return_value=True)
@patch('routers.phone_calls.phone_calls_db')
def test_twiml_invalid_e164(mock_db, mock_check, mock_sig, client):
    mock_db.get_primary_phone_number.return_value = {'phone_number': '+15551234567'}

    resp = client.post('/v1/phone/twiml', data={'To': 'not-a-number', 'From': 'client:test-uid', 'CallId': 'C1'})
    assert resp.status_code == 200
    assert 'Invalid destination number' in resp.text


@patch('routers.phone_calls.validate_twilio_signature', return_value=True)
@patch('routers.phone_calls.phone_calls_db')
def test_twiml_no_verified_caller_id(mock_db, mock_sig, client):
    mock_db.get_primary_phone_number.return_value = None

    resp = client.post('/v1/phone/twiml', data={'To': '+15559876543', 'From': 'client:test-uid', 'CallId': 'C1'})
    assert resp.status_code == 200
    assert 'No verified caller ID' in resp.text


@patch('routers.phone_calls.validate_twilio_signature', return_value=False)
def test_twiml_invalid_signature(mock_sig, client):
    resp = client.post(
        '/v1/phone/twiml',
        data={'To': '+15559876543', 'From': 'client:test-uid', 'CallId': 'C1'},
    )
    assert resp.status_code == 403
    assert 'Invalid Twilio signature' in resp.json()['detail']


@patch('routers.phone_calls.validate_twilio_signature', return_value=True)
@patch('routers.phone_calls.check_caller_id_verified', return_value=True)
@patch('routers.phone_calls.phone_calls_db')
def test_twiml_success(mock_db, mock_check, mock_sig, client):
    mock_db.get_primary_phone_number.return_value = {'phone_number': '+15551234567'}

    resp = client.post('/v1/phone/twiml', data={'To': '+15559876543', 'From': 'client:test-uid', 'CallId': 'C1'})
    assert resp.status_code == 200
    body = resp.text
    assert '<Dial callerId="+15551234567">' in body
    assert '+15559876543' in body


@patch('routers.phone_calls.validate_twilio_signature', return_value=True)
@patch('routers.phone_calls.check_caller_id_verified', return_value=True)
@patch('routers.phone_calls.phone_calls_db')
def test_twiml_free_tier_reserves_successful_call(mock_db, mock_check, mock_sig, client, monkeypatch):
    mock_db.get_primary_phone_number.return_value = {'phone_number': '+15551234567'}
    snapshot = SimpleNamespace(has_access=True, is_paid=False, monthly_limit=5, max_duration_seconds=None)
    reserve = MagicMock(return_value=snapshot)
    monkeypatch.setattr('routers.phone_calls.get_quota_snapshot', MagicMock(return_value=snapshot))
    monkeypatch.setattr('routers.phone_calls.reserve_phone_call_quota', reserve)

    resp = client.post('/v1/phone/twiml', data={'To': '+15559876543', 'From': f'client:{TEST_UID}', 'CallId': 'C1'})

    assert resp.status_code == 200
    reserve.assert_called_once_with(TEST_UID)
    assert '<Dial callerId="+15551234567">' in resp.text


@patch('routers.phone_calls.validate_twilio_signature', return_value=True)
@patch('routers.phone_calls.check_caller_id_verified', return_value=True)
@patch('routers.phone_calls.phone_calls_db')
def test_twiml_free_tier_rejects_when_atomic_quota_reservation_fails(
    mock_db, mock_check, mock_sig, client, monkeypatch
):
    mock_db.get_primary_phone_number.return_value = {'phone_number': '+15551234567'}
    snapshot = SimpleNamespace(has_access=True, is_paid=False, monthly_limit=5, max_duration_seconds=None)
    exhausted = SimpleNamespace(has_access=False, is_paid=False, monthly_limit=5, max_duration_seconds=None)
    reserve = MagicMock(return_value=exhausted)
    monkeypatch.setattr('routers.phone_calls.get_quota_snapshot', MagicMock(return_value=snapshot))
    monkeypatch.setattr('routers.phone_calls.reserve_phone_call_quota', reserve)

    resp = client.post('/v1/phone/twiml', data={'To': '+15559876543', 'From': f'client:{TEST_UID}', 'CallId': 'C1'})

    assert resp.status_code == 200
    reserve.assert_called_once_with(TEST_UID)
    assert 'Monthly phone call limit reached' in resp.text
    assert '<Dial' not in resp.text
