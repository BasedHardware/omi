from __future__ import annotations

from testing.memory.v3_get_runtime_snapshot import (
    LOW_CARDINALITY_RUNTIME_SNAPSHOT_REASONS,
    V3GetRuntimeSnapshotInput,
    build_v3_get_runtime_snapshot,
)


def _input(**overrides):
    values = {
        'authenticated_subject_uid': 'server-uid',
        'control_subject_uid': 'server-uid',
        'grant_subject_uid': 'server-uid',
        'projection_subject_uid': 'server-uid',
        'cursor_subject_uid': 'server-uid',
        'cohort': 'memory_enrolled',
        'control_generation': 7,
        'default_memory_grant': True,
        'runtime_config_version': 'cfg-2026-06-20',
        'runtime_config_stale': False,
        'account_generation': 7,
        'projection_generation': 7,
        'projection_commit': 'commit-9',
        'projection_converged': True,
        'write_converged': True,
        'delete_converged': True,
        'tombstone_converged': True,
        'cursor_policy_version': 'policy-v1',
        'cursor_secret_version': 'secret-v4',
        'archive_capability': False,
        'archive_requested': False,
        'deadline_ms': 250,
        'deadline_remaining_ms': 150,
        'read_timestamp_ms': 1_000_000,
        'server_now_ms': 1_000_010,
        'read_timestamp_max_future_skew_ms': 1000,
    }
    values.update(overrides)
    return V3GetRuntimeSnapshotInput(**values)


def test_runtime_snapshot_coherent_contract_is_ready_and_sanitized():
    result = build_v3_get_runtime_snapshot(_input())

    assert result.status == 'READY'
    assert result.reason == 'snapshot_coherent'
    assert result.http_status == 200
    assert result.snapshot is not None
    assert result.snapshot.subject_uid == 'server-uid'
    assert result.snapshot.account_generation == 7
    assert result.snapshot.projection_generation == 7
    assert result.snapshot.projection_commit_present is True
    assert result.snapshot.default_memory_grant is True
    assert result.snapshot.archive_capability is False
    assert result.snapshot.archive_requested is False
    assert result.log_fields == {
        'route': 'GET /v3/memories',
        'status': 'READY',
        'reason': 'snapshot_coherent',
        'cohort': 'memory_enrolled',
        'archive_requested': 'false',
        'archive_capability': 'false',
    }
    assert 'server-uid' not in repr(result.log_fields)
    assert 'commit-9' not in repr(result.log_fields)
    assert 'secret-v4' not in repr(result.log_fields)


def test_runtime_snapshot_fail_closed_reason_matrix():
    cases = [
        ({'control_subject_uid': 'other-uid'}, 'subject_uid_mismatch', 403),
        ({'default_memory_grant': False}, 'missing_default_memory_grant', 403),
        ({'runtime_config_version': None}, 'missing_runtime_config_version', 503),
        ({'runtime_config_stale': True}, 'stale_runtime_config', 503),
        ({'account_generation': 8}, 'generation_mismatch', 409),
        ({'projection_generation': 8}, 'generation_mismatch', 409),
        ({'projection_commit': None}, 'projection_not_converged', 503),
        ({'projection_converged': False}, 'projection_not_converged', 503),
        ({'write_converged': False}, 'write_not_converged', 503),
        ({'delete_converged': False}, 'delete_not_converged', 503),
        ({'tombstone_converged': False}, 'tombstone_not_converged', 503),
        ({'cursor_policy_version': None}, 'missing_cursor_policy_version', 503),
        ({'cursor_secret_version': None}, 'missing_cursor_secret_version', 503),
        ({'archive_requested': True, 'archive_capability': False}, 'archive_capability_missing', 403),
        ({'deadline_remaining_ms': 0}, 'deadline_expired_or_missing', 504),
        ({'deadline_ms': None}, 'deadline_expired_or_missing', 504),
        ({'read_timestamp_ms': None}, 'invalid_read_timestamp', 503),
        ({'read_timestamp_ms': 1_002_000}, 'future_read_timestamp', 503),
        ({'account_generation': '7'}, 'malformed_source_output', 503),
    ]

    for overrides, reason, status in cases:
        result = build_v3_get_runtime_snapshot(_input(**overrides))
        assert result.status == 'BLOCKED', overrides
        assert result.reason == reason
        assert result.http_status == status
        assert result.snapshot is None
        assert result.reason in LOW_CARDINALITY_RUNTIME_SNAPSHOT_REASONS
        assert result.log_fields['reason'] == reason
        assert 'server-uid' not in repr(result.log_fields)
        assert 'secret-v4' not in repr(result.log_fields)
        assert 'commit-9' not in repr(result.log_fields)


def test_runtime_snapshot_rejects_client_owned_or_malformed_sources():
    cases = [
        {'server_owned_subject': False},
        {'server_owned_control': False},
        {'server_owned_grant': False},
        {'server_owned_runtime_config': False},
        {'server_owned_generation': False},
        {'server_owned_projection': False},
        {'server_owned_convergence': False},
        {'server_owned_cursor': False},
        {'server_owned_deadline': False},
        {'server_owned_read_timestamp': False},
        {'authenticated_subject_uid': ''},
        {'cohort': ''},
        {'runtime_config_version': ''},
        {'projection_commit': ''},
        {'cursor_policy_version': ''},
        {'cursor_secret_version': ''},
        {'deadline_remaining_ms': '10'},
        {'read_timestamp_ms': -1},
    ]

    for overrides in cases:
        result = build_v3_get_runtime_snapshot(_input(**overrides))
        assert result.status == 'BLOCKED', overrides
        assert result.reason == 'malformed_source_output'
        assert result.snapshot is None


def test_runtime_snapshot_allows_archive_request_only_with_separate_capability():
    result = build_v3_get_runtime_snapshot(_input(archive_requested=True, archive_capability=True))

    assert result.status == 'READY'
    assert result.snapshot is not None
    assert result.snapshot.archive_requested is True
    assert result.snapshot.archive_capability is True
    assert result.log_fields['archive_requested'] == 'true'
    assert result.log_fields['archive_capability'] == 'true'
