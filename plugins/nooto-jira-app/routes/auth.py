"""OAuth 2.0 (3LO) routes for Atlassian — slice B owns this file.

Routes:
    GET /auth/jira              start (HMAC-signed state, 302 to authorize URL)
    GET /auth/jira/callback     finish (verify state, exchange code, persist tokens)
    GET /setup/jira             { is_setup_completed: bool }

References:
    plugins/omi-linear-app/main.py:335-410 — OAuth route shape
    plugins/omi-linear-app/db.py             — token storage + refresh
"""

import logging
import os
import time
import urllib.parse
from typing import Any, Optional

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from db import (
    consume_oauth_state,
    is_setup_completed,
    sign_state,
    store_jira_tokens,
    store_oauth_state,
    verify_state,
)

router = APIRouter()
log = logging.getLogger("nooto-jira-app.auth")

# ── Atlassian endpoints ────────────────────────────────────────────────────

ATLASSIAN_AUTHORIZE_URL = "https://auth.atlassian.com/authorize"
ATLASSIAN_TOKEN_URL = "https://auth.atlassian.com/oauth/token"
ATLASSIAN_RESOURCES_URL = "https://api.atlassian.com/oauth/token/accessible-resources"
ATLASSIAN_ME_URL = "https://api.atlassian.com/me"

DEFAULT_SCOPES = "read:jira-work write:jira-work read:jira-user offline_access"

# ── Templates ──────────────────────────────────────────────────────────────

_TEMPLATES_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "templates")
templates = Jinja2Templates(directory=_TEMPLATES_DIR)


def _render_setup(
    request: Request,
    *,
    status: str,
    uid: Optional[str] = None,
    display_name: Optional[str] = None,
    sites: Optional[list[dict[str, Any]]] = None,
    default_cloud_id: Optional[str] = None,
    error_message: Optional[str] = None,
    subtitle: Optional[str] = None,
    status_code: int = 200,
) -> HTMLResponse:
    return templates.TemplateResponse(
        "setup.html",
        {
            "request": request,
            "status": status,
            "uid": uid or "",
            "display_name": display_name,
            "sites": sites or [],
            "default_cloud_id": default_cloud_id,
            "error_message": error_message,
            "subtitle": subtitle,
        },
        status_code=status_code,
    )


def _env_configured() -> bool:
    return bool(
        os.getenv("JIRA_CLIENT_ID")
        and os.getenv("JIRA_CLIENT_SECRET")
        and os.getenv("JIRA_REDIRECT_URI")
        and os.getenv("JIRA_OAUTH_STATE_SECRET")
    )


# ── Routes ─────────────────────────────────────────────────────────────────


@router.get("/auth/jira")
async def jira_auth_start(uid: str = ""):
    """Kick off the Atlassian 3LO flow."""
    if not uid:
        raise HTTPException(status_code=400, detail="uid is required")
    if not _env_configured():
        raise HTTPException(status_code=400, detail="Jira OAuth is not configured on this server")

    state = sign_state(uid)
    store_oauth_state(uid, state)

    scopes = os.getenv("JIRA_SCOPES", DEFAULT_SCOPES)
    params = {
        "audience": "api.atlassian.com",
        "client_id": os.getenv("JIRA_CLIENT_ID", ""),
        "scope": scopes,
        "redirect_uri": os.getenv("JIRA_REDIRECT_URI", ""),
        "state": state,
        "response_type": "code",
        "prompt": "consent",
    }
    auth_url = f"{ATLASSIAN_AUTHORIZE_URL}?{urllib.parse.urlencode(params)}"
    return RedirectResponse(url=auth_url, status_code=302)


