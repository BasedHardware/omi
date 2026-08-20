"""X (Twitter) connector routes.

Connect flow (backend-mediated OAuth2 + PKCE, mirrors the existing integrations):
  1. Desktop GET /v1/x/oauth-url?success_redirect_url=<app deep link>
       -> { auth_url }. App opens auth_url in the system browser.
  2. X redirects to GET /v2/integrations/x/callback?code&state
       -> backend exchanges the code, stores tokens, kicks off the first sync,
          and returns an HTML page that redirects to the app's deep link.
  3. Desktop polls GET /v1/x/connection-status until connected.

The desktop passes its own URL scheme as success_redirect_url, so dev
(omi-computer-dev://) and prod (omi://) builds each get redirected back to
themselves without the backend needing to know which is calling.
"""

import json
import logging
from html import escape
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

import database.x_posts as x_posts_db
from utils import x_connector
from utils.executors import start_background_task
from utils.other import endpoints as auth

router = APIRouter()
logger = logging.getLogger(__name__)

DEFAULT_DEEP_LINK = 'omi://x/callback'
X_POST_KINDS = (x_posts_db.KIND_TWEET, x_posts_db.KIND_BOOKMARK, x_posts_db.KIND_LIKE)

# Mirrors routers.auth._validate_redirect_uri allowlist (custom schemes + loopback http).
_LOOPBACK_HOSTNAMES = frozenset({"localhost", "127.0.0.1", "::1"})
_FORBIDDEN_REDIRECT_SCHEMES = frozenset(
    {"https", "javascript", "data", "vbscript", "file", "blob", "filesystem", "about"}
)
_ASCII_LETTERS = frozenset("abcdefghijklmnopqrstuvwxyz")
_ASCII_ALNUM = _ASCII_LETTERS | frozenset("0123456789")


def _is_valid_redirect_scheme(scheme: str) -> bool:
    if not scheme or scheme[0] not in _ASCII_LETTERS:
        return False
    return all(c in _ASCII_ALNUM or c in "+-." for c in scheme)


def is_allowed_success_redirect_url(redirect_uri: str) -> bool:
    """Return True when redirect_uri is a safe native/loopback deep link."""
    if not redirect_uri:
        return False
    # No legitimate deep link contains markup delimiters, quotes, or control
    # characters; they only appear when someone is aiming at the callback page.
    if any(c in redirect_uri for c in '<>"\'`') or any(c.isspace() or ord(c) < 0x20 for c in redirect_uri):
        return False
    try:
        parsed = urlparse(redirect_uri)
        scheme = (parsed.scheme or "").strip().lower()
        if not scheme:
            return False
        if scheme == "http":
            hostname = (parsed.hostname or "").strip().lower()
            parsed.port  # validates the port component — `localhost:notaport` is rejected
            return hostname in _LOOPBACK_HOSTNAMES
        if scheme in _FORBIDDEN_REDIRECT_SCHEMES:
            return False
        return _is_valid_redirect_scheme(scheme)
    except ValueError:
        # Malformed authority (`http://[`) makes urlparse/`.port` raise; that is
        # invalid client input, so treat it as disallowed rather than a 500.
        return False


def _validated_success_redirect(url: Optional[str]) -> str:
    if url and is_allowed_success_redirect_url(url):
        return url
    return DEFAULT_DEEP_LINK


class OAuthUrlResponse(BaseModel):
    success: bool
    auth_url: Optional[str] = None
    error: Optional[str] = None


class XConnectionStatusResponse(BaseModel):
    """X integration connection status for the current user."""

    success: bool = Field(description='Whether the request succeeded.')
    connected: bool = Field(description='Whether the user has connected their X account.')
    handle: Optional[str] = Field(default=None, description='X handle, when connected.')
    post_count: int = Field(default=0, description='Number of synced posts.')
    memory_count: int = Field(default=0, description='Number of extracted memories.')
    syncing: bool = Field(default=False, description='Whether a sync is currently in progress.')
    last_synced_at: Optional[str] = Field(default=None, description='ISO timestamp of the last successful sync.')
    last_sync_source: Optional[str] = Field(default=None, description='Source of the last sync (oauth|rapidapi).')


class XSyncResponse(BaseModel):
    """Outcome of an X posts sync."""

    success: bool = Field(description='Whether the sync completed without error.')
    source: Optional[str] = Field(default=None, description='Sync source used (oauth|rapidapi).')
    new_posts: int = Field(default=0, description='Number of new posts stored.')
    memories_created: int = Field(default=0, description='Number of memories extracted from new posts.')
    error: Optional[str] = Field(default=None, description='Error code on failure (not_connected|fetch_failed).')


class XDisconnectResponse(BaseModel):
    """Ack for disconnecting the X integration."""

    success: bool = Field(description='Whether the disconnect succeeded.')


class XPostsResponse(BaseModel):
    """List of the user's synced X posts."""

    posts: List[Dict[str, Any]] = Field(description='Synced X posts, newest first.')


