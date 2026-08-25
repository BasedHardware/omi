from datetime import datetime, timezone

import pytest

from testing.memory.v3_canary_approval import (
    ROUTE_SCOPE,
    APPROVAL_STATUSES,
    CANARY_COHORTS,
    V3CanaryApprovalArtifact,
    build_v3_canary_approval_telemetry_labels,
    read_memory_v3_canary_approval_artifact_decision,
    validate_memory_v3_canary_approval_artifact,
)

NOW = datetime(2026, 6, 20, 12, 0, 0, tzinfo=timezone.utc)


def _artifact(**overrides):
    data = {
        'schema_version': 1,
        'artifact_id': 'memory-v3-get-canary-approval-2026-06-20',
        'route_scope': 'GET /v3/memories',
        'owner': 'product_privacy_ops',
        'status': 'approved',
        'cohort': 'canary_1',
        'issued_at': '2026-06-20T10:00:00+00:00',
        'expires_at': '2026-06-21T10:00:00+00:00',
        'approval': {
            'approval_id': 'apr_v3_get_001',
            'approved_at': '2026-06-20T10:30:00+00:00',
            'approved_by': 'product_privacy_ops',
        },
        'rollback_plan': {
            'owner': 'memory_platform_oncall',
            'disable_gate': 'emergency_read_disable',
            'max_disable_minutes': 15,
            'steps': ['set_server_owned_read_disable', 'verify_v3_get_fail_closed', 'notify_product_privacy_ops'],
        },
        'monitoring_gates': [
            {'gate_id': 'fail_closed_rate', 'metric': 'v3_fail_closed_rate', 'max_threshold': 0.01},
            {'gate_id': 'p95_latency_ms', 'metric': 'v3_get_p95_latency_ms', 'max_threshold': 500},
        ],
        'metadata': {'change_ticket': 'MEM-17-V3-CANARY-001'},
    }
    data.update(overrides)
    return data


def test_artifact_schema_pins_bounded_route_cohort_status_and_metadata_only_approval():
    assert ROUTE_SCOPE == 'GET /v3/memories'
    assert CANARY_COHORTS == {'shadow', 'canary_1', 'canary_5', 'canary_25'}
    assert APPROVAL_STATUSES == {'pending', 'approved', 'rejected'}

    parsed = V3CanaryApprovalArtifact.from_dict(_artifact())

    assert parsed.route_scope == 'GET /v3/memories'
    assert parsed.owner == 'product_privacy_ops'
    assert parsed.status == 'approved'
    assert parsed.cohort == 'canary_1'
    assert parsed.approval_id == 'apr_v3_get_001'
    assert parsed.approved_at == '2026-06-20T10:30:00+00:00'
    assert parsed.rollback_owner == 'memory_platform_oncall'
    assert parsed.monitoring_gate_ids == ('fail_closed_rate', 'p95_latency_ms')


@pytest.mark.parametrize(
    'artifact,reason',
    [
        (None, 'artifact_missing'),
        ({'schema_version': 1}, 'artifact_malformed'),
        (_artifact(cohort='uid_123'), 'unsupported_cohort'),
        (_artifact(rollback_plan={}), 'rollback_plan_missing'),
        (_artifact(monitoring_gates=[]), 'monitoring_gates_missing'),
        (_artifact(status='pending'), 'approval_pending'),
        (_artifact(status='rejected'), 'approval_rejected'),
        (_artifact(approval={}), 'approval_missing'),
        (_artifact(expires_at='2026-06-19T10:00:00+00:00'), 'artifact_stale'),
        (_artifact(route_scope='GET /v3/memories/{memory_id}'), 'route_scope_mismatch'),
    ],
)
def test_validation_fails_closed_for_missing_malformed_unapproved_stale_or_route_mismatched_artifacts(artifact, reason):
    decision = validate_memory_v3_canary_approval_artifact(
        artifact,
        requested_route_scope='GET /v3/memories',
        requested_cohort='canary_1',
        now=NOW,
    )

    assert decision.approved is False
    assert decision.fail_closed is True
    assert decision.reason == reason
    assert decision.runtime_wired is False
    assert decision.production_rollout_approved is False


@pytest.mark.parametrize(
    'field_path,value',
    [
        ('owner', 'uid_abc123'),
        ('artifact_id', 'sess_123456789'),
        ('approval.approval_id', 'cursor_token_abc'),
        ('metadata.uid', 'user-1'),
        ('metadata.session_id', 'session-1'),
        ('metadata.cursor', 'cursor-secret'),
        ('metadata.request_payload', {'limit': 100}),
        ('metadata.memory_content', 'raw memory text'),
    ],
)
def test_validation_rejects_user_session_cohort_high_cardinality_and_sensitive_metadata_misuse(field_path, value):
    artifact = _artifact()
    target = artifact
    parts = field_path.split('.')
    for part in parts[:-1]:
        target = target[part]
    target[parts[-1]] = value

    decision = validate_memory_v3_canary_approval_artifact(
        artifact,
        requested_route_scope='GET /v3/memories',
        requested_cohort='canary_1',
        now=NOW,
    )

    assert decision.approved is False
    assert decision.fail_closed is True
    assert decision.reason in {'high_cardinality_or_sensitive_value', 'high_cardinality_or_sensitive_key'}


