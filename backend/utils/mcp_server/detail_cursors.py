"""Authenticated transcript positions; no uid, conversation id or content in tokens.

Owner and view are authenticated as associated data, never serialized into the
cursor. A domain-separated application key works across serving replicas and
restarts. Missing key material fails closed; cursors never authorize a read.
"""

import base64
import binascii
import functools
import json
import os
from typing import Any, Dict

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from utils.mcp_server.cursors import CURSOR_MAX_TOKEN_CHARS, offset_position
from utils.mcp_server.errors import ToolExecutionError


@functools.lru_cache(maxsize=8)
def _derive_key(secret: str) -> bytes:
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=b'mcp-transcript-cursor-v1').derive(
        secret.encode('utf-8')
    )


def _cipher() -> AESGCM:
    secret = os.getenv('ENCRYPTION_SECRET', '')
    if len(secret.encode('utf-8')) < 32:
        raise ToolExecutionError('Transcript paging is temporarily unavailable.', code=-32603)
    return AESGCM(_derive_key(secret))


def _context(uid: str, filters: Dict[str, Any]) -> bytes:
    return json.dumps({'owner': uid, 'view': filters}, sort_keys=True, separators=(',', ':')).encode('utf-8')


def encode_detail_cursor(*, uid: str, filters: Dict[str, Any], position: Dict[str, int]) -> str:
    nonce = os.urandom(12)
    payload = json.dumps({'v': 1, **position}, separators=(',', ':')).encode('utf-8')
    encrypted = _cipher().encrypt(nonce, payload, _context(uid, filters))
    return base64.urlsafe_b64encode(nonce + encrypted).decode('ascii').rstrip('=')


def decode_detail_cursor(token: Any, *, uid: str, filters: Dict[str, Any]) -> Dict[str, int]:
    invalid = ToolExecutionError('Invalid transcript cursor. Restart without cursor.', code=-32602)
    if not isinstance(token, str) or not token or len(token) > CURSOR_MAX_TOKEN_CHARS:
        raise invalid
    try:
        raw = base64.b64decode(token + '=' * (-len(token) % 4), altchars=b'-_', validate=True)
        # Reject alternate encodings of the same token, including changed pad bits.
        if base64.urlsafe_b64encode(raw).decode('ascii').rstrip('=') != token or len(raw) < 28:
            raise invalid
        payload = json.loads(_cipher().decrypt(raw[:12], raw[12:], _context(uid, filters)))
        if not isinstance(payload, dict) or payload.get('v') != 1:
            raise invalid
        # Transcript documents already bound the space; do not inherit the list
        # cursor's arbitrary 100k-position ceiling for long imported transcripts.
        offset = offset_position(payload, maximum=2**63 - 1)
        char_offset = offset_position({'offset': payload.get('char_offset')}, maximum=2**63 - 1)
    except (ValueError, TypeError, binascii.Error, InvalidTag):
        raise invalid from None
    return {'offset': offset, 'char_offset': char_offset}
