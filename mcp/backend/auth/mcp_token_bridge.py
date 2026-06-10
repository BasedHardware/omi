"""
backend/auth/mcp_token_bridge.py - FIXED for langchain-mcp-adapters 0.1.0

Per-user MCP client cache — one client per user_id, reused across requests.
Rebuilds only when token changes (Google auto-refresh) or explicit invalidation.

API CHANGE in langchain-mcp-adapters 0.1.0:
- MultiServerMCPClient is NOT a context manager anymore
- Use `async with client.session(server_name) as session:` instead
"""

from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from typing import Dict, List, Optional, Tuple

from auth.google_oauth import get_valid_google_token
from auth.github_oauth import get_github_token

logger = logging.getLogger(__name__)

GOOGLE_MCP_URL = os.getenv("MCP_SERVER_URL", "http://localhost:8001/mcp").rstrip("/")
GITHUB_MCP_URL = "https://api.githubcopilot.com/mcp"

# user_id → last token used to build the client
_google_token_cache: Dict[str, str] = {}
_github_token_cache: Dict[str, str] = {}

# user_id → MultiServerMCPClient instance (just configured, not entered)
_google_clients: Dict[str, object] = {}
_github_clients: Dict[str, object] = {}


def _build_google_client(token: str):
    from langchain_mcp_adapters.client import MultiServerMCPClient
    return MultiServerMCPClient({
        "google_workspace": {
            "transport": "streamable_http",
            "url": GOOGLE_MCP_URL,
            "headers": {"Authorization": f"Bearer {token}"},
            "timeout": 120,
        }
    })


def _build_github_client(token: str):
    from langchain_mcp_adapters.client import MultiServerMCPClient
    return MultiServerMCPClient({
        "github": {
            "transport": "streamable_http",
            "url": GITHUB_MCP_URL,
            "headers": {"Authorization": f"Bearer {token}"},
            "timeout": 60,
        }
    })


# ── Google ────────────────────────────────────────────────────────────────────

@asynccontextmanager
async def get_google_workspace_session(user_id: str):
    """
    Async context manager that yields (tools_list, error_string).

    FIXED for langchain-mcp-adapters 0.1.0:
    Uses `async with client.session(server_name) as session:` instead of
    `async with client as session:`.
    """
    token = await get_valid_google_token(user_id)
    if not token:
        yield [], "Google account not connected. Please connect in Settings."
        return

    # Rebuild client only when token changes (e.g. after OAuth refresh)
    if _google_token_cache.get(user_id) != token or user_id not in _google_clients:
        logger.info(f"Building new Google MCP client for user {user_id}")
        _google_clients[user_id] = _build_google_client(token)
        _google_token_cache[user_id] = token

    client = _google_clients[user_id]

    # FIXED: Use client.session() context manager (new API in 0.1.0)
    try:
        from langchain_mcp_adapters.tools import load_mcp_tools
        
        async with client.session("google_workspace") as session:
            tools = await load_mcp_tools(session)
            logger.info(f"Google MCP session opened for {user_id}: "
                        f"{len(tools)} tools available")
            yield tools, None
    except Exception as exc:
        logger.error(f"Google MCP session error for {user_id}: {exc}")
        yield [], str(exc)


@asynccontextmanager
async def get_github_session(user_id: str):
    """
    Async context manager that yields (tools_list, error_string) for GitHub.
    """
    token = await get_github_token(user_id)
    if not token:
        yield [], "GitHub account not connected. Please connect in Settings → Integrations."
        return

    if _github_token_cache.get(user_id) != token or user_id not in _github_clients:
        logger.info(f"Building new GitHub MCP client for user {user_id}")
        _github_clients[user_id] = _build_github_client(token)
        _github_token_cache[user_id] = token

    client = _github_clients[user_id]

    # FIXED: Use client.session() context manager
    try:
        from langchain_mcp_adapters.tools import load_mcp_tools
        
        async with client.session("github") as session:
            tools = await load_mcp_tools(session)
            logger.info(f"GitHub MCP session opened for {user_id}: "
                        f"{len(tools)} tools available")
            yield tools, None
    except Exception as exc:
        logger.error(f"GitHub MCP session error for {user_id}: {exc}")
        yield [], str(exc)


# ── Legacy wrappers — kept so nothing else breaks ────────────────────────────

async def get_google_workspace_client_for_user(user_id: str):
    """Legacy: returns raw (unentered) client. Use get_google_workspace_session() instead."""
    token = await get_valid_google_token(user_id)
    if not token:
        return None
    if _google_token_cache.get(user_id) != token or user_id not in _google_clients:
        logger.info(f"Building new Google MCP client for user {user_id}")
        _google_clients[user_id] = _build_google_client(token)
        _google_token_cache[user_id] = token
    return _google_clients[user_id]


async def get_github_client_for_user(user_id: str):
    """Legacy: returns raw (unentered) client. Use get_github_session() instead."""
    token = await get_github_token(user_id)
    if not token:
        return None
    if _github_token_cache.get(user_id) != token or user_id not in _github_clients:
        logger.info(f"Building new GitHub MCP client for user {user_id}")
        _github_clients[user_id] = _build_github_client(token)
        _github_token_cache[user_id] = token
    return _github_clients[user_id]


# ── Invalidation ──────────────────────────────────────────────────────────────

def invalidate_google_client(user_id: str) -> None:
    """Call when Google returns 401 — forces token refresh + client rebuild."""
    _google_clients.pop(user_id, None)
    _google_token_cache.pop(user_id, None)
    logger.info(f"Invalidated Google MCP client for user {user_id}")


def invalidate_github_client(user_id: str) -> None:
    """Call when GitHub returns 401 — forces rebuild on next request."""
    _github_clients.pop(user_id, None)
    _github_token_cache.pop(user_id, None)
    logger.info(f"Invalidated GitHub MCP client for user {user_id}")


# Back-compat wrapper used by some older call sites
async def get_github_client_for_user_with_fallback(user_id: str):
    token = await get_github_token(user_id)
    if not token:
        return None, None
    client = await get_github_client_for_user(user_id)
    return client, token