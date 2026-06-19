from config.v17_memory import PASSED, V17Mode, V17StageGate
from utils.memory.v17_default_read_rollout import read_v17_default_read_rollout


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
    assert mcp_decision.v17_default_mcp_enabled is True
    assert developer_decision.v17_default_developer_enabled is True


def test_shared_rollout_helper_fails_closed_for_missing_malformed_uid_mismatch_and_missing_consumer_grant():
    missing = _FirestoreFake()
    missing_decision = read_v17_default_read_rollout(uid='u1', db_client=missing, consumer='mcp')
    assert missing_decision.v17_default_mcp_enabled is False
    assert missing_decision.fallback_reason == 'missing_rollout_state'
    assert missing.collection_paths == []

    malformed = _FirestoreFake({'users/u1/memory_control/state': {'uid': 'u1', 'mode': 'read', 'stage_gates': 'bad'}})
    malformed_decision = read_v17_default_read_rollout(uid='u1', db_client=malformed, consumer='developer_api')
    assert malformed_decision.v17_default_developer_enabled is False
    assert malformed_decision.fallback_reason == 'malformed_rollout_state'
    assert malformed.collection_paths == []

    uid_mismatch = _FirestoreFake({'users/u1/memory_control/state': _enabled_rollout_doc(uid='other')})
    uid_mismatch_decision = read_v17_default_read_rollout(uid='u1', db_client=uid_mismatch, consumer='mcp')
    assert uid_mismatch_decision.v17_default_mcp_enabled is False
    assert uid_mismatch_decision.fallback_reason == 'uid_mismatch'
    assert uid_mismatch.collection_paths == []

    no_grant = _FirestoreFake(
        {'users/u1/memory_control/state': _enabled_rollout_doc() | {'grants': {'developer_api': {}}}}
    )
    no_grant_decision = read_v17_default_read_rollout(uid='u1', db_client=no_grant, consumer='developer_api')
    assert no_grant_decision.rollout_capabilities.v17_reads_enabled is True
    assert no_grant_decision.app_has_default_memory_grant is False
    assert no_grant_decision.v17_default_developer_enabled is False
    assert no_grant_decision.fallback_reason == 'missing_developer_default_memory_grant'
    assert no_grant.collection_paths == []
