"""Pure/local fake-injectable `/v3` V17 control-reader decision contract.

The module defines the typed input/output seam that future server-side `/v3` GET
runtime wiring can consume after real control-source, security, and runtime
evidence exists. It intentionally performs no I/O, imports no web/database/cloud
clients, and does not wire routes or choose a production control-document path.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Protocol


class V17V3ControlRouteFamily(str, Enum):
    LEGACY_PRIMARY = 'legacy_primary'
    V17_PROJECTION = 'v17_projection'
    FAIL_CLOSED = 'fail_closed'


class V17V3ControlDecisionReason(str, Enum):
    NON_ENROLLED_LEGACY_ALLOWED = 'non_enrolled_legacy_allowed'
    V17_PROJECTION_ALLOWED = 'v17_projection_allowed'
    MISSING_CONTROL_DOC = 'missing_control_doc'
    STALE_GENERATION = 'stale_generation'
    NO_DEFAULT_MEMORY_GRANT = 'no_default_memory_grant'
    PROJECTION_NOT_READY = 'projection_not_ready'
    WRITE_CONVERGENCE_NOT_READY = 'write_convergence_not_ready'
    INVALID_OR_MISSING_CURSOR_SECRET = 'invalid_or_missing_cursor_secret'
    ARCHIVE_NOT_ALLOWED = 'archive_not_allowed'
    STALE_SHORT_TERM_DEFAULT_HIDDEN = 'stale_short_term_default_hidden'


@dataclass(frozen=True)
class V17V3ControlReaderRequest:
    uid: str
    expected_account_generation: int | None
    cursor_v17_read_requested: bool
    cursor_secret_config_present: bool
    archive_requested: bool = False
    request_id: str | None = None
    now_epoch_seconds: int | None = None


@dataclass(frozen=True)
class V17V3ControlState:
    uid: str
    cohort_enrolled: bool
    default_memory_grant: bool | None
    account_generation: int | None
    control_generation: int | None
    projection_ready: bool
    write_convergence_ready: bool
    archive_allowed: bool = False
    short_term_freshness_default_visible: bool = False
    schema_version: str | None = None
    source_generation: int | None = None


@dataclass(frozen=True)
class V17V3ControlRouteDecision:
    route_family: V17V3ControlRouteFamily
    allowed: bool
    reason: V17V3ControlDecisionReason
    fallback_to_legacy_allowed: bool
    archive_default_available: bool
    stale_short_term_default_visible: bool
    requires_projection_reader: bool
    requires_legacy_reader: bool
    http_status: int
    legacy_offset_behavior_preserved_outside_contract: bool = False
    proof_flags: dict[str, bool] = field(default_factory=dict)


class V17V3ControlReader(Protocol):
    """Fake-injectable interface shape for future server-owned control reads."""

    def read_control_state(self, request: V17V3ControlReaderRequest) -> V17V3ControlState | None:
        """Return caller-supplied control state, or None when the doc/source is missing."""


def _decision(
    *,
    route_family: V17V3ControlRouteFamily,
    allowed: bool,
    reason: V17V3ControlDecisionReason,
    fallback_to_legacy_allowed: bool = False,
    archive_default_available: bool = False,
    stale_short_term_default_visible: bool = False,
    requires_projection_reader: bool = False,
    requires_legacy_reader: bool = False,
    http_status: int = 503,
    legacy_offset_behavior_preserved_outside_contract: bool = False,
) -> V17V3ControlRouteDecision:
    return V17V3ControlRouteDecision(
        route_family=route_family,
        allowed=allowed,
        reason=reason,
        fallback_to_legacy_allowed=fallback_to_legacy_allowed,
        archive_default_available=archive_default_available,
        stale_short_term_default_visible=stale_short_term_default_visible,
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


def _fail_closed(reason: V17V3ControlDecisionReason, *, http_status: int = 503) -> V17V3ControlRouteDecision:
    return _decision(
        route_family=V17V3ControlRouteFamily.FAIL_CLOSED,
        allowed=False,
        reason=reason,
        http_status=http_status,
    )


def _generation_is_stale(request: V17V3ControlReaderRequest, control: V17V3ControlState) -> bool:
    if request.expected_account_generation is None:
        return True
    if control.account_generation is None or control.control_generation is None:
        return True
    if control.account_generation != request.expected_account_generation:
        return True
    return control.control_generation < request.expected_account_generation


def decide_v17_v3_control_route(
    request: V17V3ControlReaderRequest,
    control_state: V17V3ControlState | None,
) -> V17V3ControlRouteDecision:
    """Map fake-injected control state to a deterministic `/v3` read-route decision.

    Non-enrolled users receive only a legacy-primary route marker; the existing
    legacy offset behavior, including first-page `offset=0 -> limit=5000`, stays
    outside this contract. Enrolled or unknown gated states fail closed and never
    downgrade to legacy on control, grant, projection, write, cursor, Archive, or
    Short-term visibility failures.
    """

    if control_state is None:
        return _fail_closed(V17V3ControlDecisionReason.MISSING_CONTROL_DOC)

    if not control_state.cohort_enrolled:
        return _decision(
            route_family=V17V3ControlRouteFamily.LEGACY_PRIMARY,
            allowed=True,
            reason=V17V3ControlDecisionReason.NON_ENROLLED_LEGACY_ALLOWED,
            fallback_to_legacy_allowed=True,
            requires_legacy_reader=True,
            http_status=200,
            legacy_offset_behavior_preserved_outside_contract=True,
        )

    if _generation_is_stale(request, control_state):
        return _fail_closed(V17V3ControlDecisionReason.STALE_GENERATION)
    if control_state.default_memory_grant is not True:
        return _fail_closed(V17V3ControlDecisionReason.NO_DEFAULT_MEMORY_GRANT, http_status=403)
    if not control_state.projection_ready:
        return _fail_closed(V17V3ControlDecisionReason.PROJECTION_NOT_READY)
    if not control_state.write_convergence_ready:
        return _fail_closed(V17V3ControlDecisionReason.WRITE_CONVERGENCE_NOT_READY)
    if request.cursor_v17_read_requested and not request.cursor_secret_config_present:
        return _fail_closed(V17V3ControlDecisionReason.INVALID_OR_MISSING_CURSOR_SECRET)
    if request.archive_requested and not control_state.archive_allowed:
        return _fail_closed(V17V3ControlDecisionReason.ARCHIVE_NOT_ALLOWED, http_status=404)
    if not control_state.short_term_freshness_default_visible:
        return _fail_closed(V17V3ControlDecisionReason.STALE_SHORT_TERM_DEFAULT_HIDDEN)

    return _decision(
        route_family=V17V3ControlRouteFamily.V17_PROJECTION,
        allowed=True,
        reason=V17V3ControlDecisionReason.V17_PROJECTION_ALLOWED,
        requires_projection_reader=True,
        http_status=200,
        stale_short_term_default_visible=True,
    )