@router.get('/v1/x/oauth-url', response_model=OAuthUrlResponse, tags=['x'])
def x_oauth_url(
    success_redirect_url: Optional[str] = Query(None),
    uid: str = Depends(auth.get_current_user_uid),
):
    if not x_connector.is_oauth_configured():
        return OAuthUrlResponse(success=False, error='x_oauth_not_configured')
    if success_redirect_url is not None and not is_allowed_success_redirect_url(success_redirect_url):
        raise HTTPException(status_code=400, detail='success_redirect_url is not permitted')
    try:
        url = x_connector.build_authorize_url(uid, success_redirect_url=success_redirect_url)
        return OAuthUrlResponse(success=True, auth_url=url)
    except Exception as e:
        logger.error(f'x_oauth_url failed for uid={uid}: {e}')
        return OAuthUrlResponse(success=False, error='internal_error')


def _redirect_html(deep_link: str, ok: bool, message: str) -> HTMLResponse:
    icon = '✓' if ok else '⚠️'
    # The link reaches here from a client-supplied success_redirect_url. Escaping
    # only quotes is not enough: a `</script>` inside the value closes the script
    # element and the rest executes as markup on the backend origin. Escape for
    # the attribute context, and serialize as JSON for the script context (with
    # `<` escaped so no substring can terminate the element).
    attr_link = escape(deep_link, quote=True)
    script_link = json.dumps(deep_link).replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')
    html = f"""<!doctype html><html><head><meta charset="utf-8">
<title>X · Omi</title>
<meta http-equiv="refresh" content="0;url={attr_link}">
<style>body{{font-family:-apple-system,system-ui,sans-serif;background:#0b0b0f;color:#eaeaea;
display:flex;height:100vh;margin:0;align-items:center;justify-content:center;text-align:center}}
.c{{max-width:360px}}.i{{font-size:42px}}</style></head>
<body><div class="c"><div class="i">{icon}</div><h2>{escape(message)}</h2>
<p>Returning to Omi…</p></div>
<script>setTimeout(function(){{window.location.href={script_link};}},150);</script>
</body></html>"""
    return HTMLResponse(content=html)


@router.get('/v1/x/oauth/callback', response_class=HTMLResponse, tags=['x'])
async def x_oauth_callback(
    request: Request,
    code: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    error: Optional[str] = Query(None),
):
    if error or not code or not state:
        return _redirect_html(f'{DEFAULT_DEEP_LINK}?error={error or "missing_code"}', False, 'Connection cancelled')

    st = x_connector.consume_oauth_state(state)
    if not st:
        return _redirect_html(f'{DEFAULT_DEEP_LINK}?error=invalid_state', False, 'Link expired')

    uid = st['uid']
    deep_link = _validated_success_redirect(st.get('success_redirect_url'))
    try:
        token_resp = await x_connector.exchange_code(code, st['verifier'])
        # Resolve the account so we can store the handle for status + RapidAPI fallback.
        handle = None
        x_user_id = None
        try:
            me = await x_connector.fetch_me(token_resp['access_token'])
            handle = me.get('username')
            x_user_id = str(me.get('id')) if me.get('id') else None
        except Exception as e:
            logger.info(f'x callback: fetch_me failed (non-fatal): {e}')
        x_connector._store_tokens(uid, token_resp, handle=handle, x_user_id=x_user_id)
        # First ingest in the background so the browser redirect is instant.
        start_background_task(x_connector.sync_x_for_user(uid), name=f'x_initial_sync_{uid}')
        return _redirect_html(f'{deep_link}?status=success', True, 'X connected')
    except Exception as e:
        logger.error(f'x callback failed for uid={uid}: {e}')
        return _redirect_html(f'{deep_link}?error=exchange_failed', False, 'Connection failed')


@router.get('/v1/x/connection-status', tags=['x'], response_model=XConnectionStatusResponse)
def x_connection_status(uid: str = Depends(auth.get_current_user_uid)):
    return x_connector.connection_status(uid)


@router.get('/v1/x/posts', tags=['x'], response_model=XPostsResponse)
def list_x_posts(
    kind: Optional[str] = Query(None, description="Filter by kind: 'tweet', 'bookmark', or 'like'"),
    limit: int = Query(100, ge=1, le=500, description="Maximum number of posts to return"),
    uid: str = Depends(auth.get_current_user_uid),
):
    """List the user's synced X posts, newest first.

    The connector stores every synced post under the user's account and mines memories
    from them, but there was no endpoint to read the raw posts back. Supports an optional
    kind filter ('tweet', 'bookmark', 'like') and a bounded limit.
    """
    if kind is not None and kind not in X_POST_KINDS:
        raise HTTPException(status_code=400, detail="kind must be one of: tweet, bookmark, like")
    return {'posts': x_posts_db.get_x_posts(uid, limit=limit, kind=kind)}


@router.post('/v1/x/sync', tags=['x'], response_model=XSyncResponse)
async def x_sync(uid: str = Depends(auth.get_current_user_uid)):
    return await x_connector.sync_x_for_user(uid)


@router.post('/v1/x/disconnect', tags=['x'], response_model=XDisconnectResponse)
def x_disconnect(uid: str = Depends(auth.get_current_user_uid)):
    x_connector.disconnect(uid)
    return {'success': True}
