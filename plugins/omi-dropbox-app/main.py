"""
Dropbox Integration App for Omi.

Automatically saves conversation summaries, transcripts, and audio to Dropbox.
"""

import io
import os
import secrets
import struct
import wave
from collections import OrderedDict
from datetime import datetime, timedelta
from typing import Dict, Optional
from urllib.parse import urlencode

import requests
from dotenv import load_dotenv
from fastapi import FastAPI, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse

from db import (
    store_dropbox_tokens,
    get_dropbox_tokens,
    update_dropbox_tokens,
    delete_dropbox_tokens,
    store_oauth_state,
    get_oauth_state,
    delete_oauth_state,
    get_user_settings,
    store_user_settings,
)
from models import Conversation, EndpointResponse
from dropbox_client import DropboxClient

load_dotenv()

# ============== Configuration ==============

DROPBOX_APP_KEY = os.getenv("DROPBOX_APP_KEY", "")
DROPBOX_APP_SECRET = os.getenv("DROPBOX_APP_SECRET", "")
DROPBOX_REDIRECT_URI = os.getenv("DROPBOX_REDIRECT_URI", "http://localhost:8080/auth/dropbox/callback")

DROPBOX_AUTH_URL = "https://www.dropbox.com/oauth2/authorize"
DROPBOX_TOKEN_URL = "https://api.dropboxapi.com/oauth2/token"

# ============== FastAPI App ==============

app = FastAPI(
    title="Dropbox Omi Integration",
    description="Automatically save Omi conversations to Dropbox",
    version="1.0.0",
)

# ============== Audio Buffer ==============
# Store audio chunks by user ID. OrderedDict is LRU: oldest uid is evicted
# when the key count or process-wide byte budget is spent.
audio_buffers: OrderedDict[str, bytes] = OrderedDict()
audio_sample_rates: Dict[str, int] = {}

# Audio accumulates in process memory until the conversation webhook uploads
# it, so the buffer must be bounded: a multi-hour conversation (or a spray of
# unknown uids) otherwise grows without limit. ~100 MB holds ~52 minutes of
# 16 kHz PCM16; the tail beyond the cap is dropped so the webhook still uploads
# the audio that fit. A separate process-wide budget stops 512 × 100 MiB.
MAX_AUDIO_BUFFER_BYTES = 100 * 1024 * 1024
MAX_AUDIO_BUFFERS = 512
MAX_AUDIO_TOTAL_BYTES = 256 * 1024 * 1024


def _audio_total_bytes() -> int:
    return sum(len(chunk) for chunk in audio_buffers.values())


def _evict_oldest_audio() -> None:
    if not audio_buffers:
        return
    old_uid, _ = audio_buffers.popitem(last=False)
    audio_sample_rates.pop(old_uid, None)


def _make_room_for(uid: str) -> int:
    """Evict LRU uids until this write can proceed. Returns bytes this uid may append."""
    if uid not in audio_buffers:
        while audio_buffers and len(audio_buffers) >= MAX_AUDIO_BUFFERS:
            _evict_oldest_audio()
        while audio_buffers and _audio_total_bytes() >= MAX_AUDIO_TOTAL_BYTES:
            _evict_oldest_audio()
    else:
        while _audio_total_bytes() >= MAX_AUDIO_TOTAL_BYTES and len(audio_buffers) > 1:
            oldest = next(iter(audio_buffers))
            if oldest == uid:
                audio_buffers.move_to_end(uid)
                continue
            _evict_oldest_audio()
    existing = len(audio_buffers.get(uid, b""))
    per_uid = max(0, MAX_AUDIO_BUFFER_BYTES - existing)
    global_space = max(0, MAX_AUDIO_TOTAL_BYTES - _audio_total_bytes())
    return min(per_uid, global_space)


