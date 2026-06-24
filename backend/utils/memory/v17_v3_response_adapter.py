"""Backward-compatible shim — implementation lives in ``utils.memory.v3_response_adapter`` (WS-G8b)."""

from utils.memory.v3_response_adapter import (
    adapt_v17_v3_memory_response,
    V17V3CompatibilityReadPath,
    V17V3MemoryReadServiceResult,
    V17V3MemoryResponse,
    V17V3ResponseShapeError,
    V3MemoryResponse,
    V3ResponseShapeError,
    _ALLOWED_HEADER_NAMES,
    _allowed_headers,
    _assert_memorydb_body_shape,
    _BODY_ALLOWED_READ_PATHS,
    _body_for_success,
    _FORBIDDEN_BODY_FIELDS,
    _NO_DATA_READ_PATHS,
)

__all__ = [
    "adapt_v17_v3_memory_response",
    "V17V3CompatibilityReadPath",
    "V17V3MemoryReadServiceResult",
    "V17V3MemoryResponse",
    "V17V3ResponseShapeError",
    "V3MemoryResponse",
    "V3ResponseShapeError",
    "_ALLOWED_HEADER_NAMES",
    "_allowed_headers",
    "_assert_memorydb_body_shape",
    "_BODY_ALLOWED_READ_PATHS",
    "_body_for_success",
    "_FORBIDDEN_BODY_FIELDS",
    "_NO_DATA_READ_PATHS",
]
