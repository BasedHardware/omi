import logging
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from datetime import datetime, timedelta
from typing import Optional
import firebase_admin
from firebase_admin import credentials, auth as firebase_auth

from backend.database.session import get_db
from backend.dependencies.auth import get_current_user
from backend.schemas.oauth import OAuthToken, OAuthCallback

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/oauth", tags=["oauth"])

# OAuth2 scheme for token authentication
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/oauth/token")

# Firebase configuration
FIREBASE_CONFIG = {
    "credential": os.getenv("FIREBASE_CREDENTIAL_PATH"),
    "project_id": os.getenv("FIREBASE_PROJECT_ID"),
}

def get_firebase_app():
    """Get or create Firebase Admin app instance."""
    if not firebase_admin._apps:
        try:
            cred = credentials.Certificate(FIREBASE_CONFIG["credential"])
            firebase_admin.initialize_app(cred, {
                "project_id": FIREBASE_CONFIG["project_id"]
            })
        except Exception as e:
            logger.error(f"Failed to initialize Firebase: {type(e).__name__}")
            raise HTTPException(status_code=500, detail="Firebase service unavailable")
    return firebase_admin.get_app()

@router.post("/token")
async def exchange_token(
    request: Request,
    db: Session = Depends(get_db)
):
    """Exchange OAuth code for tokens."""
    form_data = await request.form()
    code = form_data.get("code")
    grant_type = form_data.get("grant_type", "authorization_code")

    if not code:
        raise HTTPException(status_code=400, detail="Authorization code is required")

    if grant_type != "authorization_code":
        raise HTTPException(status_code=400, detail="Invalid grant type")

    try:
        # Exchange code for token with provider
        token_response = await exchange_code_for_token(code)
        return OAuthToken(**token_response)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Token exchange failed: {type(e).__name__}")
        raise HTTPException(status_code=500, detail="Token exchange failed")

@router.get("/callback/{provider}")
async def oauth_callback(
    provider: str,
    request: Request,
    db: Session = Depends(get_db)
):
    """Handle OAuth callback from provider."""
    query_params = request.query_params
    code = query_params.get("code")
    state = query_params.get("state")

    if not code:
        raise HTTPException(status_code=400, detail="Authorization code is required")

    try:
        # Verify state and exchange code
        token_response = await exchange_code_for_token(code, provider)
        return {"access_token": token_response["access_token"], "token_type": "bearer"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"OAuth callback failed: {type(e).__name__}")
        raise HTTPException(status_code=500, detail="Authentication failed")

@router.post("/verify")
async def verify_token(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    """Verify Firebase ID token."""
    try:
        decoded_token = firebase_auth.verify_id_token(token)
        return {"uid": decoded_token["uid"], "verified": True}
    except firebase_auth.InvalidIdTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")
    except firebase_auth.ExpiredIdTokenError:
        raise HTTPException(status_code=401, detail="Token expired")
    except Exception as e:
        logger.error(f"Token verification failed: {type(e).__name__}")
        raise HTTPException(status_code=401, detail="Authentication failed")

@router.get("/providers")
async def list_providers():
    """List available OAuth providers."""
    return [
        {"name": "google", "display_name": "Google"},
        {"name": "github", "display_name": "GitHub"},
        {"name": "facebook", "display_name": "Facebook"},
    ]

async def exchange_code_for_token(code: str, provider: str = None) -> dict:
    """Exchange authorization code for access token."""
    # This is a placeholder - actual implementation would vary by provider
    provider_config = get_provider_config(provider)

    # Exchange code for token
    token_url = provider_config.get("token_url")
    client_id = provider_config.get("client_id")
    client_secret = provider_config.get("client_secret")
    redirect_uri = provider_config.get("redirect_uri")

    # Make token exchange request
    import httpx
    async with httpx.AsyncClient() as client:
        response = await client.post(token_url, data={
            "code": code,
            "grant_type": "authorization_code",
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
        })
        response.raise_for_status()
        return response.json()

def get_provider_config(provider: str) -> dict:
    """Get configuration for an OAuth provider."""
    providers = {
        "google": {
            "token_url": os.getenv("GOOGLE_TOKEN_URL", "https://oauth2.googleapis.com/token"),
            "client_id": os.getenv("GOOGLE_CLIENT_ID"),
            "client_secret": os.getenv("GOOGLE_CLIENT_SECRET"),
            "redirect_uri": os.getenv("GOOGLE_REDIRECT_URI"),
        },
        "github": {
            "token_url": os.getenv("GITHUB_TOKEN_URL", "https://github.com/login/oauth/access_token"),
            "client_id": os.getenv("GITHUB_CLIENT_ID"),
            "client_secret": os.getenv("GITHUB_CLIENT_SECRET"),
            "redirect_uri": os.getenv("GITHUB_REDIRECT_URI"),
        },
    }
    return providers.get(provider, providers["google"])

import os
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from datetime import datetime, timedelta
from typing import Optional
import firebase_admin
from firebase_admin import credentials, auth as firebase_auth
from sqlalchemy.orm import Session
