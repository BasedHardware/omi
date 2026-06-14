import os
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import MagicMock, patch

os.environ.setdefault("ENCRYPTION_SECRET", "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv")

BACKEND_DIR = Path(__file__).resolve().parents[2]


def _ensure_package(name, path):
    module = sys.modules.get(name)
    if not isinstance(module, ModuleType):
        module = ModuleType(name)
        sys.modules[name] = module
    module.__path__ = [str(path)]

    if "." in name:
        parent_name, attr_name = name.rsplit(".", 1)
        parent = sys.modules.get(parent_name)
        if parent is not None:
            setattr(parent, attr_name, module)

    return module


def _install_module(name):
    module = ModuleType(name)
    sys.modules[name] = module
    parent_name, _, attr_name = name.rpartition(".")
    parent = sys.modules.get(parent_name)
    if parent is not None:
        setattr(parent, attr_name, module)
    return module


_ensure_package("database", BACKEND_DIR / "database")
_ensure_package("utils", BACKEND_DIR / "utils")
_ensure_package("utils.other", BACKEND_DIR / "utils" / "other")

_install_module("database.phone_calls")
_install_module("database.phone_call_usage")

_phone_utils = _install_module("utils.phone_calls")
_phone_utils.check_call_access = MagicMock()
_phone_utils.check_destination_allowed = MagicMock()
_phone_utils.get_quota_snapshot = MagicMock()

_endpoints = _install_module("utils.other.endpoints")
_endpoints.get_current_user_uid = lambda: "test-uid-123"


def _rate_limit_dependency(**_kwargs):
    def _dependency():
        return None

    return _dependency


_endpoints.rate_limit_dependency = _rate_limit_dependency

_twilio_service = _install_module("utils.twilio_service")
for _attr in [
    "generate_access_token",
    "start_caller_id_verification",
    "check_caller_id_verified",
    "delete_caller_id",
    "get_caller_id",
    "validate_twilio_signature",
]:
    setattr(_twilio_service, _attr, MagicMock())

# Mock modules that initialize GCP/Firebase clients at import time
_mock_firebase = MagicMock()
sys.modules.setdefault("database._client", MagicMock())
sys.modules.setdefault("firebase_admin", _mock_firebase)
sys.modules.setdefault("firebase_admin.auth", _mock_firebase.auth)


class _TwilioRestException(Exception):
    def __init__(self, status=None, uri=None, msg='', code=None, method=None, details=None):
        super().__init__(msg)
        self.status = status
        self.uri = uri
        self.msg = msg
        self.code = code
        self.method = method
        self.details = details


class _VoiceResponse:
    def __init__(self):
        self._children = []

    def say(self, message):
        self._children.append(f'<Say>{message}</Say>')

    def append(self, child):
        self._children.append(str(child))

    def __str__(self):
        return '<Response>' + ''.join(self._children) + '</Response>'


class _Dial:
    def __init__(self, caller_id=None, time_limit=None, **_kwargs):
        self._caller_id = caller_id
        self._time_limit = time_limit
        self._numbers = []

    def number(self, number):
        self._numbers.append(number)

    def __str__(self):
        attrs = []
        if self._caller_id is not None:
            attrs.append(f'callerId="{self._caller_id}"')
        if self._time_limit is not None:
            attrs.append(f'timeLimit="{self._time_limit}"')
        attrs_text = (' ' + ' '.join(attrs)) if attrs else ''
        numbers = ''.join(f'<Number>{number}</Number>' for number in self._numbers)
        return f'<Dial{attrs_text}>{numbers}</Dial>'


_twilio = ModuleType('twilio')
_twilio_base = ModuleType('twilio.base')
_twilio_base_exceptions = ModuleType('twilio.base.exceptions')
_twilio_base_exceptions.TwilioRestException = _TwilioRestException
_twilio_twiml = ModuleType('twilio.twiml')
_twilio_twiml_voice_response = ModuleType('twilio.twiml.voice_response')
_twilio_twiml_voice_response.VoiceResponse = _VoiceResponse
_twilio_twiml_voice_response.Dial = _Dial
_twilio_rest = ModuleType('twilio.rest')
_twilio_rest.Client = MagicMock
_twilio_jwt = ModuleType('twilio.jwt')
_twilio_jwt_access_token = ModuleType('twilio.jwt.access_token')
_twilio_jwt_access_token.AccessToken = MagicMock
_twilio_jwt_access_token_grants = ModuleType('twilio.jwt.access_token.grants')
_twilio_jwt_access_token_grants.VoiceGrant = MagicMock
_twilio_request_validator = ModuleType('twilio.request_validator')
_twilio_request_validator.RequestValidator = MagicMock
sys.modules.setdefault('twilio', _twilio)
sys.modules.setdefault('twilio.base', _twilio_base)
sys.modules.setdefault('twilio.base.exceptions', _twilio_base_exceptions)
sys.modules.setdefault('twilio.twiml', _twilio_twiml)
sys.modules.setdefault('twilio.twiml.voice_response', _twilio_twiml_voice_response)
sys.modules.setdefault('twilio.rest', _twilio_rest)
sys.modules.setdefault('twilio.jwt', _twilio_jwt)
sys.modules.setdefault('twilio.jwt.access_token', _twilio_jwt_access_token)
sys.modules.setdefault('twilio.jwt.access_token.grants', _twilio_jwt_access_token_grants)
sys.modules.setdefault('twilio.request_validator', _twilio_request_validator)

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from routers.phone_calls import router, _redact_phone, E164_PATTERN

# ---------------------------------------------------------------------------
# App / client fixtures
# ---------------------------------------------------------------------------

TEST_UID = 'test-uid-123'
TEST_UID_OTHER = 'test-uid-other'


@pytest.fixture(autouse=True)
def _stub_phone_call_plan_guards(monkeypatch):
    monkeypatch.setattr('routers.phone_calls.check_call_access', MagicMock())
    monkeypatch.setattr(
        'routers.phone_calls.get_quota_snapshot',
        MagicMock(return_value=SimpleNamespace(has_access=True, is_paid=True, max_duration_seconds=None)),
    )
    monkeypatch.setattr('routers.phone_calls.check_destination_allowed', MagicMock())


def _make_app():
    app = FastAPI()
    app.include_router(router)
    return app


@pytest.fixture()
def client():
    app = _make_app()

    # Override auth dependency to return a fixed uid
    from utils.other import endpoints as auth

    app.dependency_overrides[auth.get_current_user_uid] = lambda: TEST_UID
    return TestClient(app)


@pytest.fixture()
def client_other_uid():
    app = _make_app()
    from utils.other import endpoints as auth

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
@patch('routers.phone_calls.phone_call_usage_db')
@patch('routers.phone_calls.phone_calls_db')
def test_twiml_free_tier_counts_successful_call(mock_db, mock_usage_db, mock_check, mock_sig, client, monkeypatch):
    mock_db.get_primary_phone_number.return_value = {'phone_number': '+15551234567'}
    snapshot = SimpleNamespace(has_access=True, is_paid=False, max_duration_seconds=None)
    monkeypatch.setattr('routers.phone_calls.get_quota_snapshot', MagicMock(return_value=snapshot))

    resp = client.post('/v1/phone/twiml', data={'To': '+15559876543', 'From': f'client:{TEST_UID}', 'CallId': 'C1'})

    assert resp.status_code == 200
    mock_usage_db.increment_current_month.assert_called_once_with(TEST_UID)
    assert '<Dial callerId="+15551234567">' in resp.text
