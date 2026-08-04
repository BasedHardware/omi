"""WebPush aes128gcm encryption (RFC 8291) for the UnifiedPush send channel."""

from __future__ import annotations

import base64
import os

import http_ece
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

from utils.push import webpush_encryption as wpe


def _b64url(raw: bytes) -> str:
    """Encode as unpadded base64url, the WebPush wire form the app registers."""
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _recipient():
    """Simulate the app's UnifiedPush connector: a P-256 key pair + 16-byte auth secret.

    Returns (private_key, p256dh_b64url, auth_b64url, auth_bytes) — the app keeps the private key and
    registers p256dh/auth with the backend.
    """
    private_key = ec.generate_private_key(ec.SECP256R1())
    p256dh = private_key.public_key().public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
    )
    import os

    auth = os.urandom(16)
    return private_key, _b64url(p256dh), _b64url(auth), auth


def test_encrypted_body_roundtrips_for_a_conformant_recipient():
    private_key, p256dh, auth, auth_bytes = _recipient()
    plaintext = b'{"notification":{"title":"Hi","body":"there"},"data":{"type":"merge_completed"}}'

    body = wpe.encrypt(plaintext, p256dh=p256dh, auth=auth)

    # A conformant RFC 8291 recipient (what the app's connector does) recovers the plaintext.
    decrypted = http_ece.decrypt(body, private_key=private_key, auth_secret=auth_bytes, version="aes128gcm")
    assert decrypted == plaintext


def test_encryption_is_confidential_and_nondeterministic():
    _private_key, p256dh, auth, _auth_bytes = _recipient()
    plaintext = b'{"data":{"secret":"value"}}'

    first = wpe.encrypt(plaintext, p256dh=p256dh, auth=auth)
    second = wpe.encrypt(plaintext, p256dh=p256dh, auth=auth)

    # The plaintext must not appear on the wire, and a fresh ephemeral key + salt per message means
    # two encryptions of the same payload differ (no deterministic ciphertext leak).
    assert plaintext not in first
    assert first != second


def test_unpadded_base64url_keys_are_accepted():
    private_key, p256dh, auth, auth_bytes = _recipient()
    # The recipient helper already strips padding; assert the decoder tolerates it end to end.
    assert "=" not in p256dh and "=" not in auth
    body = wpe.encrypt(b"x", p256dh=p256dh, auth=auth)
    assert http_ece.decrypt(body, private_key=private_key, auth_secret=auth_bytes, version="aes128gcm") == b"x"


def test_invalid_public_key_raises():
    _private_key, _p256dh, auth, _auth_bytes = _recipient()
    with pytest.raises(Exception):
        wpe.encrypt(b"x", p256dh=_b64url(b"not-a-valid-point"), auth=auth)


def test_wrong_length_p256dh_is_rejected_with_a_clear_error():
    # An uncompressed P-256 point is 65 bytes (RFC 8291). A wrong length must fail fast with a
    # specific error, not a cryptic one deep inside http-ece's key import.
    _private_key, _p256dh, auth, _auth_bytes = _recipient()
    with pytest.raises(ValueError, match="p256dh"):
        wpe.encrypt(b"x", p256dh=_b64url(os.urandom(64)), auth=auth)


def test_wrong_length_auth_secret_is_rejected_with_a_clear_error():
    # RFC 8291 fixes the auth secret at 16 bytes; a shorter one must be rejected up front.
    _private_key, p256dh, _auth, _auth_bytes = _recipient()
    with pytest.raises(ValueError, match="auth"):
        wpe.encrypt(b"x", p256dh=p256dh, auth=_b64url(os.urandom(8)))
