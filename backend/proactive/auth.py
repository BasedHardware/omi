"""Firebase auth interceptor for gRPC streams."""

import contextvars
import logging

import grpc
from firebase_admin import auth

logger = logging.getLogger(__name__)

METADATA_KEY_AUTH = 'authorization'
METADATA_KEY_PLATFORM = 'x-app-platform'
METADATA_KEY_VERSION = 'x-app-version'
METADATA_KEY_DEVICE_ID = 'x-device-id'

# Context variable for the authenticated UID, set by the interceptor
current_uid: contextvars.ContextVar[str] = contextvars.ContextVar('current_uid')


def extract_uid_from_metadata(metadata: tuple) -> str:
    """Extract and verify Firebase UID from gRPC metadata.

    Expects 'authorization: Bearer <firebase_id_token>'.
    Returns the verified UID.
    Raises ValueError on auth failure.
    """
    meta_dict = dict(metadata)
    auth_value = meta_dict.get(METADATA_KEY_AUTH, '')

    if not auth_value.startswith('Bearer '):
        raise ValueError('Missing or malformed Authorization header')

    token = auth_value[7:]
    decoded = auth.verify_id_token(token)
    uid = decoded.get('uid')
    if not uid:
        raise ValueError('Token missing uid claim')
    return uid
