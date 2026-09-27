"""Canonical/legacy MCP resource URL equivalence.

Pure leaf shared by ``database.mcp_oauth`` and ``database.mcp_token_cache``:
the hosted MCP server answers on the canonical ``/v1/mcp`` path and keeps
``/v1/mcp/sse`` as a permanent compatibility alias, so both forms identify the
same protected resource on the same host while cross-host audiences stay
distinct. A single trailing slash on that path (``/v1/mcp/``) is the same
resource; grant ids hash the legacy-equivalent form, and resources that do
not already end in ``/`` are left unchanged.
"""

from typing import Optional


def canonical_mcp_resource_url(resource: str) -> str:
    """Map ``/v1/mcp/sse`` and a single trailing slash onto canonical ``/v1/mcp``.

    Strip one trailing ``/`` before the ``/sse`` suffix. ``/v1/mcp`` and
    ``/v1/mcp/sse`` do not end in ``/``, so their canonical form — and the
    legacy URL hashed into existing grant ids — stays the same.
    """
    if len(resource) > 1 and resource.endswith("/"):
        resource = resource[:-1]
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
