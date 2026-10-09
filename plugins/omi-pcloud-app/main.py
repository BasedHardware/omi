"""
pCloud Integration App for Omi.

Automatically synchronizes conversation summaries, transcripts, and audio to pCloud.
Supports multi-region routing (United States and Europe) with encrypted token storage.
"""

from __future__ import annotations

import html
import io
import os
import secrets
import wave
from collections import defaultdict
from datetime import datetime, timezone
from typing import Dict, List, Optional
from urllib.parse import quote

import requests

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

try:
    from fastapi import FastAPI, Form, Query, Request
    from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
except ImportError:

    class FastAPI:
        def __init__(self, *args, **kwargs):
            pass

        def get(self, *args, **kwargs):
            return lambda f: f

        def post(self, *args, **kwargs):
            return lambda f: f

    def Query(default=None, **kwargs):
        return default

    def Form(default=None, **kwargs):
        return default

    class Request:
        pass

    class HTMLResponse:
        def __init__(self, content="", status_code=200):
            self.content = content
            self.status_code = status_code
            self.body = content.encode("utf-8") if isinstance(content, str) else bytes(content)

    class JSONResponse:
        def __init__(self, content=None, status_code=200):
            self.content = content or {}
            self.status_code = status_code
            import json as _json

            self.body = _json.dumps(self.content).encode("utf-8")

    class RedirectResponse:
        def __init__(self, url="", status_code=307):
            self.url = str(url)
            self.status_code = status_code
            self.headers = {"location": str(url)}
            self.body = b""


from db import (
    delete_oauth_state,
    delete_pcloud_tokens,
    get_oauth_state,
    get_pcloud_tokens,
    get_user_settings,
    store_oauth_state,
    store_pcloud_tokens,
    store_user_settings,
)
from models import Conversation, EndpointResponse, PCloudUserSettings
from pcloud_client import PCloudClient

app = FastAPI(
    title="Omi pCloud Backup Plugin",
    description="Extensible cloud backup destination for Omi conversations",
    version="1.0.0",
)

# Configuration from environment
PCLOUD_CLIENT_ID = os.getenv("PCLOUD_CLIENT_ID", "")
PCLOUD_CLIENT_SECRET = os.getenv("PCLOUD_CLIENT_SECRET", "")
PCLOUD_REDIRECT_URI = os.getenv("PCLOUD_REDIRECT_URI", "")

# OAuth endpoints for pCloud (US vs EU)
AUTH_URL_US = "https://my.pcloud.com/oauth2/authorize"
AUTH_URL_EU = "https://e-my.pcloud.com/oauth2/authorize"
TOKEN_URL_US = "https://api.pcloud.com/oauth2_token"
TOKEN_URL_EU = "https://eapi.pcloud.com/oauth2_token"

# In-memory bounded audio buffer
MAX_AUDIO_BUFFER_BYTES = 25 * 1024 * 1024  # 25 MB per user
AUDIO_BUFFER_TTL_SECONDS = 3600  # 1 hour eviction

audio_buffers: Dict[str, bytes] = defaultdict(bytes)
audio_sample_rates: Dict[str, int] = {}
audio_buffer_created: Dict[str, datetime] = {}


def create_wav_file(audio_bytes: bytes, sample_rate: int = 16000) -> bytes:
    """Converts raw PCM16 audio bytes to WAV format."""
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(1)  # Mono
        wav_file.setsampwidth(2)  # 16-bit PCM
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(audio_bytes)
    return buffer.getvalue()


def get_and_clear_audio(uid: str) -> Optional[bytes]:
    """Retrieves accumulated audio for a user and cleans up buffer."""
    if uid in audio_buffers and audio_buffers[uid]:
        audio_data = audio_buffers[uid]
        sample_rate = audio_sample_rates.get(uid, 16000)
        del audio_buffers[uid]
        audio_sample_rates.pop(uid, None)
        audio_buffer_created.pop(uid, None)
        return create_wav_file(audio_data, sample_rate)
    return None


def _evict_stale_audio_buffers() -> None:
    """Evicts stale audio buffers exceeding TTL."""
    now = datetime.now(timezone.utc)
    stale_uids = [
        uid
        for uid, created in audio_buffer_created.items()
        if (now - created).total_seconds() > AUDIO_BUFFER_TTL_SECONDS
    ]
    for uid in stale_uids:
        audio_buffers.pop(uid, None)
        audio_sample_rates.pop(uid, None)
        audio_buffer_created.pop(uid, None)


