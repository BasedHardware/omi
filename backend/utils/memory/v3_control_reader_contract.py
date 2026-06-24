"""Canonical module for ``utils.memory.v3_control_reader_contract`` (WS-G8b).

Neutral ``v3_control_reader_contract`` is the source of truth. Legacy ``v3_control_reader_contract`` remains an importable alias.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Protocol

from config.memory_rollout import MemoryRolloutMode


class V3ControlRouteFamily(str, Enum):
    LEGACY_PRIMARY = 'legacy_primary'
    MEMORY_PROJECTION = 'memory_projection'
    FAIL_CLOSED = 'fail_closed'


class V3ControlDecisionReason(str, Enum):
    NON_ENROLLED_LEGACY_ALLOWED = 'non_enrolled_legacy_allowed'
    ROLLOUT_LEGACY_AUTHORITATIVE = 'rollout_legacy_authoritative'
    MEMORY_PROJECTION_ALLOWED = 'memory_projection_allowed'
    MISSING_CONTROL_DOC = 'missing_control_doc'
    CONTROL_READ_FAILED = 'control_read_failed'
    MALFORMED_CONTROL_DOC = 'malformed_control_doc'
    UID_MISMATCH = 'uid_mismatch'
    UNSUPPORTED_CONTROL_SCHEMA = 'unsupported_control_schema'
    GLOBAL_READ_GATE_CLOSED = 'global_read_gate_closed'
    STALE_GENERATION = 'stale_generation'
    NO_DEFAULT_MEMORY_GRANT = 'no_default_memory_grant'
    PROJECTION_NOT_READY = 'projection_not_ready'
    WRITE_CONVERGENCE_NOT_READY = 'write_convergence_not_ready'
    INVALID_OR_MISSING_CURSOR_SECRET = 'invalid_or_missing_cursor_secret'
    ARCHIVE_NOT_ALLOWED = 'archive_not_allowed'


@dataclass(frozen=True)
class V3ControlReaderRequest:
    uid: str
    expected_account_generation: int | None
    cursor_memory_read_requested: bool
    cursor_secret_config_present: bool
    archive_requested: bool = False
    request_id: str | None = None
    now_epoch_seconds: int | None = None


@dataclass(frozen=True)
class V3ControlState:
    uid: str
    schema_version: int | str | None
    configured_mode: MemoryRolloutMode
    persisted_mode: MemoryRolloutMode
    effective_mode: MemoryRolloutMode
    mode_epoch: int
    cutover_epoch: int
    account_generation: int | None
    default_memory_grant: bool
    archive_allowed: bool
    rollout_write_ready: bool
    projection_ready: bool
    global_read_gate_open: bool
    write_convergence_ready: bool


@dataclass(frozen=True)
class V3ControlReadResult:
    cohort_enrolled: bool
    source_path: str
    state: V3ControlState | None = None
    read_error_reason: V3ControlDecisionReason | None = None


@dataclass(frozen=True)
class V3ControlRouteDecision:
    route_family: V3ControlRouteFamily
    allowed: bool
    reason: V3ControlDecisionReason
    fallback_to_legacy_allowed: bool
    archive_default_available: bool
    requires_projection_reader: bool
    requires_legacy_reader: bool
    http_status: int
    legacy_offset_behavior_preserved_outside_contract: bool = False
    proof_flags: dict[str, bool] = field(default_factory=dict)


class V3ControlReader(Protocol):
    """Fake-injectable interface shape for future server-owned control reads."""

    def read_control_state(self, request: V3ControlReaderRequest) -> V3ControlReadResult:
        """Return caller-supplied control read envelope."""
        ...


def _decision(
    *,
    route_family: V3ControlRouteFamily,
    allowed: bool,
    reason: V3ControlDecisionReason,
    fallback_to_legacy_allowed: bool = False,
    archive_default_available: bool = False,
    requires_projection_reader: bool = False,
    requires_legacy_reader: bool = False,
    http_status: int = 503,
    legacy_offset_behavior_preserved_outside_contract: bool = False,
) -> V3ControlRouteDecision:
    return V3ControlRouteDecision(
        route_family=route_family,
        allowed=allowed,
        reason=reason,
        fallback_to_legacy_allowed=fallback_to_legacy_allowed,
        archive_default_available=archive_default_available,
        requires_projection_reader=requires_projection_reader,
        requires_legacy_reader=requires_legacy_reader,
        http_status=http_status,
        legacy_offset_behavior_preserved_outside_contract=legacy_offset_behavior_preserved_outside_contract,
        proof_flags={
            'runtime_wired': False,
            'production_reader_implemented': False,
            'mutation_allowed': False,
        },
    )


def _fail_closed(reason: V3ControlDecisionReason, *, http_status: int = 503) -> V3ControlRouteDecision:
    return _decision(
        route_family=V3ControlRouteFamily.FAIL_CLOSED,
        allowed=False,
        reason=reason,
        http_status=http_status,
    )


def _legacy_primary(*, reason: V3ControlDecisionReason, fallback_to_legacy_allowed: bool) -> V3ControlRouteDecision:
    return _decision(
        route_family=V3ControlRouteFamily.LEGACY_PRIMARY,
        allowed=True,
        reason=reason,
        fallback_to_legacy_allowed=fallback_to_legacy_allowed,
        requires_legacy_reader=True,
        http_status=200,
        legacy_offset_behavior_preserved_outside_contract=True,
    )


def _generation_is_stale(request: V3ControlReaderRequest, control: V3ControlState) -> bool:
    if request.expected_account_generation is None:
        return True
    if control.account_generation is None:
        return True
    return control.account_generation != request.expected_account_generation


def decide_v3_control_route(
    request: V3ControlReaderRequest,
    control_read_result: V3ControlReadResult,
) -> V3ControlRouteDecision:
    """Map adapter control-read results to a deterministic `/v3` read-route decision.

    Non-enrolled users receive only a legacy-primary route marker without requiring
    a control document. Enrolled effective off/shadow/write states are legacy
    primary because legacy remains authoritative in those rollout phases. Enrolled
    read-mode users fail closed on control, generation, gate, grant, projection,
    write-convergence, cursor, and Archive failures; no legacy fallback is allowed.
    """

    if not control_read_result.cohort_enrolled:
        return _legacy_primary(
            reason=V3ControlDecisionReason.NON_ENROLLED_LEGACY_ALLOWED,
            fallback_to_legacy_allowed=True,
        )

    if control_read_result.state is None:
        return _fail_closed(control_read_result.read_error_reason or V3ControlDecisionReason.MISSING_CONTROL_DOC)

    control = control_read_result.state
    if control.uid != request.uid:
        return _fail_closed(V3ControlDecisionReason.UID_MISMATCH)

    if control.effective_mode != MemoryRolloutMode.read:
        return _legacy_primary(
            reason=V3ControlDecisionReason.ROLLOUT_LEGACY_AUTHORITATIVE,
            fallback_to_legacy_allowed=False,
        )

    if _generation_is_stale(request, control):
        return _fail_closed(V3ControlDecisionReason.STALE_GENERATION)
    if not control.global_read_gate_open:
        return _fail_closed(V3ControlDecisionReason.GLOBAL_READ_GATE_CLOSED)
    if control.default_memory_grant is not True:
        return _fail_closed(V3ControlDecisionReason.NO_DEFAULT_MEMORY_GRANT, http_status=403)
    if not control.rollout_write_ready or not control.write_convergence_ready:
        return _fail_closed(V3ControlDecisionReason.WRITE_CONVERGENCE_NOT_READY)
    if not control.projection_ready:
        return _fail_closed(V3ControlDecisionReason.PROJECTION_NOT_READY)
    if request.cursor_memory_read_requested and not request.cursor_secret_config_present:
        return _fail_closed(V3ControlDecisionReason.INVALID_OR_MISSING_CURSOR_SECRET)
    if request.archive_requested and not control.archive_allowed:
        return _fail_closed(V3ControlDecisionReason.ARCHIVE_NOT_ALLOWED, http_status=403)

    return _decision(
        route_family=V3ControlRouteFamily.MEMORY_PROJECTION,
        allowed=True,
        reason=V3ControlDecisionReason.MEMORY_PROJECTION_ALLOWED,
        requires_projection_reader=True,
        http_status=200,
    )


# Neutral symbol aliases (memory names remain valid via shim)
V3ControlRouteFamily = V3ControlRouteFamily
V3ControlDecisionReason = V3ControlDecisionReason
V3ControlReaderRequest = V3ControlReaderRequest
V3ControlState = V3ControlState
V3ControlReadResult = V3ControlReadResult
V3ControlRouteDecision = V3ControlRouteDecision
V3ControlReader = V3ControlReader
