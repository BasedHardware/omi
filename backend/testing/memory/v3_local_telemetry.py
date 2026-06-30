"""Canonical module for ``utils.memory.v3_local_telemetry`` (WS-G8b).

Neutral ``v3_local_telemetry`` is the source of truth. Legacy ``v3_local_telemetry`` remains an importable alias.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

EVENT_NAME = 'v3_get_memory_read_decision'
EVENT_ROUTE = 'GET /v3/memories'
SCHEMA_VERSION = 1

READ_SOURCES = {'legacy_primary', 'memory_compatibility_projection', 'fail_closed'}
ROUTE_DECISIONS = {'use_legacy_safe', 'use_memory', 'deny_memory', 'fail_closed'}
FAILURE_REASONS = {
    'none',
    'control_missing',
    'control_malformed',
    'control_timeout',
    'uid_mismatch',
    'no_default_memory_grant',
    'account_generation_mismatch',
    'projection_not_ready',
    'write_convergence_not_ready',
    'cursor_invalid',
    'rollback_read_disabled',
    'archive_default_unavailable',
}
CURSOR_VALIDATION_RESULTS = {'not_present', 'valid', 'invalid'}
CURSOR_VALIDATION_REASONS = {
    'none',
    'not_present',
    'cursor_tampered',
    'cursor_expired',
    'uid_mismatch',
    'account_generation_mismatch',
    'projection_generation_mismatch',
    'filter_mismatch',
    'source_mismatch',
    'read_mode_mismatch',
    'unsupported_cursor_version',
}
CANARY_COHORTS = {'none', 'shadow', 'canary_1', 'canary_5', 'canary_25', 'general_availability'}
CANARY_ENROLLMENTS = {'not_enrolled', 'enrolled', 'unknown_fail_closed'}
PROJECTION_SOURCES = {'none', 'memory_derived_compatibility_projection'}
ARCHIVE_DEFAULT_VISIBILITY_DECISIONS = {'default_unavailable', 'explicitly_authorized', 'denied'}
SHORT_TERM_DEFAULT_VISIBILITY_DECISIONS = {'fresh_visible', 'stale_hidden', 'not_applicable'}
ROLLBACK_READ_DISABLE_GATES = {'not_wired', 'disabled', 'enabled'}
APPROVAL_STATUSES = {'missing', 'pending', 'approved', 'rejected'}
APPROVAL_OWNERS = {'missing', 'product_privacy_ops'}

FORBIDDEN_EXTRA_LABEL_KEYS = {
    'uid',
    'user_id',
    'user',
    'memory_id',
    'session_id',
    'cursor',
    'cursor_token',
    'token',
    'secret',
    'signature',
    'request_payload',
    'payload',
    'body',
    'memory_content',
    'content',
    'text',
    'transcript',
    'email',
    'name',
}


@dataclass(frozen=True)
class V3LocalTelemetryInput:
    read_source: str
    route_decision: str
    failure_reason: str
    control_generation: int | None
    projection_generation: int | None
    account_generation: int | None
    cursor_validation_result: str
    cursor_validation_reason: str
    canary_cohort: str
    canary_enrollment: str
    no_legacy_fallback: bool
    projection_source: str
    request_limit: int
    request_cursor_present: bool
    request_offset_disallowed_in_v3: bool
    archive_default_visibility_decision: str
    short_term_default_visibility_decision: str
    rollback_read_disable_gate: str
    approval_owner: str = 'missing'
    approval_status: str = 'missing'
    extra_labels: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class V3ReadDisableConfig:
    schema_version: int
    memory_reads_enabled: bool
    emergency_read_disable: bool


@dataclass(frozen=True)
class V3ReadDisableDecision:
    memory_reads_enabled: bool
    rollback_read_disable_gate: str
    failure_reason: str
    fail_closed: bool
    source: str


@dataclass(frozen=True)
class V3TelemetryEmitResult:
    emitted: bool
    production_sink_call: bool
    event: dict[str, Any]


class V3TelemetrySink(Protocol):
    production_sink_call: bool
    sink_name: str

    def emit(self, event: dict[str, Any]) -> None:
        """Emit a pre-built sanitized event."""


class NullV3TelemetrySink:
    sink_name = 'null_noop_sink'
    production_sink_call = False

    @property
    def events(self) -> list[dict[str, Any]]:
        return []

    def emit(self, event: dict[str, Any]) -> None:
        return None


class FakeV3TelemetrySink:
    sink_name = 'fake_local_test_sink'
    production_sink_call = False

    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    def emit(self, event: dict[str, Any]) -> None:
        self.events.append(dict(event))


def decide_v3_read_disable(
    *, config: V3ReadDisableConfig | dict[str, Any] | None, enrolled_memory_user: bool
) -> V3ReadDisableDecision:
    """Pure server-owned read-disable decision seam for future memory `/v3` GET.

    Missing/malformed config fails closed for enrolled memory users. Non-enrolled
    callers are outside this memory seam and retain the legacy-primary planner path
    once real route wiring exists.
    """

    if not enrolled_memory_user:
        return V3ReadDisableDecision(
            memory_reads_enabled=False,
            rollback_read_disable_gate='not_wired',
            failure_reason='none',
            fail_closed=False,
            source='non_enrolled_legacy_primary',
        )
    if config is None:
        return _disabled_decision('control_missing')
    if isinstance(config, dict):
        try:
            config = V3ReadDisableConfig(
                schema_version=config['schema_version'],
                memory_reads_enabled=config['memory_reads_enabled'],
                emergency_read_disable=config['emergency_read_disable'],
            )
        except (KeyError, TypeError):
            return _disabled_decision('control_malformed')
    if not isinstance(config, V3ReadDisableConfig):
        return _disabled_decision('control_malformed')
    if config.schema_version != SCHEMA_VERSION:
        return _disabled_decision('control_malformed')
    if not isinstance(config.memory_reads_enabled, bool) or not isinstance(config.emergency_read_disable, bool):
        return _disabled_decision('control_malformed')
    if config.emergency_read_disable:
        return _disabled_decision('rollback_read_disabled')
    if not config.memory_reads_enabled:
        return _disabled_decision('rollback_read_disabled')
    return V3ReadDisableDecision(
        memory_reads_enabled=True,
        rollback_read_disable_gate='enabled',
        failure_reason='none',
        fail_closed=False,
        source='server_owned_config_object',
    )


def build_v3_get_telemetry_event(telemetry_input: V3LocalTelemetryInput) -> dict[str, Any]:
    """Build a sanitized low-cardinality local event for future GET decisions."""

    _validate_input(telemetry_input)
    event = {
        'event_name': EVENT_NAME,
        'schema_version': SCHEMA_VERSION,
        'route': EVENT_ROUTE,
        'read_source': telemetry_input.read_source,
        'route_decision': telemetry_input.route_decision,
        'failure_reason': telemetry_input.failure_reason,
        'control_generation': _bounded_generation('control_generation', telemetry_input.control_generation),
        'projection_generation': _bounded_generation('projection_generation', telemetry_input.projection_generation),
        'account_generation': _bounded_generation('account_generation', telemetry_input.account_generation),
        'cursor_validation_result': telemetry_input.cursor_validation_result,
        'cursor_validation_reason': telemetry_input.cursor_validation_reason,
        'canary_cohort': telemetry_input.canary_cohort,
        'canary_enrollment': telemetry_input.canary_enrollment,
        'no_legacy_fallback': telemetry_input.no_legacy_fallback,
        'projection_source': telemetry_input.projection_source,
        'request_limit': _bucket_request_limit(telemetry_input.request_limit),
        'request_cursor_present': telemetry_input.request_cursor_present,
        'request_offset_disallowed_in_v3': telemetry_input.request_offset_disallowed_in_v3,
        'archive_default_visibility_decision': telemetry_input.archive_default_visibility_decision,
        'short_term_default_visibility_decision': telemetry_input.short_term_default_visibility_decision,
        'rollback_read_disable_gate': telemetry_input.rollback_read_disable_gate,
        'approval_owner': telemetry_input.approval_owner,
        'approval_status': telemetry_input.approval_status,
        'runtime_wired': False,
        'production_sink_call': False,
    }
    return event


def emit_v3_get_telemetry(
    telemetry_input: V3LocalTelemetryInput, *, sink: V3TelemetrySink | None = None
) -> V3TelemetryEmitResult:
    """Build and optionally emit to an injected local/fake sink.

    The default sink is no-op, proving no production telemetry calls occur unless
    future approved route wiring injects a real sink.
    """

    active_sink = sink or NullV3TelemetrySink()
    event = build_v3_get_telemetry_event(telemetry_input)
    event['telemetry_sink'] = active_sink.sink_name
    if isinstance(active_sink, NullV3TelemetrySink):
        return V3TelemetryEmitResult(emitted=False, production_sink_call=False, event=event)
    active_sink.emit(event)
    return V3TelemetryEmitResult(emitted=True, production_sink_call=active_sink.production_sink_call, event=event)


def _disabled_decision(failure_reason: str) -> V3ReadDisableDecision:
    return V3ReadDisableDecision(
        memory_reads_enabled=False,
        rollback_read_disable_gate='disabled',
        failure_reason=failure_reason,
        fail_closed=True,
        source='server_owned_config_object',
    )


def _validate_input(telemetry_input: V3LocalTelemetryInput) -> None:
    _require_enum('read_source', telemetry_input.read_source, READ_SOURCES)
    _require_enum('route_decision', telemetry_input.route_decision, ROUTE_DECISIONS)
    _require_enum('failure_reason', telemetry_input.failure_reason, FAILURE_REASONS)
    _require_enum('cursor_validation_result', telemetry_input.cursor_validation_result, CURSOR_VALIDATION_RESULTS)
    _require_enum('cursor_validation_reason', telemetry_input.cursor_validation_reason, CURSOR_VALIDATION_REASONS)
    _require_enum('canary_cohort', telemetry_input.canary_cohort, CANARY_COHORTS)
    _require_enum('canary_enrollment', telemetry_input.canary_enrollment, CANARY_ENROLLMENTS)
    _require_enum('projection_source', telemetry_input.projection_source, PROJECTION_SOURCES)
    _require_enum(
        'archive_default_visibility_decision',
        telemetry_input.archive_default_visibility_decision,
        ARCHIVE_DEFAULT_VISIBILITY_DECISIONS,
    )
    _require_enum(
        'short_term_default_visibility_decision',
        telemetry_input.short_term_default_visibility_decision,
        SHORT_TERM_DEFAULT_VISIBILITY_DECISIONS,
    )
    _require_enum('rollback_read_disable_gate', telemetry_input.rollback_read_disable_gate, ROLLBACK_READ_DISABLE_GATES)
    _require_enum('approval_owner', telemetry_input.approval_owner, APPROVAL_OWNERS)
    _require_enum('approval_status', telemetry_input.approval_status, APPROVAL_STATUSES)
    _require_bool('no_legacy_fallback', telemetry_input.no_legacy_fallback)
    _require_bool('request_cursor_present', telemetry_input.request_cursor_present)
    _require_bool('request_offset_disallowed_in_v3', telemetry_input.request_offset_disallowed_in_v3)
    _validate_extra_labels(telemetry_input.extra_labels)


def _require_enum(field_name: str, value: str, allowed_values: set[str]) -> None:
    if value not in allowed_values:
        raise ValueError(f'{field_name} must be one of {sorted(allowed_values)}')


def _require_bool(field_name: str, value: bool) -> None:
    if not isinstance(value, bool):
        raise ValueError(f'{field_name} must be boolean')


def _bounded_generation(field_name: str, value: int | None) -> int | None:
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool) or value < 0 or value > 2_147_483_647:
        raise ValueError(f'{field_name} must be a bounded non-negative integer or None')
    return value


def _bucket_request_limit(limit: int) -> str:
    if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1:
        raise ValueError('request_limit must be a positive integer')
    if limit <= 25:
        return '1_25'
    if limit <= 100:
        return '26_100'
    if limit <= 500:
        return '101_500'
    return 'over_max_rejected'


def _validate_extra_labels(extra_labels: dict[str, str]) -> None:
    if not isinstance(extra_labels, dict):
        raise ValueError('extra_labels must be a dictionary')
    for key in extra_labels:
        if key in FORBIDDEN_EXTRA_LABEL_KEYS:
            raise ValueError(f'extra_labels may not include forbidden key {key}')
        raise ValueError('extra_labels are not accepted by this local low-cardinality event')


# Neutral symbol aliases (memory names remain valid via shim)
V3LocalTelemetryInput = V3LocalTelemetryInput
V3ReadDisableConfig = V3ReadDisableConfig
V3ReadDisableDecision = V3ReadDisableDecision
V3TelemetryEmitResult = V3TelemetryEmitResult
V3TelemetrySink = V3TelemetrySink
