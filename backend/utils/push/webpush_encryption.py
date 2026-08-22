"""WebPush message encryption (RFC 8291) with the aes128gcm content coding (RFC 8188).

The UnifiedPush send channel encrypts each notification body for the recipient's registered WebPush
key set, then **hex-armors** the ciphertext (utf-8 hex text) before POSTing it to the push server
(ntfy is a text transport, so a raw binary body would be treated as an attachment). The Flutter
UnifiedPush connector (>= 6.x) exposes the recipient key set (``p256dh`` + ``auth``, both base64url)
at registration, but its native auto-decrypt does not apply over the hex-armored text channel: the
app owns the key set and decrypts manually (``hex-decode`` -> RFC 8291 decrypt). See ADR-0042.

We wrap ``http-ece`` (the reference aes128gcm implementation) rather than hand-rolling RFC 8291: for
each message we generate an ephemeral P-256 key, and http-ece runs the ECDH against the recipient's
public key, derives the content key/nonce, and frames the ``aes128gcm`` record (salt + the ephemeral
public key live in the record header, so the recipient can derive the same key). ``cryptography``
supplies the P-256 primitive. The ``aes128gcm`` body produced here (before hex-armoring) is
decryptable by any RFC 8291 recipient.
"""

from __future__ import annotations

import base64
import binascii

import http_ece
from cryptography.hazmat.primitives.asymmetric import ec

# The single content coding RFC 8291 / WebPush mandates for the encrypted body.
CONTENT_ENCODING = "aes128gcm"

# base64url uses -_ where standard base64 uses +/; translate so b64decode(validate=True) — which
# rejects non-alphabet characters — accepts a valid key and flags a malformed one.
_B64URL_TO_STD = str.maketrans("-_", "+/")


def _b64url_decode(value: str, *, label: str) -> bytes:
    """Decode a base64url value tolerating missing padding (WebPush keys are sent unpadded).

    Validates the alphabet (``validate=True``): a non-base64url character raises a clear
    ``ValueError`` (not a silently-truncated decode or a raw ``binascii.Error``) so every malformed
    registration produces the same, catchable failure at this boundary."""
    padding = "=" * (-len(value) % 4)
    try:
        return base64.b64decode(value.translate(_B64URL_TO_STD) + padding, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError(f"invalid {label}: not valid base64url ({exc})") from exc


def encrypt(plaintext: bytes, *, p256dh: str, auth: str) -> bytes:
    """Encrypt ``plaintext`` for a recipient's WebPush key set.

    ``p256dh`` is the recipient's P-256 public key (65-byte uncompressed point) and ``auth`` its
    16-byte auth secret, both base64url (the WebPush wire form the app registers). Returns the raw
    ``aes128gcm`` body (the send channel hex-armors it before POSTing to ntfy — see the module
    docstring / ADR-0042). Every malformed key set fails with a ``ValueError`` at this boundary.
    """
    recipient_key = _b64url_decode(p256dh, label="p256dh")
    auth_secret = _b64url_decode(auth, label="auth")
    # Fail fast on a malformed key set (RFC 8291): p256dh is a 65-byte uncompressed P-256 point and
    # auth is a 16-byte secret. A clear error here beats an opaque failure deep in the crypto/fanout.
    if len(recipient_key) != 65:
        raise ValueError(f"invalid p256dh: expected 65 bytes, got {len(recipient_key)}")
    if len(auth_secret) != 16:
        raise ValueError(f"invalid auth: expected 16 bytes, got {len(auth_secret)}")
    # A 65-byte value that isn't actually on the P-256 curve would otherwise fail opaquely inside
    # http_ece's ECDH; validate it here so it too surfaces as a consistent ValueError.
    try:
        ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), recipient_key)
    except ValueError as exc:
        raise ValueError(f"invalid p256dh: not a valid P-256 point ({exc})") from exc
    ephemeral = ec.generate_private_key(ec.SECP256R1())
    return http_ece.encrypt(
        plaintext,
        private_key=ephemeral,
        dh=recipient_key,
        auth_secret=auth_secret,
        version=CONTENT_ENCODING,
    )
