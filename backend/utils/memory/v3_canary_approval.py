"""Canonical module for ``utils.memory.v3_canary_approval`` (WS-G8b).

Neutral ``v3_canary_approval`` is the source of truth. Legacy ``v3_canary_approval`` remains an importable alias.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Protocol

ROUTE_SCOPE = 'GET /v3/memories'
SCHEMA_VERSION = 1
CANARY_COHORTS = {'shadow', 'canary_1', 'canary_5', 'canary_25'}
APPROVAL_STATUSES = {'pending', 'approved', 'rejected'}
_APPROVAL_OWNERS = {'product_privacy_ops'}
_ROLLBACK_OWNERS = {'memory_platform_oncall', 'product_privacy_ops'}
_MONITORING_GATE_IDS = {'fail_closed_rate', 'p95_latency_ms', 'error_rate', 'projection_freshness_seconds'}
_MONITORING_METRICS = {
    'v3_fail_closed_rate',
    'v3_get_p95_latency_ms',
    'v3_error_rate',
    'v3_projection_freshness_seconds',
}
_SENSITIVE_OR_HIGH_CARDINALITY_KEYS = {
    'uid',
    'user_id',
    'user',
    'session_id',
    'memory_id',
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
_SENSITIVE_OR_HIGH_CARDINALITY_VALUE_MARKERS = (
    'uid_',
    'user_',
    'user-',
    'sess_',
    'session_',
    'session-',
    'cursor_',
    'cursor-',
    'cursor_token',
    'secret',
    'token_',
)


@dataclass(frozen=True)
class V3CanaryApprovalArtifact:
    schema_version: int
    artifact_id: str
    route_scope: str
    owner: str
    status: str
    cohort: str
    issued_at: str
    expires_at: str
    approval_id: str
    approved_at: str
    approved_by: str
    rollback_owner: str
    rollback_disable_gate: str
    rollback_steps: tuple[str, ...]
    monitoring_gate_ids: tuple[str, ...]

    @classmethod
    def from_dict(cls, artifact: dict[str, Any]) -> 'V3CanaryApprovalArtifact':
        if not isinstance(artifact, dict):
            raise ValueError('artifact_malformed')
        required_top_level = {
            'schema_version',
            'artifact_id',
            'route_scope',
            'owner',
            'status',
            'cohort',
            'issued_at',
            'expires_at',
            'approval',
            'rollback_plan',
            'monitoring_gates',
        }
        if not required_top_level.issubset(artifact):
            raise ValueError('artifact_malformed')
        approval = artifact.get('approval')
        rollback_plan = artifact.get('rollback_plan')
        monitoring_gates = artifact.get('monitoring_gates')
        if not isinstance(approval, dict) or not approval:
            raise ValueError('approval_missing')
        if not isinstance(rollback_plan, dict) or not rollback_plan:
            raise ValueError('rollback_plan_missing')
        if not isinstance(monitoring_gates, list) or not monitoring_gates:
            raise ValueError('monitoring_gates_missing')
        try:
            return cls(
                schema_version=artifact['schema_version'],
                artifact_id=artifact['artifact_id'],
                route_scope=artifact['route_scope'],
                owner=artifact['owner'],
                status=artifact['status'],
                cohort=artifact['cohort'],
                issued_at=artifact['issued_at'],
                expires_at=artifact['expires_at'],
                approval_id=approval['approval_id'],
                approved_at=approval['approved_at'],
                approved_by=approval['approved_by'],
                rollback_owner=rollback_plan['owner'],
                rollback_disable_gate=rollback_plan['disable_gate'],
                rollback_steps=tuple(rollback_plan['steps']),
                monitoring_gate_ids=tuple(gate['gate_id'] for gate in monitoring_gates),
            )
        except (KeyError, TypeError):
            raise ValueError('artifact_malformed') from None


@dataclass(frozen=True)
class V3CanaryApprovalDecision:
    approved: bool
    fail_closed: bool
    reason: str
    route_scope: str
    canary_cohort: str
    canary_enrollment: str
    approval_owner: str
    approval_status: str
    approval_artifact_status: str
    runtime_wired: bool = False
    production_rollout_approved: bool = False
    approval_claimed: bool = False


class V3CanaryApprovalArtifactReader(Protocol):
    """Fake-injectable future server-owned artifact reader shape."""

    production_reader_call: bool
    reader_name: str

    def read_canary_approval_artifact(self, *, route_scope: str, cohort: str) -> dict[str, Any] | None:
        """Return a caller-injected artifact dict for local validation."""
        ...


def read_memory_v3_canary_approval_artifact_decision(
    *,
    reader: V3CanaryApprovalArtifactReader | None,
    requested_route_scope: str,
    requested_cohort: str,
    now: datetime,
) -> V3CanaryApprovalDecision:
    """Read an injected canary/approval artifact and validate it fail-closed.

    This is a readiness seam only. The reader is supplied by tests or future
    approved server-owned wiring; this function does not construct production
    clients, import routers, call Firestore/cloud/provider/network services, or
    emit telemetry. Missing readers, reader exceptions/timeouts, production-reader
    markers, and invalid artifacts all fail closed before any runtime approval is
    claimed.
    """

    if reader is None:
        return _blocked('artifact_reader_missing', requested_cohort=requested_cohort)
    if getattr(reader, 'production_reader_call', False) is True:
        return _blocked('artifact_reader_production_call_disallowed', requested_cohort=requested_cohort)
    try:
        artifact = reader.read_canary_approval_artifact(
            route_scope=requested_route_scope,
            cohort=requested_cohort,
        )
    except Exception:
        return _blocked('artifact_reader_failed', requested_cohort=requested_cohort)
    return validate_memory_v3_canary_approval_artifact(
        artifact,
        requested_route_scope=requested_route_scope,
        requested_cohort=requested_cohort,
        now=now,
    )


def validate_memory_v3_canary_approval_artifact(
    artifact: dict[str, Any] | None,
    *,
    requested_route_scope: str,
    requested_cohort: str,
    now: datetime,
) -> V3CanaryApprovalDecision:
    """Validate a future server-owned canary approval artifact, failing closed.

    Approval timestamps/ids are validated only as metadata. This local seam never
    claims production rollout approval and never wires runtime behavior.
    """

    if requested_cohort not in CANARY_COHORTS:
        return _blocked('unsupported_cohort', requested_cohort=requested_cohort)
    if artifact is None:
        return _blocked('artifact_missing', requested_cohort=requested_cohort)
    try:
        parsed = V3CanaryApprovalArtifact.from_dict(artifact)
    except ValueError as exc:
        return _blocked(str(exc), requested_cohort=requested_cohort)

    if parsed.schema_version != SCHEMA_VERSION:
        return _blocked('artifact_malformed', parsed)
    if (
        parsed.route_scope != ROUTE_SCOPE
        or requested_route_scope != ROUTE_SCOPE
        or parsed.route_scope != requested_route_scope
    ):
        return _blocked('route_scope_mismatch', parsed)
    if parsed.cohort not in CANARY_COHORTS:
        return _blocked('unsupported_cohort', parsed)
    high_cardinality_reason = _find_high_cardinality_or_sensitive_misuse(artifact)
    if high_cardinality_reason is not None:
        return _blocked(high_cardinality_reason, parsed)
    if parsed.owner not in _APPROVAL_OWNERS or parsed.approved_by not in _APPROVAL_OWNERS:
        return _blocked('artifact_malformed', parsed)
    if parsed.cohort != requested_cohort:
        return _blocked('cohort_mismatch', parsed)
    if parsed.status not in APPROVAL_STATUSES:
        return _blocked('artifact_malformed', parsed)
    if parsed.status == 'pending':
        return _blocked('approval_pending', parsed)
    if parsed.status == 'rejected':
        return _blocked('approval_rejected', parsed)
    if parsed.status != 'approved':
        return _blocked('approval_missing', parsed)
    if not parsed.approval_id or not parsed.approved_at:
        return _blocked('approval_missing', parsed)
    if parsed.rollback_owner not in _ROLLBACK_OWNERS:
        return _blocked('rollback_plan_missing', parsed)
    if parsed.rollback_disable_gate != 'emergency_read_disable' or not parsed.rollback_steps:
        return _blocked('rollback_plan_missing', parsed)
    if not parsed.monitoring_gate_ids or any(
        gate_id not in _MONITORING_GATE_IDS for gate_id in parsed.monitoring_gate_ids
    ):
        return _blocked('monitoring_gates_missing', parsed)
    if not _monitoring_gates_valid(artifact.get('monitoring_gates')):
        return _blocked('monitoring_gates_missing', parsed)
    if _parse_datetime(parsed.expires_at) <= _normalize_now(now):
        return _blocked('artifact_stale', parsed)
    if _parse_datetime(parsed.issued_at) > _normalize_now(now) or _parse_datetime(parsed.approved_at) > _normalize_now(
        now
    ):
        return _blocked('artifact_malformed', parsed)
    return V3CanaryApprovalDecision(
        approved=True,
        fail_closed=False,
        reason='approved',
        route_scope=ROUTE_SCOPE,
        canary_cohort=parsed.cohort,
        canary_enrollment='enrolled',
        approval_owner=parsed.owner,
        approval_status='approved',
        approval_artifact_status='valid_approved',
    )


def build_v3_canary_approval_telemetry_labels(decision: V3CanaryApprovalDecision) -> dict[str, str]:
    """Return only bounded labels suitable for future local telemetry builders."""

    labels = {
        'canary_cohort': decision.canary_cohort,
        'canary_enrollment': decision.canary_enrollment,
        'approval_owner': decision.approval_owner,
        'approval_status': decision.approval_status,
        'approval_artifact_status': decision.approval_artifact_status,
        'route_scope': decision.route_scope,
    }
    if _find_high_cardinality_or_sensitive_misuse(labels) is not None:
        raise ValueError('telemetry labels contain high-cardinality or sensitive material')
    return labels


def _blocked(
    reason: str,
    parsed: V3CanaryApprovalArtifact | None = None,
    *,
    requested_cohort: str | None = None,
) -> V3CanaryApprovalDecision:
    return V3CanaryApprovalDecision(
        approved=False,
        fail_closed=True,
        reason=reason,
        route_scope=parsed.route_scope if parsed is not None else ROUTE_SCOPE,
        canary_cohort=parsed.cohort if parsed is not None else requested_cohort or 'none',
        canary_enrollment='unknown_fail_closed',
        approval_owner=parsed.owner if parsed is not None and parsed.owner in _APPROVAL_OWNERS else 'missing',
        approval_status=parsed.status if parsed is not None and parsed.status in APPROVAL_STATUSES else 'missing',
        approval_artifact_status='invalid_fail_closed',
    )


def _parse_datetime(value: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError('artifact_malformed')
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        raise ValueError('artifact_malformed') from None
    return _normalize_now(parsed)


def _normalize_now(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _monitoring_gates_valid(monitoring_gates: Any) -> bool:
    if not isinstance(monitoring_gates, list) or not monitoring_gates:
        return False
    for gate in monitoring_gates:
        if not isinstance(gate, dict):
            return False
        if gate.get('gate_id') not in _MONITORING_GATE_IDS:
            return False
        if gate.get('metric') not in _MONITORING_METRICS:
            return False
        threshold = gate.get('max_threshold')
        if not isinstance(threshold, (int, float)) or isinstance(threshold, bool) or threshold < 0:
            return False
    return True


def _find_high_cardinality_or_sensitive_misuse(value: Any) -> str | None:
    if isinstance(value, dict):
        for key, child in value.items():
            if str(key) in _SENSITIVE_OR_HIGH_CARDINALITY_KEYS:
                return 'high_cardinality_or_sensitive_key'
            child_reason = _find_high_cardinality_or_sensitive_misuse(child)
            if child_reason is not None:
                return child_reason
    elif isinstance(value, (list, tuple)):
        for child in value:
            child_reason = _find_high_cardinality_or_sensitive_misuse(child)
            if child_reason is not None:
                return child_reason
    elif isinstance(value, str):
        lowered = value.lower()
        if any(marker in lowered for marker in _SENSITIVE_OR_HIGH_CARDINALITY_VALUE_MARKERS):
            return 'high_cardinality_or_sensitive_value'
    return None


# Neutral symbol aliases (memory names remain valid via shim)
V3CanaryApprovalArtifact = V3CanaryApprovalArtifact
V3CanaryApprovalDecision = V3CanaryApprovalDecision
V3CanaryApprovalArtifactReader = V3CanaryApprovalArtifactReader
