"""Shared-secret (HMAC) guard for Notion disconnect links.

Prevents unauthenticated callers from triggering a disconnect via a crafted
GET /disconnect?uid=<victim> link.  The settings/home page embeds an
HMAC-SHA256 signature of the uid in the disconnect href.  The disconnect
handler verifies the signature with hmac.compare_digest before mutating
state.  Fails closed: 503 when the secret is not configured, 401 on a
missing or wrong signature.

The signing secret is read from the ``NOTION_DISCONNECT_SECRET`` environment
variable.  Mirror the structure of
``plugins/omi-shipbob-app/shipbob_tools_auth.py`` (merged via PR #14684).
"""

import hashlib
import hmac
import os

_NOTION_DISCONNECT_SECRET_ENV = "NOTION_DISCONNECT_SECRET"


def _configured_secret() -> str | None:
    """Return the configured secret, or None if not set."""
    secret = os.getenv(_NOTION_DISCONNECT_SECRET_ENV)
    if secret is None:
        return None
    secret = secret.strip()
    return secret or None


def sign_uid(uid: str) -> str:
    """Return an HMAC-SHA256 signature of *uid* using the configured secret.

    Returns ``""`` when the secret is not configured — the caller can
    embed the link without a signature, and the disconnect handler will
    reject it with ``401`` / ``503`` as appropriate.
    """
    secret = _configured_secret()
    if not secret:
        return ""
    return hmac.new(secret.encode("utf-8"), uid.encode("utf-8"), hashlib.sha256).hexdigest()


def require_disconnect_auth(uid: str, sig: str) -> None:
    """Verify the disconnect signature; raise if invalid.

    - If the secret is not configured → raise ``HTTPException(503)``.
    - If *sig* is missing or wrong → raise ``HTTPException(401)``.
    - If *sig* matches → return ``None`` (success).
    """
    secret = _configured_secret()
    if not secret:
        from fastapi import HTTPException
        raise HTTPException(status_code=503, detail="notion disconnect auth is not configured")

    expected = sign_uid(uid)
    if not hmac.compare_digest(sig, expected):
        from fastapi import HTTPException
        raise HTTPException(status_code=401, detail="unauthorized")