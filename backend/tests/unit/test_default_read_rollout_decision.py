from config.memory_rollout import PASSED, MemoryRolloutMode, MemoryRolloutStageGate
from utils.memory.default_read_rollout import (
    MemoryReadDecision,
    DEFAULT_READ_ROLLOUT_SCHEMA_VERSION,
    DEFAULT_READ_ROLLOUT_TIMEOUT_SECONDS,
    GLOBAL_READ_GATE_PATH,
    WRITE_CONVERGENCE_GATE_PATH,
    assert_legacy_memory_write_allowed_for_default_read_decision,
    build_default_read_rollout_audit_events,
    legacy_safe_default_read_rollout_decision,
    read_archive_read_rollout,
    read_global_read_gate,
    read_write_convergence_gate,
    render_default_read_rollout_metrics,
    read_default_read_rollout,
    read_default_read_rollout_decisions,
)


class _Snapshot:
    def __init__(self, data=None, *, exists=True):
        self._data = data
        self.exists = exists

    def to_dict(self):
        if self._data is None:
            return None
        return dict(self._data)


class _DocumentRef:
    def __init__(self, db_client, path):
        self._db_client = db_client
        self.path = path

    def get(self, timeout=None):
        self._db_client.document_get_paths.append(self.path)
        self._db_client.document_get_timeouts.append(timeout)
        if self._db_client.get_exception is not None:
            raise self._db_client.get_exception
        if self.path not in self._db_client.docs:
            return _Snapshot(None, exists=False)
        return _Snapshot(self._db_client.docs[self.path], exists=True)


class _FirestoreFake:
    def __init__(self, docs=None, *, get_exception=None):
        self.docs = docs or {}
        self.get_exception = get_exception
        self.document_get_paths = []
        self.document_get_timeouts = []
        self.collection_paths = []

    def document(self, path):
        return _DocumentRef(self, path)

    def collection(self, path):
        self.collection_paths.append(path)
        raise AssertionError('rollout helper must not read memory_items collections')


def _enabled_rollout_doc(uid='u1'):
    return {
        'schema_version': DEFAULT_READ_ROLLOUT_SCHEMA_VERSION,
        'uid': uid,
        'mode': MemoryRolloutMode.read.value,
        'mode_epoch': 7,
        'cutover_epoch': 7,
        'account_generation': 3,
        'fallback_projection_ready': True,
        'persistent_memory_writes_started': True,
        'writes_blocked': False,
        'stage_gates': {
            MemoryRolloutStageGate.shadow.value: PASSED,
            MemoryRolloutStageGate.write.value: PASSED,
            MemoryRolloutStageGate.read.value: PASSED,
        },
        'grants': {
            'mcp': {'default_memory': True, 'archive': True},
            'developer_api': {'default_memory': True, 'archive': True},
        },
        'mcp_default_memory_grant': False,
        'developer_default_memory_grant': False,
    }


def test_global_read_gate_allows_reads_only_when_enabled_and_kill_switch_inactive():
    db_client = _FirestoreFake({GLOBAL_READ_GATE_PATH: {'memory_reads_enabled': True, 'kill_switch_active': False}})

    decision = read_global_read_gate(db_client=db_client)

    assert db_client.document_get_paths == [GLOBAL_READ_GATE_PATH]
    assert db_client.document_get_timeouts == [DEFAULT_READ_ROLLOUT_TIMEOUT_SECONDS]
    assert db_client.collection_paths == []
    assert decision.read_decision == MemoryReadDecision.USE_MEMORY
    assert decision.fallback_reason is None


def test_global_read_gate_uses_bounded_timeout_and_fails_closed_for_firestore_transport_exceptions():
    class PermissionDenied(Exception):
        pass

    failing_db_client = _FirestoreFake(get_exception=PermissionDenied('permission denied'))

    decision = read_global_read_gate(db_client=failing_db_client)

    assert failing_db_client.document_get_paths == [GLOBAL_READ_GATE_PATH]
    assert failing_db_client.document_get_timeouts == [DEFAULT_READ_ROLLOUT_TIMEOUT_SECONDS]
    assert failing_db_client.collection_paths == []
    assert decision.read_decision == MemoryReadDecision.DENY_MEMORY
    assert decision.fallback_reason == 'global_read_gate_read_failed'


