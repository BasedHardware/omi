from config.v17_memory import PASSED, V17Mode, V17StageGate
from utils.memory.v17_default_read_rollout import (
    V17ReadDecision,
    build_v17_default_read_rollout_audit_events,
    legacy_safe_v17_default_read_rollout_decision,
    read_v17_archive_read_rollout,
    render_v17_default_read_rollout_metrics,
    read_v17_default_read_rollout,
    read_v17_default_read_rollout_decisions,
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

    def get(self):
        self._db_client.document_get_paths.append(self.path)
        if self.path not in self._db_client.docs:
            return _Snapshot(None, exists=False)
        return _Snapshot(self._db_client.docs[self.path], exists=True)


class _FirestoreFake:
    def __init__(self, docs=None):
        self.docs = docs or {}
        self.document_get_paths = []
        self.collection_paths = []

    def document(self, path):
        return _DocumentRef(self, path)

    def collection(self, path):
        self.collection_paths.append(path)
        raise AssertionError('rollout helper must not read memory_items collections')


def _enabled_rollout_doc(uid='u1'):
    return {
        'uid': uid,
        'mode': V17Mode.read.value,
        'mode_epoch': 7,
        'cutover_epoch': 7,
        'account_generation': 3,
        'fallback_projection_ready': True,
        'persistent_v17_writes_started': True,
        'writes_blocked': False,
        'stage_gates': {
            V17StageGate.shadow.value: PASSED,
            V17StageGate.write.value: PASSED,
            V17StageGate.read.value: PASSED,
        },
        'grants': {
            'mcp': {'default_memory': True, 'archive': True},
            'developer_api': {'default_memory': True, 'archive': True},
        },
        'mcp_default_memory_grant': False,
        'developer_default_memory_grant': False,
    }


def test_shared_rollout_helper_reads_memory_control_state_for_mcp_and_developer_grants_without_archive_default():
    db_client = _FirestoreFake({'users/u1/memory_control/state': _enabled_rollout_doc()})

    mcp_decision = read_v17_default_read_rollout(uid='u1', db_client=db_client, consumer='mcp')
    developer_decision = read_v17_default_read_rollout(uid='u1', db_client=db_client, consumer='developer_api')

    assert db_client.document_get_paths == ['users/u1/memory_control/state', 'users/u1/memory_control/state']
    assert db_client.collection_paths == []
    assert mcp_decision.rollout_capabilities.v17_reads_enabled is True
    assert developer_decision.rollout_capabilities.v17_reads_enabled is True
    assert mcp_decision.app_has_default_memory_grant is True
    assert developer_decision.app_has_default_memory_grant is True
    assert mcp_decision.archive_capability is False
    assert developer_decision.archive_capability is False
    assert mcp_decision.read_decision == V17ReadDecision.USE_V17
    assert developer_decision.read_decision == V17ReadDecision.USE_V17
    assert mcp_decision.v17_default_mcp_enabled is True
    assert developer_decision.v17_default_developer_enabled is True


def test_shared_rollout_helper_fails_closed_for_missing_malformed_uid_mismatch_and_missing_consumer_grant():
    missing = _FirestoreFake()
    missing_decision = read_v17_default_read_rollout(uid='u1', db_client=missing, consumer='mcp')
    assert missing_decision.v17_default_mcp_enabled is False
    assert missing_decision.read_decision == V17ReadDecision.DENY_MEMORY
    assert missing_decision.fallback_reason == 'missing_rollout_state'
    assert missing.collection_paths == []

    malformed = _FirestoreFake({'users/u1/memory_control/state': {'uid': 'u1', 'mode': 'read', 'stage_gates': 'bad'}})
    malformed_decision = read_v17_default_read_rollout(uid='u1', db_client=malformed, consumer='developer_api')
    assert malformed_decision.v17_default_developer_enabled is False
    assert malformed_decision.read_decision == V17ReadDecision.DENY_MEMORY
    assert malformed_decision.fallback_reason == 'malformed_rollout_state'
    assert malformed.collection_paths == []

    uid_mismatch = _FirestoreFake({'users/u1/memory_control/state': _enabled_rollout_doc(uid='other')})
    uid_mismatch_decision = read_v17_default_read_rollout(uid='u1', db_client=uid_mismatch, consumer='mcp')
    assert uid_mismatch_decision.v17_default_mcp_enabled is False
    assert uid_mismatch_decision.read_decision == V17ReadDecision.DENY_MEMORY
    assert uid_mismatch_decision.fallback_reason == 'uid_mismatch'
    assert uid_mismatch.collection_paths == []

    no_grant = _FirestoreFake(
        {'users/u1/memory_control/state': _enabled_rollout_doc() | {'grants': {'developer_api': {}}}}
    )
    no_grant_decision = read_v17_default_read_rollout(uid='u1', db_client=no_grant, consumer='developer_api')
    assert no_grant_decision.rollout_capabilities.v17_reads_enabled is True
    assert no_grant_decision.app_has_default_memory_grant is False
    assert no_grant_decision.v17_default_developer_enabled is False
    assert no_grant_decision.read_decision == V17ReadDecision.DENY_MEMORY
    assert no_grant_decision.fallback_reason == 'missing_developer_default_memory_grant'
    assert no_grant.collection_paths == []


def test_shared_rollout_helper_distinguishes_shadow_only_and_explicit_legacy_safe_decisions():
    shadow_doc = _enabled_rollout_doc() | {
        'mode': V17Mode.shadow.value,
        'fallback_projection_ready': False,
        'stage_gates': {V17StageGate.shadow.value: PASSED},
        'grants': {'mcp': {'default_memory': True}},
    }
    db_client = _FirestoreFake({'users/u1/memory_control/state': shadow_doc})

    shadow_decision = read_v17_default_read_rollout(uid='u1', db_client=db_client, consumer='mcp')
    legacy_safe_decision = legacy_safe_v17_default_read_rollout_decision(
        uid='u1', source_path='legacy/users/u1/memories', consumer='mcp', reason='explicit_legacy_endpoint'
    )

    assert shadow_decision.read_decision == V17ReadDecision.SHADOW_ONLY
    assert shadow_decision.v17_default_enabled is False
    assert shadow_decision.fallback_reason == 'shadow_only'
    assert legacy_safe_decision.read_decision == V17ReadDecision.USE_LEGACY_SAFE
    assert legacy_safe_decision.fallback_reason == 'explicit_legacy_endpoint'


def test_shared_rollout_helper_computes_persisted_archive_capability_distinct_from_default_reads():
    rollout_doc = _enabled_rollout_doc() | {
        'grants': {
            'omi_chat': {'default_memory': True, 'archive': True},
        }
    }
    db_client = _FirestoreFake({'users/u1/memory_control/state': rollout_doc})

    default_decision = read_v17_default_read_rollout(uid='u1', db_client=db_client, consumer='omi_chat')
    archive_decision = read_v17_archive_read_rollout(uid='u1', db_client=db_client, consumer='omi_chat')

    assert db_client.document_get_paths == ['users/u1/memory_control/state', 'users/u1/memory_control/state']
    assert db_client.collection_paths == []
    assert default_decision.read_decision == V17ReadDecision.USE_V17
    assert default_decision.archive_capability is False
    assert archive_decision.read_decision == V17ReadDecision.USE_V17
    assert archive_decision.archive_capability is True
    assert archive_decision.app_has_default_memory_grant is True


def test_shared_rollout_helper_fails_closed_for_missing_malformed_disabled_and_no_archive_grant():
    missing_archive = _enabled_rollout_doc() | {'grants': {'omi_chat': {'default_memory': True}}}
    missing_archive_decision = read_v17_archive_read_rollout(
        uid='u1', db_client=_FirestoreFake({'users/u1/memory_control/state': missing_archive}), consumer='omi_chat'
    )
    assert missing_archive_decision.read_decision == V17ReadDecision.DENY_MEMORY
    assert missing_archive_decision.fallback_reason == 'missing_chat_archive_capability'
    assert missing_archive_decision.archive_capability is False

    malformed_archive = _enabled_rollout_doc() | {'grants': {'omi_chat': {'default_memory': True, 'archive': 'yes'}}}
    malformed_archive_decision = read_v17_archive_read_rollout(
        uid='u1', db_client=_FirestoreFake({'users/u1/memory_control/state': malformed_archive}), consumer='omi_chat'
    )
    assert malformed_archive_decision.read_decision == V17ReadDecision.DENY_MEMORY
    assert malformed_archive_decision.fallback_reason == 'malformed_archive_capability'
    assert malformed_archive_decision.archive_capability is False

    disabled_archive = _enabled_rollout_doc() | {
        'mode': V17Mode.off.value,
        'grants': {'omi_chat': {'default_memory': True, 'archive': True}},
    }
    disabled_archive_decision = read_v17_archive_read_rollout(
        uid='u1', db_client=_FirestoreFake({'users/u1/memory_control/state': disabled_archive}), consumer='omi_chat'
    )
    assert disabled_archive_decision.read_decision == V17ReadDecision.DENY_MEMORY
    assert disabled_archive_decision.fallback_reason == 'v17_reads_disabled'
    assert disabled_archive_decision.archive_capability is False

    no_default_grant = _enabled_rollout_doc() | {'grants': {'omi_chat': {'archive': True}}}
    no_default_grant_decision = read_v17_archive_read_rollout(
        uid='u1', db_client=_FirestoreFake({'users/u1/memory_control/state': no_default_grant}), consumer='omi_chat'
    )
    assert no_default_grant_decision.read_decision == V17ReadDecision.DENY_MEMORY
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

    decisions = read_v17_default_read_rollout_decisions(uid='u1', db_client=db_client)
    audit = build_v17_default_read_rollout_audit_events(decisions)

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
                'read_decision': 'USE_V17',
                'fallback_reason': None,
                'default_memory_grant': True,
                'v17_reads_enabled': True,
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
                'v17_reads_enabled': True,
                'archive_default_visible': False,
                'archive_capability': False,
            },
            {
                'uid': 'u1',
                'source_path': 'users/u1/memory_control/state',
                'consumer': 'omi_chat',
                'enabled': True,
                'outcome': 'enabled',
                'read_decision': 'USE_V17',
                'fallback_reason': None,
                'default_memory_grant': True,
                'v17_reads_enabled': True,
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

    decisions = read_v17_default_read_rollout_decisions(uid='u1', db_client=db_client)
    audit = build_v17_default_read_rollout_audit_events(decisions)
    metrics = render_v17_default_read_rollout_metrics(audit['counters'])

    assert db_client.document_get_paths == ['users/u1/memory_control/state']
    assert db_client.collection_paths == []
    assert 'uid' not in metrics
    assert 'u1' not in metrics
    assert 'source_path' not in metrics
    assert 'users/u1/memory_control/state' not in metrics
    assert (
        'v17_default_read_rollout_decisions_total{consumer="mcp",outcome="enabled",fallback_reason="none"} 1' in metrics
    )
    assert (
        'v17_default_read_rollout_decisions_total{consumer="developer_api",outcome="fallback",'
        'fallback_reason="missing_developer_default_memory_grant"} 1' in metrics
    )
    assert (
        'v17_default_read_rollout_decisions_total{consumer="omi_chat",outcome="enabled",fallback_reason="none"} 1'
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

    metrics = render_v17_default_read_rollout_metrics(counters)

    assert 'customer-specific' not in metrics
    assert 'users/u1' not in metrics
    assert (
        'v17_default_read_rollout_decisions_total{consumer="mcp",outcome="fallback",fallback_reason="other"} 1'
        in metrics
    )
