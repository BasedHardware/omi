"""
backend/auth/google_oauth.py

Handles the Google OAuth 2.0 flow for your app.

Flow:
  1. Frontend calls GET /auth/google/connect  → returns a Google auth URL
  2. User visits the URL, grants access
  3. Google redirects to GET /auth/google/callback?code=...&state=...
  4. This module exchanges the code for tokens and stores them in Supabase
  5. The MCP server (in EXTERNAL_OAUTH21_PROVIDER mode) receives the
     access token on every tool call via Authorization: Bearer header

Token refresh:
  - get_valid_google_token() checks expiry and auto-refreshes when needed.
  - Call this before every MCP request in the orchestrator.
"""

import os
import secrets
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Tuple
from urllib.parse import urlencode

import httpx
from dotenv import load_dotenv
from auth.supabase_client import get_service_client

load_dotenv()

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_OAUTH_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_OAUTH_CLIENT_SECRET", "")
GOOGLE_REDIRECT_URI = os.getenv(
    "GOOGLE_OAUTH_REDIRECT_URI",
    "http://localhost:8000/auth/google/callback",
)

# Scopes your app needs — keep in sync with the MCP server's --tools flag
GOOGLE_SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.compose",
    "https://www.googleapis.com/auth/gmail.labels",
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/calendar.events",
]

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"

# In-memory state store (replace with Redis for multi-instance deployments)
_oauth_states: Dict[str, str] = {}   # state → user_id


def build_google_auth_url(user_id: str) -> str:
    """
    Generates a Google OAuth authorization URL and stores the state
    so the callback can associate the code with the correct user.
    """
    state = secrets.token_urlsafe(32)
    _oauth_states[state] = user_id

    params = {
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": " ".join(GOOGLE_SCOPES),
        "access_type": "offline",       # ensures we get a refresh_token
        "prompt": "consent",            # forces refresh_token even on re-auth
        "state": state,
    }
    return f"{GOOGLE_AUTH_URL}?{urlencode(params)}"


async def handle_google_callback(code: str, state: str) -> Tuple[str, str]:
    """
    Exchanges the authorization code for tokens and stores them in Supabase.

    Returns:
        (user_id, google_email) tuple on success.
    Raises:
        ValueError on invalid state or token exchange failure.
    """
    user_id = _oauth_states.pop(state, None)
    if not user_id:
        raise ValueError("Invalid or expired OAuth state. Please try connecting again.")

    # Exchange code for tokens
    async with httpx.AsyncClient() as client:
        token_resp = await client.post(
            GOOGLE_TOKEN_URL,
            data={
                "code": code,
                "client_id": GOOGLE_CLIENT_ID,
                "client_secret": GOOGLE_CLIENT_SECRET,
                "redirect_uri": GOOGLE_REDIRECT_URI,
                "grant_type": "authorization_code",
            },
        )

    if token_resp.status_code != 200:
        raise ValueError(f"Google token exchange failed: {token_resp.text}")

    token_data = token_resp.json()
    access_token = token_data["access_token"]
    refresh_token = token_data.get("refresh_token")
    expires_in = token_data.get("expires_in", 3600)
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)

    # Fetch the Google account email
    async with httpx.AsyncClient() as client:
        info_resp = await client.get(
            GOOGLE_USERINFO_URL,
            headers={"Authorization": f"Bearer {access_token}"},
        )

    if info_resp.status_code != 200:
        raise ValueError(f"Failed to fetch Google user info: {info_resp.text}")

    google_email = info_resp.json().get("email", "")

    # Upsert into Supabase (service key bypasses RLS)
    db = get_service_client()
    db.table("google_tokens").upsert(
        {
            "user_id": user_id,
            "email": google_email,
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_uri": GOOGLE_TOKEN_URL,
            "scopes": GOOGLE_SCOPES,
            "expires_at": expires_at.isoformat(),
        },
        on_conflict="user_id",
    ).execute()

    return user_id, google_email


async def get_valid_google_token(user_id: str) -> Optional[str]:
    """
    Returns a valid Google access token for user_id.
    Auto-refreshes if the stored token is expired or close to expiry.
    Returns None if the user hasn't connected their Google account yet.
    """
    db = get_service_client()
    result = (
        db.table("google_tokens")
        .select("*")
        .eq("user_id", user_id)
        .single()
        .execute()
    )

    if not result.data:
        return None

    row = result.data
    expires_at = row.get("expires_at")
    access_token = row["access_token"]
    refresh_token = row.get("refresh_token")

    # Check if the token is still valid (with a 60-second buffer)
    if expires_at:
        expiry = datetime.fromisoformat(expires_at)
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=timezone.utc)
        if expiry > datetime.now(timezone.utc) + timedelta(seconds=60):
            return access_token

    # Token is expired — refresh it
    if not refresh_token:
        # No refresh token stored — user must re-authorize
        return None

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            GOOGLE_TOKEN_URL,
            data={
                "client_id": GOOGLE_CLIENT_ID,
                "client_secret": GOOGLE_CLIENT_SECRET,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            },
        )

    if resp.status_code != 200:
        # Refresh failed (revoked) — clear the bad token
        db.table("google_tokens").delete().eq("user_id", user_id).execute()
        return None

    refreshed = resp.json()
    new_access_token = refreshed["access_token"]
    new_expires_at = datetime.now(timezone.utc) + timedelta(
        seconds=refreshed.get("expires_in", 3600)
    )

    db.table("google_tokens").update(
        {
            "access_token": new_access_token,
            "expires_at": new_expires_at.isoformat(),
        }
    ).eq("user_id", user_id).execute()

    return new_access_token


async def get_google_connection_status(user_id: str) -> Dict:
    """Returns whether the user has connected their Google account."""
    db = get_service_client()
    result = (
        db.table("google_tokens")
        .select("email, expires_at, scopes")
        .eq("user_id", user_id)
        .execute()
    )
    if result.data:
        row = result.data[0]
        return {
            "connected": True,
            "email": row["email"],
            "scopes": row.get("scopes", []),
        }
    return {"connected": False, "email": None, "scopes": []}


async def disconnect_google(user_id: str) -> None:
    """Removes stored Google tokens for a user."""
    db = get_service_client()
    db.table("google_tokens").delete().eq("user_id", user_id).execute()