def test_global_read_gate_fails_closed_for_missing_disabled_kill_switch_and_malformed_config():
    cases = [
        ({}, 'missing_global_read_gate'),
        (
            {GLOBAL_READ_GATE_PATH: {'memory_reads_enabled': False, 'kill_switch_active': False}},
            'global_memory_reads_disabled',
        ),
        (
            {GLOBAL_READ_GATE_PATH: {'memory_reads_enabled': True, 'kill_switch_active': True}},
            'global_memory_read_kill_switch_active',
        ),
        (
            {GLOBAL_READ_GATE_PATH: {'memory_reads_enabled': 'true', 'kill_switch_active': False}},
            'malformed_global_read_gate',
        ),
        (
            {GLOBAL_READ_GATE_PATH: {'memory_reads_enabled': True, 'kill_switch_active': 'no'}},
            'malformed_global_read_gate',
        ),
    ]

    for docs, expected_reason in cases:
        db_client = _FirestoreFake(docs)
        decision = read_global_read_gate(db_client=db_client)

        assert db_client.document_get_paths == [GLOBAL_READ_GATE_PATH]
        assert db_client.collection_paths == []
        assert decision.read_decision == MemoryReadDecision.DENY_MEMORY
        assert decision.fallback_reason == expected_reason


def test_write_convergence_gate_requires_durable_outbox_dual_write_and_delete_readiness():
    db_client = _FirestoreFake(
        {
            WRITE_CONVERGENCE_GATE_PATH: {
                'durable_outbox_enabled': True,
                'dual_write_projection_ready': True,
                'delete_convergence_ready': True,
                'idempotency_contract_ready': True,
            }
        }
    )

    policy = read_write_convergence_gate(db_client=db_client)

    assert db_client.document_get_paths == [WRITE_CONVERGENCE_GATE_PATH]
    assert db_client.document_get_timeouts == [DEFAULT_READ_ROLLOUT_TIMEOUT_SECONDS]
    assert db_client.collection_paths == []
    assert policy.ready is True
    assert policy.reason == 'ok'


def test_write_convergence_gate_uses_bounded_timeout_and_fails_closed_for_firestore_transport_exceptions():
    class DeadlineExceeded(Exception):
        pass

    failing_db_client = _FirestoreFake(get_exception=DeadlineExceeded('deadline exceeded'))

    policy = read_write_convergence_gate(db_client=failing_db_client)

    assert failing_db_client.document_get_paths == [WRITE_CONVERGENCE_GATE_PATH]
    assert failing_db_client.document_get_timeouts == [DEFAULT_READ_ROLLOUT_TIMEOUT_SECONDS]
    assert failing_db_client.collection_paths == []
    assert policy.ready is False
    assert policy.reason == 'write_convergence_gate_read_failed'


def test_write_convergence_gate_fails_closed_for_missing_or_malformed_readiness_config():
    cases = [
        ({}, 'missing_write_convergence_gate'),
        (
            {
                WRITE_CONVERGENCE_GATE_PATH: {
                    'durable_outbox_enabled': True,
                    'dual_write_projection_ready': True,
                    'delete_convergence_ready': True,
                    'idempotency_contract_ready': False,
                }
            },
            'write_convergence_not_ready',
        ),
        (
            {
                WRITE_CONVERGENCE_GATE_PATH: {
                    'durable_outbox_enabled': True,
                    'dual_write_projection_ready': 'yes',
                    'delete_convergence_ready': True,
                    'idempotency_contract_ready': True,
                }
            },
            'malformed_write_convergence_gate',
        ),
    ]

    for docs, expected_reason in cases:
        db_client = _FirestoreFake(docs)
        policy = read_write_convergence_gate(db_client=db_client)

        assert db_client.document_get_paths == [WRITE_CONVERGENCE_GATE_PATH]
        assert db_client.collection_paths == []
        assert policy.ready is False
        assert policy.reason == expected_reason


