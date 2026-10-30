"""Tool-result payload shaping shared by the MCP transport and handlers.

Leaf module: imports only ``versions`` constants so tool handlers can measure
the exact serialized size of what the transport will emit without importing
the transport itself.
"""

import json
from datetime import datetime
from typing import Any, Dict

from utils.mcp_server.versions import JSONRPC_VERSION, META_SERVER_INFO, PROTOCOL_VERSION_2026, SERVER_INFO


def _json_default(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def json_safe(value: Any) -> Any:
    return json.loads(json.dumps(value, default=_json_default))


def compact_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def tool_result_payload(result: Dict[str, Any]) -> Dict[str, Any]:
    structured = json_safe(result)
    return {
        "content": [{"type": "text", "text": compact_json(structured)}],
        "structuredContent": structured,
    }


def tool_error_payload(code: str, message: str) -> Dict[str, Any]:
    structured = {"error": {"code": code, "message": message}}
    return {
        "isError": True,
        "content": [{"type": "text", "text": compact_json(structured)}],
        "structuredContent": structured,
    }


def complete_result(result: Dict[str, Any], effective_version: str) -> Dict[str, Any]:
    """2026-07-28 results carry resultType and serverInfo ``_meta``."""
    if effective_version != PROTOCOL_VERSION_2026:
        return result
    decorated = dict(result)
    decorated["resultType"] = "complete"
    meta = dict(decorated.get("_meta") or {})
    meta[META_SERVER_INFO] = dict(SERVER_INFO)
    decorated["_meta"] = meta
    return decorated


def tool_response_serialized_chars(result: Dict[str, Any]) -> int:
    """Largest serialized size a tool response can take on the wire.

    Measures the SSE frame variant — ``json.dumps`` defaults (``ensure_ascii``
    escaping and spaced separators) plus ``data:`` framing — with the
    2026-07-28 ``complete_result`` decoration and a small ``id``. The plain
    ``JSONResponse`` body is strictly smaller for the same result, so this is
    an upper bound for both transports. A client echoing an oversized ``id``
    inflates only its own envelope.
    """
    response = {
        "jsonrpc": JSONRPC_VERSION,
        "id": 0,
        "result": complete_result(tool_result_payload(result), PROTOCOL_VERSION_2026),
    }
    return len(f"event: message\ndata: {json.dumps(response, default=str)}\n\n")
