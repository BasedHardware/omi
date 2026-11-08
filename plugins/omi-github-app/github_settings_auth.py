"""Signed browser session for the GitHub App settings routes.

The settings page is reached from Omi with only ``?uid=``, so the plugin cannot
treat that query value as proof of identity: anyone can call the mutating
settings routes with another user's uid and overwrite their stored agent key,
provider, or repository binding.

After a successful GitHub OAuth callback the plugin now issues an HMAC-signed
session cookie bound to that uid, and every settings write requires the cookie
to name the same uid with a valid signature. ``/auth/callback`` also refuses to
rebind a uid that already has a stored access token unless that signed session
is present or the OAuth token belongs to the same GitHub identity that is
already stored, so an attacker cannot overwrite an existing GitHub binding by
starting OAuth for someone else's uid. The identity path lets users who linked
before this guard shipped recover their own session by reconnecting.

Fails closed: 503 when ``GITHUB_SETTINGS_SECRET`` is unset, 401 when the cookie
is missing, names another uid, or carries a bad signature. Mirrors the
shared-secret guard in ``github_tools_auth.py`` but is scoped per browser
session instead of per trusted backend caller.
"""

import hashlib
import hmac
import os
from typing import Optional

from fastapi import HTTPException, Request

SECRET_ENV = "GITHUB_SETTINGS_SECRET"
COOKIE_NAME = "omi_github_settings"
COOKIE_MAX_AGE_SECONDS = 30 * 24 * 60 * 60


def _configured_secret() -> Optional[str]:
    secret = os.getenv(SECRET_ENV)
    if secret is None:
        return None
    secret = secret.strip()
    return secret or None


def _signature(secret: str, uid: str) -> str:
    return hmac.new(secret.encode("utf-8"), uid.encode("utf-8"), hashlib.sha256).hexdigest()


def session_value(uid: str) -> str:
    """Return the cookie value for a successfully authenticated uid."""
    secret = _configured_secret()
    if secret is None:
        raise HTTPException(status_code=503, detail="github settings auth is not configured")
    return f"{uid}.{_signature(secret, uid)}"


def session_matches(request: Request, uid: str) -> bool:
    """True when the request carries a valid session cookie for exactly *uid*."""
    secret = _configured_secret()
    if secret is None or not uid:
        return False
    cookie = request.cookies.get(COOKIE_NAME)
    if not cookie:
        return False
    cookie_uid, _, signature = cookie.rpartition(".")
    if not cookie_uid or not signature or cookie_uid != uid:
        return False
    return hmac.compare_digest(signature, _signature(secret, uid))


def require_settings_session(request: Request, uid: str) -> None:
    """Reject settings writes that do not belong to a signed-in browser session."""
    secret = _configured_secret()
    if secret is None:
        raise HTTPException(status_code=503, detail="github settings auth is not configured")

    cookie = request.cookies.get(COOKIE_NAME)
    if not cookie:
        raise HTTPException(status_code=401, detail="unauthorized")
    cookie_uid, _, signature = cookie.rpartition(".")
    if not cookie_uid or not signature or cookie_uid != uid:
        raise HTTPException(status_code=401, detail="unauthorized")
    if not hmac.compare_digest(signature, _signature(secret, uid)):
        raise HTTPException(status_code=401, detail="unauthorized")
