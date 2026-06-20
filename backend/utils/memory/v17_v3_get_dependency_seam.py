"""Pure pre-wiring seam for future GET `/v3/memories` dependencies.

This module defines a local adapter/composition shape for route dependencies that
will later surround the runtime GET handler. It performs no FastAPI route wiring,
I/O, Firestore/vector/provider/network calls, telemetry sink calls, mutations, or
production app imports.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Literal, Mapping

DependencyStatus = Literal['READY', 'BLOCKED', 'LEGACY_PRIMARY_ONLY']
DecisionKind = Literal['allow', 'fail_closed', 'legacy_primary_only']

LOW_CARDINALITY_DECISION_CODES = frozenset(
    {
        'auth_ok',
        'missing_or_invalid_auth',
        'no_client_uid_override',
        'client_uid_override_rejected',
        'control_ok',
        'control_unavailable',
        'config_ok',
        'config_unavailable',
        'cursor_ok',
        'cursor_invalid',
        'projection_source_ok',
        'projection_source_unavailable',
        'rate_limit_backpressure_ok',
        'backpressure_denied',
        'non_enrolled_legacy_primary',
    }
)


@dataclass(frozen=True)
class V17V3GetDependencyContext:
    route: str
    client_uid_override_present: bool
    enrolled: bool
    control_ready: bool
    config_ready: bool
    cursor_ready: bool
    projection_source_ready: bool
    backpressure_ready: bool


@dataclass(frozen=True)
class V17V3GetDependencyDecision:
    kind: DecisionKind
    decision_code: str
    http_status: int = 200
    subject_uid: str | None = None

    @staticmethod
    def allowed(decision_code: str, *, subject_uid: str | None = None) -> 'V17V3GetDependencyDecision':
        return V17V3GetDependencyDecision(kind='allow', decision_code=decision_code, subject_uid=subject_uid)

    @staticmethod
    def fail_closed(decision_code: str, *, http_status: int) -> 'V17V3GetDependencyDecision':
        return V17V3GetDependencyDecision(kind='fail_closed', decision_code=decision_code, http_status=http_status)

    @staticmethod
    def legacy(decision_code: str) -> 'V17V3GetDependencyDecision':
        return V17V3GetDependencyDecision(kind='legacy_primary_only', decision_code=decision_code)


DependencyAdapter = Callable[[V17V3GetDependencyContext], V17V3GetDependencyDecision]


@dataclass(frozen=True)
class V17V3GetDependencyAdapters:
    authenticate_subject: DependencyAdapter
    reject_client_uid_override: DependencyAdapter
    load_enrollment_control: DependencyAdapter
    validate_runtime_config: DependencyAdapter
    validate_cursor: DependencyAdapter
    select_projection_source: DependencyAdapter
    check_rate_limit_backpressure: DependencyAdapter


@dataclass(frozen=True)
class V17V3GetDependencyChainResult:
    status: DependencyStatus
    http_status: int
    decision_code: str
    dependency_step: str
    executed_steps: tuple[str, ...]
    subject_uid: str | None = None
    should_fetch_legacy: bool = False
    should_fetch_v17_projection: bool = False
    legacy_fallback_allowed: bool = False
    v17_legacy_merge_allowed: bool = False
    projection_reads_allowed_after_step: str | None = None
    route_wired: bool = False
    runtime_wiring_changed: bool = False
    production_rollout_approved: bool = False
    logs_secret_material: bool = False
    logs_cursor_token: bool = False
    logs_user_content: bool = False
    logs_client_supplied_uid: bool = False
    logged_fields: Mapping[str, str] = field(default_factory=dict)


_ORDER: tuple[tuple[str, str], ...] = (
    ('authenticate_subject', 'auth'),
    ('reject_client_uid_override', 'reject_client_uid_override'),
    ('load_enrollment_control', 'enrollment_control'),
    ('validate_runtime_config', 'config'),
    ('validate_cursor', 'cursor'),
    ('select_projection_source', 'projection_source'),
    ('check_rate_limit_backpressure', 'rate_limit_backpressure'),
)


def _assert_low_cardinality(decision_code: str) -> None:
    if decision_code not in LOW_CARDINALITY_DECISION_CODES:
        raise ValueError('unsupported_v17_v3_get_dependency_decision_code')


def _logged_fields(
    context: V17V3GetDependencyContext, *, decision_code: str, dependency_step: str, status: DependencyStatus
) -> dict[str, str]:
    return {
        'route': context.route,
        'decision_code': decision_code,
        'dependency_step': dependency_step,
        'status': status,
    }


def _result(
    context: V17V3GetDependencyContext,
    *,
    status: DependencyStatus,
    http_status: int,
    decision_code: str,
    dependency_step: str,
    executed_steps: tuple[str, ...],
    subject_uid: str | None = None,
    should_fetch_legacy: bool = False,
    should_fetch_v17_projection: bool = False,
    projection_reads_allowed_after_step: str | None = None,
) -> V17V3GetDependencyChainResult:
    _assert_low_cardinality(decision_code)
    return V17V3GetDependencyChainResult(
        status=status,
        http_status=http_status,
        decision_code=decision_code,
        dependency_step=dependency_step,
        executed_steps=executed_steps,
        subject_uid=subject_uid,
        should_fetch_legacy=should_fetch_legacy,
        should_fetch_v17_projection=should_fetch_v17_projection,
        projection_reads_allowed_after_step=projection_reads_allowed_after_step,
        logged_fields=_logged_fields(
            context, decision_code=decision_code, dependency_step=dependency_step, status=status
        ),
    )


def plan_v17_v3_get_dependency_chain(
    context: V17V3GetDependencyContext,
    adapters: V17V3GetDependencyAdapters,
) -> V17V3GetDependencyChainResult:
    """Run the future GET dependency adapter seam in deterministic order.

    Authenticated subject binding is first. Client uid override rejection runs
    before enrollment/control. Non-enrolled callers exit as legacy-primary-only
    without V17/legacy merge. Enrolled callers must pass control, config, cursor,
    projection-source, and rate-limit/backpressure before projection reads are
    allowed. Any missing/invalid gate fails closed with no reads.
    """

    executed_steps: list[str] = []
    subject_uid: str | None = None

    for adapter_attr, public_step in _ORDER:
        decision = getattr(adapters, adapter_attr)(context)
        executed_steps.append(public_step)
        _assert_low_cardinality(decision.decision_code)

        if adapter_attr == 'authenticate_subject':
            subject_uid = decision.subject_uid
            if decision.kind != 'allow' or not subject_uid:
                return _result(
                    context,
                    status='BLOCKED',
                    http_status=decision.http_status if decision.http_status >= 400 else 401,
                    decision_code=decision.decision_code,
                    dependency_step=public_step,
                    executed_steps=tuple(executed_steps),
                )

        if decision.kind == 'fail_closed':
            return _result(
                context,
                status='BLOCKED',
                http_status=decision.http_status,
                decision_code=decision.decision_code,
                dependency_step=public_step,
                executed_steps=tuple(executed_steps),
                subject_uid=subject_uid,
            )

        if decision.kind == 'legacy_primary_only':
            return _result(
                context,
                status='LEGACY_PRIMARY_ONLY',
                http_status=200,
                decision_code=decision.decision_code,
                dependency_step=public_step,
                executed_steps=tuple(executed_steps),
                subject_uid=subject_uid,
                should_fetch_legacy=True,
            )

    return _result(
        context,
        status='READY',
        http_status=200,
        decision_code='rate_limit_backpressure_ok',
        dependency_step='rate_limit_backpressure',
        executed_steps=tuple(executed_steps),
        subject_uid=subject_uid,
        should_fetch_v17_projection=True,
        projection_reads_allowed_after_step='rate_limit_backpressure',
    )