def test_approved_artifact_allows_requested_cohort_and_builds_bounded_telemetry_labels_only():
    decision = validate_memory_v3_canary_approval_artifact(
        _artifact(),
        requested_route_scope='GET /v3/memories',
        requested_cohort='canary_1',
        now=NOW,
    )

    assert decision.approved is True
    assert decision.fail_closed is False
    assert decision.reason == 'approved'
    labels = build_v3_canary_approval_telemetry_labels(decision)
    assert labels == {
        'canary_cohort': 'canary_1',
        'canary_enrollment': 'enrolled',
        'approval_owner': 'product_privacy_ops',
        'approval_status': 'approved',
        'approval_artifact_status': 'valid_approved',
        'route_scope': 'GET /v3/memories',
    }
    forbidden = {
        'uid',
        'user_id',
        'session_id',
        'cursor',
        'cursor_token',
        'secret',
        'request_payload',
        'memory_content',
    }
    assert forbidden.isdisjoint(labels)


def test_requested_unsupported_or_mismatched_cohort_fails_closed_before_runtime_wiring():
    unsupported = validate_memory_v3_canary_approval_artifact(
        _artifact(cohort='canary_1'),
        requested_route_scope='GET /v3/memories',
        requested_cohort='general_availability',
        now=NOW,
    )
    assert unsupported.approved is False
    assert unsupported.reason == 'unsupported_cohort'

    mismatch = validate_memory_v3_canary_approval_artifact(
        _artifact(cohort='canary_5'), requested_route_scope='GET /v3/memories', requested_cohort='canary_1', now=NOW
    )
    assert mismatch.approved is False
    assert mismatch.reason == 'cohort_mismatch'


class _FakeApprovalArtifactReader:
    production_reader_call = False
    reader_name = 'fake_local_canary_approval_reader'

    def __init__(self, artifact=None, *, raises=None):
        self.artifact = artifact
        self.raises = raises
        self.calls = []

    def read_canary_approval_artifact(self, *, route_scope, cohort):
        self.calls.append({'route_scope': route_scope, 'cohort': cohort})
        if self.raises is not None:
            raise self.raises
        return self.artifact


@pytest.mark.parametrize(
    'reader,reason',
    [
        (None, 'artifact_reader_missing'),
        (_FakeApprovalArtifactReader(raises=TimeoutError('local fake timeout')), 'artifact_reader_failed'),
        (_FakeApprovalArtifactReader(artifact={'schema_version': 1}), 'artifact_malformed'),
        (
            _FakeApprovalArtifactReader(artifact=_artifact(route_scope='GET /v3/memories/{memory_id}')),
            'route_scope_mismatch',
        ),
        (_FakeApprovalArtifactReader(artifact=_artifact(cohort='canary_5')), 'cohort_mismatch'),
        (_FakeApprovalArtifactReader(artifact=_artifact(expires_at='2026-06-19T10:00:00+00:00')), 'artifact_stale'),
        (_FakeApprovalArtifactReader(artifact=_artifact(status='pending')), 'approval_pending'),
        (_FakeApprovalArtifactReader(artifact=_artifact(status='rejected')), 'approval_rejected'),
        (
            _FakeApprovalArtifactReader(artifact=_artifact(metadata={'uid': 'uid_123'})),
            'high_cardinality_or_sensitive_key',
        ),
    ],
)
def test_injected_server_owned_artifact_reader_fails_closed_for_missing_exceptions_and_invalid_artifacts(
    reader, reason
):
    decision = read_memory_v3_canary_approval_artifact_decision(
        reader=reader,
        requested_route_scope='GET /v3/memories',
        requested_cohort='canary_1',
        now=NOW,
    )

    assert decision.approved is False
    assert decision.fail_closed is True
    assert decision.reason == reason
    assert decision.runtime_wired is False
    assert decision.production_rollout_approved is False
    assert decision.approval_claimed is False


def test_injected_server_owned_artifact_reader_validates_fake_artifact_and_exposes_bounded_labels_only():
    reader = _FakeApprovalArtifactReader(artifact=_artifact())

    decision = read_memory_v3_canary_approval_artifact_decision(
        reader=reader,
        requested_route_scope='GET /v3/memories',
        requested_cohort='canary_1',
        now=NOW,
    )

    assert reader.calls == [{'route_scope': 'GET /v3/memories', 'cohort': 'canary_1'}]
    assert decision.approved is True
    assert decision.fail_closed is False
    assert decision.reason == 'approved'
    assert decision.runtime_wired is False
    assert decision.production_rollout_approved is False
    labels = build_v3_canary_approval_telemetry_labels(decision)
    assert labels == {
        'canary_cohort': 'canary_1',
        'canary_enrollment': 'enrolled',
        'approval_owner': 'product_privacy_ops',
        'approval_status': 'approved',
        'approval_artifact_status': 'valid_approved',
        'route_scope': 'GET /v3/memories',
    }
    forbidden = {'uid', 'session_id', 'memory_content', 'cursor', 'secret', 'request_payload'}
    assert forbidden.isdisjoint(labels)
