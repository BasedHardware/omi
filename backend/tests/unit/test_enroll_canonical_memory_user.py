from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / 'scripts/enroll_canonical_memory_user.py'


def load_script():
    spec = importlib.util.spec_from_file_location('enroll_canonical_memory_user', SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class _Snapshot:
    def __init__(self, data=None):
        self._data = data
        self.exists = data is not None

    def to_dict(self):
        return self._data


class _Document:
    def __init__(self, db, path):
        self._db = db
        self._path = path

    def get(self):
        return _Snapshot(self._db.docs.get(self._path))

    def set(self, payload, merge=False):
        self._db.writes.append((self._path, payload, merge))
        if merge and self._path in self._db.docs:
            self._db.docs[self._path] = self._db.docs[self._path] | payload
        else:
            self._db.docs[self._path] = dict(payload)


class _Db:
    def __init__(self, docs=None):
        self.docs = docs or {}
        self.writes = []

    def document(self, path):
        return _Document(self, path)


def test_write_stage_builds_closed_read_gate_and_enabled_write_state():
    script = load_script()

    docs = script.build_rollout_documents(uid='uid-a', stage='write', account_generation=1)
    payloads = {doc.path: doc.payload for doc in docs}

    assert payloads['memory_control/global_read_gate']['memory_reads_enabled'] is False
    assert payloads['memory_control/global_read_gate']['kill_switch_active'] is True
    assert payloads['memory_control/write_convergence_gate']['durable_outbox_enabled'] is True
    state = payloads['users/uid-a/memory_control/state']
    assert state['mode'] == 'write'
    assert state['writes_blocked'] is False
    assert state['persistent_memory_writes_started'] is True
    assert state['stage_gates']['shadow'] == 'passed'
    assert state['stage_gates']['write'] == 'passed'
    assert state['stage_gates']['read'] == 'blocked'
    assert state['grants']['omi_chat']['default_memory'] is False


def test_read_stage_builds_open_read_gate_and_default_memory_grant():
    script = load_script()

    docs = script.build_rollout_documents(uid='uid-a', stage='read', account_generation=7)
    payloads = {doc.path: doc.payload for doc in docs}

    assert payloads['memory_control/global_read_gate']['memory_reads_enabled'] is True
    assert payloads['memory_control/global_read_gate']['kill_switch_active'] is False
    state = payloads['users/uid-a/memory_control/state']
    assert state['mode'] == 'read'
    assert state['fallback_projection_ready'] is True
    assert state['stage_gates']['read'] == 'passed'
    assert state['grants']['omi_chat']['default_memory'] is True


def test_apply_refuses_existing_different_docs_without_acknowledgement():
    script = load_script()
    docs = script.build_rollout_documents(uid='uid-a', stage='write', account_generation=1)
    db = _Db({'memory_control/global_read_gate': {'memory_reads_enabled': True, 'kill_switch_active': False}})

    with pytest.raises(RuntimeError, match='Refusing to update existing differing docs'):
        script.apply_documents(db, docs, allow_existing_update=False)

    assert db.writes == []


def test_apply_writes_merge_when_update_acknowledged():
    script = load_script()
    docs = script.build_rollout_documents(uid='uid-a', stage='write', account_generation=1)
    db = _Db({'memory_control/global_read_gate': {'memory_reads_enabled': True, 'kill_switch_active': False}})

    result = script.apply_documents(db, docs, allow_existing_update=True)

    assert result['written_paths'] == [doc.path for doc in docs]
    assert 'memory_control/global_read_gate' in result['updated_existing_paths']
    assert all(merge is True for _, _, merge in db.writes)


def test_v3_read_prereq_inspection_reports_missing_and_present_docs():
    script = load_script()
    db = _Db({'users/uid-a/memory_state/head': {'source': 'memory_state_head'}})

    result = script.inspect_v3_read_prerequisites(db, uid='uid-a')

    assert result == {
        'users/uid-a/memory_state/head': True,
        'users/uid-a/v3_compatibility_projection/state': False,
    }


def test_read_stage_apply_requires_prerequisite_docs():
    script = load_script()

    with pytest.raises(RuntimeError, match='requires existing v3 read prerequisite docs'):
        script.assert_v3_read_prerequisites_ready(
            {
                'users/uid-a/memory_state/head': True,
                'users/uid-a/v3_compatibility_projection/state': False,
            }
        )


def test_read_stage_apply_accepts_present_prerequisite_docs():
    script = load_script()

    script.assert_v3_read_prerequisites_ready(
        {
            'users/uid-a/memory_state/head': True,
            'users/uid-a/v3_compatibility_projection/state': True,
        }
    )
