"""Canonical/legacy MCP resource URL equivalence.

Pure leaf shared by ``database.mcp_oauth`` and ``database.mcp_token_cache``:
the hosted MCP server answers on the canonical ``/v1/mcp`` path and keeps
``/v1/mcp/sse`` as a permanent compatibility alias, so both forms identify the
same protected resource on the same host while cross-host audiences stay
distinct.
"""

from typing import Optional


def canonical_mcp_resource_url(resource: str) -> str:
    """Map a legacy ``/v1/mcp/sse`` resource URL onto the canonical ``/v1/mcp``."""
    suffix = "/sse"
    return resource[: -len(suffix)] if resource.endswith(suffix) else resource


def legacy_mcp_resource_url(resource: str) -> str:
    return canonical_mcp_resource_url(resource) + "/sse"


def mcp_resource_urls_match(left: Optional[str], right: Optional[str]) -> bool:
    """Canonical-form equality: legacy ``/sse`` and canonical audiences are the
    same resource for issuance and validation, on either endpoint path."""
    if left is None or right is None:
        return left is right
    return canonical_mcp_resource_url(left) == canonical_mcp_resource_url(right)