def generate_summary_markdown(conversation: Conversation) -> str:
    """Generates structured summary.md content from an Omi conversation."""
    structured = conversation.structured
    finished_at = conversation.finished_at or conversation.created_at or datetime.now(timezone.utc)
    date_str = finished_at.strftime("%Y-%m-%d %H:%M UTC")

    category = getattr(structured, "category", "general")
    if hasattr(category, "value"):
        category = category.value

    emoji = getattr(structured, "emoji", "💬") or "💬"
    title = getattr(structured, "title", "New Conversation") or "New Conversation"
    overview = getattr(structured, "overview", "") or ""

    content = f"# {title} {emoji}\n\n**Date**: {date_str}\n**Category**: {category}\n\n## Summary\n\n{overview}\n"

    if hasattr(structured, "action_items") and structured.action_items:
        content += "\n## Action Items\n\n"
        for item in structured.action_items:
            checkbox = "x" if getattr(item, "completed", False) else " "
            desc = getattr(item, "description", "")
            content += f"- [{checkbox}] {desc}\n"

    content += "\n---\n*Saved by Omi pCloud Backup Integration*\n"
    return content


def generate_transcript_markdown(conversation: Conversation) -> str:
    """Generates transcript.md content with speaker segments and timestamps."""
    structured = conversation.structured
    finished_at = conversation.finished_at or conversation.created_at or datetime.now(timezone.utc)
    date_str = finished_at.strftime("%Y-%m-%d %H:%M UTC")
    title = getattr(structured, "title", "Conversation") or "Conversation"

    content = f"# Transcript: {title}\n\n**Date**: {date_str}\n\n---\n\n"

    segments = getattr(conversation, "transcript_segments", [])
    if segments:
        for seg in segments:
            speaker = getattr(seg, "speaker", None) or ("User" if getattr(seg, "is_user", False) else "Speaker")
            start = getattr(seg, "start", 0.0)
            end = getattr(seg, "end", 0.0)
            text = getattr(seg, "text", "")
            time_tag = f"[{int(start // 60):02d}:{int(start % 60):02d} - {int(end // 60):02d}:{int(end % 60):02d}]"
            content += f"**{speaker}** {time_tag}: {text}\n\n"
    else:
        content += "*No transcript recorded.*\n\n"

    content += "---\n*Saved by Omi pCloud Backup Integration*\n"
    return content


def create_folder_name(title: str, finished_at: Optional[datetime]) -> str:
    """Creates a filesystem-safe folder name for the conversation."""
    safe_title = PCloudClient.sanitize_path(title)[:50] if title else "Conversation"
    if not finished_at:
        finished_at = datetime.now(timezone.utc)
    date_str = finished_at.strftime("%Y-%m-%d %H-%M")
    return f"{safe_title} ({date_str})"


