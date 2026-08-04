"""WebPush message encryption (RFC 8291) with the aes128gcm content coding (RFC 8188).

The UnifiedPush send channel encrypts each notification body for the recipient's registered WebPush
key set before POSTing it to the push server (ntfy). The Flutter UnifiedPush connector (>= 6.x)
generates the key pair, exposes the public key set (``p256dh`` + ``auth``, both base64url) at
registration, and auto-decrypts the delivered message — so the app needs no crypto of its own and
this is the only encryption surface we own.

We wrap ``http-ece`` (the reference aes128gcm implementation) rather than hand-rolling RFC 8291: for
each message we generate an ephemeral P-256 key, and http-ece runs the ECDH against the recipient's
public key, derives the content key/nonce, and frames the ``aes128gcm`` record (salt + the ephemeral
public key live in the record header, so the recipient can derive the same key). ``cryptography``
supplies the P-256 primitive. A body produced here is decryptable by any RFC 8291 recipient.
"""

from __future__ import annotations

import base64

import http_ece
from cryptography.hazmat.primitives.asymmetric import ec

# The single content coding UnifiedPush 3.x / WebPush mandates. Set as the POST Content-Encoding.
CONTENT_ENCODING = "aes128gcm"


def _b64url_decode(value: str) -> bytes:
    """Decode a base64url value tolerating missing padding (WebPush keys are sent unpadded)."""
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def encrypt(plaintext: bytes, *, p256dh: str, auth: str) -> bytes:
    """Encrypt ``plaintext`` for a recipient's WebPush key set.

    ``p256dh`` is the recipient's P-256 public key (65-byte uncompressed point) and ``auth`` its
    16-byte auth secret, both base64url (the WebPush wire form the app registers). Returns the
    ``aes128gcm`` body to POST with ``Content-Encoding: aes128gcm``.
    """
    recipient_key = _b64url_decode(p256dh)
    auth_secret = _b64url_decode(auth)
    # Fail fast on a malformed key set (RFC 8291): p256dh is a 65-byte uncompressed P-256 point and
    # auth is a 16-byte secret. A clear error here beats an opaque failure deep in the crypto/fanout.
    if len(recipient_key) != 65:
        raise ValueError(f"invalid p256dh: expected 65 bytes, got {len(recipient_key)}")
    if len(auth_secret) != 16:
        raise ValueError(f"invalid auth: expected 16 bytes, got {len(auth_secret)}")
    ephemeral = ec.generate_private_key(ec.SECP256R1())
    return http_ece.encrypt(
        plaintext,
        private_key=ephemeral,
        dh=recipient_key,
        auth_secret=auth_secret,
        version=CONTENT_ENCODING,
    )
