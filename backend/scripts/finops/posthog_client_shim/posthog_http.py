"""Container shim for posthog_http: PostHog MCP over streamable HTTP.

Replaces the skill-local client in Cloud Run (no ~/.claude there). Same session
contract as the original: posthog_mcp_session() yields a session with call_tool.
The API key arrives via MCP_POSTHOG_API_KEY (mounted secret injected by posthog_dau.py).
"""

from __future__ import annotations

import inspect
import os

POSTHOG_MCP_URL = "https://mcp.posthog.com/mcp"


def _api_key() -> str:
    value = (os.environ.get("MCP_POSTHOG_API_KEY") or "").strip()
    if not value:
        raise RuntimeError("MCP_POSTHOG_API_KEY missing from the environment")
    return value


def _no_redirect_client(*args, **kwargs):
    """httpx client that returns 3xx instead of following it with the API key."""
    import httpx

    kwargs["follow_redirects"] = False
    return httpx.AsyncClient(*args, **kwargs)


async def posthog_mcp_session():
    from mcp.client.streamable_http import streamablehttp_client
    from mcp import ClientSession

    headers = {"Authorization": "Bearer " + _api_key()}
    if "httpx_client_factory" not in inspect.signature(streamablehttp_client).parameters:
        raise RuntimeError("PostHog MCP client cannot refuse redirects")
    cm = streamablehttp_client(POSTHOG_MCP_URL, headers=headers, httpx_client_factory=_no_redirect_client)

    read, write, _ = await cm.__aenter__()
    session = ClientSession(read, write)
    await session.__aenter__()
    await session.initialize()
    return session