async def _read_audio_limited(request: Request, max_bytes: int) -> bytes:
    """Read at most max_bytes from the request. Do not materialize a larger body."""
    if max_bytes <= 0:
        return b""
    stream = getattr(request, "stream", None)
    if stream is None:
        body = await request.body()
        return body[:max_bytes]
    chunks = []
    taken = 0
    async for chunk in request.stream():
        if taken >= max_bytes:
            break
        piece = chunk[: max_bytes - taken]
        chunks.append(piece)
        taken += len(piece)
        if len(chunk) > len(piece):
            break
    return b"".join(chunks)


def create_wav_file(audio_bytes: bytes, sample_rate: int = 16000) -> bytes:
    """Convert raw PCM16 audio to WAV format."""
    buffer = io.BytesIO()
    with wave.open(buffer, 'wb') as wav_file:
        wav_file.setnchannels(1)  # Mono
        wav_file.setsampwidth(2)  # 16-bit = 2 bytes
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(audio_bytes)
    return buffer.getvalue()


def get_and_clear_audio(uid: str) -> Optional[bytes]:
    """Get accumulated audio for a user and clear the buffer."""
    if uid in audio_buffers and audio_buffers[uid]:
        audio_data = audio_buffers[uid]
        sample_rate = audio_sample_rates.get(uid, 16000)
        del audio_buffers[uid]
        if uid in audio_sample_rates:
            del audio_sample_rates[uid]
        return create_wav_file(audio_data, sample_rate)
    return None


# ============== Helper Functions ==============


def get_valid_access_token(uid: str) -> Optional[str]:
    """Get a valid access token, refreshing if needed."""
    tokens = get_dropbox_tokens(uid)
    if not tokens:
        return None

    access_token = tokens.get("access_token")
    refresh_token = tokens.get("refresh_token")
    expires_at_str = tokens.get("expires_at")

    if not access_token:
        return None

    # Check if token is expired (with 5 min buffer)
    if expires_at_str and refresh_token:
        try:
            expires_at = datetime.fromisoformat(expires_at_str.replace("Z", "+00:00"))
            if datetime.now(expires_at.tzinfo) >= expires_at - timedelta(minutes=5):
                # Token expired or about to expire, refresh it
                new_token = refresh_access_token(refresh_token)
                if new_token:
                    return new_token
                return None
        except Exception:
            pass

    return access_token


def refresh_access_token(refresh_token: str) -> Optional[str]:
    """Refresh the access token using refresh token."""
    try:
        response = requests.post(
            DROPBOX_TOKEN_URL,
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": DROPBOX_APP_KEY,
                "client_secret": DROPBOX_APP_SECRET,
            },
        )

        if response.status_code == 200:
            data = response.json()
            new_access_token = data.get("access_token")
            expires_in = data.get("expires_in", 14400)  # Default 4 hours
            new_expires_at = (datetime.utcnow() + timedelta(seconds=expires_in)).isoformat() + "Z"

            # Note: We can't update tokens here without uid, caller should handle
            return new_access_token

        return None
    except Exception:
        return None


def generate_summary_markdown(conversation: Conversation) -> str:
    """Generate summary.md content from conversation."""
    structured = conversation.structured
    finished_at = conversation.finished_at or conversation.created_at

    date_str = finished_at.strftime("%Y-%m-%d %H:%M")
    category = getattr(structured.category, "value", structured.category)

    content = f"""# {structured.title} {structured.emoji}

**Date**: {date_str}
**Category**: {category}

## Summary

{structured.overview}
"""

    # Add action items if present
    if structured.action_items:
        content += "\n## Action Items\n\n"
        for item in structured.action_items:
            checkbox = "x" if item.completed else " "
            content += f"- [{checkbox}] {item.description}\n"

    # Add plugin results if present
    if conversation.plugins_results:
        content += "\n## App Insights\n\n"
        for pr in conversation.plugins_results:
            if pr.content:
                content += f"{pr.content}\n\n"

    content += "\n---\n*Saved by Omi Dropbox Integration*\n"
    return content


