"""OMI MS365 Plugin — FastAPI entrypoint.

Exposes:
- /                           Landing + health
- /setup/ms365?uid=<omi_uid>  Setup screen for OMI to link a user
- /auth/microsoft             Start OAuth
- /auth/microsoft/callback    OAuth redirect handler
- /status?uid=<omi_uid>       Check if a user is connected
- /setup_check?uid=<omi_uid>  Same as /status — used by OMI registry
- /disconnect?uid=<omi_uid>   Revoke local token
- /webhook/memory             OMI memory_creation webhook (no-op for now)
- /.well-known/omi-tools.json Tool manifest advertised to OMI
- /tools/<tool_name>          Tool execution endpoint called by OMI
"""
from __future__ import annotations

import json
import logging
import secrets
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from itsdangerous import BadSignature, URLSafeSerializer

from config import get_settings
from services import auth, mail, profile
from services import calendar as cal
from services import teams as teams_svc
from services import sharepoint as sp

logging.basicConfig(level=get_settings().log_level)
log = logging.getLogger("omi-ms365")

app = FastAPI(title="OMI MS365 Plugin")
_signer = URLSafeSerializer(get_settings().session_secret, salt="oauth-state")


# ---------------------------------------------------------------------------
# Setup + OAuth flow
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def root() -> str:
    return """
    <html><body style="font-family: system-ui; max-width: 640px; margin: 40px auto;">
      <h2>OMI MS365 Plugin</h2>
      <p>This is the backend for the OMI Microsoft 365 integration (Outlook, Teams, SharePoint, OneDrive).</p>
      <p>Plugin status: <strong>running</strong></p>
      <p>Users activate the plugin from within the OMI app.</p>
    </body></html>
    """


@app.get("/setup/ms365", response_class=HTMLResponse)
async def setup_page(uid: str = Query(..., description="OMI user id")) -> str:
    """OMI loads this page inside its in-app webview when the user taps 'Setup'."""
    redirect = f"/auth/microsoft?uid={uid}"
    return f"""
    <html><body style="font-family: system-ui; max-width: 640px; margin: 40px auto;">
      <h2>Connect Microsoft 365</h2>
      <p>This will let OMI read and act on your Outlook, Teams and SharePoint data
         on your behalf. You can revoke access at any time.</p>
      <p><a href="{redirect}"
         style="display:inline-block; background:#2563eb; color:white; padding:12px 20px;
         border-radius:8px; text-decoration:none;">Connect with Microsoft →</a></p>
    </body></html>
    """


@app.get("/auth/microsoft")
async def auth_start(uid: str = Query(...)) -> RedirectResponse:
    state = _signer.dumps({"uid": uid, "nonce": secrets.token_urlsafe(16)})
    url = auth.build_auth_url(state)
    return RedirectResponse(url)


@app.get("/auth/microsoft/callback")
async def auth_callback(
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    error_description: str | None = None,
) -> HTMLResponse:
    if error:
        return HTMLResponse(
            f"<h3>Authorization failed</h3><pre>{error}: {error_description}</pre>",
            status_code=400,
        )
    if not code or not state:
        raise HTTPException(400, "Missing code or state")

    try:
        payload = _signer.loads(state)
    except BadSignature:
        raise HTTPException(400, "Invalid state")

    uid: str = payload["uid"]
    await auth.exchange_code_for_token(code, uid)
    return HTMLResponse(
        """
        <html><body style="font-family: system-ui; text-align:center; padding:40px;">
          <h2>✓ Connected</h2>
          <p>You can close this tab and return to OMI.</p>
        </body></html>
        """
    )


@app.get("/status")
async def status(uid: str = Query(...)) -> dict[str, Any]:
    try:
        tok = await auth.get_access_token(uid)
        return {"connected": bool(tok)}
    except auth.AuthError:
        return {"connected": False}


