"""
Zomato Food Ordering App for Omi

Public OMI app that proxies Zomato's MCP server tools as chat tool endpoints.
Handles per-user OAuth and token management.
"""

import logging
import os
import secrets
import time

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from db import (
    delete_zomato_tokens,
    get_oauth_state,
    get_zomato_tokens,
    store_oauth_state,
    store_zomato_tokens,
)
from mcp_proxy import (
    build_authorization_url,
    call_zomato_tool,
    discover_oauth_metadata,
    discover_tools,
    exchange_oauth_code,
    generate_pkce_pair,
    register_oauth_client,
)
from models import ChatToolResponse

load_dotenv()

logger = logging.getLogger(__name__)

APP_BASE_URL = os.getenv("APP_BASE_URL", "http://localhost:8080")
ZOMATO_MCP_URL = "https://mcp-server.zomato.com/mcp"

# Cache for OAuth metadata and client credentials
_oauth_cache = {}

app = FastAPI(
    title="Zomato Omi Integration",
    description="Order food from Zomato through Omi chat",
    version="1.0.0",
)


# ============================================
# Health & Landing
# ============================================


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/")
async def landing():
    return HTMLResponse(
        """
        <html>
        <head><title>Zomato x Omi</title></head>
        <body style="font-family: sans-serif; max-width: 600px; margin: 50px auto; text-align: center;">
            <h1>Zomato x Omi</h1>
            <p>Order food through your Omi conversations.</p>
            <p>Enable this app in the Omi app store to get started.</p>
        </body>
        </html>
        """
    )


# ============================================
# OAuth Flow
# ============================================


async def _get_oauth_config() -> dict:
    """Get or discover OAuth metadata and register a client. Cached."""
    if _oauth_cache.get("metadata") and _oauth_cache.get("client"):
        return _oauth_cache

    metadata = await discover_oauth_metadata(ZOMATO_MCP_URL)
    if not metadata:
        raise HTTPException(status_code=502, detail="Could not discover Zomato OAuth metadata")

    _oauth_cache["metadata"] = metadata

    redirect_uri = f"{APP_BASE_URL}/auth/zomato/callback"

    # Try dynamic client registration
    if metadata.get("registration_endpoint"):
        try:
            client = await register_oauth_client(
                metadata["registration_endpoint"],
                redirect_uri,
                metadata.get("scopes_supported"),
            )
            _oauth_cache["client"] = client
        except Exception as e:
            logger.warning(f"Dynamic client registration failed: {e}")

    # Fall back to env var credentials
    if not _oauth_cache.get("client"):
        client_id = os.getenv("ZOMATO_CLIENT_ID")
        if not client_id:
            raise HTTPException(
                status_code=500,
                detail="No OAuth client credentials available. Set ZOMATO_CLIENT_ID env var.",
            )
        _oauth_cache["client"] = {
            "client_id": client_id,
            "client_secret": os.getenv("ZOMATO_CLIENT_SECRET"),
        }

    return _oauth_cache


@app.get("/auth/zomato")
async def auth_zomato(uid: str):
    """Initiate Zomato OAuth flow for a user."""
    config = await _get_oauth_config()
    metadata = config["metadata"]
    client = config["client"]

    code_verifier, code_challenge = generate_pkce_pair()
    state = secrets.token_urlsafe(32)

    store_oauth_state(
        state,
        {
            "uid": uid,
            "code_verifier": code_verifier,
            "client_id": client["client_id"],
            "client_secret": client.get("client_secret"),
            "token_endpoint": metadata["token_endpoint"],
        },
    )

    redirect_uri = f"{APP_BASE_URL}/auth/zomato/callback"
    auth_url = build_authorization_url(
        metadata["authorization_endpoint"],
        client["client_id"],
        redirect_uri,
        state,
        metadata.get("scopes_supported"),
        code_challenge,
    )

    return RedirectResponse(url=auth_url)


@app.get("/auth/zomato/callback")
async def auth_callback(code: str, state: str):
    """Handle Zomato OAuth callback."""
    state_data = get_oauth_state(state)
    if not state_data:
        raise HTTPException(status_code=400, detail="Invalid or expired OAuth state")

    uid = state_data["uid"]
    redirect_uri = f"{APP_BASE_URL}/auth/zomato/callback"

    tokens = await exchange_oauth_code(
        state_data["token_endpoint"],
        code,
        redirect_uri,
        state_data["client_id"],
        state_data.get("client_secret"),
        state_data.get("code_verifier"),
    )

    token_data = {
        "access_token": tokens["access_token"],
        "refresh_token": tokens.get("refresh_token"),
        "token_endpoint": state_data["token_endpoint"],
        "client_id": state_data["client_id"],
        "client_secret": state_data.get("client_secret"),
    }
    if tokens.get("expires_in"):
        token_data["expires_at"] = time.time() + tokens["expires_in"]

    store_zomato_tokens(uid, token_data)

    return HTMLResponse(
        """
        <html>
        <head><title>Connected!</title></head>
        <body style="font-family: sans-serif; max-width: 600px; margin: 50px auto; text-align: center;">
            <h1>Zomato Connected!</h1>
            <p>You can now order food through Omi. Go back to the app and start chatting!</p>
        </body>
        </html>
        """
    )


@app.get("/setup/zomato")
async def setup_check(uid: str):
    """Check if a user has completed Zomato setup."""
    tokens = get_zomato_tokens(uid)
    return {"is_setup_completed": tokens is not None}


@app.get("/disconnect")
async def disconnect(uid: str):
    """Disconnect a user's Zomato account."""
    delete_zomato_tokens(uid)
    return {"status": "disconnected"}


# ============================================
# Chat Tool Endpoints
# ============================================


def _get_user_tokens(uid: str) -> tuple:
    """Get user's access token and full token dict. Raises 401 if not found."""
    tokens = get_zomato_tokens(uid)
    if not tokens or not tokens.get("access_token"):
        raise HTTPException(status_code=401, detail="User not authenticated with Zomato. Please connect first.")
    return tokens["access_token"], tokens


async def _call_tool(uid: str, tool_name: str, arguments: dict) -> ChatToolResponse:
    """Common handler for all chat tool endpoints."""
    access_token, oauth_tokens = _get_user_tokens(uid)
    result = await call_zomato_tool(tool_name, arguments, access_token, oauth_tokens)

    # Persist any refreshed tokens
    if oauth_tokens.get("access_token") != access_token:
        store_zomato_tokens(uid, oauth_tokens)

    return ChatToolResponse(result=result)


@app.post("/tools/{tool_name}")
async def generic_tool_endpoint(tool_name: str, request: Request):
    """Generic endpoint that forwards any tool call to Zomato's MCP server.

    This handles all Zomato MCP tools dynamically — no need to hardcode
    individual endpoints per tool.
    """
    body = await request.json()
    uid = body.get("uid")
    if not uid:
        raise HTTPException(status_code=400, detail="uid is required")

    # Extract tool arguments (everything except OMI metadata fields)
    arguments = {k: v for k, v in body.items() if k not in ("uid", "app_id", "tool_name")}

    return await _call_tool(uid, tool_name, arguments)


# ============================================
# Tool Discovery / Manifest
# ============================================


@app.get("/tools")
async def list_tools():
    """Discover and return available Zomato MCP tools."""
    try:
        tools = await discover_tools()
        return {"tools": tools}
    except Exception as e:
        logger.error(f"Tool discovery failed: {e}")
        return {"tools": [], "error": str(e)}
