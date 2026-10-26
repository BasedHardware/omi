"""Signed browser session for the Slack App settings routes.

The settings page is reached from Omi with only ``?uid=``, so the plugin cannot
treat that query value as proof of identity: anyone can call the mutating
settings routes with another user's uid and overwrite their default channel,
refresh their workspace channel cache, or log them out and delete their stored
Slack OAuth token.

After a successful Slack OAuth callback the plugin issues an HMAC-signed
session cookie bound to that uid, and every settings write requires the cookie
to name the same uid with a valid signature. ``/auth/callback`` also refuses to
rebind a uid that already has a stored access token unless that signed session
is present or the OAuth token belongs to the same Slack workspace (team_id)
that is already stored, so an attacker cannot overwrite an existing Slack
binding by starting OAuth for someone else's uid. The workspace check lets
users who linked before this guard shipped recover their own session by
reconnecting.

Fails closed: 503 when ``SLACK_SETTINGS_SECRET`` is unset, 401 when the cookie
is missing, names another uid, or carries a bad signature.
"""

import hashlib
import hmac
import os
from typing import Any, Optional

from fastapi import HTTPException, Request

SECRET_ENV = "SLACK_SETTINGS_SECRET"
COOKIE_NAME = "omi_slack_settings"
COOKIE_MAX_AGE_SECONDS = 30 * 24 * 60 * 60


def _raise_http_error(status_code: int, detail: str) -> None:
    try:
        exc = HTTPException(status_code=status_code, detail=detail)
    except TypeError:
        exc = HTTPException(detail)
        exc.status_code = status_code
        exc.detail = detail
    raise exc


def _configured_secret() -> Optional[str]:
    secret = os.getenv(SECRET_ENV)
    if secret is None:
        return None
    secret = secret.strip()
    return secret or None


def _signature(secret: str, uid: str) -> str:
    return hmac.new(secret.encode("utf-8"), uid.encode("utf-8"), hashlib.sha256).hexdigest()


def _request_cookies(request: Any) -> dict:
    if request is None:
        return {}
    cookies = getattr(request, "cookies", None)
    return cookies if isinstance(cookies, dict) else {}


def session_value(uid: str) -> str:
    """Return the cookie value for a successfully authenticated uid."""
    secret = _configured_secret()
    if secret is None:
        _raise_http_error(503, "slack settings auth is not configured")
    return f"{uid}.{_signature(secret, uid)}"


def session_matches(request: Request, uid: str) -> bool:
    """True when the request carries a valid session cookie for exactly *uid*."""
    secret = _configured_secret()
    if secret is None or not uid:
        return False
    cookie = _request_cookies(request).get(COOKIE_NAME)
    if not cookie or not isinstance(cookie, str):
        return False
    cookie_uid, _, signature = cookie.rpartition(".")
    if not cookie_uid or not signature or cookie_uid != uid:
        return False
    return hmac.compare_digest(signature, _signature(secret, uid))


def require_settings_session(request: Request, uid: str) -> None:
    """Reject settings writes that do not belong to a signed-in browser session."""
    secret = _configured_secret()
    if secret is None:
        _raise_http_error(503, "slack settings auth is not configured")

    cookie = _request_cookies(request).get(COOKIE_NAME)
    if not cookie or not isinstance(cookie, str):
        _raise_http_error(401, "unauthorized")
    cookie_uid, _, signature = cookie.rpartition(".")
    if not cookie_uid or not signature or cookie_uid != uid:
        _raise_http_error(401, "unauthorized")
    if not hmac.compare_digest(signature, _signature(secret, uid)):
        _raise_http_error(401, "unauthorized")
