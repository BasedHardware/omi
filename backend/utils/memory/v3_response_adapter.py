"""Canonical module for ``utils.memory.v3_response_adapter`` (WS-G8b).

Neutral ``v3_response_adapter`` is the source of truth. Legacy ``v3_response_adapter`` remains an importable alias.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, cast

from utils.memory.v3_compatibility import V3CompatibilityReadPath
from utils.memory.v3_memory_read_service import V3MemoryReadServiceResult

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
    'memory_source',
    'memory_policy',
    'source_policy',
    'archive_default_available',
    'stale_short_term_default_visible',
}

_BODY_ALLOWED_READ_PATHS = {V3CompatibilityReadPath.MEMORY_COMPATIBILITY_PROJECTION}
_NO_DATA_READ_PATHS = {V3CompatibilityReadPath.FAIL_CLOSED, V3CompatibilityReadPath.DENY}


@dataclass(frozen=True)
class V3MemoryResponse:
    http_status: int
    body: list[Any] | None
    headers: dict[str, str]
    legacy_fallback_marker_present: bool = False
    archive_default_available: bool = False
    stale_short_term_default_visible: bool = False
    proof_fields: dict[str, bool] = field(default_factory=dict[str, bool])


class V3ResponseShapeError(ValueError):
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
        typed_item = cast(Mapping[str, object], item)
        leaked_fields = _FORBIDDEN_BODY_FIELDS.intersection(typed_item)
        if leaked_fields:
            raise V3ResponseShapeError(
                'memory_only_body_field_forbidden',
                f'memory-only fields must not be exposed in List[MemoryDB] body at index {index}: '
                f'{sorted(leaked_fields)}',
            )


def _body_for_success(envelope: V3MemoryReadServiceResult, memorydb_items: list[Any]) -> list[Any]:
    body = [] if envelope.body == [] else memorydb_items
    _assert_memorydb_body_shape(body)
    return body


def adapt_v3_memory_response(
    envelope: V3MemoryReadServiceResult,
    *,
    memorydb_items: list[Any],
) -> V3MemoryResponse:
    """Adapt a local read envelope into a legacy-compatible `/v3` response.

    The JSON body remains exactly a `List[MemoryDB]` (or no body for denial /
    fail-closed states). memory diagnostics are exposed only through the allowed
    additive headers.
    """

    headers = _allowed_headers(envelope.headers)
    proof_fields = {
        'archive_default_available': False,
        'stale_short_term_default_visible': False,
    }

    if envelope.read_path in _NO_DATA_READ_PATHS or envelope.http_status >= 400:
        return V3MemoryResponse(
            http_status=envelope.http_status,
            body=None,
            headers=headers,
            proof_fields=proof_fields,
        )

    if envelope.read_path not in _BODY_ALLOWED_READ_PATHS:
        return V3MemoryResponse(
            http_status=envelope.http_status,
            body=None,
            headers=headers,
            proof_fields=proof_fields,
        )

    body = _body_for_success(envelope, memorydb_items)
    return V3MemoryResponse(
        http_status=envelope.http_status,
        body=body,
        headers=headers,
        proof_fields=proof_fields,
    )


# Neutral symbol aliases (memory names remain valid via shim)
V3MemoryResponse = V3MemoryResponse
V3ResponseShapeError = V3ResponseShapeError
