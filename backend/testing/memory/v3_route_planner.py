"""Canonical module for ``utils.memory.v3_route_planner`` (WS-G8b).

Neutral ``v3_route_planner`` is the source of truth. Legacy ``v3_route_planner`` remains an importable alias.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Mapping, Sequence

from utils.memory.v3.compatibility import V3CompatibilityReadPath
from utils.memory.v3.memory_read_service import (
    V3MemoryReadRequest,
    V3MemoryReadServiceInput,
    V3MemoryReadServiceResult,
    plan_v3_memory_read,
)
from utils.memory.v3.request_adapter import V3AdaptedRequest, adapt_v3_request_parameters
from utils.memory.v3.response_adapter import V3MemoryResponse, adapt_v3_memory_response
from utils.memory.v3.projection_readiness import V3ProjectionReadinessContext
from utils.memory.v3.write_convergence import (
    V3WriteConvergenceContext,
    V3WriteConvergenceDecision,
    decide_v3_write_convergence,
)


@dataclass(frozen=True)
class V3RoutePlanInput:
    uid: str
    query_params: Mapping[str, Any] | None
    enrolled: bool
    control_state: str
    default_memory_grant: bool | None
    projection_readiness_context: V3ProjectionReadinessContext | dict[str, Any] | None = None
    write_convergence_contexts: Sequence[V3WriteConvergenceContext | Mapping[str, Any]] = field(default_factory=tuple)
    page_body: list[Any] = field(default_factory=list)
    memorydb_items: list[Any] = field(default_factory=list)
    cursor_context: Any | None = None
    cursor_secret: bytes | None = None
    next_keyset: Any | None = None
    cursor_ttl_seconds: int = 300


@dataclass(frozen=True)
class V3RouteExecutionPlan:
    plan_kind: str
    http_status: int
    adapted_request: V3AdaptedRequest
    read_envelope: V3MemoryReadServiceResult | None = None
    response: V3MemoryResponse | None = None
    write_convergence_decisions: tuple[V3WriteConvergenceDecision, ...] = ()
    fail_closed_reason: str | None = None
    should_fetch_legacy: bool = False
    should_fetch_memory_projection: bool = False
    legacy_fallback_allowed: bool = False
    route_wired: bool = False
    archive_default_available: bool = False
    stale_short_term_default_visible: bool = False


def _write_context(value: V3WriteConvergenceContext | Mapping[str, Any]) -> V3WriteConvergenceContext:
    if isinstance(value, V3WriteConvergenceContext):
        return value
    return V3WriteConvergenceContext(**value)


def _decide_write_convergence(
    contexts: Sequence[V3WriteConvergenceContext | Mapping[str, Any]],
) -> tuple[V3WriteConvergenceDecision, ...]:
    return tuple(decide_v3_write_convergence(_write_context(context)) for context in contexts)


def _write_convergence_ready(decisions: Sequence[V3WriteConvergenceDecision]) -> bool:
    return all(decision.read_cutover_allowed for decision in decisions)


def _projection_with_write_convergence(
    projection_readiness_context: V3ProjectionReadinessContext | dict[str, Any] | None,
    *,
    write_ready: bool,
) -> V3ProjectionReadinessContext | dict[str, Any] | None:
    if projection_readiness_context is None or write_ready:
        return projection_readiness_context
    if isinstance(projection_readiness_context, dict):
        updated = dict(projection_readiness_context)
        updated['create_converged'] = False
        return updated
    if hasattr(projection_readiness_context, 'create_converged'):
        return replace(projection_readiness_context, create_converged=False)
    return projection_readiness_context


def _failure_plan(
    *,
    adapted_request: V3AdaptedRequest,
    reason: str,
    http_status: int,
    plan_kind: str = 'fail_closed',
    read_envelope: V3MemoryReadServiceResult | None = None,
    write_decisions: tuple[V3WriteConvergenceDecision, ...] = (),
) -> V3RouteExecutionPlan:
    return V3RouteExecutionPlan(
        plan_kind=plan_kind,
        http_status=http_status,
        adapted_request=adapted_request,
        read_envelope=read_envelope,
        write_convergence_decisions=write_decisions,
        fail_closed_reason=reason,
    )


def _read_request(adapted_request: V3AdaptedRequest) -> V3MemoryReadRequest:
    return V3MemoryReadRequest(
        limit=adapted_request.limit,
        offset=adapted_request.offset,
        cursor=adapted_request.cursor,
        v3_cursor_mode=adapted_request.v3_cursor_mode,
    )


def _plan_kind_for_envelope(envelope: V3MemoryReadServiceResult) -> str:
    if envelope.read_path == V3CompatibilityReadPath.MEMORY_COMPATIBILITY_PROJECTION and envelope.http_status < 400:
        return 'memory_response_envelope'
    if envelope.read_path == V3CompatibilityReadPath.DENY:
        return 'deny'
    return 'fail_closed'


def plan_v3_memory_route(route_input: V3RoutePlanInput) -> V3RouteExecutionPlan:
    """Return a pure route-adjacent `/v3` execution plan.

    The returned envelope is suitable for a future web route to consume, but
    this function never imports or wires a web framework. Non-enrolled callers receive an
    explicit legacy-primary marker only. Enrolled invalid, denied, not-ready, or
    malformed states fail closed and never fall back to legacy.
    """

    adapted_request = adapt_v3_request_parameters(route_input.query_params, enrolled=route_input.enrolled)

    if not route_input.enrolled:
        envelope = plan_v3_memory_read(
            V3MemoryReadServiceInput(
                uid=route_input.uid,
                enrolled=False,
                control_state=route_input.control_state,
                default_memory_grant=route_input.default_memory_grant,
                request=_read_request(adapted_request),
                projection_readiness_context=None,
            )
        )
        return V3RouteExecutionPlan(
            plan_kind='legacy_primary_plan_only',
            http_status=envelope.http_status,
            adapted_request=adapted_request,
            read_envelope=envelope,
            fail_closed_reason=None,
        )

    if not adapted_request.valid:
        return _failure_plan(
            adapted_request=adapted_request,
            reason=adapted_request.fail_closed_reason or 'invalid_request_parameters',
            http_status=400,
        )

    write_decisions = _decide_write_convergence(route_input.write_convergence_contexts)
    write_ready = _write_convergence_ready(write_decisions)
    projection_context = _projection_with_write_convergence(
        route_input.projection_readiness_context,
        write_ready=write_ready,
    )

    envelope = plan_v3_memory_read(
        V3MemoryReadServiceInput(
            uid=route_input.uid,
            enrolled=True,
            control_state=route_input.control_state,
            default_memory_grant=route_input.default_memory_grant,
            request=_read_request(adapted_request),
            projection_readiness_context=projection_context,
            page_body=route_input.page_body,
            cursor_context=route_input.cursor_context,
            cursor_secret=route_input.cursor_secret,
            next_keyset=route_input.next_keyset,
            requested_archive=adapted_request.include_archive,
            cursor_ttl_seconds=route_input.cursor_ttl_seconds,
        )
    )

    plan_kind = _plan_kind_for_envelope(envelope)
    if plan_kind != 'memory_response_envelope':
        return _failure_plan(
            adapted_request=adapted_request,
            reason=envelope.read_decision,
            http_status=envelope.http_status,
            plan_kind=plan_kind,
            read_envelope=envelope,
            write_decisions=write_decisions,
        )

    response = adapt_v3_memory_response(envelope, memorydb_items=route_input.memorydb_items)
    return V3RouteExecutionPlan(
        plan_kind='memory_response_envelope',
        http_status=response.http_status,
        adapted_request=adapted_request,
        read_envelope=envelope,
        response=response,
        write_convergence_decisions=write_decisions,
    )


# Neutral symbol aliases (memory names remain valid via shim)
V3RoutePlanInput = V3RoutePlanInput
V3RouteExecutionPlan = V3RouteExecutionPlan