def generate_transcript_markdown(conversation: Conversation) -> str:
    """Generate transcript.md content from conversation."""
    structured = conversation.structured
    finished_at = conversation.finished_at or conversation.created_at

    date_str = finished_at.strftime("%Y-%m-%d %H:%M")
    duration = conversation.get_duration() or "Unknown"

    transcript_text = conversation.get_transcript(include_timestamps=True)

    content = f"""# Transcript: {structured.title}

**Date**: {date_str}
**Duration**: {duration}

---

{transcript_text}

---
*Saved by Omi Dropbox Integration*
"""
    return content


def create_folder_name(title: str, finished_at: datetime) -> str:
    """Create a safe folder name for the conversation."""
    safe_title = DropboxClient.sanitize_path(title)[:50]
    date_str = finished_at.strftime("%Y-%m-%d %H-%M")
    return f"{safe_title} ({date_str})"


# ============== HTML Templates ==============


def get_home_page_html(
    uid: str, connected: bool, display_name: str = "", email: str = "", settings: dict = None
) -> str:
    """Generate home page HTML."""
    if settings is None:
        settings = get_user_settings(uid)

    if connected:
        return f"""
<!DOCTYPE html>
<html>
<head>
    <title>Dropbox - Omi Integration</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 500px; margin: 50px auto; padding: 20px; background: #f5f5f5; }}
        .card {{ background: white; border-radius: 12px; padding: 24px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }}
        h1 {{ color: #0061fe; margin-bottom: 8px; font-size: 24px; }}
        .status {{ color: #28a745; font-weight: 500; margin-bottom: 20px; }}
        .user-info {{ background: #f8f9fa; padding: 12px; border-radius: 8px; margin-bottom: 20px; }}
        .settings-form {{ margin-top: 20px; }}
        .form-group {{ margin-bottom: 16px; }}
        label {{ display: block; margin-bottom: 6px; font-weight: 500; color: #333; }}
        input[type="text"] {{ width: 100%; padding: 10px; border: 1px solid #ddd; border-radius: 6px; font-size: 14px; box-sizing: border-box; }}
        .checkbox-group {{ display: flex; align-items: center; gap: 8px; }}
        input[type="checkbox"] {{ width: 18px; height: 18px; }}
        .btn {{ display: inline-block; padding: 12px 24px; border-radius: 6px; text-decoration: none; font-weight: 500; cursor: pointer; border: none; font-size: 14px; }}
        .btn-primary {{ background: #0061fe; color: white; }}
        .btn-danger {{ background: #dc3545; color: white; margin-left: 10px; }}
        .btn:hover {{ opacity: 0.9; }}
        .actions {{ margin-top: 24px; display: flex; gap: 10px; }}
    </style>
</head>
<body>
    <div class="card">
        <h1>Dropbox Connected</h1>
        <p class="status">Your Dropbox account is connected</p>
        <div class="user-info">
            <strong>{display_name}</strong><br>
            <span style="color: #666;">{email}</span>
        </div>

        <form class="settings-form" method="POST" action="/settings?uid={uid}">
            <div class="form-group">
                <label for="folder_name">Folder Name</label>
                <input type="text" id="folder_name" name="folder_name" value="{settings.get('folder_name', 'Omi Conversations')}" placeholder="Omi Conversations">
            </div>

            <div class="form-group">
                <div class="checkbox-group">
                    <input type="checkbox" id="save_summary" name="save_summary" {'checked' if settings.get('save_summary', True) else ''}>
                    <label for="save_summary" style="margin-bottom: 0;">Save Summary</label>
                </div>
            </div>

            <div class="form-group">
                <div class="checkbox-group">
                    <input type="checkbox" id="save_transcript" name="save_transcript" {'checked' if settings.get('save_transcript', True) else ''}>
                    <label for="save_transcript" style="margin-bottom: 0;">Save Transcript</label>
                </div>
            </div>

            <div class="form-group">
                <div class="checkbox-group">
                    <input type="checkbox" id="save_audio" name="save_audio" {'checked' if settings.get('save_audio', True) else ''}>
                    <label for="save_audio" style="margin-bottom: 0;">Save Audio Recording</label>
                </div>
            </div>

            <div class="actions">
                <button type="submit" class="btn btn-primary">Save Settings</button>
                <a href="/disconnect?uid={uid}" class="btn btn-danger">Disconnect</a>
            </div>
        </form>
    </div>
</body>
</html>
"""
    else:
        return f"""
<!DOCTYPE html>
<html>
<head>
    <title>Dropbox - Omi Integration</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 500px; margin: 50px auto; padding: 20px; background: #f5f5f5; }}
        .card {{ background: white; border-radius: 12px; padding: 24px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); text-align: center; }}
        h1 {{ color: #0061fe; margin-bottom: 8px; font-size: 24px; }}
        p {{ color: #666; margin-bottom: 24px; }}
        .btn {{ display: inline-block; padding: 14px 32px; background: #0061fe; color: white; border-radius: 8px; text-decoration: none; font-weight: 500; }}
        .btn:hover {{ background: #0052d9; }}
    </style>
</head>
<body>
    <div class="card">
        <h1>Connect Dropbox</h1>
        <p>Connect your Dropbox account to automatically save your Omi conversations.</p>
        <a href="/auth/dropbox?uid={uid}" class="btn">Connect Dropbox</a>
    </div>
</body>
</html>
"""


