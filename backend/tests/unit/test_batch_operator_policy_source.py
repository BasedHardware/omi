"""Operator runs never pin a recovery policy from their own process environment."""

from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import sys

import pytest

from tests.unit.test_batch_pipeline_quarantine_recovery import setup, legacy_dependencies, row
from tests.unit.test_batch_pipeline_speech_redrive import enabled
from database.batch_pipeline_policy import UNPINNED_REFUSAL, UnpinnedPolicyRefused, load_stage_policy
from database.batch_pipeline_projection_protocol import ProjectionBlocked
from database.batch_pipeline_quarantine_recovery import SilenceDispositionStore
from database.batch_pipeline_speech_redrive import SpeechRedriveStore
from database.batch_pipeline_terminal_empty import TerminalEmptyStore, intent_snapshot
from utils.batch_pipeline.speech_redrive import redrive_one

OWNER = 'synthetic-owner'
SERVER = {
    'K_SERVICE': 'synthetic-serving-role',
    'BATCH_PIPELINE_RECOVERY_MODE': 'on',
    'BATCH_PIPELINE_RECOVERY_UID_ALLOWLIST': OWNER,
    'BATCH_PIPELINE_SPEECH_EMPTY_MULTILINGUAL_ENABLED': 'true',
    'BATCH_PIPELINE_TERMINAL_EMPTY_DISPOSITION_ENABLED': 'true',
}


def laptop_env(monkeypatch, *, enabled_locally):
    """The operator's own env: deliberately different from the serving role."""
    value = 'true' if enabled_locally else 'false'
    monkeypatch.setenv('K_SERVICE', 'operator-laptop')
    monkeypatch.setenv('BATCH_PIPELINE_RECOVERY_MODE', 'on' if enabled_locally else 'off')
    monkeypatch.setenv('BATCH_PIPELINE_SPEECH_EMPTY_MULTILINGUAL_ENABLED', value)
    monkeypatch.setenv('BATCH_PIPELINE_TERMINAL_EMPTY_DISPOSITION_ENABLED', value)


def unpinned(client):
    job = row(client)
    assert 'recovery' not in (job.get('policy_parts') or {})
    return job


@pytest.mark.parametrize('enabled_locally', [True, False])
def test_operator_without_server_flags_refuses_unpinned_unit_and_writes_nothing(
    setup, monkeypatch, legacy_dependencies, enabled_locally
):
    client, store, binding, artifacts, legacy, alternate, old = enabled(setup, monkeypatch, legacy_dependencies)
    laptop_env(monkeypatch, enabled_locally=enabled_locally)
    unpinned(client)
    before = deepcopy(client.rows)
    assert (
        redrive_one(store, artifacts, 'bad', binding.owner_id, 'plan', old, server_flags=None, clock=lambda: 100)
        == 'policy_unpinned'
    )
    with pytest.raises(UnpinnedPolicyRefused) as refused:
        SpeechRedriveStore(store, server_flags=None).prepare('bad', binding.owner_id, 'plan', old, 100)
    assert str(refused.value) == UNPINNED_REFUSAL and refused.value.stage == 'recovery'
    assert isinstance(refused.value, ProjectionBlocked)
    with pytest.raises(UnpinnedPolicyRefused):
        load_stage_policy(store, 'bad', 'recovery', server_flags=None)
    assert client.rows == before
    artifacts.fetch_audio.assert_not_called()
    legacy.assert_not_called()
    alternate.assert_not_called()


def test_other_operator_stores_refuse_unpinned_unit_without_writes(setup, monkeypatch, legacy_dependencies):
    client, store, binding, _, _, _, _ = enabled(setup, monkeypatch, legacy_dependencies)
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_DISPOSITION_ENABLED', 'true')
    laptop_env(monkeypatch, enabled_locally=True)
    job = unpinned(client)
    before = deepcopy(client.rows)
    with pytest.raises(UnpinnedPolicyRefused):
        SilenceDispositionStore(store, server_flags=None).prepare_silence('bad', binding.owner_id, 'plan', 100)
    with pytest.raises(UnpinnedPolicyRefused):
        TerminalEmptyStore(store, server_flags=None).prepare(
            'bad', binding.owner_id, 'plan', intent_snapshot(job), 'silence', False, 100
        )
    assert client.rows == before


def test_operator_stores_require_an_explicit_choice(setup):
    _, store, *_ = setup
    for cls in (SpeechRedriveStore, TerminalEmptyStore, SilenceDispositionStore):
        with pytest.raises(TypeError):
            cls(store)


def test_operator_with_server_flags_pins_server_values_not_its_own(setup, monkeypatch, legacy_dependencies):
    client, store, binding, artifacts, _, alternate, old = enabled(setup, monkeypatch, legacy_dependencies)
    laptop_env(monkeypatch, enabled_locally=False)
    unpinned(client)
    assert (
        redrive_one(store, artifacts, 'bad', binding.owner_id, 'plan', old, server_flags=SERVER, clock=lambda: 100)
        == 'recovered'
    )
    job = row(client)
    part = job['policy_parts']['recovery']
    assert part['source_role'] == 'synthetic-serving-role'
    assert part['recovery_enabled'] and part['speech_empty_multilingual'] and part['terminal_empty_disposition']
    assert job['policy_part_sources']['recovery'] == 'operator_server_flags'
    alternate.assert_called_once()


