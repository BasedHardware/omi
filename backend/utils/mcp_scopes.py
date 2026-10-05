from typing import Optional

from config.mcp_scopes import (
    MCP_DEFAULT_API_KEY_SCOPES as MCP_DEFAULT_API_KEY_SCOPES,
    MCP_FULL_ACCESS_SCOPES as MCP_FULL_ACCESS_SCOPES,
    MCP_OPT_IN_SCOPES as MCP_OPT_IN_SCOPES,
    MCP_SUPPORTED_SCOPES as MCP_SUPPORTED_SCOPES,
)

MCP_DEFAULT_APP_ID = "mcp-api"
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