def test_legacy_write_guard_allows_memory_enabled_write_only_with_ready_convergence_policy():
    enabled_decision = read_default_read_rollout(
        uid='u1', db_client=_FirestoreFake({'users/u1/memory_control/state': _enabled_rollout_doc()}), consumer='mcp'
    )
    ready_policy = read_write_convergence_gate(
        db_client=_FirestoreFake(
            {
                WRITE_CONVERGENCE_GATE_PATH: {
                    'durable_outbox_enabled': True,
                    'dual_write_projection_ready': True,
                    'delete_convergence_ready': True,
                    'idempotency_contract_ready': True,
                }
            }
        )
    )
    missing_policy = read_write_convergence_gate(db_client=_FirestoreFake())

    blocked_without_policy = assert_legacy_memory_write_allowed_for_default_read_decision(
        enabled_decision, operation='create_memory'
    )
    blocked_with_missing_policy = assert_legacy_memory_write_allowed_for_default_read_decision(
        enabled_decision, operation='create_memory', write_convergence_policy=missing_policy
    )
    allowed_with_ready_policy = assert_legacy_memory_write_allowed_for_default_read_decision(
        enabled_decision, operation='create_memory', write_convergence_policy=ready_policy
    )

    assert blocked_without_policy.allowed is False
    assert blocked_with_missing_policy.allowed is False
    assert blocked_with_missing_policy.detail['convergence_reason'] == 'missing_write_convergence_gate'
    assert allowed_with_ready_policy.allowed is True
    assert allowed_with_ready_policy.detail['reason'] == 'legacy_memory_write_allowed_with_memory_convergence'


def test_shared_rollout_helper_reads_memory_control_state_for_mcp_and_developer_grants_without_archive_default():
    db_client = _FirestoreFake({'users/u1/memory_control/state': _enabled_rollout_doc()})

    mcp_decision = read_default_read_rollout(uid='u1', db_client=db_client, consumer='mcp')
    developer_decision = read_default_read_rollout(uid='u1', db_client=db_client, consumer='developer_api')

    assert db_client.document_get_paths == ['users/u1/memory_control/state', 'users/u1/memory_control/state']
    assert db_client.collection_paths == []
    assert mcp_decision.rollout_capabilities.memory_reads_enabled is True
    assert developer_decision.rollout_capabilities.memory_reads_enabled is True
    assert mcp_decision.app_has_default_memory_grant is True
    assert developer_decision.app_has_default_memory_grant is True
    assert mcp_decision.archive_capability is False
    assert developer_decision.archive_capability is False
    assert mcp_decision.read_decision == MemoryReadDecision.USE_MEMORY
    assert developer_decision.read_decision == MemoryReadDecision.USE_MEMORY
    assert mcp_decision.memory_default_mcp_enabled is True
    assert developer_decision.memory_default_developer_enabled is True


def test_shared_rollout_helper_fails_closed_for_missing_malformed_uid_mismatch_and_missing_consumer_grant():
    missing = _FirestoreFake()
    missing_decision = read_default_read_rollout(uid='u1', db_client=missing, consumer='mcp')
    assert missing_decision.memory_default_mcp_enabled is False
    assert missing_decision.read_decision == MemoryReadDecision.DENY_MEMORY
    assert missing_decision.fallback_reason == 'missing_rollout_state'
    assert missing.collection_paths == []

    malformed = _FirestoreFake(
        {
            'users/u1/memory_control/state': {
                'schema_version': DEFAULT_READ_ROLLOUT_SCHEMA_VERSION,
                'uid': 'u1',
                'mode': 'read',
                'stage_gates': 'bad',
            }
        }
    )
    malformed_decision = read_default_read_rollout(uid='u1', db_client=malformed, consumer='developer_api')
    assert malformed_decision.memory_default_developer_enabled is False
    assert malformed_decision.read_decision == MemoryReadDecision.DENY_MEMORY
    assert malformed_decision.fallback_reason == 'malformed_rollout_state'
    assert malformed.collection_paths == []

    uid_mismatch = _FirestoreFake({'users/u1/memory_control/state': _enabled_rollout_doc(uid='other')})
    uid_mismatch_decision = read_default_read_rollout(uid='u1', db_client=uid_mismatch, consumer='mcp')
    assert uid_mismatch_decision.memory_default_mcp_enabled is False
    assert uid_mismatch_decision.read_decision == MemoryReadDecision.DENY_MEMORY
    assert uid_mismatch_decision.fallback_reason == 'uid_mismatch'
    assert uid_mismatch.collection_paths == []

    no_grant = _FirestoreFake(
        {'users/u1/memory_control/state': _enabled_rollout_doc() | {'grants': {'developer_api': {}}}}
    )
    no_grant_decision = read_default_read_rollout(uid='u1', db_client=no_grant, consumer='developer_api')
    assert no_grant_decision.rollout_capabilities.memory_reads_enabled is True
    assert no_grant_decision.app_has_default_memory_grant is False
    assert no_grant_decision.memory_default_developer_enabled is False
    assert no_grant_decision.read_decision == MemoryReadDecision.DENY_MEMORY
    assert no_grant_decision.fallback_reason == 'missing_developer_default_memory_grant'
    assert no_grant.collection_paths == []