def get_setup_page_html(
    uid: str,
    connected: bool,
    email: str = "",
    userid: Optional[int] = None,
    settings: Optional[dict] = None,
    notice: Optional[str] = None,
) -> str:
    """Renders accessible, responsive HTML setup page for mobile/desktop webviews."""
    if settings is None:
        settings = get_user_settings(uid)

    uid_q = quote(uid or "", safe="")
    folder_name = html.escape(settings.get("folder_name", "Omi Conversations"))
    save_summary = settings.get("save_summary", True)
    save_transcript = settings.get("save_transcript", True)
    save_audio = settings.get("save_audio", True)
    location_id = settings.get("location_id", 1)

    notice_banner = ""
    if notice:
        notice_banner = f"""<div style="background:#e6f4ea;color:#137333;padding:12px;border-radius:8px;margin-bottom:16px;font-size:14px;">{html.escape(notice)}</div>"""

    status_badge = (
        f"""<div style="display:inline-block;background:#e6f4ea;color:#137333;padding:4px 12px;border-radius:16px;font-size:13px;font-weight:600;">✓ Connected as {html.escape(email or f'User #{userid}')}</div>"""
        if connected
        else """<div style="display:inline-block;background:#feefe3;color:#c5221f;padding:4px 12px;border-radius:16px;font-size:13px;font-weight:600;">● Not Connected</div>"""
    )

    action_buttons = (
        f"""<a href="/disconnect?uid={uid_q}" style="display:inline-block;background:#d93025;color:#fff;text-decoration:none;padding:10px 18px;border-radius:8px;font-size:14px;font-weight:500;">Disconnect pCloud</a>"""
        if connected
        else f"""<a href="/auth/pcloud?uid={uid_q}&location_id={location_id}" style="display:inline-block;background:#1a73e8;color:#fff;text-decoration:none;padding:10px 20px;border-radius:8px;font-size:14px;font-weight:500;">Connect pCloud Account</a>"""
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>pCloud Backup Settings — Omi</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #f8f9fa; color: #202124; margin: 0; padding: 24px; }}
    .card {{ max-width: 520px; margin: 0 auto; background: #fff; border-radius: 12px; padding: 28px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
    h1 {{ font-size: 20px; margin: 0 0 16px 0; }}
    label {{ display: block; font-size: 14px; font-weight: 500; margin-top: 14px; margin-bottom: 6px; }}
    input[type="text"], select {{ width: 100%; box-sizing: border-box; padding: 10px; border: 1px solid #dadce0; border-radius: 6px; font-size: 14px; }}
    .checkbox-group {{ margin-top: 16px; }}
    .checkbox-item {{ display: flex; align-items: center; margin-bottom: 10px; font-size: 14px; }}
    .checkbox-item input {{ margin-right: 10px; width: 18px; height: 18px; }}
    .btn-submit {{ background: #1a73e8; color: #fff; border: none; padding: 10px 20px; border-radius: 6px; font-size: 14px; font-weight: 500; cursor: pointer; margin-top: 18px; }}
    .retention-box {{ margin-top: 24px; padding: 14px; background: #f1f3f4; border-radius: 8px; font-size: 12px; color: #5f6368; line-height: 1.5; }}
  </style>
</head>
<body>
  <div class="card">
    <h1>☁️ pCloud Backup for Omi</h1>
    {notice_banner}
    <div style="margin-bottom: 20px;">
      {status_badge}
    </div>
    <div style="margin-bottom: 24px;">
      {action_buttons}
    </div>
    <form method="post" action="/settings?uid={uid_q}">
      <label for="folder_name">Destination Root Folder</label>
      <input type="text" id="folder_name" name="folder_name" value="{folder_name}" required>

      <label for="location_id">Data Center Region</label>
      <select id="location_id" name="location_id">
        <option value="1" {'selected' if location_id == 1 else ''}>United States / Global (api.pcloud.com)</option>
        <option value="2" {'selected' if location_id == 2 else ''}>European Union (eapi.pcloud.com)</option>
      </select>

      <div class="checkbox-group">
        <label>Backup Preferences (Explicit Consent)</label>
        <div class="checkbox-item">
          <input type="checkbox" id="save_summary" name="save_summary" {'checked' if save_summary else ''}>
          <label for="save_summary" style="margin:0;font-weight:normal;">Save conversation summaries (summary.md)</label>
        </div>
        <div class="checkbox-item">
          <input type="checkbox" id="save_transcript" name="save_transcript" {'checked' if save_transcript else ''}>
          <label for="save_transcript" style="margin:0;font-weight:normal;">Save private transcripts (transcript.md)</label>
        </div>
        <div class="checkbox-item">
          <input type="checkbox" id="save_audio" name="save_audio" {'checked' if save_audio else ''}>
          <label for="save_audio" style="margin:0;font-weight:normal;">Save raw conversation audio (audio.wav)</label>
        </div>
      </div>

      <button type="submit" class="btn-submit">Save Settings</button>
    </form>

    <div class="retention-box">
      <strong>Privacy & Retention Policy:</strong><br>
      • Your access credentials are encrypted at rest using per-account isolation.<br>
      • Private transcripts and audio files require explicit opt-in consent above.<br>
      • Disconnecting revokes access on pCloud and permanently removes local credentials. Existing files already backed up to pCloud remain permanently preserved in your private personal storage and are never deleted by Omi.
    </div>
  </div>
</body>
</html>"""


# ============== API Endpoints ==============


@app.get("/")
@app.get("/health")
async def health_check():
    """Health check endpoint confirming provider service status."""
    return {"status": "ok", "provider": "pcloud", "version": "1.0.0"}


@app.get("/setup/pcloud", response_class=HTMLResponse)
async def setup_page(
    uid: str = Query(...),
    status: Optional[str] = Query(None),
):
    """Renders the setup HTML page for the given user ID."""
    tokens = get_pcloud_tokens(uid)
    connected = tokens is not None
    email = tokens.get("email", "") if tokens else ""
    userid = tokens.get("userid") if tokens else None
    settings = get_user_settings(uid)

    notice = None
    if status == "connected":
        notice = "Successfully connected your pCloud account!"
    elif status == "disconnected":
        notice = "Disconnected pCloud account and erased local tokens."
    elif status == "settings_saved":
        notice = "Preferences saved successfully."

    html_body = get_setup_page_html(
        uid=uid,
        connected=connected,
        email=email,
        userid=userid,
        settings=settings,
        notice=notice,
    )
    return HTMLResponse(content=html_body)


@app.get("/auth/pcloud")
async def auth_pcloud(
    uid: str = Query(...),
    location_id: int = Query(1),
):
    """Initiates OAuth 2.0 authorization with pCloud."""
    if not PCLOUD_CLIENT_ID:
        return JSONResponse(
            status_code=500,
            content={"error": "pCloud OAuth credentials not configured on server (PCLOUD_CLIENT_ID missing)"},
        )

    state = secrets.token_hex(16)
    store_oauth_state(state=state, uid=uid, location_id=location_id)

    auth_base = AUTH_URL_EU if location_id == 2 else AUTH_URL_US
    redirect_uri = quote(PCLOUD_REDIRECT_URI or "", safe="")
    auth_url = f"{auth_base}?client_id={PCLOUD_CLIENT_ID}&response_type=code&redirect_uri={redirect_uri}&state={state}"
    return RedirectResponse(url=auth_url)


@app.get("/auth/pcloud/callback")
async def auth_pcloud_callback(
    code: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    error: Optional[str] = Query(None),
):
    """Handles OAuth 2.0 callback, exchanges code for access token, and stores encrypted credentials."""
    if error or not code or not state:
        return HTMLResponse(
            f"<h2>OAuth Failed</h2><p>{html.escape(error or 'Missing authorization code')}</p>",
            status_code=400,
        )

    state_data = get_oauth_state(state)
    if not state_data:
        return HTMLResponse("<h2>Invalid or Expired OAuth State</h2>", status_code=400)

    uid = state_data["uid"]
    location_id = state_data.get("location_id", 1)
    delete_oauth_state(state)

    token_url = TOKEN_URL_EU if location_id == 2 else TOKEN_URL_US
    try:
        resp = requests.post(
            token_url,
            data={
                "client_id": PCLOUD_CLIENT_ID,
                "client_secret": PCLOUD_CLIENT_SECRET,
                "code": code,
            },
            timeout=20,
        )
        if resp.status_code != 200:
            return HTMLResponse(
                "<h2>Token Exchange Error</h2><p>Failed to exchange authorization code with pCloud API.</p>",
                status_code=502,
            )

        data = resp.json()
        if data.get("result") != 0:
            return HTMLResponse(
                f"<h2>pCloud OAuth Error</h2><p>{html.escape(data.get('error', 'Unknown'))}</p>",
                status_code=502,
            )

        access_token = data.get("access_token", "")
        userid = data.get("userid")
        loc_id = data.get("locationid", location_id)

        # Retrieve user email via client
        client = PCloudClient(access_token, location_id=loc_id)
        user_info, _ = client.get_user_info()
        email = user_info.get("email") if user_info else None

        store_pcloud_tokens(
            uid=uid,
            access_token=access_token,
            location_id=loc_id,
            userid=userid,
            email=email,
        )
        return RedirectResponse(f"/setup/pcloud?uid={quote(uid, safe='')}&status=connected")
    except Exception:
        return HTMLResponse(
            "<h2>Unexpected Server Exception</h2><p>An unexpected error occurred during authorization.</p>",
            status_code=500,
        )


@app.get("/disconnect")
async def disconnect_pcloud(uid: str = Query(...)):
    """Revokes credentials on pCloud and disconnects user from local database."""
    tokens = get_pcloud_tokens(uid)
    if tokens:
        access_token = tokens.get("access_token")
        location_id = tokens.get("location_id", 1)
        if access_token:
            try:
                client = PCloudClient(access_token, location_id=location_id)
                client.logout()
            except Exception:
                pass
        # Erase encrypted tokens from database
        delete_pcloud_tokens(uid)

    return RedirectResponse(f"/setup/pcloud?uid={quote(uid, safe='')}&status=disconnected")


@app.post("/settings")
async def save_settings(
    uid: str = Query(...),
    folder_name: str = Form("Omi Conversations"),
    location_id: int = Form(1),
    save_summary: Optional[str] = Form(None),
    save_transcript: Optional[str] = Form(None),
    save_audio: Optional[str] = Form(None),
):
    """Saves user preferences for folder location, region, and privacy consent."""
    settings = {
        "folder_name": folder_name.strip() or "Omi Conversations",
        "location_id": 2 if location_id == 2 else 1,
        "save_summary": save_summary is not None,
        "save_transcript": save_transcript is not None,
        "save_audio": save_audio is not None,
    }
    store_user_settings(uid, settings)
    return RedirectResponse(f"/setup/pcloud?uid={quote(uid, safe='')}&status=settings_saved", status_code=303)


@app.post("/audio")
async def on_audio_chunk(
    request: Request,
    uid: str = Query(...),
    sample_rate: int = Query(16000),
):
    """Receives and buffers raw audio chunks for the current conversation."""
    body = await request.body()
    if not body:
        return JSONResponse({"status": "empty_chunk"})

    _evict_stale_audio_buffers()
    current_size = len(audio_buffers[uid])
    if current_size + len(body) <= MAX_AUDIO_BUFFER_BYTES:
        audio_buffers[uid] += body
        audio_sample_rates[uid] = sample_rate
        if uid not in audio_buffer_created:
            audio_buffer_created[uid] = datetime.now(timezone.utc)
    return JSONResponse({"status": "received", "buffered_bytes": len(audio_buffers[uid])})


@app.post("/conversation", response_model=EndpointResponse)
async def on_conversation_created(
    conversation: Conversation,
    uid: str = Query(...),
):
    """Webhook invoked by Omi when a conversation is finalized.

    Exports summary, transcript, and audio to pCloud based on explicit consent settings.
    """
    tokens = get_pcloud_tokens(uid)
    if not tokens or not tokens.get("access_token"):
        return EndpointResponse(message="pCloud account not connected")

    if getattr(conversation, "discarded", False):
        return EndpointResponse(message="Skipped discarded conversation")

    settings = get_user_settings(uid)
    save_summary = settings.get("save_summary", True)
    save_transcript = settings.get("save_transcript", True)
    save_audio = settings.get("save_audio", True)
    folder_name = settings.get("folder_name", "Omi Conversations")
    location_id = tokens.get("location_id", settings.get("location_id", 1))

    if not save_summary and not save_transcript and not save_audio:
        return EndpointResponse(message="No backup items enabled in user settings")

    client = PCloudClient(tokens["access_token"], location_id=location_id)

    finished_at = conversation.finished_at or conversation.created_at
    conv_folder = create_folder_name(conversation.structured.title, finished_at)
    target_path = f"/{folder_name}/{conv_folder}"

    # Ensure parent folder hierarchy exists sequentially
    folder_id, folder_err = client.ensure_folder(target_path)
    if folder_err:
        return EndpointResponse(message=f"Failed to create pCloud folder: {folder_err}")

    uploaded_files: List[str] = []

    # 1. Export summary markdown
    if save_summary:
        summary_md = generate_summary_markdown(conversation)
        res, err = client.upload_file(
            folder_ref=target_path,
            filename="summary.md",
            content=summary_md.encode("utf-8"),
            overwrite=True,
        )
        if not err and res:
            uploaded_files.append("summary.md")

    # 2. Export transcript markdown (explicit user consent check)
    if save_transcript and getattr(conversation, "transcript_segments", None):
        transcript_md = generate_transcript_markdown(conversation)
        res, err = client.upload_file(
            folder_ref=target_path,
            filename="transcript.md",
            content=transcript_md.encode("utf-8"),
            overwrite=True,
        )
        if not err and res:
            uploaded_files.append("transcript.md")

    # 3. Export audio WAV (explicit user consent check)
    if save_audio:
        _evict_stale_audio_buffers()
        audio_wav = get_and_clear_audio(uid)
        if audio_wav:
            res, err = client.upload_file(
                folder_ref=target_path,
                filename="audio.wav",
                content=audio_wav,
                overwrite=True,
            )
            if not err and res:
                uploaded_files.append("audio.wav")

    return EndpointResponse(message=f"Backed up to pCloud: {', '.join(uploaded_files)}")
