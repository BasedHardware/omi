from typing import Iterable, Optional, cast

from config.mcp_scopes import (
    MCP_DEFAULT_API_KEY_SCOPES as MCP_DEFAULT_API_KEY_SCOPES,
    MCP_FULL_ACCESS_SCOPES as MCP_FULL_ACCESS_SCOPES,
    MCP_OPT_IN_SCOPES as MCP_OPT_IN_SCOPES,
    MCP_READ_ONLY_API_KEY_SCOPES as MCP_READ_ONLY_API_KEY_SCOPES,
    MCP_SUPPORTED_SCOPES as MCP_SUPPORTED_SCOPES,
)

MCP_DEFAULT_APP_ID = "mcp-api"
MCP_MEMORY_GRANT_SCOPES = ["memories.read", "memories.write"]
MCP_MEMORY_CONTROL_COLLECTION = "memory_control"
MCP_APP_KEY_MEMORY_GRANTS_DOC_ID = "app_key_memory_grants"


def validate_mcp_scopes(scopes: object) -> bool:
    """Return True iff ``scopes`` is a non-empty list of supported MCP scopes."""
    if not isinstance(scopes, list) or not scopes:
        return False
    allowed = set(MCP_SUPPORTED_SCOPES)
    items = cast(list[object], scopes)
    return all(isinstance(scope, str) and scope in allowed for scope in items)


def normalize_mcp_scopes(
    scopes: Optional[list[str]],
    *,
    explicit_scopes: bool = False,
) -> list[str]:
    """Normalize MCP API key scopes while preserving explicitly narrowed grants.

    When ``explicit_scopes`` is False (legacy keys and omitted-scopes creation),
    keys receive the full compatibility default scope set plus any explicitly
    requested opt-in scopes. When ``explicit_scopes`` is True, only the
    caller's validated scope set is retained without widening to defaults.
    """
    raw_items: Iterable[object] = cast(Iterable[object], scopes) if isinstance(scopes, (list, tuple, set)) else ()
    if explicit_scopes:
        allowed = set(MCP_SUPPORTED_SCOPES)
        return sorted({scope for scope in raw_items if isinstance(scope, str) and scope in allowed})

    requested = {scope for scope in raw_items if isinstance(scope, str)}
    return sorted(set(MCP_DEFAULT_API_KEY_SCOPES).union(requested.intersection(MCP_OPT_IN_SCOPES)))