def test_rollout_doc_requires_exact_uid_schema_and_canonical_nested_grant_precedence():
    missing_uid = _enabled_rollout_doc()
    missing_uid.pop('uid')
    missing_uid_decision = read_default_read_rollout(
        uid='u1', db_client=_FirestoreFake({'users/u1/memory_control/state': missing_uid}), consumer='mcp'
    )
    assert missing_uid_decision.read_decision == MemoryReadDecision.DENY_MEMORY
    assert missing_uid_decision.fallback_reason == 'uid_mismatch'

    missing_schema = _enabled_rollout_doc()
    missing_schema.pop('schema_version')
    missing_schema_decision = read_default_read_rollout(
        uid='u1', db_client=_FirestoreFake({'users/u1/memory_control/state': missing_schema}), consumer='mcp'
    )
    assert missing_schema_decision.read_decision == MemoryReadDecision.DENY_MEMORY
    assert missing_schema_decision.fallback_reason == 'unsupported_rollout_schema'

    unsupported_schema = _enabled_rollout_doc() | {'schema_version': 0}
    unsupported_schema_decision = read_default_read_rollout(
        uid='u1', db_client=_FirestoreFake({'users/u1/memory_control/state': unsupported_schema}), consumer='mcp'
    )
    assert unsupported_schema_decision.read_decision == MemoryReadDecision.DENY_MEMORY
    assert unsupported_schema_decision.fallback_reason == 'unsupported_rollout_schema'

    nested_false_with_stale_top_level_true = _enabled_rollout_doc() | {
        'grants': {'mcp': {'default_memory': False}},
        'mcp_default_memory_grant': True,
    }
    nested_false_decision = read_default_read_rollout(
        uid='u1',
        db_client=_FirestoreFake({'users/u1/memory_control/state': nested_false_with_stale_top_level_true}),
        consumer='mcp',
    )
    assert nested_false_decision.app_has_default_memory_grant is False
    assert nested_false_decision.read_decision == MemoryReadDecision.DENY_MEMORY
    assert nested_false_decision.fallback_reason == 'missing_mcp_default_memory_grant'

    nested_absent_with_stale_top_level_true = _enabled_rollout_doc() | {
        'grants': {'mcp': {}},
        'mcp_default_memory_grant': True,
    }
    nested_absent_decision = read_default_read_rollout(
        uid='u1',
        db_client=_FirestoreFake({'users/u1/memory_control/state': nested_absent_with_stale_top_level_true}),
        consumer='mcp',
    )
    assert nested_absent_decision.app_has_default_memory_grant is False
    assert nested_absent_decision.read_decision == MemoryReadDecision.DENY_MEMORY
    assert nested_absent_decision.fallback_reason == 'missing_mcp_default_memory_grant'


def test_rollout_reads_use_bounded_timeout_and_fail_closed_for_firestore_transport_exceptions():
    class PermissionDenied(Exception):
        pass

    db_client = _FirestoreFake({'users/u1/memory_control/state': _enabled_rollout_doc()})
    decision = read_default_read_rollout(uid='u1', db_client=db_client, consumer='mcp')
    assert decision.read_decision == MemoryReadDecision.USE_MEMORY
    assert db_client.document_get_timeouts == [DEFAULT_READ_ROLLOUT_TIMEOUT_SECONDS]

    failing_db_client = _FirestoreFake(get_exception=PermissionDenied('permission denied'))
    failing_decision = read_default_read_rollout(uid='u1', db_client=failing_db_client, consumer='mcp')
    assert failing_decision.read_decision == MemoryReadDecision.DENY_MEMORY
    assert failing_decision.fallback_reason == 'rollout_read_failed'
    assert failing_db_client.document_get_timeouts == [DEFAULT_READ_ROLLOUT_TIMEOUT_SECONDS]

    failing_shared_decisions = read_default_read_rollout_decisions(uid='u1', db_client=failing_db_client)
    assert {consumer: decision.fallback_reason for consumer, decision in failing_shared_decisions.items()} == {
        'mcp': 'rollout_read_failed',
        'developer_api': 'rollout_read_failed',
        'omi_chat': 'rollout_read_failed',
    }


