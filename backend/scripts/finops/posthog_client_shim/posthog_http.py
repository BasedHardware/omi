"""Container shim for posthog_http: PostHog MCP over streamable HTTP.

Replaces the skill-local client in Cloud Run (no ~/.claude there). Same session
contract as the original: posthog_mcp_session() yields a session with call_tool.
The API key arrives via MCP_POSTHOG_API_KEY (mounted secret injected by posthog_dau.py).
"""

from __future__ import annotations

import os

POSTHOG_MCP_URL = "https://mcp.posthog.com/mcp"


def _api_key() -> str:
    value = (os.environ.get("MCP_POSTHOG_API_KEY") or "").strip()
    if not value:
        raise RuntimeError("MCP_POSTHOG_API_KEY missing from the environment")
    return value


async def posthog_mcp_session():
    from mcp.client.streamable_http import streamablehttp_client
    from mcp import ClientSession

    headers = {"Authorization": "Bearer " + _api_key()}
    cm = streamablehttp_client(POSTHOG_MCP_URL, headers=headers)

    read, write, _ = await cm.__aenter__()
    session = ClientSession(read, write)
    await session.__aenter__()
    await session.initialize()
    return session
