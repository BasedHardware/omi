"""Canonical module for ``utils.memory.v3_projection_readiness`` (WS-G8b).

Neutral ``v3_projection_readiness`` is the source of truth. Legacy ``v3_projection_readiness`` remains an importable alias.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

DERIVED_COMPATIBILITY_PROJECTION_SOURCE = 'memory_derived_compatibility_projection'


class V3ProjectionReadinessState(str, Enum):
    READY = 'READY'
    READY_EMPTY = 'READY_EMPTY'
    BLOCKED = 'BLOCKED'


@dataclass(frozen=True)
class V3ProjectionReadinessContext:
    uid: str
    expected_account_generation: int | None = None
    account_generation: int | None = None
    projection_generation: int | None = None
    create_converged: bool = False
    update_converged: bool = False
    delete_converged: bool = False
    projection_source: str | None = None
    tombstone_fence_present: bool = False
    tombstone_fence_generation: int | None = None
    source_commit_id: str | None = None
    source_version: str | None = None
    projection_commit_id: str | None = None
    projection_version: str | None = None
    freshness_fence_present: bool = False
    freshness_fence_generation: int | None = None
    projection_empty: bool = False


@dataclass(frozen=True)
class V3ProjectionReadinessDecision:
    state: V3ProjectionReadinessState
    read_cutover_allowed: bool
    http_status: int
    reason: str
    source: str | None
    required_account_generation: int | None
    projection_generation: int | None
    can_return_enabled_empty_list: bool = False
    response_body_override: list[object] | None = None
    legacy_fallback_allowed: bool = False
    archive_default_available: bool = False
    stale_short_term_default_visible: bool = False
    headers: dict[str, str] = field(default_factory=dict[str, str])


@dataclass(frozen=True)
class _Blocker:
    reason: str
    source: str | None
    required_account_generation: int | None
    projection_generation: int | None


def _blocked(context: V3ProjectionReadinessContext, reason: str) -> V3ProjectionReadinessDecision:
    return V3ProjectionReadinessDecision(
        state=V3ProjectionReadinessState.BLOCKED,
        read_cutover_allowed=False,
        http_status=503,
        reason=reason,
        source=context.projection_source,
        required_account_generation=context.expected_account_generation,
        projection_generation=context.projection_generation,
        can_return_enabled_empty_list=False,
        response_body_override=None,
        headers={
            'X-Omi-Memory-Projection-Readiness': 'blocked',
            'X-Omi-Memory-Projection-Blocker': reason,
        },
    )


def _first_blocker(context: V3ProjectionReadinessContext) -> _Blocker | None:
    if context.expected_account_generation is None:
        return _Blocker(
            'expected_account_generation_missing',
            context.projection_source,
            context.expected_account_generation,
            context.projection_generation,
        )
    if context.account_generation is None:
        return _Blocker(
            'account_generation_missing',
            context.projection_source,
            context.expected_account_generation,
            context.projection_generation,
        )
    if context.account_generation != context.expected_account_generation:
        return _Blocker(
            'account_generation_mismatch',
            context.projection_source,
            context.expected_account_generation,
            context.projection_generation,
        )
    if context.projection_generation is None:
        return _Blocker(
            'projection_generation_missing',
            context.projection_source,
            context.expected_account_generation,
            context.projection_generation,
        )
    if context.projection_generation < context.expected_account_generation:
        return _Blocker(
            'projection_generation_stale',
            context.projection_source,
            context.expected_account_generation,
            context.projection_generation,
        )
    if not context.create_converged:
        return _Blocker(
            'external_create_convergence_not_ready',
            context.projection_source,
            context.expected_account_generation,
            context.projection_generation,
        )
    if not context.update_converged:
        return _Blocker(
            'external_update_convergence_not_ready',
            context.projection_source,
            context.expected_account_generation,
            context.projection_generation,
        )
    if not context.delete_converged:
        return _Blocker(
            'external_delete_convergence_not_ready',
            context.projection_source,
            context.expected_account_generation,
            context.projection_generation,
        )
    if context.projection_source != DERIVED_COMPATIBILITY_PROJECTION_SOURCE:
        return _Blocker(
            'projection_source_not_memory_derived',
            context.projection_source,
            context.expected_account_generation,
            context.projection_generation,
        )
    if not context.tombstone_fence_present:
        return _Blocker(
            'tombstone_fence_missing',
            context.projection_source,
            context.expected_account_generation,
            context.projection_generation,
        )
    if context.tombstone_fence_generation is None:
        return _Blocker(
            'tombstone_fence_generation_missing',
            context.projection_source,
            context.expected_account_generation,
            context.projection_generation,
        )
    if context.tombstone_fence_generation < context.expected_account_generation:
        return _Blocker(
            'tombstone_fence_stale',
            context.projection_source,
            context.expected_account_generation,
            context.projection_generation,
        )
    missing_fence_fields = [
        ('source_commit_id', context.source_commit_id),
        ('source_version', context.source_version),
        ('projection_commit_id', context.projection_commit_id),
        ('projection_version', context.projection_version),
    ]
    for field_name, value in missing_fence_fields:
        if not value:
            return _Blocker(
                f'{field_name}_missing',
                context.projection_source,
                context.expected_account_generation,
                context.projection_generation,
            )
    if not context.freshness_fence_present:
        return _Blocker(
            'freshness_fence_missing',
            context.projection_source,
            context.expected_account_generation,
            context.projection_generation,
        )
    if context.freshness_fence_generation is None:
        return _Blocker(
            'freshness_fence_generation_missing',
            context.projection_source,
            context.expected_account_generation,
            context.projection_generation,
        )
    if context.freshness_fence_generation < context.expected_account_generation:
        return _Blocker(
            'freshness_fence_stale',
            context.projection_source,
            context.expected_account_generation,
            context.projection_generation,
        )
    return None


def decide_v3_projection_readiness(
    context: V3ProjectionReadinessContext,
) -> V3ProjectionReadinessDecision:
    blocker = _first_blocker(context)
    if blocker is not None:
        return _blocked(context, blocker.reason)

    if context.projection_empty:
        return V3ProjectionReadinessDecision(
            state=V3ProjectionReadinessState.READY_EMPTY,
            read_cutover_allowed=True,
            http_status=200,
            reason='memory_derived_projection_ready_empty',
            source=context.projection_source,
            required_account_generation=context.expected_account_generation,
            projection_generation=context.projection_generation,
            can_return_enabled_empty_list=True,
            response_body_override=[],
            headers={
                'X-Omi-Memory-Projection-Readiness': 'ready_empty',
                'X-Omi-Memory-Projection-Source': DERIVED_COMPATIBILITY_PROJECTION_SOURCE,
            },
        )

    return V3ProjectionReadinessDecision(
        state=V3ProjectionReadinessState.READY,
        read_cutover_allowed=True,
        http_status=200,
        reason='memory_derived_projection_ready',
        source=context.projection_source,
        required_account_generation=context.expected_account_generation,
        projection_generation=context.projection_generation,
        headers={
            'X-Omi-Memory-Projection-Readiness': 'ready',
            'X-Omi-Memory-Projection-Source': DERIVED_COMPATIBILITY_PROJECTION_SOURCE,
        },
    )


# Neutral symbol aliases (memory names remain valid via shim)
V3_DERIVED_COMPATIBILITY_PROJECTION_SOURCE = DERIVED_COMPATIBILITY_PROJECTION_SOURCE
V3ProjectionReadinessState = V3ProjectionReadinessState
V3ProjectionReadinessContext = V3ProjectionReadinessContext
V3ProjectionReadinessDecision = V3ProjectionReadinessDecision