def test_shared_rollout_helper_distinguishes_shadow_only_and_explicit_legacy_safe_decisions():
    shadow_doc = _enabled_rollout_doc() | {
        'mode': MemoryRolloutMode.shadow.value,
        'fallback_projection_ready': False,
        'stage_gates': {MemoryRolloutStageGate.shadow.value: PASSED},
        'grants': {'mcp': {'default_memory': True}},
    }
    db_client = _FirestoreFake({'users/u1/memory_control/state': shadow_doc})

    shadow_decision = read_default_read_rollout(uid='u1', db_client=db_client, consumer='mcp')
    legacy_safe_decision = legacy_safe_default_read_rollout_decision(
        uid='u1', source_path='legacy/users/u1/memories', consumer='mcp', reason='explicit_legacy_endpoint'
    )

    assert shadow_decision.read_decision == MemoryReadDecision.SHADOW_ONLY
    assert shadow_decision.memory_default_enabled is False
    assert shadow_decision.fallback_reason == 'shadow_only'
    assert legacy_safe_decision.read_decision == MemoryReadDecision.USE_LEGACY_SAFE
    assert legacy_safe_decision.fallback_reason == 'explicit_legacy_endpoint'


def test_shared_rollout_helper_computes_persisted_archive_capability_distinct_from_default_reads():
    rollout_doc = _enabled_rollout_doc() | {
        'grants': {
            'omi_chat': {'default_memory': True, 'archive': True},
        }
    }
    db_client = _FirestoreFake({'users/u1/memory_control/state': rollout_doc})

    default_decision = read_default_read_rollout(uid='u1', db_client=db_client, consumer='omi_chat')
    archive_decision = read_archive_read_rollout(uid='u1', db_client=db_client, consumer='omi_chat')

    assert db_client.document_get_paths == ['users/u1/memory_control/state', 'users/u1/memory_control/state']
    assert db_client.collection_paths == []
    assert default_decision.read_decision == MemoryReadDecision.USE_MEMORY
    assert default_decision.archive_capability is False
    assert archive_decision.read_decision == MemoryReadDecision.USE_MEMORY
    assert archive_decision.archive_capability is True
    assert archive_decision.app_has_default_memory_grant is True


def test_shared_rollout_helper_fails_closed_for_missing_malformed_disabled_and_no_archive_grant():
    missing_archive = _enabled_rollout_doc() | {'grants': {'omi_chat': {'default_memory': True}}}
    missing_archive_decision = read_archive_read_rollout(
        uid='u1', db_client=_FirestoreFake({'users/u1/memory_control/state': missing_archive}), consumer='omi_chat'
    )
    assert missing_archive_decision.read_decision == MemoryReadDecision.DENY_MEMORY
    assert missing_archive_decision.fallback_reason == 'missing_chat_archive_capability'
    assert missing_archive_decision.archive_capability is False

    malformed_archive = _enabled_rollout_doc() | {'grants': {'omi_chat': {'default_memory': True, 'archive': 'yes'}}}
    malformed_archive_decision = read_archive_read_rollout(
        uid='u1', db_client=_FirestoreFake({'users/u1/memory_control/state': malformed_archive}), consumer='omi_chat'
    )
    assert malformed_archive_decision.read_decision == MemoryReadDecision.DENY_MEMORY
    assert malformed_archive_decision.fallback_reason == 'malformed_archive_capability'
    assert malformed_archive_decision.archive_capability is False

    disabled_archive = _enabled_rollout_doc() | {
        'mode': MemoryRolloutMode.off.value,
        'grants': {'omi_chat': {'default_memory': True, 'archive': True}},
    }
    disabled_archive_decision = read_archive_read_rollout(
        uid='u1', db_client=_FirestoreFake({'users/u1/memory_control/state': disabled_archive}), consumer='omi_chat'
    )
    assert disabled_archive_decision.read_decision == MemoryReadDecision.DENY_MEMORY
    assert disabled_archive_decision.fallback_reason == 'memory_reads_disabled'
    assert disabled_archive_decision.archive_capability is False

    no_default_grant = _enabled_rollout_doc() | {'grants': {'omi_chat': {'archive': True}}}
    no_default_grant_decision = read_archive_read_rollout(
        uid='u1', db_client=_FirestoreFake({'users/u1/memory_control/state': no_default_grant}), consumer='omi_chat'
    )
    assert no_default_grant_decision.read_decision == MemoryReadDecision.DENY_MEMORY
    assert no_default_grant_decision.fallback_reason == 'missing_chat_default_memory_grant'
    assert no_default_grant_decision.archive_capability is False


