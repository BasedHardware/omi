from typing import Optional

MCP_DEFAULT_APP_ID = "mcp-api"
MCP_DEFAULT_API_KEY_SCOPES = [
    "memories.read",
    "memories.write",
    "conversations.read",
    "action_items.read",
    "action_items.write",
    "goals.read",
    "chat.read",
    "screen_activity.read",
    "people.read",
    "people.rename",
]
MCP_OPT_IN_SCOPES = ["people.cleanup"]
MCP_SUPPORTED_SCOPES = MCP_DEFAULT_API_KEY_SCOPES + MCP_OPT_IN_SCOPES
# Backward-compatible export for existing callers. "Full access" historically
# meant the automatically granted MCP key capabilities; risky new scopes remain
# intentionally outside that set.
MCP_FULL_ACCESS_SCOPES = list(MCP_DEFAULT_API_KEY_SCOPES)
MCP_MEMORY_GRANT_SCOPES = ["memories.read", "memories.write"]
MCP_MEMORY_CONTROL_COLLECTION = "memory_control"
MCP_APP_KEY_MEMORY_GRANTS_DOC_ID = "app_key_memory_grants"


def normalize_mcp_scopes(scopes: Optional[list[str]]) -> list[str]:
    """Return the legacy/default grant plus explicitly requested risky scopes.

    MCP API keys historically receive the complete compatibility scope set.
    People cleanup is different: even though dismissal is reversible in storage,
    it removes a record from normal product reads and must therefore be opt-in.
    """

    requested = set(scopes or ())
    return sorted(set(MCP_DEFAULT_API_KEY_SCOPES).union(requested.intersection(MCP_OPT_IN_SCOPES)))
