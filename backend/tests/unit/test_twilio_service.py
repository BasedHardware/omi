import os
from unittest.mock import patch, MagicMock

os.environ.setdefault('TWILIO_ACCOUNT_SID', 'ACtest123')
os.environ.setdefault('TWILIO_AUTH_TOKEN', 'test_auth_token')
os.environ.setdefault('TWILIO_API_KEY_SID', 'SKtest123')
os.environ.setdefault('TWILIO_API_KEY_SECRET', 'test_api_secret')
os.environ.setdefault('TWILIO_TWIML_APP_SID', 'APtest123')

from utils.twilio_service import generate_access_token, validate_twilio_signature


@patch('twilio.jwt.access_token.AccessToken.to_jwt', return_value='mock.jwt.token')
def test_generate_access_token(mock_jwt):
    result = generate_access_token('user-abc', ttl=600)
    assert result['access_token'] == 'mock.jwt.token'
    assert result['identity'] == 'user-abc'
    assert result['ttl'] == 600


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
    """When auth_token is not set, validation is skipped (returns True for local dev)."""
    with patch('utils.twilio_service.auth_token', None):
        result = validate_twilio_signature(
            'https://example.com/twiml',
            {'To': '+15551234567'},
            '',
        )
        assert result is True
