from dataclasses import dataclass

from config.memory_rollout import MemoryRolloutMode, MemoryRolloutConfig
from database.memory_collections import MemoryCollections
from utils.memory.default_read_rollout import DEFAULT_READ_ROLLOUT_TIMEOUT_SECONDS
from utils.memory.v3_control_reader_contract import (
    V3ControlDecisionReason,
    V3ControlReaderRequest,
    V3ControlRouteFamily,
    decide_v3_control_route,
)
from utils.memory.v3_control_state_adapter import read_v3_control, resolve_v3_effective_mode


@dataclass
class FakeSnapshot:
    data: dict | None
    exists: bool = True

    def to_dict(self):
        return self.data


class FakeDoc:
    def __init__(self, path, db):
        self.path = path
        self.db = db

    def get(self, timeout=None):
        self.db.get_calls.append((self.path, timeout))
        if self.path in self.db.fail_paths:
            raise RuntimeError('boom')
        if self.path not in self.db.docs:
            return FakeSnapshot(None, exists=False)
        return FakeSnapshot(self.db.docs[self.path])


class FakeDb:
    def __init__(self, docs=None, fail_paths=None):
        self.docs = docs or {}
        self.fail_paths = set(fail_paths or set())
        self.document_calls = []
        self.get_calls = []

    def document(self, path):
        self.document_calls.append(path)
        assert 'memory_items' not in path
        return FakeDoc(path, self)


def _config(mode=MemoryRolloutMode.read, enabled_users=('uid-a',)):
    return MemoryRolloutConfig(enabled_users=set(enabled_users), mode=mode)


def _doc(uid='uid-a', mode='read', **overrides):
    values = {
        'uid': uid,
        'schema_version': 1,
        'mode': mode,
        'mode_epoch': 1,
        'cutover_epoch': 1,
        'account_generation': 50,
        'fallback_projection_ready': True,
        'persistent_memory_writes_started': True,
        'writes_blocked': False,
        'stage_gates': {'shadow': 'passed', 'write': 'passed', 'read': 'passed'},
        'grants': {'omi_chat': {'default_memory': True, 'archive': False}},
    }
    values.update(overrides)
    return values


def _read_gate(enabled=True):
    return {'memory_reads_enabled': enabled, 'kill_switch_active': False}


def _write_gate(ready=True):
    return {
        'durable_outbox_enabled': ready,
        'dual_write_projection_ready': ready,
        'delete_convergence_ready': ready,
        'idempotency_contract_ready': ready,
    }


def _ready_docs(uid='uid-a', control_doc=None):
    control_path = MemoryCollections(uid=uid).memory_control_state
    return {
        control_path: control_doc or _doc(uid=uid),
        'memory_control/global_read_gate': _read_gate(True),
        'memory_control/write_convergence_gate': _write_gate(True),
    }


def test_non_enrolled_returns_legacy_eligibility_without_firestore_read():
    db = FakeDb()
    result = read_v3_control(uid='uid-a', db_client=db, rollout_config=_config(enabled_users=()))

    assert result.cohort_enrolled is False
    assert result.source_path == 'users/uid-a/memory_control/state'
    assert result.state is None
    assert db.document_calls == []
    decision = decide_v3_control_route(
        V3ControlReaderRequest('uid-a', 50, False, False),
        result,
    )
    assert decision.route_family == V3ControlRouteFamily.LEGACY_PRIMARY
    assert decision.reason == V3ControlDecisionReason.NON_ENROLLED_LEGACY_ALLOWED


def test_enrolled_reads_exact_control_doc_once_with_existing_timeout_and_no_memory_items_touch():
    db = FakeDb(_ready_docs())
    result = read_v3_control(uid='uid-a', db_client=db, rollout_config=_config())

    assert result.cohort_enrolled is True
    assert result.source_path == 'users/uid-a/memory_control/state'
    assert result.state is not None
    assert db.get_calls[0] == ('users/uid-a/memory_control/state', DEFAULT_READ_ROLLOUT_TIMEOUT_SECONDS)
    assert db.get_calls.count(('users/uid-a/memory_control/state', DEFAULT_READ_ROLLOUT_TIMEOUT_SECONDS)) == 1
    assert all('memory_items' not in path for path in db.document_calls)


def test_off_shadow_write_map_to_legacy_authoritative_and_do_not_read_global_gates():
    for mode in (MemoryRolloutMode.off, MemoryRolloutMode.shadow, MemoryRolloutMode.write):
        db = FakeDb({MemoryCollections(uid='uid-a').memory_control_state: _doc(mode=mode.value)})
        result = read_v3_control(uid='uid-a', db_client=db, rollout_config=_config(mode=MemoryRolloutMode.read))

        assert result.state.effective_mode == mode
        assert db.document_calls == ['users/uid-a/memory_control/state']
        decision = decide_v3_control_route(V3ControlReaderRequest('uid-a', 50, False, False), result)
        assert decision.route_family == V3ControlRouteFamily.LEGACY_PRIMARY
        assert decision.reason == V3ControlDecisionReason.ROLLOUT_LEGACY_AUTHORITATIVE
        assert decision.fallback_to_legacy_allowed is False


