"""Signed envelopes for MCP Redis cache values.

Redis is a shared cache, not a trusted store: any producer (or a stolen
credential) can write a value under a ``mcp:*`` key. Every cache payload is
therefore wrapped in an HMAC-SHA256 envelope so an unsigned or foreign-signed
blob is dropped and the caller falls through to the authoritative Firestore
read instead of minting an identity or client record.

The signing key is derived from ``ENCRYPTION_SECRET`` with HKDF-SHA256
(``info="mcp-cache-v1"``), so cache MACs never reuse a raw application secret
directly. Each envelope also binds a short type tag (``"cimd"`` for client
metadata, ``"at"`` for access-token identities): a valid signed blob copied
across cache types fails closed instead of being reinterpreted.
"""

import functools
import hashlib
import hmac
import json
import logging
import os
from typing import Any, Optional

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

logger = logging.getLogger(__name__)

_SECRET_ENV = "ENCRYPTION_SECRET"
_HKDF_INFO = b"mcp-cache-v1"
_ENVELOPE_VERSION = 2


@functools.lru_cache(maxsize=8)
def _derive_key(secret: str) -> bytes:
    return HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=None,
        info=_HKDF_INFO,
    ).derive(secret.encode("utf-8"))


def _key() -> Optional[bytes]:
    """Derive the cache-signing key, or ``None`` when no secret is configured.
    The HKDF derivation is memoized per distinct secret, so a changed
    ``ENCRYPTION_SECRET`` still switches keys while the hot path derives once."""
    secret = os.getenv(_SECRET_ENV) or ""
    if not secret:
        return None
    return _derive_key(secret)


def integrity_available() -> bool:
    return _key() is not None


def _canonical(payload: Any) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def dumps_signed(payload: Any, type_tag: str) -> Optional[str]:
    """Serialize ``payload`` with its type tag and a MAC over both fields, or
    ``None`` when no signing secret is configured — an unsigned envelope must
    never be produced, so callers must treat ``None`` as "do not cache"."""
    key = _key()
    if key is None:
        return None
    envelope = {"v": _ENVELOPE_VERSION, "type": type_tag, "data": payload}
    mac = hmac.new(key, _canonical(envelope), hashlib.sha256).hexdigest()
    return json.dumps({**envelope, "mac": mac})


def loads_verified(raw: Optional[str], type_tag: str) -> Optional[Any]:
    """Return the payload only when the envelope is shaped right, carries the
    expected type tag, and MACs under the configured key.

    Any mismatch — wrong tag, wrong key, tampered fields, malformed JSON —
    returns ``None``; cross-type reuse and unsigned attacker writes can never
    serve cache content.
    """
    if raw is None:
        return None
    key = _key()
    if key is None:
        return None
    try:
        envelope = json.loads(raw)
    except (TypeError, ValueError):
        return None
    if (
        not isinstance(envelope, dict)
        or envelope.get("v") != _ENVELOPE_VERSION
        or envelope.get("type") != type_tag
        or "data" not in envelope
        or not isinstance(envelope.get("mac"), str)
    ):
        return None
    expected = hmac.new(
        key,
        _canonical({"v": envelope["v"], "type": envelope["type"], "data": envelope["data"]}),
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(envelope["mac"], expected):
        return None
    return envelope["data"]
