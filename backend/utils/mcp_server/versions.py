"""MCP protocol revision constants and version negotiation helpers.

Supported revisions, newest first: the 2026 stateless revision plus every
handshake revision released clients still negotiate.
"""

from typing import Any, Dict, Optional, Tuple

JSONRPC_VERSION = "2.0"

META_PROTOCOL_VERSION = "io.modelcontextprotocol/protocolVersion"
META_CLIENT_INFO = "io.modelcontextprotocol/clientInfo"
META_CLIENT_CAPABILITIES = "io.modelcontextprotocol/clientCapabilities"
META_SERVER_INFO = "io.modelcontextprotocol/serverInfo"

PROTOCOL_VERSION_2026 = "2026-07-28"
NEGOTIATED_FALLBACK_VERSION = "2025-11-25"
# Old clients that never declare a revision (no header, no ``_meta``) keep the
# behavior they were written against.
DEFAULT_PROTOCOL_VERSION = "2025-03-26"

SUPPORTED_PROTOCOL_VERSIONS: Tuple[str, ...] = (
    "2026-07-28",
    "2025-11-25",
    "2025-06-18",
    "2025-03-26",
    "2024-11-05",
)
# Revisions that go through ``initialize`` negotiation. 2026-07-28 is stateless:
# it is declared per request via ``_meta``/header, never negotiated.
HANDSHAKE_PROTOCOL_VERSIONS: Tuple[str, ...] = SUPPORTED_PROTOCOL_VERSIONS[1:]
# Revisions whose transport still allows JSON-RPC batch (array) requests.
BATCH_PROTOCOL_VERSIONS = frozenset({"2025-03-26", "2024-11-05"})

SERVER_INFO = {"name": "omi-mcp-server", "version": "1.0.0"}
MCP_CAPABILITIES = {"tools": {}}

TOOLS_LIST_TTL_MS = 3_600_000
TOOLS_LIST_CACHE_SCOPE = "private"

MCP_PROTOCOL_VERSION_HEADER = "mcp-protocol-version"
MCP_METHOD_HEADER = "mcp-method"
MCP_NAME_HEADER = "mcp-name"


class JsonRpcProtocolError(Exception):
    """A message-level protocol failure carried as a JSON-RPC error."""

    def __init__(self, code: int, message: str, data: Optional[Dict[str, Any]] = None):
        self.code = code
        self.message = message
        self.data = data
        super().__init__(message)


def is_supported_version(version: Optional[str]) -> bool:
    return version in SUPPORTED_PROTOCOL_VERSIONS


def is_batch_era_version(version: Optional[str]) -> bool:
    return version in BATCH_PROTOCOL_VERSIONS


def negotiate_protocol_version(requested: Any) -> str:
    """``initialize`` negotiation: echo a supported handshake revision else fall back."""
    if isinstance(requested, str) and requested in HANDSHAKE_PROTOCOL_VERSIONS:
        return requested
    return NEGOTIATED_FALLBACK_VERSION


def declared_protocol_version(message: Dict[str, Any]) -> Optional[str]:
    """Per-message stateless revision from ``params._meta`` or message ``_meta``."""
    params = message.get("params")
    if isinstance(params, dict):
        meta = params.get("_meta")
        if isinstance(meta, dict):
            value = meta.get(META_PROTOCOL_VERSION)
            if isinstance(value, str) and value:
                return value
    meta = message.get("_meta")
    if isinstance(meta, dict):
        value = meta.get(META_PROTOCOL_VERSION)
        if isinstance(value, str) and value:
            return value
    return None


def declared_client_capabilities(message: Dict[str, Any]) -> Any:
    """The ``_meta`` clientCapabilities value a stateless message carries, if any."""
    params = message.get("params")
    if isinstance(params, dict):
        meta = params.get("_meta")
        if isinstance(meta, dict) and META_CLIENT_CAPABILITIES in meta:
            return meta[META_CLIENT_CAPABILITIES]
    meta = message.get("_meta")
    if isinstance(meta, dict):
        return meta.get(META_CLIENT_CAPABILITIES)
    return None


def client_info_name(message: Dict[str, Any]) -> Optional[str]:
    """Best-effort client identity for analytics, from ``clientInfo`` or ``_meta``."""
    params = message.get("params")
    if isinstance(params, dict):
        info = params.get("clientInfo")
        if isinstance(info, dict) and isinstance(info.get("name"), str):
            return info["name"]
        meta = params.get("_meta")
        if isinstance(meta, dict):
            info = meta.get(META_CLIENT_INFO)
            if isinstance(info, dict) and isinstance(info.get("name"), str):
                return info["name"]
    meta = message.get("_meta")
    if isinstance(meta, dict):
        info = meta.get(META_CLIENT_INFO)
        if isinstance(info, dict) and isinstance(info.get("name"), str):
            return info["name"]
    return None


def unsupported_version_error(requested: Optional[str] = None) -> JsonRpcProtocolError:
    """``UnsupportedProtocolVersionError`` (-32022) per the 2026-07-28 schema.

    ``error.data`` is exactly ``{supported, requested}`` — the client picks a
    mutually supported version from ``supported`` and retries.
    """
    return JsonRpcProtocolError(
        -32022,
        "Unsupported MCP protocol version",
        data={
            "supported": list(SUPPORTED_PROTOCOL_VERSIONS),
            "requested": requested if isinstance(requested, str) else None,
        },
    )


def resolve_effective_version(message: Dict[str, Any], header_version: Optional[str]) -> str:
    """Resolve the effective revision for one message.

    A stateless ``_meta`` declaration wins over the header; the two must agree
    when both are present. Undeclared messages fall back to the header, then to
    the legacy default. Unsupported explicit versions are rejected.
    """
    if message.get("method") == "initialize":
        # The handshake negotiates from params.protocolVersion; the header
        # belongs to post-initialize requests and must not block it.
        header_version = None
    declared = declared_protocol_version(message)
    if header_version and declared and declared != header_version:
        raise JsonRpcProtocolError(
            -32020,
            f"Protocol version mismatch: header declares {header_version} " f"but the message declares {declared}.",
        )
    if declared:
        if not is_supported_version(declared):
            raise unsupported_version_error(declared)
        return declared
    if header_version:
        if not is_supported_version(header_version):
            raise unsupported_version_error(header_version)
        return header_version
    return DEFAULT_PROTOCOL_VERSION