# ============== Endpoints ==============


@app.get("/", response_class=HTMLResponse)
async def home(uid: str = Query(None)):
    """Home page - shows connection status and settings."""
    if not uid:
        return JSONResponse(
            {
                "app": "Dropbox Omi Integration",
                "version": "1.0.0",
                "description": "Automatically save Omi conversations to Dropbox",
            }
        )

    tokens = get_dropbox_tokens(uid)
    if tokens:
        return HTMLResponse(
            get_home_page_html(
                uid=uid,
                connected=True,
                display_name=tokens.get("display_name", ""),
                email=tokens.get("email", ""),
            )
        )
    else:
        return HTMLResponse(get_home_page_html(uid=uid, connected=False))


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy"}


@app.get("/setup/dropbox")
async def check_setup(uid: str = Query(...)):
    """Check if user has completed setup (for Omi)."""
    tokens = get_dropbox_tokens(uid)
    return {"is_setup_completed": tokens is not None}


# ============== OAuth Endpoints ==============


@app.get("/auth/dropbox")
async def auth_dropbox(uid: str = Query(...)):
    """Start Dropbox OAuth flow."""
    # Generate state for CSRF protection
    state = f"{uid}:{secrets.token_urlsafe(32)}"
    store_oauth_state(uid, state)

    # Build authorization URL
    params = {
        "client_id": DROPBOX_APP_KEY,
        "redirect_uri": DROPBOX_REDIRECT_URI,
        "response_type": "code",
        "token_access_type": "offline",  # Get refresh token
        "state": state,
    }

    auth_url = f"{DROPBOX_AUTH_URL}?{urlencode(params)}"
    return RedirectResponse(url=auth_url)


