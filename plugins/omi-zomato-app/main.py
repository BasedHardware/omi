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


LOCALHOST_REDIRECT_URI = "http://localhost/callback"


async def _get_oauth_config() -> dict:
    """Get or discover OAuth metadata and register a client with localhost redirect. Cached."""
    if _oauth_cache.get("metadata") and _oauth_cache.get("client"):
        return _oauth_cache

    metadata = await discover_oauth_metadata(ZOMATO_MCP_URL)
    if not metadata:
        raise HTTPException(status_code=502, detail="Could not discover Zomato OAuth metadata")

    _oauth_cache["metadata"] = metadata

    # Register with localhost redirect URI (Zomato only whitelists localhost)
    if metadata.get("registration_endpoint"):
        try:
            client = await register_oauth_client(
                metadata["registration_endpoint"],
                LOCALHOST_REDIRECT_URI,
                metadata.get("scopes_supported"),
            )
            _oauth_cache["client"] = client
        except Exception as e:
            logger.warning(f"Dynamic client registration failed: {e}")

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
    """Serve a relay page that handles Zomato OAuth via localhost redirect interception.

    Zomato only allows localhost redirect URIs. This page opens Zomato auth,
    then intercepts the localhost redirect to capture the auth code and
    sends it to our server for token exchange.
    """
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

    auth_url = build_authorization_url(
        metadata["authorization_endpoint"],
        client["client_id"],
        LOCALHOST_REDIRECT_URI,
        state,
        metadata.get("scopes_supported"),
        code_challenge,
    )

    callback_url = f"{APP_BASE_URL}/auth/zomato/callback"

    return HTMLResponse(
        f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>Connect Zomato</title>
        <style>
            * {{ margin: 0; padding: 0; box-sizing: border-box; }}
            body {{ font-family: -apple-system, BlinkMacSystemFont, sans-serif; background: #1a1a1a; color: #fff;
                    display: flex; justify-content: center; align-items: center; min-height: 100vh; padding: 20px; }}
            .container {{ max-width: 400px; text-align: center; }}
            h1 {{ font-size: 24px; margin-bottom: 12px; }}
            p {{ color: #aaa; margin-bottom: 24px; font-size: 14px; }}
            .btn {{ display: inline-block; background: #e23744; color: #fff; padding: 14px 32px; border-radius: 8px;
                    text-decoration: none; font-size: 16px; font-weight: 600; cursor: pointer; border: none; }}
            .btn:hover {{ background: #c62d3a; }}
            .status {{ margin-top: 20px; font-size: 14px; color: #aaa; }}
            .spinner {{ display: none; margin: 20px auto; width: 30px; height: 30px; border: 3px solid #333;
                        border-top-color: #e23744; border-radius: 50%; animation: spin 0.8s linear infinite; }}
            @keyframes spin {{ to {{ transform: rotate(360deg); }} }}
            .success {{ color: #4caf50; font-size: 18px; font-weight: 600; }}
            .error {{ color: #e23744; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>Connect Zomato</h1>
            <p id="msg">Tap below to authorize Omi to order food on your behalf.</p>
            <button class="btn" id="authBtn" onclick="startAuth()">Authorize with Zomato</button>
            <div class="spinner" id="spinner"></div>
            <div class="status" id="status"></div>
        </div>
        <script>
            const AUTH_URL = "{auth_url}";
            const CALLBACK_URL = "{callback_url}";
            let authWindow = null;
            let pollTimer = null;

            function startAuth() {{
                document.getElementById('authBtn').style.display = 'none';
                document.getElementById('spinner').style.display = 'block';
                document.getElementById('status').textContent = 'Waiting for authorization...';

                // Open Zomato auth in a new window/tab
                authWindow = window.open(AUTH_URL, '_blank', 'width=500,height=700');

                // If popup was blocked, redirect in same window with a different strategy
                if (!authWindow || authWindow.closed) {{
                    // Fall back: redirect in same window, user will need to come back
                    document.getElementById('status').textContent = 'Redirecting to Zomato...';
                    window.location.href = AUTH_URL;
                    return;
                }}

                // Poll the popup location to catch localhost redirect
                pollTimer = setInterval(checkPopup, 500);

                // Also set a timeout
                setTimeout(function() {{
                    if (pollTimer) {{
                        clearInterval(pollTimer);
                        document.getElementById('spinner').style.display = 'none';
                        document.getElementById('status').innerHTML =
                            '<span class="error">Timed out. Please try again.</span>';
                        document.getElementById('authBtn').style.display = 'inline-block';
                    }}
                }}, 300000); // 5 min timeout
            }}

            function checkPopup() {{
                if (!authWindow || authWindow.closed) {{
                    clearInterval(pollTimer);
                    pollTimer = null;
                    document.getElementById('spinner').style.display = 'none';
                    document.getElementById('status').innerHTML =
                        '<span class="error">Authorization window closed. Please try again.</span>';
                    document.getElementById('authBtn').style.display = 'inline-block';
                    return;
                }}

                try {{
                    // Try to read the popup URL - this will throw cross-origin errors
                    // until it redirects to localhost (which is a different kind of error)
                    const popupUrl = authWindow.location.href;

                    // If we can read it and it starts with localhost, we caught the redirect
                    if (popupUrl && popupUrl.startsWith('http://localhost')) {{
                        clearInterval(pollTimer);
                        pollTimer = null;
                        authWindow.close();

                        // Extract code and state from the URL
                        const url = new URL(popupUrl);
                        const code = url.searchParams.get('code');
                        const state = url.searchParams.get('state');

                        if (code && state) {{
                            document.getElementById('status').textContent = 'Completing setup...';
                            exchangeCode(code, state);
                        }} else {{
                            document.getElementById('spinner').style.display = 'none';
                            document.getElementById('status').innerHTML =
                                '<span class="error">Authorization failed. No code received.</span>';
                            document.getElementById('authBtn').style.display = 'inline-block';
                        }}
                    }}
                }} catch (e) {{
                    // Expected: cross-origin error while on Zomato's domain. Keep polling.
                }}
            }}

            async function exchangeCode(code, state) {{
                try {{
                    const resp = await fetch(CALLBACK_URL + '?code=' + encodeURIComponent(code) + '&state=' + encodeURIComponent(state));
                    if (resp.ok) {{
                        document.getElementById('spinner').style.display = 'none';
                        document.getElementById('msg').textContent = '';
                        document.getElementById('status').innerHTML =
                            '<span class="success">Zomato Connected!</span><br><br>You can now order food through Omi. Go back to the app.';
                    }} else {{
                        const err = await resp.text();
                        throw new Error(err);
                    }}
                }} catch (e) {{
                    document.getElementById('spinner').style.display = 'none';
                    document.getElementById('status').innerHTML =
                        '<span class="error">Setup failed: ' + e.message + '</span>';
                    document.getElementById('authBtn').style.display = 'inline-block';
                }}
            }}
        </script>
    </body>
    </html>
    """
    )


@app.get("/auth/callback")
@app.get("/auth/zomato/callback")
async def auth_callback(code: str, state: str):
    """Exchange auth code for tokens. Called by the relay page or OAuthWebView after intercepting localhost redirect."""
    state_data = get_oauth_state(state)
    if not state_data:
        raise HTTPException(status_code=400, detail="Invalid or expired OAuth state")

    uid = state_data["uid"]

    tokens = await exchange_oauth_code(
        state_data["token_endpoint"],
        code,
        LOCALHOST_REDIRECT_URI,
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

    return JSONResponse({"status": "ok", "message": "Zomato connected successfully"})


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


@app.get("/.well-known/omi-tools.json")
async def omi_tools_manifest():
    """Omi Chat Tools Manifest endpoint."""
    return {
        "tools": [
            {
                "name": "search_restaurants",
                "description": "Search for restaurants nearby. Use this when the user wants to find places to eat, order food, or is looking for a specific cuisine or restaurant.",
                "endpoint": "/tools/search_restaurants",
                "method": "POST",
                "parameters": {
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Search query (e.g., restaurant name, cuisine type, dish)",
                        },
                        "location": {"type": "string", "description": "Location or area to search in"},
                    },
                    "required": ["query"],
                },
                "auth_required": True,
                "status_message": "Searching restaurants on Zomato...",
            },
            {
                "name": "get_restaurant_menu",
                "description": "Browse a restaurant's menu to see available items, prices, and ratings. Use this after the user has selected a restaurant.",
                "endpoint": "/tools/get_restaurant_menu",
                "method": "POST",
                "parameters": {
                    "properties": {
                        "restaurant_id": {"type": "string", "description": "The restaurant ID to fetch menu for"},
                    },
                    "required": ["restaurant_id"],
                },
                "auth_required": True,
                "status_message": "Loading menu...",
            },
            {
                "name": "add_to_cart",
                "description": "Add an item to the user's Zomato cart. Use this when the user wants to order a specific dish.",
                "endpoint": "/tools/add_to_cart",
                "method": "POST",
                "parameters": {
                    "properties": {
                        "item_id": {"type": "string", "description": "The menu item ID to add"},
                        "quantity": {"type": "integer", "description": "Number of items to add (default: 1)"},
                    },
                    "required": ["item_id"],
                },
                "auth_required": True,
                "status_message": "Adding to cart...",
            },
            {
                "name": "get_cart",
                "description": "View the current contents of the user's Zomato cart including items, quantities, and total price.",
                "endpoint": "/tools/get_cart",
                "method": "POST",
                "parameters": {"properties": {}, "required": []},
                "auth_required": True,
                "status_message": "Loading your cart...",
            },
            {
                "name": "place_order",
                "description": "Place a food order from the current cart. Use this when the user confirms they want to order.",
                "endpoint": "/tools/place_order",
                "method": "POST",
                "parameters": {
                    "properties": {
                        "delivery_address": {"type": "string", "description": "Delivery address for the order"},
                    },
                    "required": [],
                },
                "auth_required": True,
                "status_message": "Placing your order...",
            },
        ]
    }


@app.get("/tools")
async def list_tools():
    """Discover and return available Zomato MCP tools (dynamic from MCP server)."""
    try:
        tools = await discover_tools()
        return {"tools": tools}
    except Exception as e:
        logger.error(f"Tool discovery failed: {e}")
        return {"tools": [], "error": str(e)}