def test_operator_server_flags_disable_even_when_local_env_enables(setup, monkeypatch, legacy_dependencies):
    client, store, binding, artifacts, _, alternate, old = enabled(setup, monkeypatch, legacy_dependencies)
    laptop_env(monkeypatch, enabled_locally=True)
    server = {**SERVER, 'BATCH_PIPELINE_SPEECH_EMPTY_MULTILINGUAL_ENABLED': 'false'}
    assert (
        redrive_one(store, artifacts, 'bad', binding.owner_id, 'plan', old, server_flags=server, clock=lambda: 100)
        == 'disabled'
    )
    part = row(client)['policy_parts']['recovery']
    assert part['source_role'] == 'synthetic-serving-role' and not part['speech_empty_multilingual']
    alternate.assert_not_called()


def test_operator_reuses_a_pinned_policy_without_server_flags(setup, monkeypatch, legacy_dependencies):
    client, store, binding, artifacts, _, alternate, old = enabled(setup, monkeypatch, legacy_dependencies)
    _, pinned = load_stage_policy(store, 'bad', 'recovery', server_flags=SERVER)
    laptop_env(monkeypatch, enabled_locally=False)
    assert (
        redrive_one(store, artifacts, 'bad', binding.owner_id, 'plan', old, server_flags=None, clock=lambda: 100)
        == 'recovered'
    )
    assert row(client)['policy_parts']['recovery'] == pinned.to_dict()
    alternate.assert_called_once()


@pytest.mark.parametrize('server_flags', [None, SERVER])
def test_operator_copies_a_stored_sibling_part_without_resolving(setup, monkeypatch, legacy_dependencies, server_flags):
    client, store, *_ = enabled(setup, monkeypatch, legacy_dependencies)
    laptop_env(monkeypatch, enabled_locally=True)
    stored = {**SERVER, 'K_SERVICE': 'anchor-serving-role'}
    from config.policy import resolve_stage_policy

    pinned = resolve_stage_policy(OWNER, 'recovery', flags=stored).to_dict()
    sibling = client.rows[('batch_pipeline_prod_jobs', 'good')]
    sibling.update(policy_parts={'recovery': pinned}, policy_part_sources={'recovery': 'fallback'})
    row(client)['projection_binding']['segment_ids'] = ['good', 'bad']
    unpinned(client)
    _, policy = load_stage_policy(store, 'bad', 'recovery', server_flags=server_flags)
    assert policy.to_dict() == pinned and policy.source_role == 'anchor-serving-role'
    job = row(client)
    assert job['policy_parts']['recovery'] == pinned
    assert job['policy_part_sources']['recovery'] == 'fallback'
    assert client.rows[('batch_pipeline_prod_jobs', 'good')]['policy_parts']['recovery'] == pinned


def test_inherited_recovery_prepare_uses_the_operator_choice(setup, monkeypatch, legacy_dependencies):
    client, store, binding, *_ = enabled(setup, monkeypatch, legacy_dependencies)
    laptop_env(monkeypatch, enabled_locally=True)
    unpinned(client)
    before = deepcopy(client.rows)
    with pytest.raises(UnpinnedPolicyRefused):
        SilenceDispositionStore(store, server_flags=None).prepare('bad', binding.owner_id, 100)
    assert client.rows == before


def test_serving_path_still_resolves_its_own_environment(setup, monkeypatch, legacy_dependencies):
    client, store, *_ = enabled(setup, monkeypatch, legacy_dependencies)
    monkeypatch.setenv('K_SERVICE', 'backend-integration')
    unpinned(client)
    _, policy = load_stage_policy(store, 'bad', 'recovery')
    job = row(client)
    assert policy.source_role == 'backend-integration' and policy.recovery_enabled
    assert job['policy_parts']['recovery'] == policy.to_dict()
    assert job['policy_part_sources']['recovery'] == 'fallback'


def load_held():
    path = Path(__file__).parents[2] / 'scripts'
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))
    spec = importlib.util.spec_from_file_location('held_operator_flags', path / 'batch_pipeline_held_disposition.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_server_flags_file_is_explicit_scoped_and_validated(tmp_path, monkeypatch):
    held = load_held()
    monkeypatch.setenv('BATCH_PIPELINE_RECOVERY_MODE', 'on')
    assert held.load_server_flags(None) is None
    source = tmp_path / 'server.json'
    source.write_text(json.dumps({**SERVER, 'ENCRYPTION_SECRET': 'synthetic-secret', 'OTHER': 'x'}))
    assert held.load_server_flags(str(source)) == SERVER
    for body, reason in (
        ('{', 'server_flags_unreadable'),
        (json.dumps(['K_SERVICE']), 'server_flags_invalid'),
        (json.dumps({'K_SERVICE': 'role', 'BATCH_PIPELINE_RECOVERY_MODE': True}), 'server_flags_invalid'),
        (json.dumps({'BATCH_PIPELINE_RECOVERY_MODE': 'on'}), 'server_flags_role_required'),
    ):
        source.write_text(body)
        with pytest.raises(held.Refused, match=reason):
            held.load_server_flags(str(source))
    with pytest.raises(held.Refused, match='server_flags_unreadable'):
        held.load_server_flags(str(tmp_path / 'missing.json'))