@app.get("/auth/dropbox/callback")
async def auth_callback(
    code: str = Query(None),
    state: str = Query(None),
    error: str = Query(None),
    error_description: str = Query(None),
):
    """Handle Dropbox OAuth callback."""
    # Handle errors
    if error:
        return HTMLResponse(
            f"""
<!DOCTYPE html>
<html>
<head><title>Authorization Failed</title></head>
<body style="font-family: sans-serif; text-align: center; padding: 50px;">
    <h1 style="color: #dc3545;">Authorization Failed</h1>
    <p>{error_description or error}</p>
</body>
</html>
""",
            status_code=400,
        )

    if not code or not state:
        return HTMLResponse("Missing code or state", status_code=400)

    # Extract uid from state
    try:
        uid = state.split(":")[0]
    except Exception:
        return HTMLResponse("Invalid state format", status_code=400)

    # Verify state for CSRF protection
    stored_state = get_oauth_state(uid)
    if stored_state != state:
        return HTMLResponse("State mismatch - possible CSRF attack", status_code=400)

    # Clean up state
    delete_oauth_state(uid)

    # Exchange code for tokens
    try:
        response = requests.post(
            DROPBOX_TOKEN_URL,
            data={
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": DROPBOX_REDIRECT_URI,
                "client_id": DROPBOX_APP_KEY,
                "client_secret": DROPBOX_APP_SECRET,
            },
        )

        if response.status_code != 200:
            return HTMLResponse(f"Token exchange failed: {response.text}", status_code=400)

        token_data = response.json()
        access_token = token_data.get("access_token")
        refresh_token = token_data.get("refresh_token")
        expires_in = token_data.get("expires_in", 14400)
        account_id = token_data.get("account_id")

        if not access_token:
            return HTMLResponse("No access token received", status_code=400)

        # Calculate expiration
        expires_at = (datetime.utcnow() + timedelta(seconds=expires_in)).isoformat() + "Z"

        # Get user info
        display_name = ""
        email = ""
        client = DropboxClient(access_token)
        account_info, _ = client.get_account()
        if account_info:
            name_info = account_info.get("name", {})
            display_name = name_info.get("display_name", "")
            email = account_info.get("email", "")

        # Store tokens
        store_dropbox_tokens(
            uid=uid,
            access_token=access_token,
            refresh_token=refresh_token,
            expires_at=expires_at,
            account_id=account_id,
            display_name=display_name,
            email=email,
        )

        # Redirect to home page
        return RedirectResponse(url=f"/?uid={uid}")

    except Exception as e:
        return HTMLResponse(f"Error during authorization: {str(e)}", status_code=500)


@app.get("/disconnect")
async def disconnect(uid: str = Query(...)):
    """Disconnect Dropbox account."""
    delete_dropbox_tokens(uid)
    return RedirectResponse(url=f"/?uid={uid}")


# ============== Settings Endpoint ==============


@app.post("/settings")
async def update_settings(request: Request, uid: str = Query(...)):
    """Update user settings."""
    form_data = await request.form()

    settings = {
        "folder_name": form_data.get("folder_name", "Omi Conversations"),
        "save_summary": "save_summary" in form_data,
        "save_transcript": "save_transcript" in form_data,
        "save_audio": "save_audio" in form_data,
    }

    store_user_settings(uid, settings)
    return RedirectResponse(url=f"/?uid={uid}", status_code=303)


# ============== Webhook Endpoint ==============


