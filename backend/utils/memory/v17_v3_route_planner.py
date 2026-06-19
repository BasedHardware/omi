"""Pure/local `/v3` route-planning composition proof.

The planner composes the local request adapter, decision/read service,
write-convergence proof, projection-readiness proof, and response adapter into a
route-adjacent execution envelope. It intentionally performs no web-framework
route wiring, app startup, network/provider/cloud calls, Firestore/Pinecone
calls, mutations, or data fetching.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Mapping, Sequence

from utils.memory.v17_v3_compatibility import V17V3CompatibilityReadPath
from utils.memory.v17_v3_memory_read_service import (
    V17V3MemoryReadRequest,
    V17V3MemoryReadServiceInput,
    V17V3MemoryReadServiceResult,
    plan_v17_v3_memory_read,
)
from utils.memory.v17_v3_request_adapter import V17V3AdaptedRequest, adapt_v17_v3_request_parameters
from utils.memory.v17_v3_response_adapter import V17V3MemoryResponse, adapt_v17_v3_memory_response
from utils.memory.v17_v3_projection_readiness import V17V3ProjectionReadinessContext
from utils.memory.v17_v3_write_convergence import (
    V17V3WriteConvergenceContext,
    V17V3WriteConvergenceDecision,
    decide_v17_v3_write_convergence,
)


@dataclass(frozen=True)
class V17V3RoutePlanInput:
    uid: str
    query_params: Mapping[str, Any] | None
    enrolled: bool
    control_state: str
    default_memory_grant: bool | None
    projection_readiness_context: V17V3ProjectionReadinessContext | dict[str, Any] | None = None
    write_convergence_contexts: Sequence[V17V3WriteConvergenceContext | Mapping[str, Any]] = field(
        default_factory=tuple
    )
    page_body: list[Any] = field(default_factory=list)
    memorydb_items: list[Any] = field(default_factory=list)
    cursor_context: Any | None = None
    cursor_secret: bytes | None = None
    next_keyset: Any | None = None
    cursor_ttl_seconds: int = 300


@dataclass(frozen=True)
class V17V3RouteExecutionPlan:
    plan_kind: str
    http_status: int
    adapted_request: V17V3AdaptedRequest
    read_envelope: V17V3MemoryReadServiceResult | None = None
    response: V17V3MemoryResponse | None = None
    write_convergence_decisions: tuple[V17V3WriteConvergenceDecision, ...] = ()
    fail_closed_reason: str | None = None
    should_fetch_legacy: bool = False
    should_fetch_v17_projection: bool = False
    legacy_fallback_allowed: bool = False
    route_wired: bool = False
    archive_default_available: bool = False
    stale_short_term_default_visible: bool = False


def _write_context(value: V17V3WriteConvergenceContext | Mapping[str, Any]) -> V17V3WriteConvergenceContext:
    if isinstance(value, V17V3WriteConvergenceContext):
        return value
    return V17V3WriteConvergenceContext(**value)


def _decide_write_convergence(
    contexts: Sequence[V17V3WriteConvergenceContext | Mapping[str, Any]],
) -> tuple[V17V3WriteConvergenceDecision, ...]:
    return tuple(decide_v17_v3_write_convergence(_write_context(context)) for context in contexts)


def _write_convergence_ready(decisions: Sequence[V17V3WriteConvergenceDecision]) -> bool:
    return all(decision.read_cutover_allowed for decision in decisions)


def _projection_with_write_convergence(
    projection_readiness_context: V17V3ProjectionReadinessContext | dict[str, Any] | None,
    *,
    write_ready: bool,
) -> V17V3ProjectionReadinessContext | dict[str, Any] | None:
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
    adapted_request: V17V3AdaptedRequest,
    reason: str,
    http_status: int,
    plan_kind: str = 'fail_closed',
    read_envelope: V17V3MemoryReadServiceResult | None = None,
    write_decisions: tuple[V17V3WriteConvergenceDecision, ...] = (),
) -> V17V3RouteExecutionPlan:
    return V17V3RouteExecutionPlan(
        plan_kind=plan_kind,
        http_status=http_status,
        adapted_request=adapted_request,
        read_envelope=read_envelope,
        write_convergence_decisions=write_decisions,
        fail_closed_reason=reason,
    )


def _read_request(adapted_request: V17V3AdaptedRequest) -> V17V3MemoryReadRequest:
    return V17V3MemoryReadRequest(
        limit=adapted_request.limit,
        offset=adapted_request.offset,
        cursor=adapted_request.cursor,
        v17_cursor_mode=adapted_request.v17_cursor_mode,
    )


def _plan_kind_for_envelope(envelope: V17V3MemoryReadServiceResult) -> str:
    if envelope.read_path == V17V3CompatibilityReadPath.V17_COMPATIBILITY_PROJECTION and envelope.http_status < 400:
        return 'v17_response_envelope'
    if envelope.read_path == V17V3CompatibilityReadPath.DENY:
        return 'deny'
    return 'fail_closed'


def plan_v17_v3_memory_route(route_input: V17V3RoutePlanInput) -> V17V3RouteExecutionPlan:
    """Return a pure route-adjacent `/v3` execution plan.

    The returned envelope is suitable for a future web route to consume, but
    this function never imports or wires a web framework. Non-enrolled callers receive an
    explicit legacy-primary marker only. Enrolled invalid, denied, not-ready, or
    malformed states fail closed and never fall back to legacy.
    """

    adapted_request = adapt_v17_v3_request_parameters(route_input.query_params, enrolled=route_input.enrolled)

    if not route_input.enrolled:
        envelope = plan_v17_v3_memory_read(
            V17V3MemoryReadServiceInput(
                uid=route_input.uid,
                enrolled=False,
                control_state=route_input.control_state,
                default_memory_grant=route_input.default_memory_grant,
                request=_read_request(adapted_request),
                projection_readiness_context=None,
            )
        )
        return V17V3RouteExecutionPlan(
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

    envelope = plan_v17_v3_memory_read(
        V17V3MemoryReadServiceInput(
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
    if plan_kind != 'v17_response_envelope':
        return _failure_plan(
            adapted_request=adapted_request,
            reason=envelope.read_decision,
            http_status=envelope.http_status,
            plan_kind=plan_kind,
            read_envelope=envelope,
            write_decisions=write_decisions,
        )

    response = adapt_v17_v3_memory_response(envelope, memorydb_items=route_input.memorydb_items)
    return V17V3RouteExecutionPlan(
        plan_kind='v17_response_envelope',
        http_status=response.http_status,
        adapted_request=adapted_request,
        read_envelope=envelope,
        response=response,
        write_convergence_decisions=write_decisions,
    )
