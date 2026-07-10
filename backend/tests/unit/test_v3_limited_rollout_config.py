import importlib.util
from pathlib import Path

import pytest

from config.memory_rollout import MemoryRolloutMode
from utils.memory.v3_limited_rollout_config import (
    GLOBAL_READ_GATE_PATH,
    WRITE_CONVERGENCE_GATE_PATH,
    build_limited_rollout_config_bundle,
    build_whitelisted_user_control_state,
)


def _script_module():
    script = Path(__file__).resolve().parents[2] / 'scripts' / 'v3_limited_rollout_config.py'
    spec = importlib.util.spec_from_file_location('v3_limited_rollout_config_script', script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_disabled_limited_rollout_bundle_is_inert_by_default():
    bundle = build_limited_rollout_config_bundle(uid='uid-a', account_generation=7)

    assert bundle.apply_by_default is False
    assert bundle.writes_executed is False
    assert bundle.documents[GLOBAL_READ_GATE_PATH]['memory_reads_enabled'] is False
    assert bundle.documents[GLOBAL_READ_GATE_PATH]['kill_switch_active'] is True
    assert bundle.documents[WRITE_CONVERGENCE_GATE_PATH]['durable_outbox_enabled'] is False
    assert bundle.documents[WRITE_CONVERGENCE_GATE_PATH]['idempotency_contract_ready'] is False
    assert 'users/uid-a/memory_state/head' not in bundle.documents
    assert bundle.documents['users/uid-a/memory_control/state']['mode'] == 'off'
    assert bundle.documents['users/uid-a/memory_control/state']['fallback_projection_ready'] is False
    assert bundle.documents['users/uid-a/memory_control/state']['persistent_memory_writes_started'] is False
    assert bundle.documents['users/uid-a/memory_control/state']['writes_blocked'] is True
    assert bundle.documents['users/uid-a/memory_control/state']['stage_gates'] == {
        'shadow': 'blocked',
        'write': 'blocked',
        'read': 'blocked',
    }
    assert bundle.documents['users/uid-a/memory_control/state']['grants'] == {
        'omi_chat': {'default_memory': False, 'archive': False}
    }


def test_limited_rollout_bundle_has_no_activation_flags_or_self_attested_readiness():
    bundle = build_limited_rollout_config_bundle(uid='uid-a', account_generation=7)

    assert bundle.documents[GLOBAL_READ_GATE_PATH]['memory_reads_enabled'] is False
    assert bundle.documents[GLOBAL_READ_GATE_PATH]['kill_switch_active'] is True
    assert all(
        value is False
        for key, value in bundle.documents[WRITE_CONVERGENCE_GATE_PATH].items()
        if key.endswith('_ready') or key.endswith('_enabled')
    )
    assert bundle.documents['users/uid-a/memory_control/state']['fallback_projection_ready'] is False


@pytest.mark.parametrize('bad_uid,account_generation', [('', 1), ('uid-a', -1)])
def test_user_control_template_rejects_missing_uid_or_negative_generation(bad_uid, account_generation):
    with pytest.raises(ValueError):
        build_whitelisted_user_control_state(
            uid=bad_uid, account_generation=account_generation, mode=MemoryRolloutMode.read
        )


def test_cli_report_is_dry_run_config_only():
    report = _script_module().build_report(uid='uid-a', account_generation=7)

    assert report['artifact'] == 'v3_limited_rollout_config'
    assert report['status'] == 'SAFE_INERT_TEMPLATE'
    assert report['read_only'] is True
    assert report['writes_executed'] is False
    assert report['apply_by_default'] is False
    assert set(report['documents']) == {
        GLOBAL_READ_GATE_PATH,
        WRITE_CONVERGENCE_GATE_PATH,
        'users/uid-a/memory_control/state',
    }