@app.post("/conversation", response_model=EndpointResponse)
async def on_conversation_created(
    conversation: Conversation,
    uid: str = Query(...),
):
    """
    Webhook called by Omi when a conversation is created.
    Saves summary and transcript to Dropbox.
    """
    print(f"[WEBHOOK] Received conversation for uid={uid}")
    print(f"[WEBHOOK] Title: {conversation.structured.title}")
    print(f"[WEBHOOK] Overview: {conversation.structured.overview[:100]}...")
    print(f"[WEBHOOK] Discarded: {conversation.discarded}")
    print(f"[WEBHOOK] Segments count: {len(conversation.transcript_segments)}")
    print(f"[WEBHOOK] Action items count: {len(conversation.structured.action_items)}")
    print(f"[WEBHOOK] Plugins results count: {len(conversation.plugins_results)}")
    for i, pr in enumerate(conversation.plugins_results):
        print(f"[WEBHOOK] Plugin {i}: {pr.plugin_id} -> {pr.content[:100] if pr.content else 'empty'}...")

    # Check if user is connected
    access_token = get_valid_access_token(uid)
    if not access_token:
        print(f"[WEBHOOK] ERROR: No valid access token for uid={uid}")
        return EndpointResponse(message="")

    print(f"[WEBHOOK] Access token found")

    # Skip discarded conversations
    if conversation.discarded:
        print(f"[WEBHOOK] Skipping discarded conversation")
        return EndpointResponse(message="")

    # Get user settings
    settings = get_user_settings(uid)
    folder_name = settings.get("folder_name", "Omi Conversations")
    save_summary = settings.get("save_summary", True)
    save_transcript = settings.get("save_transcript", True)
    save_audio = settings.get("save_audio", True)
    print(
        f"[WEBHOOK] Settings: folder={folder_name}, summary={save_summary}, transcript={save_transcript}, audio={save_audio}"
    )

    # Nothing to save
    if not save_summary and not save_transcript and not save_audio:
        print(f"[WEBHOOK] Nothing to save (all disabled)")
        return EndpointResponse(message="")

    # Create Dropbox client
    client = DropboxClient(access_token)

    # Create folder paths
    finished_at = conversation.finished_at or conversation.created_at
    conv_folder_name = create_folder_name(conversation.structured.title, finished_at)
    root_path = f"/{folder_name}"
    conv_path = f"{root_path}/{conv_folder_name}"
    print(f"[WEBHOOK] Folder path: {conv_path}")

    # Ensure root folder exists
    success, error = client.ensure_folder_exists(root_path)
    if not success:
        print(f"[WEBHOOK] ERROR: Failed to create root folder: {error}")
        return EndpointResponse(message="")
    print(f"[WEBHOOK] Root folder OK")

    # Create conversation folder
    result, error = client.create_folder(conv_path)
    if error and "already_exists" not in str(result):
        print(f"[WEBHOOK] ERROR: Failed to create conversation folder: {error}")
        return EndpointResponse(message="")
    print(f"[WEBHOOK] Conversation folder created")

    files_saved = []

    # Save summary
    if save_summary:
        summary_content = generate_summary_markdown(conversation)
        print(f"[WEBHOOK] Uploading summary.md ({len(summary_content)} bytes)")
        result, error = client.upload_file(
            f"{conv_path}/summary.md",
            summary_content.encode("utf-8"),
        )
        if error:
            print(f"[WEBHOOK] ERROR uploading summary: {error}")
        else:
            print(f"[WEBHOOK] Summary uploaded successfully")
            files_saved.append("summary")

    # Save transcript
    if save_transcript and conversation.transcript_segments:
        transcript_content = generate_transcript_markdown(conversation)
        print(f"[WEBHOOK] Uploading transcript.md ({len(transcript_content)} bytes)")
        result, error = client.upload_file(
            f"{conv_path}/transcript.md",
            transcript_content.encode("utf-8"),
        )
        if error:
            print(f"[WEBHOOK] ERROR uploading transcript: {error}")
        else:
            print(f"[WEBHOOK] Transcript uploaded successfully")
            files_saved.append("transcript")

    # Save audio if available
    if save_audio:
        audio_wav = get_and_clear_audio(uid)
        if audio_wav:
            print(f"[WEBHOOK] Uploading audio.wav ({len(audio_wav)} bytes)")
            result, error = client.upload_file(
                f"{conv_path}/audio.wav",
                audio_wav,
            )
            if error:
                print(f"[WEBHOOK] ERROR uploading audio: {error}")
            else:
                print(f"[WEBHOOK] Audio uploaded successfully")
                files_saved.append("audio")
        else:
            print(f"[WEBHOOK] No audio available for this conversation")

    # Return notification message
    if files_saved:
        print(f"[WEBHOOK] SUCCESS: Saved {files_saved}")
        return EndpointResponse(message=f"Saved to Dropbox: {', '.join(files_saved)}")

    print(f"[WEBHOOK] No files saved")
    return EndpointResponse(message="")


# ============== Chat Tools ==============