@app.get("/setup_check")
async def setup_check(uid: str = Query(...)) -> dict[str, Any]:
    """Alias for /status — OMI registry calls this to verify setup is complete."""
    try:
        tok = await auth.get_access_token(uid)
        return {"is_setup_completed": bool(tok)}
    except auth.AuthError:
        return {"is_setup_completed": False}


@app.post("/disconnect")
async def disconnect(uid: str = Query(...)) -> dict[str, Any]:
    await auth.disconnect(uid)
    return {"status": "disconnected"}


# ---------------------------------------------------------------------------
# OMI memory_creation webhook
# ---------------------------------------------------------------------------

@app.post("/webhook/memory")
async def memory_webhook(request: Request, uid: str | None = Query(default=None)) -> dict[str, Any]:
    """OMI posts created memories here so the plugin can react to them.

    For now this is an acknowledgement endpoint — the MS365 tools are invoked
    explicitly by the assistant via /tools/<name>. Future revisions may use
    this hook to auto-archive memories to OneDrive or create calendar events
    mentioned in transcripts.
    """
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    if not uid:
        uid = payload.get("uid") or (payload.get("user") or {}).get("id")
    log.info("memory webhook uid=%s keys=%s", uid, list(payload.keys()))
    return {"received": True}


# ---------------------------------------------------------------------------
# OMI tool manifest
# ---------------------------------------------------------------------------

MANIFEST_PATH = Path(__file__).parent / "omi-tools.json"


@app.get("/.well-known/omi-tools.json")
async def tool_manifest() -> JSONResponse:
    return JSONResponse(content=_load_manifest())


def _load_manifest() -> dict[str, Any]:
    with open(MANIFEST_PATH) as f:
        manifest = json.load(f)
    base = get_settings().app_base_url.rstrip("/")
    # Inject absolute URLs so OMI doesn't need to guess
    for tool in manifest.get("tools", []):
        tool["endpoint"] = f"{base}/tools/{tool['name']}"
    manifest["setup_url"] = f"{base}/setup/ms365"
    return manifest


# ---------------------------------------------------------------------------
# Tool dispatch
# ---------------------------------------------------------------------------

async def _auth_guard(uid: str) -> None:
    try:
        await auth.get_access_token(uid)
    except auth.AuthError as e:
        raise HTTPException(401, f"Microsoft not connected — {e}")


@app.post("/tools/{tool_name}")
async def tool_dispatch(tool_name: str, request: Request) -> Any:
    body: dict[str, Any] = {}
    try:
        body = await request.json()
    except Exception:
        pass
    uid: str | None = body.get("uid") or request.query_params.get("uid")
    if not uid:
        raise HTTPException(400, "uid (OMI user id) is required")
    args: dict[str, Any] = body.get("args", {}) or {}

    await _auth_guard(uid)

    try:
        handler = _TOOLS[tool_name]
    except KeyError:
        raise HTTPException(404, f"Unknown tool: {tool_name}")
    try:
        return await handler(uid, **args)
    except TypeError as e:
        raise HTTPException(400, f"Bad arguments for {tool_name}: {e}")


# tool_name -> coroutine(uid, **args)
_TOOLS: dict[str, Any] = {
    # profile
    "get_me": profile.me,
    # mail
    "list_recent_emails": mail.list_recent,
    "search_emails": mail.search,
    "read_email": mail.read,
    "send_email": mail.send,
    # calendar
    "list_upcoming_events": cal.list_upcoming,
    "create_event": cal.create_event,
    "find_free_slots": cal.find_free_slots,
    # teams
    "list_recent_chats": teams_svc.list_recent_chats,
    "send_chat_message": teams_svc.send_chat_message,
    "list_my_teams": teams_svc.list_my_teams,
    "create_online_meeting": teams_svc.create_online_meeting,
    # sharepoint / onedrive
    "list_recent_files": sp.list_recent_files,
    "search_files": sp.search_files,
    "upload_text_file": sp.upload_text_file,
    "read_file_text": sp.read_file_text,
}
