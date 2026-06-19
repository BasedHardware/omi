"""Pure/local `/v3` external write-convergence contract seam.

The seam models whether caller-supplied create/update/delete write evidence is
converged enough for enrolled V17 `/v3` read cutover. It performs no I/O,
routing, mutations, app startup, provider calls, or client imports.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class V17V3ExternalWriteOperation(str, Enum):
    CREATE = 'create'
    UPDATE = 'update'
    DELETE = 'delete'


class V17V3WriteConvergenceStatus(str, Enum):
    CONVERGED = 'CONVERGED'
    DISABLED = 'DISABLED'
    MISSING = 'MISSING'
    STALE = 'STALE'
    PARTIAL = 'PARTIAL'
    SWALLOWED_FAILURE = 'SWALLOWED_FAILURE'
    INDEPENDENT_DUAL_WRITE_WITHOUT_DURABLE_OUTBOX = 'INDEPENDENT_DUAL_WRITE_WITHOUT_DURABLE_OUTBOX'
    BLOCKED = 'BLOCKED'


@dataclass(frozen=True)
class V17V3WriteConvergenceContext:
    uid: str
    enrolled: bool
    operation: V17V3ExternalWriteOperation
    write_surface_active: bool
    reads_blocked_for_cohort: bool
    v17_authoritative_write_path_available: bool
    status: V17V3WriteConvergenceStatus | None
    expected_account_generation: int | None
    observed_account_generation: int | None
    durable_outbox_fence: bool
    independent_dual_write: bool
    swallowed_failure: bool
    projection_update_committed: bool
    projection_commit_id: str | None
    projection_generation: int | None
    tombstone_committed: bool = False
    projection_removal_committed: bool = False
    vector_cleanup_outbox_fence: bool = False


@dataclass(frozen=True)
class V17V3WriteConvergenceDecision:
    status: V17V3WriteConvergenceStatus
    write_success_allowed: bool
    read_cutover_allowed: bool
    http_status: int
    reason: str
    operation: V17V3ExternalWriteOperation
    headers: dict[str, str] = field(default_factory=dict)
    safe_pilot_policy_allowed: bool = False
    legacy_direct_write_fallback_allowed: bool = False
    archive_default_available: bool = False
    stale_short_term_default_visible: bool = False


def _headers(status: str, operation: V17V3ExternalWriteOperation, reason: str) -> dict[str, str]:
    return {
        'X-Omi-Memory-Write-Convergence': status,
        'X-Omi-Memory-Write-Operation': operation.value,
        'X-Omi-Memory-Write-Decision': reason,
    }


def _blocked(context: V17V3WriteConvergenceContext, reason: str) -> V17V3WriteConvergenceDecision:
    return V17V3WriteConvergenceDecision(
        status=V17V3WriteConvergenceStatus.BLOCKED,
        write_success_allowed=False,
        read_cutover_allowed=False,
        http_status=503,
        reason=reason,
        operation=context.operation,
        headers=_headers('blocked', context.operation, reason),
    )


def _disabled_safe_pilot(context: V17V3WriteConvergenceContext, reason: str) -> V17V3WriteConvergenceDecision:
    return V17V3WriteConvergenceDecision(
        status=V17V3WriteConvergenceStatus.DISABLED,
        write_success_allowed=False,
        read_cutover_allowed=False,
        http_status=503,
        reason=reason,
        operation=context.operation,
        headers=_headers('disabled', context.operation, reason),
        safe_pilot_policy_allowed=True,
    )


def _first_blocker(context: V17V3WriteConvergenceContext) -> str | None:
    if context.status is None:
        return 'write_convergence_status_missing'
    if context.status == V17V3WriteConvergenceStatus.MISSING:
        return 'write_convergence_missing'
    if context.status == V17V3WriteConvergenceStatus.STALE:
        return 'write_convergence_stale'
    if context.status == V17V3WriteConvergenceStatus.PARTIAL:
        return 'write_convergence_partial'
    if context.status == V17V3WriteConvergenceStatus.SWALLOWED_FAILURE or context.swallowed_failure:
        return 'write_failure_swallowed'
    if (
        context.status == V17V3WriteConvergenceStatus.INDEPENDENT_DUAL_WRITE_WITHOUT_DURABLE_OUTBOX
        or (context.independent_dual_write and not context.durable_outbox_fence)
        or not context.durable_outbox_fence
    ):
        return 'durable_outbox_fence_missing'
    if not context.v17_authoritative_write_path_available:
        return 'v17_authoritative_write_path_unavailable'
    if context.expected_account_generation is None:
        return 'expected_account_generation_missing'
    if context.observed_account_generation is None:
        return 'observed_account_generation_missing'
    if context.observed_account_generation != context.expected_account_generation:
        return 'account_generation_mismatch'
    if not context.projection_update_committed:
        return 'projection_update_commit_missing'
    if not context.projection_commit_id:
        return 'projection_commit_id_missing'
    if context.projection_generation is None:
        return 'projection_generation_missing'
    if context.projection_generation < context.expected_account_generation:
        return 'projection_generation_stale'
    if context.operation == V17V3ExternalWriteOperation.DELETE:
        if not context.tombstone_committed:
            return 'delete_tombstone_missing'
        if not context.projection_removal_committed:
            return 'delete_projection_removal_missing'
        if not context.vector_cleanup_outbox_fence:
            return 'delete_vector_cleanup_outbox_fence_missing'
    return None


def decide_v17_v3_write_convergence(
    context: V17V3WriteConvergenceContext,
) -> V17V3WriteConvergenceDecision:
    """Return a local write-convergence decision for one external `/v3` write.

    Non-enrolled accounts receive only a legacy-primary plan marker; enrolled V17
    accounts must present V17-authoritative write evidence and projection/delete
    fences before write success or read cutover is allowed.
    """

    if not context.enrolled:
        reason = 'non_enrolled_legacy_primary_write_plan_only'
        return V17V3WriteConvergenceDecision(
            status=V17V3WriteConvergenceStatus.BLOCKED,
            write_success_allowed=False,
            read_cutover_allowed=False,
            http_status=200,
            reason=reason,
            operation=context.operation,
            headers=_headers('legacy_primary_plan_only', context.operation, reason),
        )

    if context.status == V17V3WriteConvergenceStatus.DISABLED:
        if context.reads_blocked_for_cohort:
            return _disabled_safe_pilot(context, 'external_writes_disabled_reads_blocked_safe_pilot')
        if not context.write_surface_active:
            return _disabled_safe_pilot(context, 'external_writes_disabled_no_active_write_surface_safe_pilot')
        return _blocked(context, 'external_writes_disabled_but_reads_not_blocked')

    blocker = _first_blocker(context)
    if blocker is not None:
        return _blocked(context, blocker)

    reason = f'{context.operation.value}_write_converged'
    return V17V3WriteConvergenceDecision(
        status=V17V3WriteConvergenceStatus.CONVERGED,
        write_success_allowed=True,
        read_cutover_allowed=True,
        http_status=200,
        reason=reason,
        operation=context.operation,
        headers=_headers('converged', context.operation, reason),
    )
