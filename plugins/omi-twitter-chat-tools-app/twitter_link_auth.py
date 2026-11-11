"""HMAC guard for the Twitter disconnect link.

GET /disconnect used to delete tokens for any uid in the query string.
The settings page now embeds an HMAC-SHA256 of the uid, and the handler
checks it with hmac.compare_digest before deleting. Fails closed: 503
when TWITTER_TOOLS_SECRET is unset, 401 when the signature is missing
or wrong.
"""

import hashlib
import hmac
import os

from fastapi import HTTPException

_TWITTER_TOOLS_SECRET_ENV = "TWITTER_TOOLS_SECRET"


def _configured_secret() -> str | None:
    secret = os.getenv(_TWITTER_TOOLS_SECRET_ENV)
    if secret is None:
        return None
    secret = secret.strip()
    return secret or None


def sign_uid(uid: str) -> str:
    """Return the hex HMAC of uid, or '' when the secret is not set."""
    secret = _configured_secret()
    if not secret:
        return ""
    return hmac.new(secret.encode("utf-8"), uid.encode("utf-8"), hashlib.sha256).hexdigest()


def require_signed_link(uid: str, sig: str) -> None:
    """Raise 503 if unconfigured, 401 if sig does not match uid."""
    secret = _configured_secret()
    if not secret:
        raise HTTPException(status_code=503, detail="twitter disconnect auth is not configured")

    expected = sign_uid(uid)
    presented = sig or ""
    if len(presented) != len(expected) or not hmac.compare_digest(presented, expected):
        raise HTTPException(status_code=401, detail="unauthorized")
