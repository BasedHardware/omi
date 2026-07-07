"""Canonical module for ``utils.memory.v3_compatibility`` (WS-G8b).

Planner/test-path `/v3` compatibility decisions. Production GET routing uses
``v3_control_reader_contract.decide_v3_control_route`` instead; this module
remains for ``plan_v3_memory_read`` and equivalence tests that document
intentional divergence (e.g. ``rollout_write_ready`` coupling, archive 404).
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any

from utils.memory.memory_read_rollout_core import (
    ENROLLED_FAIL_CLOSED_CONTROL_STATES,
    MemoryReadGateBlock,
    SUPPORTED_ENROLLED_CONTROL_STATES,
    evaluate_enrolled_memory_read_gates,
    EnrolledMemoryReadGateContext,
)

# Neutral ``v3_compatibility`` is the source of truth. Legacy ``v3_compatibility`` remains an importable alias.


class V3CompatibilityReadPath(str, Enum):
    LEGACY_PRIMARY = 'LEGACY_PRIMARY'
    MEMORY_COMPATIBILITY_PROJECTION = 'MEMORY_COMPATIBILITY_PROJECTION'
    FAIL_CLOSED = 'FAIL_CLOSED'
    DENY = 'DENY'


@dataclass(frozen=True)
class V3CompatibilityContext:
    uid: str
    enrolled: bool
    control_state: str = 'missing'
    default_memory_grant: bool | None = None
    write_convergence_ready: bool = False
    projection_ready: bool = False
    projection_empty: bool = False
    requested_archive: bool = False


@dataclass(frozen=True)
class V3CursorMode:
    enabled_mode: str = 'additive_memory_cursor'
    opaque: bool = True
    signed: bool = True
    keyset_fields: tuple[str, str] = ('created_at_desc', 'memory_id_desc')
    generation_bound: bool = True
    projection_bound: bool = True
    allows_offset: bool = False
    applies_first_page_5000_override: bool = False


@dataclass(frozen=True)
class V3CompatibilityDecision:
    read_path: V3CompatibilityReadPath
    http_status: int
    reason: str
    headers: dict[str, str]
    body_contract: str = 'List[MemoryDB]'
    metadata_location: str = 'headers'
    body_additions: tuple[str, ...] = ()
    legacy_primary_allowed: bool = False
    legacy_fallback_allowed: bool = False
    product_overridable: bool = False
    archive_available: bool = False
    response_body_override: list[Any] | None = None


def _headers(*, source: str, reason: str) -> dict[str, str]:
    return {'X-Omi-Memory-Read-Source': source, 'X-Omi-Memory-Read-Decision': reason}


def _fail_closed(reason: str) -> V3CompatibilityDecision:
    return V3CompatibilityDecision(
        read_path=V3CompatibilityReadPath.FAIL_CLOSED,
        http_status=503,
        reason=reason,
        headers=_headers(source='none', reason=reason),
    )


def decide_v3_compatibility(context: V3CompatibilityContext) -> V3CompatibilityDecision:
    """Pure Oracle-prescribed `/v3` memory compatibility decision seam.

    This function is intentionally local and side-effect free. It performs no
    Firestore, Pinecone, provider, network, routing, or mutation work. Runtime
    `/v3` route wiring remains blocked until a later slice supplies the backing
    read/projection/write convergence services and product approval.
    """

    if not context.enrolled:
        reason = 'non_enrolled_legacy_primary'
        return V3CompatibilityDecision(
            read_path=V3CompatibilityReadPath.LEGACY_PRIMARY,
            http_status=200,
            reason=reason,
            headers=_headers(source='legacy_primary', reason=reason),
            legacy_primary_allowed=True,
        )

    if context.control_state in ENROLLED_FAIL_CLOSED_CONTROL_STATES:
        return _fail_closed(f'enrolled_{context.control_state}_fail_closed')

    if context.control_state not in SUPPORTED_ENROLLED_CONTROL_STATES:
        return _fail_closed('enrolled_unsupported_schema_fail_closed')

    if context.default_memory_grant is not True:
        reason = 'no_default_memory_grant_privacy_consent_deny'
        return V3CompatibilityDecision(
            read_path=V3CompatibilityReadPath.DENY,
            http_status=403,
            reason=reason,
            headers=_headers(source='none', reason=reason),
            product_overridable=True,
        )

    if context.requested_archive:
        reason = 'archive_default_unavailable'
        return V3CompatibilityDecision(
            read_path=V3CompatibilityReadPath.DENY,
            http_status=404,
            reason=reason,
            headers=_headers(source='none', reason=reason),
            archive_available=False,
        )

    gate_result = evaluate_enrolled_memory_read_gates(
        EnrolledMemoryReadGateContext(
            global_read_gate_open=True,
            default_memory_grant=context.default_memory_grant,
            memory_reads_enabled=context.projection_ready,
            write_convergence_ready=context.write_convergence_ready,
            check_global_read_gate=False,
            require_write_convergence=True,
            require_rollout_write_for_convergence=False,
        )
    )
    if gate_result.blocked:
        if gate_result.block == MemoryReadGateBlock.WRITE_CONVERGENCE_NOT_READY:
            return _fail_closed('write_convergence_not_ready')
        if gate_result.block == MemoryReadGateBlock.PROJECTION_NOT_READY:
            return _fail_closed('memory_projection_not_ready')
        # Any other (unmapped or future) shared gate block denies the read rather
        # than silently falling through to a memory projection success.
        return _fail_closed('enrolled_read_gate_blocked_fail_closed')

    if context.projection_empty:
        reason = 'memory_projection_empty_no_legacy_fallback'
        return V3CompatibilityDecision(
            read_path=V3CompatibilityReadPath.MEMORY_COMPATIBILITY_PROJECTION,
            http_status=200,
            reason=reason,
            headers=_headers(source='memory_compatibility_projection', reason=reason),
            response_body_override=[],
        )

    reason = 'memory_compatibility_projection_primary'
    return V3CompatibilityDecision(
        read_path=V3CompatibilityReadPath.MEMORY_COMPATIBILITY_PROJECTION,
        http_status=200,
        reason=reason,
        headers=_headers(source='memory_compatibility_projection', reason=reason),
    )


def describe_v3_cursor_mode() -> V3CursorMode:
    """Return the allowed memory `/v3` cursor contract without parsing live cursors."""

    return V3CursorMode()


# Neutral symbol aliases (memory names remain valid via shim)
V3CompatibilityReadPath = V3CompatibilityReadPath
V3CompatibilityContext = V3CompatibilityContext
V3CursorMode = V3CursorMode
V3CompatibilityDecision = V3CompatibilityDecision
