"""Pure/local `/v3` MemoryDB response-shape adapter proof.

This adapter converts a caller-supplied V17 `/v3` read-service envelope plus
caller-supplied MemoryDB-compatible items into the legacy-compatible response
body and additive diagnostics headers. It performs no I/O, app startup, route
wiring, provider calls, database/cloud imports, or mutation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from utils.memory.v17_v3_compatibility import V17V3CompatibilityReadPath
from utils.memory.v17_v3_memory_read_service import V17V3MemoryReadServiceResult

_ALLOWED_HEADER_NAMES = {
    'X-Omi-Memory-Read-Source',
    'X-Omi-Memory-Read-Decision',
    'X-Omi-Memory-Next-Cursor',
    'Link',
}

_FORBIDDEN_BODY_FIELDS = {
    'source',
    'policy',
    'cursor',
    'read_source',
    'read_decision',
    'v17_source',
    'v17_policy',
    'source_policy',
    'archive_default_available',
    'stale_short_term_default_visible',
}

_BODY_ALLOWED_READ_PATHS = {V17V3CompatibilityReadPath.V17_COMPATIBILITY_PROJECTION}
_NO_DATA_READ_PATHS = {V17V3CompatibilityReadPath.FAIL_CLOSED, V17V3CompatibilityReadPath.DENY}


@dataclass(frozen=True)
class V17V3MemoryResponse:
    http_status: int
    body: list[Any] | None
    headers: dict[str, str]
    legacy_fallback_marker_present: bool = False
    archive_default_available: bool = False
    stale_short_term_default_visible: bool = False
    proof_fields: dict[str, bool] = field(default_factory=dict)


class V17V3ResponseShapeError(ValueError):
    def __init__(self, reason: str, detail: str):
        super().__init__(detail)
        self.reason = reason
        self.detail = detail


def _allowed_headers(headers: Mapping[str, str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for name in _ALLOWED_HEADER_NAMES:
        value = headers.get(name)
        if value is None:
            continue
        if name == 'Link' and 'rel="next"' not in value and 'rel=next' not in value:
            continue
        result[name] = value
    return result


def _assert_memorydb_body_shape(items: list[Any]) -> None:
    for index, item in enumerate(items):
        if not isinstance(item, Mapping):
            continue
        leaked_fields = _FORBIDDEN_BODY_FIELDS.intersection(item)
        if leaked_fields:
            raise V17V3ResponseShapeError(
                'v17_only_body_field_forbidden',
                f'V17-only fields must not be exposed in List[MemoryDB] body at index {index}: '
                f'{sorted(leaked_fields)}',
            )


def _body_for_success(envelope: V17V3MemoryReadServiceResult, memorydb_items: list[Any]) -> list[Any]:
    body = [] if envelope.body == [] else memorydb_items
    _assert_memorydb_body_shape(body)
    return body


def adapt_v17_v3_memory_response(
    envelope: V17V3MemoryReadServiceResult,
    *,
    memorydb_items: list[Any],
) -> V17V3MemoryResponse:
    """Adapt a local read envelope into a legacy-compatible `/v3` response.

    The JSON body remains exactly a `List[MemoryDB]` (or no body for denial /
    fail-closed states). V17 diagnostics are exposed only through the allowed
    additive headers.
    """

    headers = _allowed_headers(envelope.headers)
    proof_fields = {
        'archive_default_available': False,
        'stale_short_term_default_visible': False,
    }

    if envelope.read_path in _NO_DATA_READ_PATHS or envelope.http_status >= 400:
        return V17V3MemoryResponse(
            http_status=envelope.http_status,
            body=None,
            headers=headers,
            proof_fields=proof_fields,
        )

    if envelope.read_path not in _BODY_ALLOWED_READ_PATHS:
        return V17V3MemoryResponse(
            http_status=envelope.http_status,
            body=None,
            headers=headers,
            proof_fields=proof_fields,
        )

    body = _body_for_success(envelope, memorydb_items)
    return V17V3MemoryResponse(
        http_status=envelope.http_status,
        body=body,
        headers=headers,
        proof_fields=proof_fields,
    )
