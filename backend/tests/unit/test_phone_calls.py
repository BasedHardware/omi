import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from routers.phone_calls import router, _redact_phone, E164_PATTERN
from utils.other import endpoints as auth
import database.phone_calls as phone_db

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


# ---------------------------------------------------------------------------
# Set primary caller ID (POST /{id}/primary) + rename (PATCH /{id})
# ---------------------------------------------------------------------------

_NUMBER = {
    'id': 'n2',
    'phone_number': '+15551230002',
    'friendly_name': 'Work',
    'verified_at': '2026-01-01T00:00:00+00:00',
    'is_primary': True,
}


@patch('routers.phone_calls.phone_calls_db')
def test_make_primary_success(mock_db, client):
    mock_db.set_primary_phone_number.return_value = True
    mock_db.get_phone_number.return_value = _NUMBER
    resp = client.post('/v1/phone/numbers/n2/primary')
    assert resp.status_code == 200
    body = resp.json()
    assert body['id'] == 'n2' and body['is_primary'] is True
    mock_db.set_primary_phone_number.assert_called_once_with(TEST_UID, 'n2')


@patch('routers.phone_calls.phone_calls_db')
def test_make_primary_not_found(mock_db, client):
    mock_db.set_primary_phone_number.return_value = False
    resp = client.post('/v1/phone/numbers/ghost/primary')
    assert resp.status_code == 404
    mock_db.get_phone_number.assert_not_called()


@patch('routers.phone_calls.phone_calls_db')
def test_rename_success_strips_whitespace(mock_db, client):
    mock_db.rename_phone_number.return_value = True
    mock_db.get_phone_number.return_value = {**_NUMBER, 'id': 'n1', 'friendly_name': 'Home', 'is_primary': False}
    resp = client.patch('/v1/phone/numbers/n1', json={'friendly_name': '  Home  '})
    assert resp.status_code == 200
    assert resp.json()['friendly_name'] == 'Home'
    mock_db.rename_phone_number.assert_called_once_with(TEST_UID, 'n1', 'Home')


@patch('routers.phone_calls.phone_calls_db')
def test_rename_not_found(mock_db, client):
    mock_db.rename_phone_number.return_value = False
    resp = client.patch('/v1/phone/numbers/ghost', json={'friendly_name': 'X'})
    assert resp.status_code == 404


@patch('routers.phone_calls.phone_calls_db')
def test_rename_rejects_empty(mock_db, client):
    resp = client.patch('/v1/phone/numbers/n1', json={'friendly_name': ''})
    assert resp.status_code == 422  # min_length=1 on the request model
    mock_db.rename_phone_number.assert_not_called()


@patch('routers.phone_calls.phone_calls_db')
def test_rename_rejects_whitespace_only(mock_db, client):
    resp = client.patch('/v1/phone/numbers/n1', json={'friendly_name': '   '})
    assert resp.status_code == 422  # blank after strip
    mock_db.rename_phone_number.assert_not_called()


def _id_doc(doc_id):
    d = MagicMock()
    d.id = doc_id
    return d


def test_set_primary_reassigns_flags(monkeypatch):
    fake_db = MagicMock()
    col = fake_db.collection.return_value.document.return_value.collection.return_value
    col.select.return_value.stream.return_value = iter([_id_doc('a'), _id_doc('b'), _id_doc('c')])
    batch = fake_db.batch.return_value
    monkeypatch.setattr(phone_db, 'db', fake_db)

    assert phone_db.set_primary_phone_number('uid', 'b') is True
    payloads = [c.args[1] for c in batch.update.call_args_list]
    assert payloads.count({'is_primary': True}) == 1  # only b
    assert payloads.count({'is_primary': False}) == 2  # a and c
    batch.commit.assert_called_once()


def test_set_primary_missing_returns_false(monkeypatch):
    fake_db = MagicMock()
    col = fake_db.collection.return_value.document.return_value.collection.return_value
    col.select.return_value.stream.return_value = iter([_id_doc('a')])
    monkeypatch.setattr(phone_db, 'db', fake_db)
    assert phone_db.set_primary_phone_number('uid', 'nope') is False
    fake_db.batch.return_value.commit.assert_not_called()


def test_rename_updates_only_friendly_name(monkeypatch):
    fake_db = MagicMock()
    ref = fake_db.collection.return_value.document.return_value.collection.return_value.document.return_value
    ref.get.return_value.exists = True
    monkeypatch.setattr(phone_db, 'db', fake_db)
    assert phone_db.rename_phone_number('uid', 'n1', 'Work') is True
    ref.update.assert_called_once_with({'friendly_name': 'Work'})


def test_rename_missing_returns_false(monkeypatch):
    fake_db = MagicMock()
    ref = fake_db.collection.return_value.document.return_value.collection.return_value.document.return_value
    ref.get.return_value.exists = False
    monkeypatch.setattr(phone_db, 'db', fake_db)
    assert phone_db.rename_phone_number('uid', 'n1', 'Work') is False
    ref.update.assert_not_called()
