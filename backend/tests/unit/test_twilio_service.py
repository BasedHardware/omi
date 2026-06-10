import os
import sys
import types
from unittest.mock import patch, MagicMock

from tests.unit.twilio_stub import install_twilio_stub

os.environ.setdefault('TWILIO_ACCOUNT_SID', 'ACtest123')
os.environ.setdefault('TWILIO_AUTH_TOKEN', 'test_auth_token')
os.environ.setdefault('TWILIO_API_KEY_SID', 'SKtest123')
os.environ.setdefault('TWILIO_API_KEY_SECRET', 'test_api_secret')
os.environ.setdefault('TWILIO_TWIML_APP_SID', 'APtest123')
install_twilio_stub()


def _install_phone_calls_stub():
    database_module = sys.modules.get('database')
    if database_module is None:
        database_module = types.ModuleType('database')
        sys.modules['database'] = database_module
    if not hasattr(database_module, '__path__'):
        database_module.__path__ = [os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'database'))]
    if 'database.phone_calls' not in sys.modules:
        stub = types.ModuleType('database.phone_calls')
        stub.get_phone_numbers = lambda uid: []
        sys.modules['database.phone_calls'] = stub
        setattr(database_module, 'phone_calls', stub)


_install_phone_calls_stub()

from utils.twilio_service import generate_access_token, validate_twilio_signature


@patch('twilio.jwt.access_token.AccessToken.to_jwt', return_value='mock.jwt.token')
def test_generate_access_token(mock_jwt):
    result = generate_access_token('user-abc', ttl=600)
    assert result['access_token'] == 'mock.jwt.token'
    assert result['identity'] == 'user-abc'
    assert result['ttl'] == 600


def test_twilio_stub_dial_appends_multiple_numbers():
    from twilio.twiml.voice_response import Dial, VoiceResponse

    dial = Dial(caller_id='+15550000000')
    first_number = dial.number('+15551111111')
    second_number = dial.number('+15552222222')

    assert str(first_number) == '<Number>+15551111111</Number>'
    assert str(second_number) == '<Number>+15552222222</Number>'

    response = VoiceResponse()
    response.append(dial)

    assert (
        str(response) == '<?xml version="1.0" encoding="utf-8"?><Response><Dial callerId="+15550000000">'
        '<Number>+15551111111</Number><Number>+15552222222</Number></Dial></Response>'
    )


def test_validate_twilio_signature_valid():
    mock_validator = MagicMock()
    mock_validator.validate.return_value = True

    with patch('utils.twilio_service.RequestValidator', return_value=mock_validator):
        with patch('utils.twilio_service.auth_token', 'test_token'):
            result = validate_twilio_signature(
                'https://example.com/twiml',
                {'To': '+15551234567'},
                'valid-sig',
            )
            assert result is True
            mock_validator.validate.assert_called_once_with(
                'https://example.com/twiml',
                {'To': '+15551234567'},
                'valid-sig',
            )


def test_validate_twilio_signature_invalid():
    mock_validator = MagicMock()
    mock_validator.validate.return_value = False

    with patch('utils.twilio_service.RequestValidator', return_value=mock_validator):
        with patch('utils.twilio_service.auth_token', 'test_token'):
            result = validate_twilio_signature(
                'https://example.com/twiml',
                {'To': '+15551234567'},
                'bad-sig',
            )
            assert result is False


def test_validate_twilio_signature_no_auth_token():
    """When auth_token is not set, validation fails (auth_token is required)."""
    with patch('utils.twilio_service.auth_token', None):
        result = validate_twilio_signature(
            'https://example.com/twiml',
            {'To': '+15551234567'},
            '',
        )
        assert result is False
