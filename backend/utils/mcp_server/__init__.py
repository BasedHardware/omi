"""Hosted MCP server internals: transport, versions, registry, and tool handlers.

``routers/mcp_sse.py`` stays a thin FastAPI surface; protocol dispatch, tool
execution, auth, OAuth, and metadata live here so the canonical ``/v1/mcp`` and
legacy ``/v1/mcp/sse`` endpoints share one implementation.
"""
