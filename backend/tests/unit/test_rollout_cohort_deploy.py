"""Staged migration preserves every live Helm fallback until a later removal PR."""

from pathlib import Path
import re
import subprocess

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]


def private_key(name):
    return name.endswith('_UID_ALLOWLIST') or name in {'MOBILE_STANDARD_BATCH_UIDS', 'OMI_MESSAGING_CHANNELS_UIDS'}


def assert_private_bindings_absent(value):
    if isinstance(value, dict):
        for key, child in value.items():
            assert not private_key(key), key
            if key == 'name' and isinstance(child, str):
                assert not private_key(child), child
            assert_private_bindings_absent(child)
    elif isinstance(value, list):
        for child in value:
            assert_private_bindings_absent(child)


def test_cloud_run_manifest_preserves_live_env_by_omitting_private_bindings():
    manifest = yaml.load((ROOT / 'backend/deploy/runtime_env.yaml').read_text(), Loader=yaml.CSafeLoader)
    for stage in ('dev', 'prod'):
        assert_private_bindings_absent(manifest['environments'][stage]['cloud_run'])


@pytest.mark.parametrize('component', ['backend-listen', 'pusher'])
@pytest.mark.parametrize('stage', ['dev', 'prod'])
def test_helm_retains_legacy_fallbacks(component, stage):
    path = ROOT / f'backend/charts/{component}/{stage}_omi_{component.replace("-", "_")}_values.yaml'
    env = {row['name']: row.get('value', '') for row in yaml.load(path.read_text(), Loader=yaml.CSafeLoader)['env']}
    assert 'AUDIO_ARCHIVE_UID_ALLOWLIST' in env
    assert 'DREAM_AGENT_UID_ALLOWLIST' in env
    if stage == 'prod':
        assert env['DREAM_AGENT_UID_ALLOWLIST']
        assert env['SPEAKER_GROUPING_SHADOW_UID_ALLOWLIST']
        if component == 'backend-listen':
            for key in (
                'SYNC_LINEAGE_RESOLVE_UID_ALLOWLIST',
                'STT_LIVE_DEMAND_UID_ALLOWLIST',
                'MOBILE_STANDARD_BATCH_UIDS',
            ):
                assert env[key]
    if stage == 'dev':
        assert env['AUDIO_ARCHIVE_UID_ALLOWLIST']
        if component == 'pusher':
            assert env['TRANSCRIPTION_SHADOW_UID_ALLOWLIST'] == 'omi-release-probe'


def test_no_secret_manager_cohort_provisioning_remains():
    path = ROOT / 'backend/charts/backend-secrets/prod_omi_backend_secrets_values.yaml'
    assert_private_bindings_absent(yaml.load(path.read_text(), Loader=yaml.CSafeLoader))
    assert not (ROOT / 'backend/scripts/private_cohort_secrets.py').exists()


def test_cloud_run_merge_and_helm_replace_are_paired_with_cohort_aware_runtime(monkeypatch):
    # Cloud Run retains omitted live env values. Helm retains its legacy entries.
    # Both stay available when the Firestore field is missing.
    from config.batch_pipeline import enabled_for
    from config import rollout_cohorts

    assert callable(enabled_for) and callable(rollout_cohorts.in_rollout_cohort)
    from config import summary_guarantee

    monkeypatch.setenv('FIRST_SUMMARY_DEADLINE_ENABLED', 'true')
    monkeypatch.setenv('FIRST_SUMMARY_DEADLINE_PERCENT', '0')
    monkeypatch.delenv('FIRST_SUMMARY_UID_ALLOWLIST', raising=False)
    assert not summary_guarantee.enabled('nonmember')
    monkeypatch.setenv('FIRST_SUMMARY_UID_ALLOWLIST', '')
    assert not summary_guarantee.enabled('nonmember')
    listen = (ROOT / 'backend/routers/transcribe.py').read_text()
    assert listen.index('await warm_rollout_cohorts(request.uid)') < listen.index('run_listen_session(request)')


@pytest.mark.parametrize('stage', ['dev', 'prod'])
def test_existing_runtime_identity_scopes_every_serving_host(stage):
    manifest = yaml.load((ROOT / 'backend/deploy/runtime_env.yaml').read_text(), Loader=yaml.CSafeLoader)
    services = manifest['environments'][stage]['cloud_run']['services']
    for name in ['backend', 'backend-sync', 'backend-sync-backfill', 'backend-integration']:
        assert services[name]['env']['OMI_ENV_STAGE']['value'] == stage
    for component in ['backend-listen', 'pusher']:
        path = ROOT / f'backend/charts/{component}/{stage}_omi_{component.replace("-", "_")}_values.yaml'
        env = yaml.load(path.read_text(), Loader=yaml.CSafeLoader)['env']
        assert [entry['value'] for entry in env if entry['name'] == 'OMI_ENV_STAGE'] == [stage]


def test_prod_messaging_policy_is_omitted_so_cloud_run_keeps_live_value():
    manifest = yaml.load((ROOT / 'backend/deploy/runtime_env.yaml').read_text(), Loader=yaml.CSafeLoader)
    for service in manifest['environments']['prod']['cloud_run']['services'].values():
        assert 'OMI_MESSAGING_CHANNEL_POLICY' not in service.get('env', {})
        assert 'OMI_MESSAGING_CHANNEL_POLICY' not in service.get('forbidden_env', [])
