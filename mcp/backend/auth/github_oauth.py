"""
backend/auth/github_oauth.py

GitHub OAuth 2.0 flow for your app.

Flow:
  1. Frontend calls GET /auth/github/connect  → returns GitHub auth URL
  2. User visits URL, grants access
  3. GitHub redirects to GET /auth/github/callback?code=...&state=...
  4. This module exchanges the code for a token and stores it in Supabase
  5. The orchestrator reads the token per-user and injects it into MCP requests

Note on token expiry:
  GitHub OAuth tokens (non-fine-grained) do NOT expire unless the user
  revokes them or your app is uninstalled. Fine-grained PATs do expire —
  if you switch to those, add an expires_at column and refresh logic.
  For now we treat them as permanent and only remove on explicit disconnect
  or a 401 from the GitHub MCP server.
"""

import os
import secrets
from typing import Optional, Dict, Tuple
from urllib.parse import urlencode

import httpx
from dotenv import load_dotenv
from auth.supabase_client import get_service_client

load_dotenv()

GITHUB_CLIENT_ID = os.getenv("GITHUB_CLIENT_ID", "")
GITHUB_CLIENT_SECRET = os.getenv("GITHUB_CLIENT_SECRET", "")
GITHUB_REDIRECT_URI = os.getenv(
    "GITHUB_OAUTH_REDIRECT_URI",
    "http://localhost:8000/auth/github/callback",
)

# Scopes needed for the GitHub MCP server tools you're using
# Adjust based on what tools you enable in the orchestrator
GITHUB_SCOPES = [
    "repo",           # full repo access (read/write code, PRs, issues)
    "read:user",      # read user profile (needed for get_me tool)
    "user:email",     # read user email
]

GITHUB_AUTH_URL = "https://github.com/login/oauth/authorize"
GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
GITHUB_USER_URL = "https://api.github.com/user"

# In-memory state store — replace with Redis for multi-instance deployments
_oauth_states: Dict[str, str] = {}   # state → user_id


def build_github_auth_url(user_id: str) -> str:
    """
    Generates a GitHub OAuth authorization URL.
    Stores the state so the callback can associate the code with the user.
    """
    state = secrets.token_urlsafe(32)
    _oauth_states[state] = user_id

    params = {
        "client_id": GITHUB_CLIENT_ID,
        "redirect_uri": GITHUB_REDIRECT_URI,
        "scope": " ".join(GITHUB_SCOPES),
        "state": state,
    }
    return f"{GITHUB_AUTH_URL}?{urlencode(params)}"


async def handle_github_callback(code: str, state: str) -> Tuple[str, str]:
    """
    Exchanges the authorization code for a GitHub access token
    and stores it in Supabase.

    Returns:
        (user_id, github_username) on success.
    Raises:
        ValueError on invalid state or failed exchange.
    """
    user_id = _oauth_states.pop(state, None)
    if not user_id:
        raise ValueError("Invalid or expired OAuth state. Please try connecting again.")

    # Exchange code for token
    async with httpx.AsyncClient() as client:
        token_resp = await client.post(
            GITHUB_TOKEN_URL,
            headers={"Accept": "application/json"},
            data={
                "client_id": GITHUB_CLIENT_ID,
                "client_secret": GITHUB_CLIENT_SECRET,
                "code": code,
                "redirect_uri": GITHUB_REDIRECT_URI,
            },
        )

    if token_resp.status_code != 200:
        raise ValueError(f"GitHub token exchange failed: {token_resp.text}")

    token_data = token_resp.json()

    if "error" in token_data:
        raise ValueError(f"GitHub OAuth error: {token_data.get('error_description', token_data['error'])}")

    access_token = token_data["access_token"]
    token_type = token_data.get("token_type", "bearer")
    scopes_str = token_data.get("scope", "")
    scopes = [s.strip() for s in scopes_str.split(",") if s.strip()]

    # Fetch GitHub username
    async with httpx.AsyncClient() as client:
        user_resp = await client.get(
            GITHUB_USER_URL,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/vnd.github+json",
            },
        )

    if user_resp.status_code != 200:
        raise ValueError(f"Failed to fetch GitHub user info: {user_resp.text}")

    github_username = user_resp.json().get("login", "")

    # Upsert into Supabase
    db = get_service_client()
    db.table("github_tokens").upsert(
        {
            "user_id": user_id,
            "github_username": github_username,
            "access_token": access_token,
            "token_type": token_type,
            "scopes": scopes,
        },
        on_conflict="user_id",
    ).execute()

    return user_id, github_username


async def get_github_token(user_id: str) -> Optional[str]:
    """
    Returns the stored GitHub access token for user_id.
    Returns None if the user hasn't connected GitHub yet.

    GitHub tokens don't expire, so no refresh logic needed.
    If the MCP server returns 401, call clear_github_token() and
    ask the user to reconnect.
    """
    db = get_service_client()
    result = (
        db.table("github_tokens")
        .select("access_token")
        .eq("user_id", user_id)
        .single()
        .execute()
    )

    if not result.data:
        return None

    return result.data["access_token"]


async def clear_github_token(user_id: str) -> None:
    """
    Removes a user's GitHub token — call this when GitHub returns 401
    so the user knows they need to reconnect.
    """
    db = get_service_client()
    db.table("github_tokens").delete().eq("user_id", user_id).execute()


async def get_github_connection_status(user_id: str) -> Dict:
    """Returns whether the user has connected their GitHub account."""
    db = get_service_client()
    result = (
        db.table("github_tokens")
        .select("github_username, scopes")
        .eq("user_id", user_id)
        .execute()
    )
    if result.data:
        row = result.data[0]
        return {
            "connected": True,
            "username": row["github_username"],
            "scopes": row.get("scopes", []),
        }
    return {"connected": False, "username": None, "scopes": []}


async def disconnect_github(user_id: str) -> None:
    """Removes stored GitHub tokens for a user."""
    db = get_service_client()
    db.table("github_tokens").delete().eq("user_id", user_id).execute()