@router.get("/auth/jira/callback", response_class=HTMLResponse)
async def jira_auth_callback(
    request: Request,
    code: Optional[str] = None,
    state: Optional[str] = None,
    error: Optional[str] = None,
    error_description: Optional[str] = None,
):
    """Finish the Atlassian 3LO flow: verify state, exchange code, persist tokens."""
    if error:
        return _render_setup(
            request,
            status="error",
            error_message=error_description or f"Authorization failed: {error}",
        )

    if not code or not state:
        return _render_setup(
            request,
            status="error",
            error_message="Missing authorization code or state.",
            status_code=400,
        )

    try:
        uid = verify_state(state)
    except (ValueError, RuntimeError) as exc:
        log.warning("Jira OAuth state verification failed: %s", exc)
        return _render_setup(
            request,
            status="error",
            error_message="Invalid or expired authorization state. Please try again.",
            status_code=400,
        )

    # GETDEL acts as a one-shot replay guard alongside the HMAC check above.
    stored = consume_oauth_state(uid)
    if stored is None or stored != state:
        log.warning("Jira OAuth state replay/missing for uid=%s", uid)
        return _render_setup(
            request,
            status="error",
            uid=uid,
            error_message="Authorization request expired or already used. Please try again.",
            status_code=400,
        )

    client_id = os.getenv("JIRA_CLIENT_ID", "")
    client_secret = os.getenv("JIRA_CLIENT_SECRET", "")
    redirect_uri = os.getenv("JIRA_REDIRECT_URI", "")

    try:
        with httpx.Client(timeout=15.0) as client:
            token_resp = client.post(
                ATLASSIAN_TOKEN_URL,
                json={
                    "grant_type": "authorization_code",
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "code": code,
                    "redirect_uri": redirect_uri,
                },
                headers={"Content-Type": "application/json"},
            )
    except (httpx.HTTPError, OSError) as exc:
        log.exception("Jira token exchange network error: %s", exc)
        return _render_setup(
            request,
            status="error",
            uid=uid,
            error_message="Network error while contacting Atlassian. Please try again.",
            status_code=502,
        )

    if token_resp.status_code != 200:
        log.warning("Jira token exchange failed (%s)", token_resp.status_code)
        return _render_setup(
            request,
            status="error",
            uid=uid,
            error_message="Failed to exchange authorization code with Atlassian.",
            status_code=502,
        )

    token_data = token_resp.json()
    access_token = token_data.get("access_token")
    refresh_token = token_data.get("refresh_token", "")
    expires_in = int(token_data.get("expires_in", 3600))
    scope = token_data.get("scope", "")

    if not access_token:
        return _render_setup(
            request,
            status="error",
            uid=uid,
            error_message="Atlassian did not return an access token.",
            status_code=502,
        )

    # accessible-resources gives us the Jira site list and their cloudids.
    try:
        with httpx.Client(timeout=15.0) as client:
            sites_resp = client.get(
                ATLASSIAN_RESOURCES_URL,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/json",
                },
            )
            me_resp = None
            try:
                me_resp = client.get(
                    ATLASSIAN_ME_URL,
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "Accept": "application/json",
                    },
                )
            except httpx.HTTPError:
                me_resp = None
    except (httpx.HTTPError, OSError) as exc:
        log.exception("Atlassian accessible-resources network error: %s", exc)
        return _render_setup(
            request,
            status="error",
            uid=uid,
            error_message="Network error while fetching Jira sites.",
            status_code=502,
        )

    if sites_resp.status_code != 200:
        return _render_setup(
            request,
            status="error",
            uid=uid,
            error_message="Failed to fetch the list of accessible Jira sites.",
            status_code=502,
        )

    raw_sites = sites_resp.json() or []
    sites: list[dict[str, Any]] = [
        {
            "id": s.get("id"),
            "url": s.get("url"),
            "name": s.get("name"),
            "scopes": s.get("scopes", []),
            "avatar_url": s.get("avatarUrl") or s.get("avatar_url"),
        }
        for s in raw_sites
        if s.get("id")
    ]

    if not sites:
        return _render_setup(
            request,
            status="error",
            uid=uid,
            error_message=(
                "No Jira sites accessible to this account. Make sure you have access to at "
                "least one Jira Cloud site, then try again."
            ),
            status_code=400,
        )

    default_cloud_id = sites[0]["id"]
    expires_at = int(time.time()) + expires_in

    store_jira_tokens(
        uid,
        access_token=access_token,
        refresh_token=refresh_token,
        expires_at=expires_at,
        sites=sites,
        default_cloud_id=default_cloud_id,
        scope=scope,
    )

    display_name: Optional[str] = None
    if me_resp is not None and me_resp.status_code == 200:
        try:
            me = me_resp.json()
            display_name = me.get("name") or me.get("nickname") or me.get("email")
        except Exception:
            display_name = None

    return _render_setup(
        request,
        status="success",
        uid=uid,
        display_name=display_name,
        sites=sites,
        default_cloud_id=default_cloud_id,
    )


@router.get("/setup/jira")
async def jira_setup_status(uid: str = ""):
    """Tell the Nooto backend whether this uid has connected Jira."""
    if not uid:
        raise HTTPException(status_code=400, detail="uid is required")
    return {"is_setup_completed": is_setup_completed(uid)}
