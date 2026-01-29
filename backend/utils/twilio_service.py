import os
from typing import Optional

from twilio.rest import Client
from twilio.jwt.access_token import AccessToken
from twilio.jwt.access_token.grants import VoiceGrant
from twilio.request_validator import RequestValidator

account_sid = os.getenv('TWILIO_ACCOUNT_SID')
auth_token = os.getenv('TWILIO_AUTH_TOKEN')
api_key_sid = os.getenv('TWILIO_API_KEY_SID')
api_key_secret = os.getenv('TWILIO_API_KEY_SECRET')
twiml_app_sid = os.getenv('TWILIO_TWIML_APP_SID')

_client = None


def _get_client() -> Client:
    global _client
    if _client is None:
        if not account_sid or not auth_token:
            raise ValueError("TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN must be set")
        _client = Client(account_sid, auth_token)
    return _client


def generate_access_token(uid: str, ttl: int = 3600) -> dict:
    """
    Generate a Twilio Access Token with Voice grant for the given user.

    Args:
        uid: User ID used as the token identity
        ttl: Token time-to-live in seconds (default 1 hour)

    Returns:
        dict with access_token, ttl, and identity
    """
    if not api_key_sid or not api_key_secret:
        raise ValueError("TWILIO_API_KEY_SID and TWILIO_API_KEY_SECRET must be set")
    if not twiml_app_sid:
        raise ValueError("TWILIO_TWIML_APP_SID must be set")

    token = AccessToken(
        account_sid,
        api_key_sid,
        api_key_secret,
        identity=uid,
        ttl=ttl,
    )

    voice_grant = VoiceGrant(
        outgoing_application_sid=twiml_app_sid,
        incoming_allow=False,
    )
    token.add_grant(voice_grant)

    return {
        'access_token': token.to_jwt(),
        'ttl': ttl,
        'identity': uid,
    }


def start_caller_id_verification(phone_number: str) -> dict:
    """
    Start the caller ID verification process via Twilio.
    Twilio will call the user's phone with a verification code.

    Args:
        phone_number: Phone number in E.164 format

    Returns:
        dict with verification_sid and status
    """
    client = _get_client()
    validation_request = client.validation_requests.create(
        friendly_name=phone_number,
        phone_number=phone_number,
    )
    return {
        'verification_sid': validation_request.call_sid,
        'phone_number': phone_number,
        'validation_code': validation_request.validation_code,
        'status': 'pending',
    }


def check_caller_id_verified(phone_number: str) -> bool:
    """
    Check if a phone number has been verified as a caller ID.

    Args:
        phone_number: Phone number in E.164 format

    Returns:
        True if the number is verified
    """
    client = _get_client()
    outgoing_caller_ids = client.outgoing_caller_ids.list(phone_number=phone_number)
    return len(outgoing_caller_ids) > 0


def get_caller_id(phone_number: str) -> Optional[dict]:
    """
    Get the caller ID record for a verified phone number.

    Args:
        phone_number: Phone number in E.164 format

    Returns:
        dict with sid, phone_number, friendly_name or None
    """
    client = _get_client()
    outgoing_caller_ids = client.outgoing_caller_ids.list(phone_number=phone_number)
    if not outgoing_caller_ids:
        return None
    cid = outgoing_caller_ids[0]
    return {
        'sid': cid.sid,
        'phone_number': cid.phone_number,
        'friendly_name': cid.friendly_name,
    }


def delete_caller_id(sid: str) -> bool:
    """
    Delete a verified caller ID.

    Args:
        sid: The Twilio SID of the outgoing caller ID

    Returns:
        True if deleted successfully
    """
    client = _get_client()
    try:
        client.outgoing_caller_ids(sid).delete()
        return True
    except Exception:
        return False


def list_caller_ids() -> list:
    """
    List all verified outgoing caller IDs for the account.

    Returns:
        List of caller ID records
    """
    client = _get_client()
    caller_ids = client.outgoing_caller_ids.list()
    return [
        {
            'sid': cid.sid,
            'phone_number': cid.phone_number,
            'friendly_name': cid.friendly_name,
        }
        for cid in caller_ids
    ]


def validate_twilio_signature(url: str, params: dict, signature: str) -> bool:
    """
    Validate that a request originated from Twilio using the X-Twilio-Signature header.

    Args:
        url: The full URL of the request
        params: The POST parameters
        signature: The X-Twilio-Signature header value

    Returns:
        True if the signature is valid
    """
    if not auth_token:
        return False
    validator = RequestValidator(auth_token)
    return validator.validate(url, params, signature)
