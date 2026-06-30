from typing import Optional

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
MCP_API_KEY_AUTH_CONTEXT_VERSION = 2


def normalize_mcp_scopes(scopes: Optional[list[str]]) -> list[str]:
    if not isinstance(scopes, list):
        scopes = []
    return sorted(set(MCP_FULL_ACCESS_SCOPES).union(scopes))
