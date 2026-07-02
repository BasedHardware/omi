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

import logging
from typing import Optional

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from utils import x_connector
from utils.auth_middleware import require_firebase
from utils.executors import start_background_task

router = APIRouter()
_firebase_router = APIRouter(dependencies=[Depends(require_firebase)])
_public_router = APIRouter()
logger = logging.getLogger(__name__)

DEFAULT_DEEP_LINK = 'omi://x/callback'


class OAuthUrlResponse(BaseModel):
    success: bool
    auth_url: Optional[str] = None
    error: Optional[str] = None


@_firebase_router.get('/v1/x/oauth-url', response_model=OAuthUrlResponse, tags=['x'])
def x_oauth_url(
    request: Request,
    success_redirect_url: Optional[str] = Query(None),
):
    uid = request.state.uid
    if not x_connector.is_oauth_configured():
        return OAuthUrlResponse(success=False, error='x_oauth_not_configured')
    try:
        url = x_connector.build_authorize_url(uid, success_redirect_url=success_redirect_url)
        return OAuthUrlResponse(success=True, auth_url=url)
    except Exception as e:
        logger.error(f'x_oauth_url failed for uid={uid}: {e}')
        return OAuthUrlResponse(success=False, error='internal_error')


def _redirect_html(deep_link: str, ok: bool, message: str) -> HTMLResponse:
    icon = '✓' if ok else '⚠️'
    safe_link = deep_link.replace('"', '%22')
    html = f"""<!doctype html><html><head><meta charset="utf-8">
<title>X · Omi</title>
<meta http-equiv="refresh" content="0;url={safe_link}">
<style>body{{font-family:-apple-system,system-ui,sans-serif;background:#0b0b0f;color:#eaeaea;
display:flex;height:100vh;margin:0;align-items:center;justify-content:center;text-align:center}}
.c{{max-width:360px}}.i{{font-size:42px}}</style></head>
<body><div class="c"><div class="i">{icon}</div><h2>{message}</h2>
<p>Returning to Omi…</p></div>
<script>setTimeout(function(){{window.location.href="{safe_link}";}},150);</script>
</body></html>"""
    return HTMLResponse(content=html)


@_public_router.get('/v1/x/oauth/callback', response_class=HTMLResponse, tags=['x'])
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
    deep_link = st.get('success_redirect_url') or DEFAULT_DEEP_LINK
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


@_firebase_router.get('/v1/x/connection-status', tags=['x'])
def x_connection_status(request: Request):
    uid = request.state.uid
    return x_connector.connection_status(uid)


@_firebase_router.post('/v1/x/sync', tags=['x'])
async def x_sync(request: Request):
    uid = request.state.uid
    return await x_connector.sync_x_for_user(uid)


@_firebase_router.post('/v1/x/disconnect', tags=['x'])
def x_disconnect(request: Request):
    uid = request.state.uid
    x_connector.disconnect(uid)
    return {'success': True}


router.include_router(_firebase_router)
router.include_router(_public_router)