@app.get("/.well-known/omi-tools.json")
async def get_omi_tools_manifest():
    """Return the chat tools manifest for Omi."""
    return {
        "tools": [
            {
                "name": "search_dropbox",
                "description": "Search for files in the user's Dropbox. Use this when the user wants to find a file, conversation, or document saved to Dropbox.",
                "endpoint": "/tools/search",
                "method": "POST",
                "parameters": {
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Search query - filename, content, or keywords to search for",
                        },
                    },
                    "required": ["query"],
                },
                "auth_required": True,
                "status_message": "Searching Dropbox...",
            },
            {
                "name": "list_dropbox_conversations",
                "description": "List recent conversations saved to Dropbox. Use this when the user wants to see their saved conversations or recent files.",
                "endpoint": "/tools/list",
                "method": "POST",
                "parameters": {
                    "properties": {
                        "folder": {
                            "type": "string",
                            "description": "Optional folder path to list. Leave empty to list the main Omi Conversations folder.",
                        },
                    },
                    "required": [],
                },
                "auth_required": True,
                "status_message": "Listing Dropbox files...",
            },
            {
                "name": "read_dropbox_file",
                "description": "Read and extract text content from a file in Dropbox. Supports text files (.txt, .md, .json, etc.) and PDFs. Use this when the user wants to read, summarize, or analyze a file from their Dropbox.",
                "endpoint": "/tools/read",
                "method": "POST",
                "parameters": {
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "The full path to the file in Dropbox (e.g., '/Omi Conversations/Meeting (2024-01-20)/summary.md')",
                        },
                    },
                    "required": ["path"],
                },
                "auth_required": True,
                "status_message": "Reading file from Dropbox...",
            },
        ]
    }


@app.post("/tools/search")
async def tool_search_dropbox(request: Request):
    """Search for files in Dropbox."""
    try:
        body = await request.json()
        uid = body.get("uid")
        query = body.get("query", "")

        if not uid:
            return {"error": "Missing user ID"}

        if not query:
            return {"error": "Please provide a search query"}

        # Get access token
        access_token = get_valid_access_token(uid)
        if not access_token:
            return {"error": "Please connect your Dropbox account first in the app settings."}

        # Search Dropbox
        client = DropboxClient(access_token)
        results, error = client.search_files(query, max_results=10)

        if error:
            return {"error": f"Search failed: {error}"}

        if not results:
            return {"result": f"No files found matching '{query}'"}

        # Format results
        output = f"**Found {len(results)} file(s) matching '{query}':**\n\n"
        for i, item in enumerate(results, 1):
            name = item["name"]
            path = item["path"]
            file_type = "📁" if item["type"] == "folder" else "📄"
            size = item.get("size", 0)
            size_str = f"{size / 1024:.1f} KB" if size > 0 else ""

            output += f"{i}. {file_type} **{name}**\n"
            output += f"   Path: `{path}`\n"
            if size_str:
                output += f"   Size: {size_str}\n"
            output += "\n"

        return {"result": output}

    except Exception as e:
        return {"error": f"Search error: {str(e)}"}


@app.post("/tools/list")
async def tool_list_dropbox(request: Request):
    """List files in Dropbox folder."""
    try:
        body = await request.json()
        uid = body.get("uid")
        folder = body.get("folder", "")

        if not uid:
            return {"error": "Missing user ID"}

        # Get access token
        access_token = get_valid_access_token(uid)
        if not access_token:
            return {"error": "Please connect your Dropbox account first in the app settings."}

        # Get user settings for default folder
        settings = get_user_settings(uid)
        default_folder = settings.get("folder_name", "Omi Conversations")

        # Use default folder if none specified
        if not folder:
            folder = f"/{default_folder}"

        # List folder
        client = DropboxClient(access_token)
        results, error = client.list_folder(folder, limit=20)

        if error:
            return {"error": f"Could not list folder: {error}"}

        if not results:
            return {"result": f"No files found in `{folder}`"}

        # Format results
        output = f"**Files in `{folder}`:**\n\n"
        for i, item in enumerate(results, 1):
            name = item["name"]
            file_type = "📁" if item["type"] == "folder" else "📄"
            size = item.get("size", 0)
            size_str = f" ({size / 1024:.1f} KB)" if size > 0 else ""
            modified = item.get("modified", "")[:10] if item.get("modified") else ""

            output += f"{i}. {file_type} **{name}**{size_str}"
            if modified:
                output += f" - {modified}"
            output += "\n"

        return {"result": output}

    except Exception as e:
        return {"error": f"List error: {str(e)}"}


