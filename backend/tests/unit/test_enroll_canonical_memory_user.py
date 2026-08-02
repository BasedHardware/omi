from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

from tests.store_fakes import FakeDocumentStore

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / 'scripts/enroll_canonical_memory_user.py'


def load_script():
    spec = importlib.util.spec_from_file_location('enroll_canonical_memory_user', SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


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
    fake = FakeDocumentStore()
    fake.set('memory_control/global_read_gate', {'memory_reads_enabled': True, 'kill_switch_active': False})

    with pytest.raises(RuntimeError, match='Refusing to update existing differing docs'):
        script.apply_documents(fake, docs, allow_existing_update=False)

    # Refusal raised before any write: the pre-existing doc is untouched and no new docs appear.
    assert fake.get('memory_control/global_read_gate').to_dict() == {
        'memory_reads_enabled': True,
        'kill_switch_active': False,
    }
    assert not fake.exists('memory_control/write_convergence_gate')
    assert not fake.exists('users/uid-a/memory_control/state')


def test_apply_writes_merge_when_update_acknowledged():
    script = load_script()
    docs = script.build_rollout_documents(uid='uid-a', stage='write', account_generation=1)
    payloads = {doc.path: doc.payload for doc in docs}
    fake = FakeDocumentStore()
    # ``legacy_marker`` is absent from the requested payload: it survives only under merge=True.
    fake.set(
        'memory_control/global_read_gate',
        {'memory_reads_enabled': True, 'kill_switch_active': False, 'legacy_marker': 'keep'},
    )

    result = script.apply_documents(fake, docs, allow_existing_update=True)

    assert result['written_paths'] == [doc.path for doc in docs]
    assert 'memory_control/global_read_gate' in result['updated_existing_paths']

    merged_gate = fake.get('memory_control/global_read_gate').to_dict()
    assert merged_gate == {**{'legacy_marker': 'keep'}, **payloads['memory_control/global_read_gate']}
    assert merged_gate['memory_reads_enabled'] is False
    assert merged_gate['kill_switch_active'] is True

    for doc in docs:
        assert fake.exists(doc.path)
    assert fake.get('memory_control/write_convergence_gate').to_dict() == payloads[
        'memory_control/write_convergence_gate'
    ]
    assert fake.get('users/uid-a/memory_control/state').to_dict() == payloads['users/uid-a/memory_control/state']


def test_v3_read_prereq_inspection_rejects_legacy_shaped_state_head():
    script = load_script()
    fake = FakeDocumentStore()
    fake.set('users/uid-a/memory_state/head', {'source': 'memory_state_head'})

    result = script.inspect_v3_read_prerequisites(fake, uid='uid-a')

    assert result == {
        'users/uid-a/memory_state/head': False,
        'users/uid-a/v3_compatibility_projection/state': False,
    }


def test_read_stage_apply_requires_prerequisite_docs():
    script = load_script()

    with pytest.raises(RuntimeError, match='requires valid v3 read prerequisite docs'):
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
