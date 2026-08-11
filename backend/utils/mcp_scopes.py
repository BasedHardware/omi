from typing import Any, Optional

MCP_DEFAULT_APP_ID = "mcp-api"
MCP_FULL_ACCESS_SCOPES = [
    "memories.read",
    "memories.write",
    "conversations.read",
    "action_items.read",
    "action_items.write",
    "goals.read",
    "chat.read",
    "screen_activity.read",
    "people.read",
]
MCP_MEMORY_GRANT_SCOPES = ["memories.read", "memories.write"]
MCP_MEMORY_CONTROL_COLLECTION = "memory_control"
MCP_APP_KEY_MEMORY_GRANTS_DOC_ID = "app_key_memory_grants"


def normalize_mcp_scopes(scopes: Optional[list[Any]]) -> list[str]:
    """Resolve the scope set a key actually carries.

    A recorded list of known scopes is authoritative: the key authorizes exactly
    those tools and nothing else. Absent or unreadable scope state predates the
    per-key scope contract, so it resolves to full access — an already-issued key
    must keep working without being regenerated.
    """
    if not isinstance(scopes, list):
        return sorted(MCP_FULL_ACCESS_SCOPES)
    allowed = set(MCP_FULL_ACCESS_SCOPES)
    resolved = sorted({scope for scope in scopes if isinstance(scope, str) and scope in allowed})
    return resolved or sorted(MCP_FULL_ACCESS_SCOPES)