@app.post("/tools/read")
async def tool_read_dropbox_file(request: Request):
    """Read and extract text content from a file in Dropbox."""
    try:
        body = await request.json()
        uid = body.get("uid")
        path = body.get("path", "")

        if not uid:
            return {"error": "Missing user ID"}

        if not path:
            return {"error": "Please provide a file path"}

        # Get access token
        access_token = get_valid_access_token(uid)
        if not access_token:
            return {"error": "Please connect your Dropbox account first in the app settings."}

        # Download file
        client = DropboxClient(access_token)
        file_bytes, error = client.download_file(path)

        if error:
            return {"error": f"Could not download file: {error}"}

        if not file_bytes:
            return {"error": "File is empty"}

        # Get file extension
        file_ext = path.lower().split(".")[-1] if "." in path else ""
        file_name = path.split("/")[-1]

        # Extract text based on file type
        text_content = ""

        if file_ext == "pdf":
            # Extract text from PDF
            try:
                import pypdf

                pdf_buffer = io.BytesIO(file_bytes)
                reader = pypdf.PdfReader(pdf_buffer)
                pages_text = []
                for i, page in enumerate(reader.pages):
                    page_text = page.extract_text()
                    if page_text:
                        pages_text.append(f"--- Page {i+1} ---\n{page_text}")
                text_content = "\n\n".join(pages_text)
                if not text_content.strip():
                    return {"error": "Could not extract text from PDF. The PDF may be image-based or scanned."}
            except ImportError:
                return {"error": "PDF reading is not available. Please contact support."}
            except Exception as e:
                return {"error": f"Error reading PDF: {str(e)}"}

        elif file_ext in [
            "txt",
            "md",
            "json",
            "csv",
            "xml",
            "html",
            "htm",
            "py",
            "js",
            "ts",
            "yaml",
            "yml",
            "ini",
            "log",
        ]:
            # Text-based files
            try:
                text_content = file_bytes.decode("utf-8")
            except UnicodeDecodeError:
                try:
                    text_content = file_bytes.decode("latin-1")
                except Exception:
                    return {"error": "Could not decode file as text"}

        elif file_ext in ["doc", "docx"]:
            return {"error": "Word documents (.doc/.docx) are not yet supported. Please convert to PDF or text."}

        elif file_ext in ["jpg", "jpeg", "png", "gif", "bmp", "webp"]:
            return {"error": "Image files cannot be read as text. Please use a document format."}

        elif file_ext in ["mp3", "wav", "m4a", "ogg", "flac"]:
            return {"error": "Audio files cannot be read as text."}

        elif file_ext in ["mp4", "mov", "avi", "mkv", "webm"]:
            return {"error": "Video files cannot be read as text."}

        else:
            # Try to read as text anyway
            try:
                text_content = file_bytes.decode("utf-8")
            except Exception:
                return {"error": f"Cannot read .{file_ext} files as text"}

        # Truncate if too long (keep under ~15k chars for reasonable response)
        max_chars = 15000
        if len(text_content) > max_chars:
            text_content = (
                text_content[:max_chars] + f"\n\n... [Truncated - file has {len(text_content)} characters total]"
            )

        # Format output
        output = f"**Contents of `{file_name}`:**\n\n{text_content}"

        return {"result": output}

    except Exception as e:
        return {"error": f"Read error: {str(e)}"}


# ============== Audio Streaming Endpoint ==============


@app.post("/audio")
async def receive_audio(
    request: Request,
    uid: str = Query(...),
    sample_rate: int = Query(16000),
):
    """
    Receive real-time audio bytes from Omi.
    Accumulates audio until the conversation webhook is triggered.
    """
    try:
        space = _make_room_for(uid)
        audio_bytes = await _read_audio_limited(request, space)

        if audio_bytes:
            existing = audio_buffers.get(uid, b"")
            audio_buffers[uid] = existing + audio_bytes
            audio_buffers.move_to_end(uid)
            audio_sample_rates[uid] = sample_rate
            print(
                f"[AUDIO] Received {len(audio_bytes)} bytes for uid={uid}, "
                f"total: {len(audio_buffers[uid])} bytes"
            )

        return {"status": "ok"}
    except Exception as e:
        print(f"[AUDIO] Error receiving audio: {e}")
        return {"status": "error", "message": str(e)}


# ============== Run Server ==============

if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
