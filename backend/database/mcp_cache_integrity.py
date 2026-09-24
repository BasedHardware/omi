"""HMAC-SHA256 integrity tags for Redis-cached MCP OAuth blobs.

Redis values are not inherently trustworthy: anything able to write the cache
could otherwise forge an access-token identity or a Client ID Metadata
Document. Every cached blob is stored as ``{"data": ..., "mac": hex}`` where
the MAC covers the canonical JSON form of ``data`` and is keyed by the
server-only ``ENCRYPTION_SECRET``. Verification re-serializes the parsed
payload canonically and compares with ``hmac.compare_digest``.

The secret never appears in Redis keys, values, or logs. Callers decide the
failure posture when it is absent: the OAuth token path fails closed
(``McpTokenStoreUnavailable`` -> 503), while CIMD simply skips caching and
revalidates by fetching.
"""

import hashlib
import hmac
import json
import os
from typing import Any, Dict, Optional

_SECRET_ENV = "ENCRYPTION_SECRET"


def _key() -> Optional[bytes]:
    secret = os.getenv(_SECRET_ENV) or ""
    return secret.encode("utf-8") if secret else None


def integrity_available() -> bool:
    return _key() is not None


def _canonical(payload: Dict[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def dumps_signed(payload: Dict[str, Any]) -> Optional[str]:
    """Serialize ``payload`` with an integrity tag, or ``None`` when the
    signing secret is not configured — the caller must not fall back to an
    unsigned write."""
    key = _key()
    if key is None:
        return None
    mac = hmac.new(key, _canonical(payload), hashlib.sha256).hexdigest()
    return json.dumps({"data": payload, "mac": mac})


def loads_verified(raw: Any) -> Optional[Dict[str, Any]]:
    """Return the signed payload, or ``None`` for a missing secret, malformed
    envelope, or MAC mismatch — an unsigned entry is never trusted."""
    key = _key()
    if key is None or raw is None:
        return None
    try:
        text = raw.decode("utf-8") if isinstance(raw, bytes) else str(raw)
        envelope = json.loads(text)
    except (ValueError, UnicodeDecodeError):
        return None
    if not isinstance(envelope, dict):
        return None
    data = envelope.get("data")
    mac = envelope.get("mac")
    if not isinstance(data, dict) or not isinstance(mac, str):
        return None
    expected = hmac.new(key, _canonical(data), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(mac, expected):
        return None
    return data
