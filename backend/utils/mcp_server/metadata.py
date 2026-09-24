"""OAuth discovery metadata documents for the hosted MCP server."""

import os
from typing import Any, Dict

import database.mcp_oauth as mcp_oauth_db
from utils.mcp_scopes import MCP_FULL_ACCESS_SCOPES

MCP_AUTHORIZATION_SERVER_URL = os.getenv("MCP_AUTHORIZATION_SERVER_URL", "https://api.omi.me")
MCP_AUTHORIZATION_ENDPOINT = f"{MCP_AUTHORIZATION_SERVER_URL}/authorize"
MCP_TOKEN_ENDPOINT = f"{MCP_AUTHORIZATION_SERVER_URL}/token"
# Canonical protected-resource metadata URL advertised in challenges. The
# legacy ``/v1/mcp/sse`` document path keeps serving the same document.
MCP_PROTECTED_RESOURCE_METADATA_URL = f"{MCP_AUTHORIZATION_SERVER_URL}/.well-known/oauth-protected-resource/v1/mcp"
MCP_SCOPES_SUPPORTED = list(MCP_FULL_ACCESS_SCOPES)

OPENAI_APPS_CHALLENGE_TOKEN = "ZsVB_wpc4R35_tHloCZCokY6H2fBkKyBJrz-4MtXjYE"

SCOPE_PERMISSION_TEXT = {
    "memories.read": "Read your Omi memories",
    "memories.write": "Create, edit, and delete your Omi memories",
    "conversations.read": "Search and read your Omi conversations",
    "action_items.read": "Read your Omi action items",
    "action_items.write": "Create, update, and delete your Omi action items",
    "goals.read": "Read your Omi goals",
    "chat.read": "Read your Omi chat history",
    "screen_activity.read": "Read your Omi screen activity",
    "people.read": "Read people saved in your Omi account",
}


def protected_resource_document() -> Dict[str, Any]:
    return {
        "resource": mcp_oauth_db.MCP_RESOURCE_URL,
        "authorization_servers": [MCP_AUTHORIZATION_SERVER_URL],
        "scopes_supported": MCP_SCOPES_SUPPORTED,
        "bearer_methods_supported": ["header"],
        "resource_documentation": "https://docs.omi.me/doc/developer/mcp/setup",
    }


def authorization_server_document() -> Dict[str, Any]:
    return {
        "issuer": MCP_AUTHORIZATION_SERVER_URL,
        "authorization_endpoint": MCP_AUTHORIZATION_ENDPOINT,
        "token_endpoint": MCP_TOKEN_ENDPOINT,
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code", "refresh_token"],
        "code_challenge_methods_supported": ["S256"],
        "token_endpoint_auth_methods_supported": mcp_oauth_db.token_endpoint_auth_methods_supported(),
        "scopes_supported": MCP_SCOPES_SUPPORTED,
    }
