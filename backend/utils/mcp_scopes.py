from typing import Optional

from config.mcp_scopes import MCP_FULL_ACCESS_SCOPES  # noqa: F401 — re-export

MCP_DEFAULT_APP_ID = "mcp-api"
MCP_MEMORY_GRANT_SCOPES = ["memories.read", "memories.write"]
MCP_MEMORY_CONTROL_COLLECTION = "memory_control"
MCP_APP_KEY_MEMORY_GRANTS_DOC_ID = "app_key_memory_grants"


def normalize_mcp_scopes(scopes: Optional[list[str]]) -> list[str]:
    return sorted(MCP_FULL_ACCESS_SCOPES)
