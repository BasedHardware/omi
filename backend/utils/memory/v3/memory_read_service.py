"""Canonical module for ``utils.memory.v3.memory_read_service`` (WS-G8b).

This module owns the canonical V3 memory-read service.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from utils.memory.v3.compatibility import (
    V3CompatibilityContext,
    V3CompatibilityReadPath,
    decide_v3_compatibility,
)
from utils.memory.v3.cursor import (
    V3CursorContext,
    V3CursorError,
    V3Keyset,
    create_v3_cursor,
    parse_v3_cursor,
    validate_v3_cursor_request,
)
from utils.memory.v3.projection_readiness import (
    V3ProjectionReadinessContext,
    V3ProjectionReadinessState,
    decide_v3_projection_readiness,
)

V3_READ_SOURCE = 'memory_compatibility_projection'
V3_READ_MODE = 'default_memory'
_DEFAULT_CURSOR_TTL_SECONDS = 300


@dataclass(frozen=True)
class V3MemoryReadRequest:
    limit: int
    offset: int | None = None
    cursor: str | None = None
    v3_cursor_mode: bool = True


@dataclass(frozen=True)
class V3MemoryReadServiceInput:
    uid: str
    enrolled: bool
    control_state: str
    default_memory_grant: bool | None
    request: V3MemoryReadRequest
    projection_readiness_context: V3ProjectionReadinessContext | dict[str, Any] | None = None
    page_body: list[Any] = field(default_factory=list)
    cursor_context: V3CursorContext | None = None
    cursor_secret: bytes | None = None
    next_keyset: V3Keyset | None = None
    requested_archive: bool = False
    cursor_ttl_seconds: int = _DEFAULT_CURSOR_TTL_SECONDS


@dataclass(frozen=True)
class V3MemoryReadServiceResult:
    http_status: int
    read_plan: str
    read_path: V3CompatibilityReadPath
    read_decision: str
    headers: dict[str, str]
    body: list[Any] | None = None
    should_fetch_legacy: bool = False
    should_fetch_memory_projection: bool = False
    legacy_fallback_allowed: bool = False
    archive_default_available: bool = False
    stale_short_term_default_visible: bool = False


def _projection_context(
    value: V3ProjectionReadinessContext | dict[str, Any] | None,
) -> V3ProjectionReadinessContext | None:
    if value is None:
        return None
    if isinstance(value, V3ProjectionReadinessContext):
        return value
    return V3ProjectionReadinessContext(**value)


def _headers(*, source: str, decision: str) -> dict[str, str]:
    return {'X-Omi-Memory-Read-Source': source, 'X-Omi-Memory-Read-Decision': decision}


def _fail_closed_cursor(reason: str) -> V3MemoryReadServiceResult:
    return V3MemoryReadServiceResult(
        http_status=400,
        read_plan='fail_closed',
        read_path=V3CompatibilityReadPath.FAIL_CLOSED,
        read_decision=reason,
        headers=_headers(source='none', decision=reason),
    )


def _classify_write_convergence_ready(reason: str) -> bool:
    return reason not in {
        'external_create_convergence_not_ready',
        'external_update_convergence_not_ready',
        'external_delete_convergence_not_ready',
    }


def _validate_memory_cursor_request(service_input: V3MemoryReadServiceInput) -> V3MemoryReadServiceResult | None:
    request = service_input.request
    if not request.v3_cursor_mode:
        return None

    try:
        validate_v3_cursor_request(limit=request.limit, cursor=request.cursor, offset=request.offset)
        if request.cursor is not None:
            if service_input.cursor_context is None or service_input.cursor_secret is None:
                raise V3CursorError('cursor_validation_context_missing')
            parse_v3_cursor(request.cursor, service_input.cursor_context, service_input.cursor_secret)
    except V3CursorError as exc:
        return _fail_closed_cursor(exc.reason)
    return None


def _add_next_cursor_headers(
    headers: dict[str, str], service_input: V3MemoryReadServiceInput
) -> dict[str, str] | V3MemoryReadServiceResult:
    if service_input.next_keyset is None:
        return headers
    if service_input.cursor_context is None or service_input.cursor_secret is None:
        return _fail_closed_cursor('next_cursor_context_missing')

    cursor = create_v3_cursor(
        service_input.next_keyset,
        service_input.cursor_context,
        service_input.cursor_secret,
        ttl_seconds=service_input.cursor_ttl_seconds,
    )
    result = dict(headers)
    result['X-Omi-Memory-Next-Cursor'] = cursor
    result['Link'] = f'<{cursor}>; rel="next"'
    return result


def plan_v3_memory_read(service_input: V3MemoryReadServiceInput) -> V3MemoryReadServiceResult:
    """Return a local `/v3` compatibility read envelope/plan.

    Non-enrolled callers receive only a legacy-primary marker; this function never
    fetches legacy rows itself. Enrolled memory cursor-mode callers fail closed on
    invalid cursor/offset semantics and never downgrade to offset or legacy.
    """

    if not service_input.enrolled:
        decision = decide_v3_compatibility(
            V3CompatibilityContext(
                uid=service_input.uid,
                enrolled=False,
                control_state=service_input.control_state,
            )
        )
        return V3MemoryReadServiceResult(
            http_status=decision.http_status,
            read_plan='legacy_primary_plan_only',
            read_path=decision.read_path,
            read_decision=decision.reason,
            headers=decision.headers,
            legacy_fallback_allowed=decision.legacy_fallback_allowed,
        )

    cursor_failure = _validate_memory_cursor_request(service_input)
    if cursor_failure is not None:
        return cursor_failure

    projection_context = _projection_context(service_input.projection_readiness_context)
    projection_ready = False
    projection_empty = False
    write_convergence_ready = False
    if projection_context is not None:
        projection_decision = decide_v3_projection_readiness(projection_context)
        projection_ready = projection_decision.read_cutover_allowed
        projection_empty = projection_decision.state == V3ProjectionReadinessState.READY_EMPTY
        write_convergence_ready = projection_ready or _classify_write_convergence_ready(projection_decision.reason)

    decision = decide_v3_compatibility(
        V3CompatibilityContext(
            uid=service_input.uid,
            enrolled=True,
            control_state=service_input.control_state,
            default_memory_grant=service_input.default_memory_grant,
            write_convergence_ready=write_convergence_ready,
            projection_ready=projection_ready,
            projection_empty=projection_empty,
            requested_archive=service_input.requested_archive,
        )
    )

    if decision.read_path != V3CompatibilityReadPath.MEMORY_COMPATIBILITY_PROJECTION:
        return V3MemoryReadServiceResult(
            http_status=decision.http_status,
            read_plan='fail_closed' if decision.read_path == V3CompatibilityReadPath.FAIL_CLOSED else 'deny',
            read_path=decision.read_path,
            read_decision=decision.reason,
            headers=decision.headers,
            legacy_fallback_allowed=decision.legacy_fallback_allowed,
            archive_default_available=decision.archive_available,
        )

    if decision.response_body_override is not None:
        return V3MemoryReadServiceResult(
            http_status=decision.http_status,
            read_plan='memory_compatibility_projection',
            read_path=decision.read_path,
            read_decision=decision.reason,
            headers=decision.headers,
            body=decision.response_body_override,
            legacy_fallback_allowed=decision.legacy_fallback_allowed,
        )

    headers_or_failure = _add_next_cursor_headers(decision.headers, service_input)
    if isinstance(headers_or_failure, V3MemoryReadServiceResult):
        return headers_or_failure

    return V3MemoryReadServiceResult(
        http_status=decision.http_status,
        read_plan='memory_compatibility_projection',
        read_path=decision.read_path,
        read_decision=decision.reason,
        headers=headers_or_failure,
        body=service_input.page_body,
        legacy_fallback_allowed=decision.legacy_fallback_allowed,
    )
