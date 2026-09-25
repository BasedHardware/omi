"""OAuth discovery metadata documents for the hosted MCP server."""

import os
from typing import Any, Dict

import database.mcp_oauth as mcp_oauth_db
from utils.mcp_scopes import MCP_FULL_ACCESS_SCOPES

MCP_AUTHORIZATION_SERVER_URL = os.getenv("MCP_AUTHORIZATION_SERVER_URL", "https://api.omi.me")
MCP_AUTHORIZATION_ENDPOINT = f"{MCP_AUTHORIZATION_SERVER_URL}/authorize"
MCP_TOKEN_ENDPOINT = f"{MCP_AUTHORIZATION_SERVER_URL}/token"
# Protected-resource metadata is per path (RFC 9728 §3.3: ``resource`` equals
# the described URL): challenges on ``/v1/mcp`` advertise the canonical
# document, challenges on ``/v1/mcp/sse`` the legacy one.
MCP_PROTECTED_RESOURCE_METADATA_URL = f"{MCP_AUTHORIZATION_SERVER_URL}/.well-known/oauth-protected-resource/v1/mcp"
MCP_LEGACY_PROTECTED_RESOURCE_METADATA_URL = (
    f"{MCP_AUTHORIZATION_SERVER_URL}/.well-known/oauth-protected-resource/v1/mcp/sse"
)
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


def protected_resource_metadata_url(path_kind: str) -> str:
    """The well-known document URL a challenge on ``path_kind`` must advertise."""
    if path_kind == "legacy_sse":
        return MCP_LEGACY_PROTECTED_RESOURCE_METADATA_URL
    return MCP_PROTECTED_RESOURCE_METADATA_URL


def protected_resource_document(resource: str) -> Dict[str, Any]:
    """RFC 9728 document for one resource path: ``resource`` equals the URL
    the document describes — canonical for ``/v1/mcp``, legacy for
    ``/v1/mcp/sse`` (and the unqualified root document, for now)."""
    return {
        "resource": resource,
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
        # RFC 9207: every authorization response (code and error redirects)
        # carries ``iss`` — advertise it so clients enforce the binding.
        "authorization_response_iss_parameter_supported": True,
        "client_id_metadata_document_supported": True,
    }
