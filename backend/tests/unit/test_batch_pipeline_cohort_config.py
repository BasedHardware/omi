"""Rollout fences across the rendered CPU hosts and the dedicated GPU chart."""

from pathlib import Path

import pytest
import yaml

from config.batch_pipeline import enabled_for

ROOT = Path(__file__).resolve().parents[2]
UID = 'vi7SA9ckQCe4ccobWNxlbdcNdC23'
SERVICES = ('backend', 'backend-sync', 'backend-sync-backfill', 'backend-integration')


@pytest.fixture(scope='module')
def manifest():
    return yaml.load((ROOT / 'deploy/runtime_env.yaml').read_text(), Loader=yaml.CSafeLoader)['environments']


def hosts(config):
    return {
        **{name: config['cloud_run']['services'][name]['env'] for name in SERVICES},
        'backend-listen': config['gke']['backend-listen']['env'],
    }


def test_only_david_is_admitted_on_every_sync_host(manifest, monkeypatch):
    for stage, config in manifest.items():
        for env in hosts(config).values():
            for key in ('BATCH_PIPELINE_ENABLED', 'BATCH_PIPELINE_PERCENT', 'BATCH_PIPELINE_UID_ALLOWLIST'):
                monkeypatch.setenv(key, env[key]['value'])
            # Admission paused 2026-10-16 (silent worker failures); prod keeps the David allowlist for resume.
            assert enabled_for(UID) is False
            for excluded in ('', 'another-owner', UID + '-suffix'):
                assert not enabled_for(excluded)
            assert env['BATCH_PIPELINE_PERCENT']['value'] == '0'
            assert env['BATCH_PIPELINE_WORKER_ENABLED']['value'] == 'false'
            assert env['BATCH_PIPELINE_SHARED_LIVE_ENABLED']['value'] == 'false'
            if stage == 'dev':
                assert env['BATCH_PIPELINE_SERVING_ENABLED']['value'] == 'false'
                assert env['BATCH_PIPELINE_UID_ALLOWLIST']['value'] == ''
                assert env['BATCH_PIPELINE_API_URL']['value'] == ''


def test_only_always_cpu_integration_host_runs_projection_pump(manifest):
    for stage, config in manifest.items():
        active = [
            name for name, env in hosts(config).items() if env['BATCH_PIPELINE_SERVING_ENABLED']['value'] == 'true'
        ]
        assert active == (['backend-integration'] if stage == 'prod' else [])
    deploy = (ROOT.parent / '.github/actions/deploy-backend-stack/action.yml').read_text()
    integration = deploy.split('id: deploy-backend-integration', 1)[1].split('id: capture-backend-integration', 1)[0]
    assert '--no-cpu-throttling' in integration and '--min-instances=3' in integration


def test_policy_identity_storage_and_unit_ceiling_match_chart(manifest):
    chart = ROOT / 'charts/batch-pipeline-worker'
    worker = yaml.safe_load((chart / 'prod_omi_batch-pipeline-worker_values.yaml').read_text())
    defaults = yaml.safe_load((chart / 'values.yaml').read_text())
    env = hosts(manifest['prod'])['backend-sync']
    assert worker['worker']['apiUrl'] == env['BATCH_PIPELINE_API_URL']['value']
    assert worker['worker']['audience'] == env['BATCH_PIPELINE_WORKER_AUDIENCE']['value']
    assert worker['gcpServiceAccount'] == env['BATCH_PIPELINE_WORKER_SERVICE_ACCOUNT']['value']
    for values in hosts(manifest['prod']).values():
        assert values['BUCKET_BATCH_PIPELINE']['value'] == worker['bucket']
        assert int(values['BATCH_PIPELINE_UNIT_SECONDS']['value']) == defaults['worker']['unitSeconds'] == 3600
    # No CPU host other than the policy target accepts this worker identity.
    for name, values in hosts(manifest['prod']).items():
        if name != 'backend-sync':
            assert values['BATCH_PIPELINE_WORKER_SERVICE_ACCOUNT']['value'] == ''
            assert values['BATCH_PIPELINE_WORKER_AUDIENCE']['value'] == ''