def test_shared_rollout_helper_builds_local_audit_events_and_counters_without_memory_item_reads():
    rollout_doc = _enabled_rollout_doc() | {
        'grants': {
            'mcp': {'default_memory': True, 'archive': True},
            'developer_api': {},
            'omi_chat': {'default_memory': True, 'archive': True},
        }
    }
    db_client = _FirestoreFake({'users/u1/memory_control/state': rollout_doc})

    decisions = read_default_read_rollout_decisions(uid='u1', db_client=db_client)
    audit = build_default_read_rollout_audit_events(decisions)

    assert db_client.document_get_paths == ['users/u1/memory_control/state']
    assert db_client.collection_paths == []
    assert audit == {
        'events': [
            {
                'uid': 'u1',
                'source_path': 'users/u1/memory_control/state',
                'consumer': 'mcp',
                'enabled': True,
                'outcome': 'enabled',
                'read_decision': 'USE_MEMORY',
                'fallback_reason': None,
                'default_memory_grant': True,
                'memory_reads_enabled': True,
                'archive_default_visible': False,
                'archive_capability': False,
            },
            {
                'uid': 'u1',
                'source_path': 'users/u1/memory_control/state',
                'consumer': 'developer_api',
                'enabled': False,
                'outcome': 'fallback',
                'read_decision': 'DENY_MEMORY',
                'fallback_reason': 'missing_developer_default_memory_grant',
                'default_memory_grant': False,
                'memory_reads_enabled': True,
                'archive_default_visible': False,
                'archive_capability': False,
            },
            {
                'uid': 'u1',
                'source_path': 'users/u1/memory_control/state',
                'consumer': 'omi_chat',
                'enabled': True,
                'outcome': 'enabled',
                'read_decision': 'USE_MEMORY',
                'fallback_reason': None,
                'default_memory_grant': True,
                'memory_reads_enabled': True,
                'archive_default_visible': False,
                'archive_capability': False,
            },
        ],
        'counters': {
            'total': {'enabled': 2, 'fallback': 1},
            'by_consumer': {
                'mcp': {'enabled': 1, 'fallback': 0, 'fallback_reasons': {}},
                'developer_api': {
                    'enabled': 0,
                    'fallback': 1,
                    'fallback_reasons': {'missing_developer_default_memory_grant': 1},
                },
                'omi_chat': {'enabled': 1, 'fallback': 0, 'fallback_reasons': {}},
            },
        },
    }


def test_shared_rollout_helper_renders_low_cardinality_prometheus_metrics_without_uid_or_source_labels():
    rollout_doc = _enabled_rollout_doc() | {
        'grants': {
            'mcp': {'default_memory': True, 'archive': True},
            'developer_api': {},
            'omi_chat': {'default_memory': True, 'archive': True},
        }
    }
    db_client = _FirestoreFake({'users/u1/memory_control/state': rollout_doc})

    decisions = read_default_read_rollout_decisions(uid='u1', db_client=db_client)
    audit = build_default_read_rollout_audit_events(decisions)
    metrics = render_default_read_rollout_metrics(audit['counters'])

    assert db_client.document_get_paths == ['users/u1/memory_control/state']
    assert db_client.collection_paths == []
    assert 'uid' not in metrics
    assert 'u1' not in metrics
    assert 'source_path' not in metrics
    assert 'users/u1/memory_control/state' not in metrics
    assert 'default_read_rollout_decisions_total{consumer="mcp",outcome="enabled",fallback_reason="none"} 1' in metrics
    assert (
        'default_read_rollout_decisions_total{consumer="developer_api",outcome="fallback",'
        'fallback_reason="missing_developer_default_memory_grant"} 1' in metrics
    )
    assert (
        'default_read_rollout_decisions_total{consumer="omi_chat",outcome="enabled",fallback_reason="none"} 1'
        in metrics
    )
    assert 'archive' not in metrics


def test_shared_rollout_metrics_buckets_unknown_dynamic_fallback_reasons():
    counters = {
        'total': {'enabled': 0, 'fallback': 1},
        'by_consumer': {
            'mcp': {
                'enabled': 0,
                'fallback': 1,
                'fallback_reasons': {'customer-specific uid u1 path users/u1/memory_control/state': 1},
            }
        },
    }

    metrics = render_default_read_rollout_metrics(counters)

    assert 'customer-specific' not in metrics
    assert 'users/u1' not in metrics
    assert (
        'default_read_rollout_decisions_total{consumer="mcp",outcome="fallback",fallback_reason="other"} 1' in metrics
    )
