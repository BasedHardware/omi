import importlib.machinery
import os
import sys
import types
from unittest.mock import patch, MagicMock

from tests.unit.twilio_stub import install_phone_calls_stub, install_twilio_stub, prepare_twilio_service_import

os.environ.setdefault('TWILIO_ACCOUNT_SID', 'ACtest123')
os.environ.setdefault('TWILIO_AUTH_TOKEN', 'test_auth_token')
os.environ.setdefault('TWILIO_API_KEY_SID', 'SKtest123')
os.environ.setdefault('TWILIO_API_KEY_SECRET', 'test_api_secret')
os.environ.setdefault('TWILIO_TWIML_APP_SID', 'APtest123')
install_twilio_stub()
prepare_twilio_service_import()
install_phone_calls_stub()

from utils.twilio_service import generate_access_token, validate_twilio_signature

_MISSING = object()


@patch('twilio.jwt.access_token.AccessToken.to_jwt', return_value='mock.jwt.token')
def test_generate_access_token(mock_jwt):
    result = generate_access_token('user-abc', ttl=600)
    assert result['access_token'] == 'mock.jwt.token'
    assert result['identity'] == 'user-abc'
    assert result['ttl'] == 600


def test_install_twilio_stub_replaces_incomplete_existing_twilio():
    module_names = [
        'twilio',
        'twilio.rest',
        'twilio.jwt',
        'twilio.jwt.access_token',
        'twilio.jwt.access_token.grants',
        'twilio.request_validator',
        'twilio.base',
        'twilio.base.exceptions',
        'twilio.twiml',
        'twilio.twiml.voice_response',
    ]
    originals = {name: sys.modules.get(name, _MISSING) for name in module_names}
    try:
        for name in module_names:
            sys.modules.pop(name, None)
        sys.modules['twilio'] = MagicMock()

        install_twilio_stub()

        assert isinstance(sys.modules['twilio'], types.ModuleType)
        assert sys.modules['twilio.base.exceptions'].TwilioRestException(status=400, uri='', code=21450).code == 21450
    finally:
        for name, module in originals.items():
            if module is _MISSING:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module


def test_install_twilio_stub_replaces_meta_path_stub_without_origin():
    module_names = [
        'twilio',
        'twilio.rest',
        'twilio.jwt',
        'twilio.jwt.access_token',
        'twilio.jwt.access_token.grants',
        'twilio.request_validator',
        'twilio.base',
        'twilio.base.exceptions',
        'twilio.twiml',
        'twilio.twiml.voice_response',
    ]
    originals = {name: sys.modules.get(name, _MISSING) for name in module_names}
    try:
        for name in module_names:
            sys.modules.pop(name, None)
        incomplete = types.ModuleType('twilio')
        incomplete.__spec__ = importlib.machinery.ModuleSpec('twilio', loader=None, is_package=True)
        sys.modules['twilio'] = incomplete

        install_twilio_stub()

        assert sys.modules['twilio'] is not incomplete
        assert sys.modules['twilio.base.exceptions'].TwilioRestException(status=400, uri='', code=21450).code == 21450
    finally:
        for name, module in originals.items():
            if module is _MISSING:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module


def test_install_phone_calls_stub_completes_existing_module():
    original = sys.modules.get('database.phone_calls', _MISSING)
    empty_stub = types.ModuleType('database.phone_calls')
    try:
        sys.modules['database.phone_calls'] = empty_stub

        stub = install_phone_calls_stub()

        assert stub is empty_stub
        assert stub.get_phone_numbers('uid-1') == []
    finally:
        if original is _MISSING:
            sys.modules.pop('database.phone_calls', None)
        else:
            sys.modules['database.phone_calls'] = original


def test_twilio_stub_dial_appends_multiple_numbers():
    from twilio.twiml.voice_response import Dial, VoiceResponse

    def without_xml_declaration(value):
        return str(value).replace('<?xml version="1.0" encoding="UTF-8"?>', '')

    dial = Dial(caller_id='+15550000000')
    first_number = dial.number('+15551111111')
    second_number = dial.number('+15552222222')

    assert without_xml_declaration(first_number) == '<Number>+15551111111</Number>'
    assert without_xml_declaration(second_number) == '<Number>+15552222222</Number>'

    response = VoiceResponse()
    response.append(dial)

    response_xml = str(response).replace('encoding="UTF-8"', 'encoding="utf-8"')
    assert (
        response_xml == '<?xml version="1.0" encoding="utf-8"?><Response><Dial callerId="+15550000000">'
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