def test_global_ceiling_never_elevates_lower_persisted_mode_and_caps_higher_persisted_mode():
    assert resolve_v3_effective_mode(MemoryRolloutMode.read, MemoryRolloutMode.write) == MemoryRolloutMode.write
    assert resolve_v3_effective_mode(MemoryRolloutMode.write, MemoryRolloutMode.read) == MemoryRolloutMode.write
    assert resolve_v3_effective_mode('shadow', 'read') == MemoryRolloutMode.shadow
    assert resolve_v3_effective_mode('off', 'read') == MemoryRolloutMode.off


def test_omi_chat_grants_only_enable_default_memory_and_archive_is_strict_boolean():
    control_doc = _doc(
        grants={
            'developer_api': {'default_memory': True, 'archive': True},
            'mcp': {'default_memory': True, 'archive': True},
            'default_memory': True,
            'omi_chat': {'default_memory': False, 'archive': 'yes'},
        }
    )
    db = FakeDb(_ready_docs(control_doc=control_doc))
    result = read_v3_control(uid='uid-a', db_client=db, rollout_config=_config())

    assert result.state.default_memory_grant is False
    assert result.state.archive_allowed is False
    decision = decide_v3_control_route(V3ControlReaderRequest('uid-a', 50, False, False), result)
    assert decision.reason == V3ControlDecisionReason.NO_DEFAULT_MEMORY_GRANT
    assert decision.http_status == 403


def test_global_read_and_convergence_docs_are_read_only_for_effective_read_mode():
    read_db = FakeDb(_ready_docs())
    read_v3_control(uid='uid-a', db_client=read_db, rollout_config=_config())
    assert 'memory_control/global_read_gate' in read_db.document_calls
    assert 'memory_control/write_convergence_gate' in read_db.document_calls

    write_db = FakeDb({MemoryCollections(uid='uid-a').memory_control_state: _doc(mode='write')})
    read_v3_control(uid='uid-a', db_client=write_db, rollout_config=_config())
    assert write_db.document_calls == ['users/uid-a/memory_control/state']


def test_missing_malformed_uid_mismatch_unsupported_schema_and_transport_failures_are_typed():
    cases = [
        (FakeDb({}), V3ControlDecisionReason.MISSING_CONTROL_DOC),
        (
            FakeDb({MemoryCollections(uid='uid-a').memory_control_state: {'uid': 'uid-a'}}),
            V3ControlDecisionReason.UNSUPPORTED_CONTROL_SCHEMA,
        ),
        (
            FakeDb({MemoryCollections(uid='uid-a').memory_control_state: _doc(uid='other')}),
            V3ControlDecisionReason.UID_MISMATCH,
        ),
        (
            FakeDb({MemoryCollections(uid='uid-a').memory_control_state: _doc(schema_version=99)}),
            V3ControlDecisionReason.UNSUPPORTED_CONTROL_SCHEMA,
        ),
        (
            FakeDb(fail_paths={MemoryCollections(uid='uid-a').memory_control_state}),
            V3ControlDecisionReason.CONTROL_READ_FAILED,
        ),
        (
            FakeDb({MemoryCollections(uid='uid-a').memory_control_state: _doc(mode_epoch='bad')}),
            V3ControlDecisionReason.MALFORMED_CONTROL_DOC,
        ),
    ]

    for db, reason in cases:
        result = read_v3_control(uid='uid-a', db_client=db, rollout_config=_config())
        decision = decide_v3_control_route(V3ControlReaderRequest('uid-a', 50, False, False), result)
        assert decision.route_family == V3ControlRouteFamily.FAIL_CLOSED
        assert decision.reason == reason
        assert decision.fallback_to_legacy_allowed is False


def test_mode_epoch_one_with_account_generation_fifty_is_valid_and_not_compared():
    db = FakeDb(_ready_docs(control_doc=_doc(mode_epoch=1, cutover_epoch=1, account_generation=50)))
    result = read_v3_control(uid='uid-a', db_client=db, rollout_config=_config())
    decision = decide_v3_control_route(V3ControlReaderRequest('uid-a', 50, False, False), result)

    assert result.state.mode_epoch == 1
    assert result.state.account_generation == 50
    assert decision.route_family == V3ControlRouteFamily.MEMORY_PROJECTION


def test_archive_defaults_false_strict_boolean_and_archive_denial_is_403():
    db = FakeDb(_ready_docs(control_doc=_doc(grants={'omi_chat': {'default_memory': True}})))
    result = read_v3_control(uid='uid-a', db_client=db, rollout_config=_config())

    assert result.state.archive_allowed is False
    decision = decide_v3_control_route(V3ControlReaderRequest('uid-a', 50, False, False, True), result)
    assert decision.reason == V3ControlDecisionReason.ARCHIVE_NOT_ALLOWED
    assert decision.http_status == 403


def test_stale_short_term_is_absent_from_adapter_state():
    db = FakeDb(_ready_docs())
    result = read_v3_control(uid='uid-a', db_client=db, rollout_config=_config())

    assert result.state is not None
    assert not hasattr(result.state, 'short_term_freshness_default_visible')
    assert not hasattr(result.state, 'stale_short_term_default_visible')
