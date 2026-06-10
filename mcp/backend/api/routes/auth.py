"""
backend/api/routes/auth.py  (updated — adds GitHub OAuth endpoints)

New endpoints added to the existing file:
  GET  /auth/github/connect      → returns GitHub OAuth URL
  GET  /auth/github/callback     → GitHub redirects here after user grants access
  DELETE /auth/github/disconnect → unlink GitHub account

GET /auth/me now also returns github connection status.
"""

from fastapi import APIRouter, HTTPException, status, Query
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, EmailStr
import os

from auth.supabase_client import get_anon_client
from auth.dependencies import CurrentUser
from auth.google_oauth import (
    build_google_auth_url,
    handle_google_callback,
    get_google_connection_status,
    disconnect_google,
)
from auth.github_oauth import (
    build_github_auth_url,
    handle_github_callback,
    get_github_connection_status,
    disconnect_github,
)

import asyncio

router = APIRouter(prefix="/auth", tags=["auth"])

FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173")


# ── Request models ─────────────────────────────────────────────────────────

class SignupRequest(BaseModel):
    email: EmailStr
    password: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


# ── Supabase Auth ──────────────────────────────────────────────────────────

@router.post("/signup", status_code=status.HTTP_201_CREATED)
async def signup(body: SignupRequest):
    client = get_anon_client()
    try:
        resp = client.auth.sign_up({"email": body.email, "password": body.password})
        if not resp.user:
            raise HTTPException(status_code=400, detail="Signup failed")
        return {
            "message": "Account created. Check your email to confirm.",
            "user_id": resp.user.id,
            "email": resp.user.email,
        }
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/login")
async def login(body: LoginRequest):
    client = get_anon_client()
    try:
        resp = client.auth.sign_in_with_password({"email": body.email, "password": body.password})
        if not resp.session:
            raise HTTPException(status_code=401, detail="Invalid credentials")
        return {
            "access_token": resp.session.access_token,
            "refresh_token": resp.session.refresh_token,
            "expires_in": resp.session.expires_in,
            "user": {"id": resp.user.id, "email": resp.user.email},
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=401, detail=str(exc))


@router.post("/logout")
async def logout(user: CurrentUser):
    client = get_anon_client()
    try:
        client.auth.sign_out()
        return {"message": "Logged out"}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/refresh")
async def refresh_session(body: RefreshRequest):
    client = get_anon_client()
    try:
        resp = client.auth.refresh_session(body.refresh_token)
        if not resp.session:
            raise HTTPException(status_code=401, detail="Invalid refresh token")
        return {
            "access_token": resp.session.access_token,
            "refresh_token": resp.session.refresh_token,
            "expires_in": resp.session.expires_in,
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=401, detail=str(exc))


@router.get("/me")
async def get_me(user: CurrentUser):
    """Returns current user + both Google and GitHub connection status."""
    google_status, github_status = await asyncio.gather(
        get_google_connection_status(user["id"]),
        get_github_connection_status(user["id"]),
    )
    return {
        "id": user["id"],
        "email": user["email"],
        "google": google_status,
        "github": github_status,
    }


# ── Google OAuth ───────────────────────────────────────────────────────────

@router.get("/google/connect")
async def google_connect(user: CurrentUser):
    url = build_google_auth_url(user_id=user["id"])
    return {"url": url}


@router.get("/google/callback")
async def google_callback(
    code: str = Query(...),
    state: str = Query(...),
    error: str = Query(None),
):
    if error:
        return RedirectResponse(url=f"{FRONTEND_URL}/settings?google=error&reason={error}")
    try:
        user_id, google_email = await handle_google_callback(code=code, state=state)
        return RedirectResponse(url=f"{FRONTEND_URL}/settings?google=connected&email={google_email}")
    except ValueError as exc:
        return RedirectResponse(url=f"{FRONTEND_URL}/settings?google=error&reason={str(exc)}")


@router.delete("/google/disconnect")
async def google_disconnect(user: CurrentUser):
    await disconnect_google(user["id"])
    return {"message": "Google account disconnected"}


# ── GitHub OAuth ───────────────────────────────────────────────────────────

@router.get("/github/connect")
async def github_connect(user: CurrentUser):
    """Returns a GitHub OAuth URL for the user to visit."""
    url = build_github_auth_url(user_id=user["id"])
    return {"url": url}


@router.get("/github/callback")
async def github_callback(
    code: str = Query(...),
    state: str = Query(...),
    error: str = Query(None),
):
    """
    GitHub redirects here after the user grants (or denies) access.
    On success → redirects to frontend with ?github=connected&username=...
    On failure → redirects to frontend with ?github=error
    """
    if error:
        return RedirectResponse(
            url=f"{FRONTEND_URL}/settings?github=error&reason={error}"
        )
    try:
        user_id, github_username = await handle_github_callback(code=code, state=state)
        return RedirectResponse(
            url=f"{FRONTEND_URL}/settings?github=connected&username={github_username}"
        )
    except ValueError as exc:
        return RedirectResponse(
            url=f"{FRONTEND_URL}/settings?github=error&reason={str(exc)}"
        )


@router.delete("/github/disconnect")
async def github_disconnect(user: CurrentUser):
    """Removes the user's stored GitHub token."""
    await disconnect_github(user["id"])
    return {"message": "GitHub account disconnected"}


# needed for get_me
import asyncio
