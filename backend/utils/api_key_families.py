"""Recognize Omi API key families so a key used on the wrong endpoint gets an actionable 401.

Each key family authenticates exactly one endpoint family: `omi_mcp_` keys only the MCP
endpoints, `omi_dev_` keys only the Developer API, and every other route requires a Firebase
ID token issued by the app. Presenting the wrong one otherwise fails as a generic
"Invalid authorization token" / "Invalid API Key", which reads as a broken key or a dead
endpoint rather than a key/endpoint mismatch.
"""

from typing import Optional

MCP_KEY_PREFIX = "omi_mcp_"
DEV_KEY_PREFIX = "omi_dev_"

FIREBASE_FAMILY = "firebase"
MCP_FAMILY = "mcp"
DEV_FAMILY = "dev"

_FAMILY_BY_PREFIX = {
    MCP_KEY_PREFIX: MCP_FAMILY,
    DEV_KEY_PREFIX: DEV_FAMILY,
}

_KEY_USAGE = {
    MCP_FAMILY: (
        "MCP API keys (omi_mcp_...) only authenticate the MCP endpoints under /v1/mcp/ "
        "(for example GET /v1/mcp/memories, GET /v1/mcp/conversations) and the MCP server at /v1/mcp/sse"
    ),
    DEV_FAMILY: (
        "Developer API keys (omi_dev_...) only authenticate the Developer API under /v1/dev/ "
        "(for example GET /v1/dev/user/memories)"
    ),
}

_ENDPOINT_EXPECTATION = {
    FIREBASE_FAMILY: "This endpoint requires a Firebase ID token from a signed-in Omi app",
    MCP_FAMILY: "This endpoint requires an MCP API key (Settings -> Developer -> MCP -> Create Key)",
    DEV_FAMILY: "This endpoint requires a Developer API key (Settings -> Developer -> Create Key)",
}


def api_key_family(token: Optional[str]) -> str:
    """Family of the presented credential, inferred from its prefix."""
    for prefix, family in _FAMILY_BY_PREFIX.items():
        if token and token.startswith(prefix):
            return family
    return FIREBASE_FAMILY


def wrong_key_family_detail(token: Optional[str], expected_family: str) -> Optional[str]:
    """401 detail explaining the mismatch, or None when the key belongs to `expected_family`."""
    presented = api_key_family(token)
    if presented == expected_family or presented == FIREBASE_FAMILY:
        return None
    return f"{_KEY_USAGE[presented]}. {_ENDPOINT_EXPECTATION[expected_family]}."
