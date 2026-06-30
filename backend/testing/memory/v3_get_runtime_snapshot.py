"""Canonical module for ``utils.memory.v3_get_runtime_snapshot`` (WS-G8b).

Neutral ``v3_get_runtime_snapshot`` is the source of truth. Legacy ``v3_get_runtime_snapshot`` remains an importable alias.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Mapping

SnapshotStatus = Literal['READY', 'BLOCKED']

LOW_CARDINALITY_RUNTIME_SNAPSHOT_REASONS = frozenset(
    {
        'snapshot_coherent',
        'subject_uid_mismatch',
        'missing_default_memory_grant',
        'missing_runtime_config_version',
        'stale_runtime_config',
        'generation_mismatch',
        'projection_not_converged',
        'write_not_converged',
        'delete_not_converged',
        'tombstone_not_converged',
        'missing_cursor_policy_version',
        'missing_cursor_secret_version',
        'archive_capability_missing',
        'deadline_expired_or_missing',
        'future_read_timestamp',
        'invalid_read_timestamp',
        'malformed_source_output',
    }
)

_SERVER_OWNED_FLAGS = (
    'server_owned_subject',
    'server_owned_control',
    'server_owned_grant',
    'server_owned_runtime_config',
    'server_owned_generation',
    'server_owned_projection',
    'server_owned_convergence',
    'server_owned_cursor',
    'server_owned_deadline',
    'server_owned_read_timestamp',
)


def _bool_text(value: bool) -> str:
    return 'true' if value else 'false'


@dataclass(frozen=True)
class V3GetRuntimeSnapshotInput:
    """Server-supplied components required to build a coherent GET runtime snapshot.

    Subject-like fields intentionally accept raw strings here so the pure builder
    can detect malformed adapter output and fail closed without leaking values.
    """

    authenticated_subject_uid: str
    control_subject_uid: str
    grant_subject_uid: str
    projection_subject_uid: str
    cursor_subject_uid: str
    cohort: str
    control_generation: int
    default_memory_grant: bool
    runtime_config_version: str | None
    runtime_config_stale: bool
    account_generation: int
    projection_generation: int
    projection_commit: str | None
    projection_converged: bool
    write_converged: bool
    delete_converged: bool
    tombstone_converged: bool
    cursor_policy_version: str | None
    cursor_secret_version: str | None
    archive_capability: bool
    archive_requested: bool
    deadline_ms: int | None
    deadline_remaining_ms: int | None
    read_timestamp_ms: int | None
    server_now_ms: int
    read_timestamp_max_future_skew_ms: int = 1000
    route: str = 'GET /v3/memories'
    server_owned_subject: bool = True
    server_owned_control: bool = True
    server_owned_grant: bool = True
    server_owned_runtime_config: bool = True
    server_owned_generation: bool = True
    server_owned_projection: bool = True
    server_owned_convergence: bool = True
    server_owned_cursor: bool = True
    server_owned_deadline: bool = True
    server_owned_read_timestamp: bool = True


@dataclass(frozen=True)
class V3GetRuntimeSnapshot:
    """Coherent, request-scoped runtime snapshot for a future memory projection read."""

    subject_uid: str
    cohort: str
    default_memory_grant: bool
    runtime_config_version_present: bool
    account_generation: int
    projection_generation: int
    control_generation: int
    projection_commit_present: bool
    write_converged: bool
    delete_converged: bool
    tombstone_converged: bool
    cursor_policy_version_present: bool
    cursor_secret_version_present: bool
    archive_capability: bool
    archive_requested: bool
    deadline_ms: int
    deadline_remaining_ms: int
    read_timestamp_ms: int


@dataclass(frozen=True)
class V3GetRuntimeSnapshotResult:
    status: SnapshotStatus
    reason: str
    http_status: int
    snapshot: V3GetRuntimeSnapshot | None = None
    log_fields: Mapping[str, str] = field(default_factory=dict)
    route_wired: bool = False
    runtime_behavior_changed: bool = False
    production_call_count: int = 0
    firestore_write_count: int = 0
    network_call_count: int = 0
    telemetry_sink_call_count: int = 0
    provider_or_vector_call_count: int = 0


def _log_fields(source: V3GetRuntimeSnapshotInput, *, status: SnapshotStatus, reason: str) -> dict[str, str]:
    return {
        'route': source.route,
        'status': status,
        'reason': reason,
        'cohort': source.cohort if isinstance(source.cohort, str) and source.cohort else 'unknown',
        'archive_requested': _bool_text(source.archive_requested is True),
        'archive_capability': _bool_text(source.archive_capability is True),
    }


def _result(
    source: V3GetRuntimeSnapshotInput,
    *,
    status: SnapshotStatus,
    reason: str,
    http_status: int,
    snapshot: V3GetRuntimeSnapshot | None = None,
) -> V3GetRuntimeSnapshotResult:
    if reason not in LOW_CARDINALITY_RUNTIME_SNAPSHOT_REASONS:
        raise ValueError('unsupported_memory_v3_runtime_snapshot_reason')
    return V3GetRuntimeSnapshotResult(
        status=status,
        reason=reason,
        http_status=http_status,
        snapshot=snapshot,
        log_fields=_log_fields(source, status=status, reason=reason),
    )


def _non_empty_string(value: object) -> bool:
    return isinstance(value, str) and bool(value)


def _valid_bool(value: object) -> bool:
    return isinstance(value, bool)


def _valid_non_negative_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _malformed(source: V3GetRuntimeSnapshotInput) -> bool:
    if any(getattr(source, flag) is not True for flag in _SERVER_OWNED_FLAGS):
        return True
    if not all(
        _non_empty_string(value)
        for value in (
            source.authenticated_subject_uid,
            source.control_subject_uid,
            source.grant_subject_uid,
            source.projection_subject_uid,
            source.cursor_subject_uid,
            source.cohort,
        )
    ):
        return True
    if not all(
        _valid_bool(value)
        for value in (
            source.default_memory_grant,
            source.runtime_config_stale,
            source.projection_converged,
            source.write_converged,
            source.delete_converged,
            source.tombstone_converged,
            source.archive_capability,
            source.archive_requested,
        )
    ):
        return True
    if not all(
        _valid_non_negative_int(value)
        for value in (
            source.control_generation,
            source.account_generation,
            source.projection_generation,
            source.server_now_ms,
            source.read_timestamp_max_future_skew_ms,
        )
    ):
        return True
    if source.runtime_config_version is not None and not _non_empty_string(source.runtime_config_version):
        return True
    if source.projection_commit is not None and not _non_empty_string(source.projection_commit):
        return True
    if source.cursor_policy_version is not None and not _non_empty_string(source.cursor_policy_version):
        return True
    if source.cursor_secret_version is not None and not _non_empty_string(source.cursor_secret_version):
        return True
    if source.deadline_ms is not None and not _valid_non_negative_int(source.deadline_ms):
        return True
    if source.deadline_remaining_ms is not None and not _valid_non_negative_int(source.deadline_remaining_ms):
        return True
    if source.read_timestamp_ms is not None and not _valid_non_negative_int(source.read_timestamp_ms):
        return True
    return False


def build_v3_get_runtime_snapshot(
    source: V3GetRuntimeSnapshotInput,
) -> V3GetRuntimeSnapshotResult:
    """Build a coherent snapshot or return a bounded fail-closed reason."""

    if not isinstance(source, V3GetRuntimeSnapshotInput):
        raise TypeError('source must be V3GetRuntimeSnapshotInput')

    if _malformed(source):
        return _result(source, status='BLOCKED', reason='malformed_source_output', http_status=503)

    subjects = {
        source.authenticated_subject_uid,
        source.control_subject_uid,
        source.grant_subject_uid,
        source.projection_subject_uid,
        source.cursor_subject_uid,
    }
    if len(subjects) != 1:
        return _result(source, status='BLOCKED', reason='subject_uid_mismatch', http_status=403)

    if source.default_memory_grant is not True:
        return _result(source, status='BLOCKED', reason='missing_default_memory_grant', http_status=403)

    if source.runtime_config_version is None:
        return _result(source, status='BLOCKED', reason='missing_runtime_config_version', http_status=503)
    if source.runtime_config_stale is True:
        return _result(source, status='BLOCKED', reason='stale_runtime_config', http_status=503)

    if not (source.account_generation == source.control_generation == source.projection_generation):
        return _result(source, status='BLOCKED', reason='generation_mismatch', http_status=409)

    if source.projection_commit is None or source.projection_converged is not True:
        return _result(source, status='BLOCKED', reason='projection_not_converged', http_status=503)
    if source.write_converged is not True:
        return _result(source, status='BLOCKED', reason='write_not_converged', http_status=503)
    if source.delete_converged is not True:
        return _result(source, status='BLOCKED', reason='delete_not_converged', http_status=503)
    if source.tombstone_converged is not True:
        return _result(source, status='BLOCKED', reason='tombstone_not_converged', http_status=503)

    if source.cursor_policy_version is None:
        return _result(source, status='BLOCKED', reason='missing_cursor_policy_version', http_status=503)
    if source.cursor_secret_version is None:
        return _result(source, status='BLOCKED', reason='missing_cursor_secret_version', http_status=503)

    if source.archive_requested and not source.archive_capability:
        return _result(source, status='BLOCKED', reason='archive_capability_missing', http_status=403)

    if source.deadline_ms is None or source.deadline_remaining_ms is None or source.deadline_remaining_ms <= 0:
        return _result(source, status='BLOCKED', reason='deadline_expired_or_missing', http_status=504)
    if source.read_timestamp_ms is None:
        return _result(source, status='BLOCKED', reason='invalid_read_timestamp', http_status=503)
    if source.read_timestamp_ms > source.server_now_ms + source.read_timestamp_max_future_skew_ms:
        return _result(source, status='BLOCKED', reason='future_read_timestamp', http_status=503)

    snapshot = V3GetRuntimeSnapshot(
        subject_uid=source.authenticated_subject_uid,
        cohort=source.cohort,
        default_memory_grant=True,
        runtime_config_version_present=True,
        account_generation=source.account_generation,
        projection_generation=source.projection_generation,
        control_generation=source.control_generation,
        projection_commit_present=True,
        write_converged=True,
        delete_converged=True,
        tombstone_converged=True,
        cursor_policy_version_present=True,
        cursor_secret_version_present=True,
        archive_capability=source.archive_capability,
        archive_requested=source.archive_requested,
        deadline_ms=source.deadline_ms,
        deadline_remaining_ms=source.deadline_remaining_ms,
        read_timestamp_ms=source.read_timestamp_ms,
    )
    return _result(source, status='READY', reason='snapshot_coherent', http_status=200, snapshot=snapshot)


# Neutral symbol aliases (memory names remain valid via shim)
V3GetRuntimeSnapshotInput = V3GetRuntimeSnapshotInput
V3GetRuntimeSnapshot = V3GetRuntimeSnapshot
V3GetRuntimeSnapshotResult = V3GetRuntimeSnapshotResult
