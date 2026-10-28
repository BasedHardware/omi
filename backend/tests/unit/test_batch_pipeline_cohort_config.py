"""Rollout fences across the rendered CPU hosts and the dedicated GPU chart."""

from pathlib import Path

import pytest
import yaml

from config.batch_pipeline import recovery_owners

ROOT = Path(__file__).resolve().parents[2]
UID = 'vi7SA9ckQCe4ccobWNxlbdcNdC23'
SERVICES = ('backend', 'backend-sync', 'backend-sync-backfill', 'backend-integration')


@pytest.fixture(scope='module')
def manifest():
    return yaml.load((ROOT / 'deploy/runtime_env.yaml').read_text(), Loader=yaml.CSafeLoader)['environments']


@pytest.fixture(scope='module')
def recovery_base_hosts():
    base = yaml.load((ROOT / 'deploy/runtime_env/_base.yaml').read_text(), Loader=yaml.CSafeLoader)[
        'environment_shared'
    ]
    return {
        **base['cloud_run']['services'],
        'backend-listen': base['gke']['backend-listen'],
    }


@pytest.fixture(scope='module')
def listen_chart_envs():
    chart = ROOT / 'charts/backend-listen'
    result = []
    for stage in ('dev', 'prod'):
        values = yaml.load((chart / f'{stage}_omi_backend_listen_values.yaml').read_text(), Loader=yaml.CSafeLoader)
        result.append({entry['name']: entry.get('value') for entry in values['env']})
    return result


def hosts(config):
    return {
        **{name: config['cloud_run']['services'][name]['env'] for name in SERVICES},
        'backend-listen': config['gke']['backend-listen']['env'],
    }


def test_shadow_controls_ship_off_and_capped_on_every_cloud_run_host(manifest):
    for config in manifest.values():
        for service in SERVICES:
            env = config['cloud_run']['services'][service]['env']
            assert env['BATCH_PIPELINE_SHADOW_PERCENT']['value'] == '0'
            assert env['BATCH_PIPELINE_SHADOW_PAID_RECOVERY_PER_HOUR']['value'] == '200'


def test_shadow_recovery_role_accepts_its_rendered_gpu_worker_identity(manifest):
    for stage, config in manifest.items():
        env = config['cloud_run']['services']['backend-integration']['env']
        chart = yaml.load(
            (ROOT / f'charts/batch-pipeline-worker/{stage}_omi_batch-pipeline-worker_values.yaml').read_text(),
            Loader=yaml.CSafeLoader,
        )
        assert env['BATCH_PIPELINE_WORKER_SERVICE_ACCOUNT']['value'] == chart['gcpServiceAccount']
        assert env['BATCH_PIPELINE_RECOVERY_TASK_AUDIENCE']['value'] == chart['worker']['shadowRecoveryApiUrl']
        # The other GPU worker RPCs stay closed on the recovery-only role.
        assert env['BATCH_PIPELINE_WORKER_AUDIENCE']['value'] == ''


def test_batch_pipeline_admission_is_configured_without_uid_allowlists(manifest, listen_chart_envs):
    for stage, config in manifest.items():
        for env in hosts(config).values():
            assert env['BATCH_PIPELINE_ENABLED']['value'] in ('true', 'false')
            assert env['BATCH_PIPELINE_PERCENT']['value'] == '0'
            if stage == 'prod':
                assert 'BATCH_PIPELINE_UID_ALLOWLIST' not in env
                assert env['BATCH_PIPELINE_ENABLED']['value'] == 'true'
            else:
                allowlist = env.get('BATCH_PIPELINE_UID_ALLOWLIST')
                assert allowlist is None or allowlist.get('value', '') == ''
            assert env['BATCH_PIPELINE_WORKER_ENABLED']['value'] == 'false'
            assert env['BATCH_PIPELINE_SHARED_LIVE_ENABLED']['value'] == 'false'
            if stage == 'dev':
                assert env['BATCH_PIPELINE_SERVING_ENABLED']['value'] == 'false'
                assert env.get('BATCH_PIPELINE_UID_ALLOWLIST', {}).get('value', '') == ''
                assert env['BATCH_PIPELINE_API_URL']['value'] == ''
    assert listen_chart_envs[0].get('BATCH_PIPELINE_UID_ALLOWLIST', '') == ''
    assert 'BATCH_PIPELINE_UID_ALLOWLIST' not in listen_chart_envs[1]
    assert listen_chart_envs[1]['BATCH_PIPELINE_ENABLED'] == 'true'
    prod_hosts = hosts(manifest['prod'])
    assert prod_hosts['backend-sync']['SYNC_BACKFILL_ORDER_PERCENT']['value'] == '100'
    assert prod_hosts['backend-sync-backfill']['SYNC_BACKFILL_ORDER_PERCENT']['value'] == '0'
    assert prod_hosts['backend-integration']['BATCH_PIPELINE_TERMINAL_EMPTY_DISPOSITION_ENABLED']['value'] == 'true'


def test_prod_sync_redrive_and_summary_deadline_manifest_fail_safe(manifest, monkeypatch):
    from config import summary_guarantee

    prod_hosts = hosts(manifest['prod'])
    for service in ('backend-sync', 'backend-sync-backfill'):
        env = prod_hosts[service]
        assert env['SYNC_DURABLE_REDRIVE_GUARD'] == {'value': 'true', 'category': 'rollout'}
        assert env['SYNC_LEGACY_COMPLETION_CONVERGENCE'] == {'value': 'true', 'category': 'rollout'}
    for service in ('backend', 'backend-integration', 'backend-listen'):
        env = prod_hosts[service]
        assert 'SYNC_DURABLE_REDRIVE_GUARD' not in env
        assert 'SYNC_LEGACY_COMPLETION_CONVERGENCE' not in env

    for service in ('backend-sync', 'backend-sync-backfill', 'backend-integration'):
        env = prod_hosts[service]
        assert env['FIRST_SUMMARY_DEADLINE_ENABLED']['value'] == 'true'
        assert env['FIRST_SUMMARY_DEADLINE_PERCENT']['value'] == '100'
        assert 'FIRST_SUMMARY_UID_ALLOWLIST' not in env
        monkeypatch.setenv('FIRST_SUMMARY_DEADLINE_ENABLED', env['FIRST_SUMMARY_DEADLINE_ENABLED']['value'])
        monkeypatch.setenv('FIRST_SUMMARY_DEADLINE_PERCENT', env['FIRST_SUMMARY_DEADLINE_PERCENT']['value'])
        monkeypatch.delenv('FIRST_SUMMARY_UID_ALLOWLIST', raising=False)
        assert summary_guarantee.enabled('any-user')
        monkeypatch.setenv('FIRST_SUMMARY_UID_ALLOWLIST', 'canary-owner')
        assert summary_guarantee.enabled('canary-owner')
        assert summary_guarantee.enabled('any-user')
        monkeypatch.setenv('FIRST_SUMMARY_DEADLINE_ENABLED', 'false')
        assert not summary_guarantee.enabled('canary-owner')
        assert not summary_guarantee.enabled('any-user')


def test_quarantine_recovery_uses_private_membership_only_on_prod_integration(
    manifest,
    recovery_base_hosts,
    listen_chart_envs,
):
    for stage, config in manifest.items():
        for name, env in hosts(config).items():
            if name == 'backend-listen':
                assert env['BATCH_PIPELINE_RECOVERY_UID_ALLOWLIST']['value'] == ''
            else:
                assert 'BATCH_PIPELINE_RECOVERY_UID_ALLOWLIST' not in env
            expected = 'on' if stage == 'prod' and name == 'backend-integration' else 'off'
            assert env['BATCH_PIPELINE_RECOVERY_MODE']['value'] == expected
    for name, host in recovery_base_hosts.items():
        if name == 'backend-listen':
            assert host['env']['BATCH_PIPELINE_RECOVERY_UID_ALLOWLIST']['value'] == ''
        else:
            assert 'BATCH_PIPELINE_RECOVERY_UID_ALLOWLIST' not in host['env']
    for chart_env in listen_chart_envs:
        assert chart_env['BATCH_PIPELINE_RECOVERY_MODE'] == 'off'
        assert chart_env['BATCH_PIPELINE_RECOVERY_UID_ALLOWLIST'] == ''


def test_only_always_cpu_integration_host_runs_projection_pump(manifest):
    for stage, config in manifest.items():
        active = [
            name for name, env in hosts(config).items() if env['BATCH_PIPELINE_SERVING_ENABLED']['value'] == 'true'
        ]
        assert active == (['backend-integration'] if stage == 'prod' else [])
    deploy = (ROOT.parent / '.github/actions/deploy-backend-stack/action.yml').read_text()
    integration = deploy.split('id: deploy-backend-integration', 1)[1].split('id: capture-backend-integration', 1)[0]
    # 2026-10-24 right-sizing: prod integration stays warm for the projection pump;
    # the dev project (based-hardware-dev) idles at 0 (lead's live change).
    integration_min = "--min-instances=${{ inputs.runtime_env == 'prod' && '3' || '0' }}"
    assert '--no-cpu-throttling' in integration and integration_min in integration


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
    # Normal worker RPCs remain restricted to the policy target. Integration
    # accepts the same principal only under the separate shadow recovery audience.
    for name, values in hosts(manifest['prod']).items():
        if name != 'backend-sync':
            expected = worker['gcpServiceAccount'] if name == 'backend-integration' else ''
            assert values['BATCH_PIPELINE_WORKER_SERVICE_ACCOUNT']['value'] == expected
            assert values['BATCH_PIPELINE_WORKER_AUDIENCE']['value'] == ''


def test_worker_head_priority_is_prod_only_and_values_driven():
    chart = ROOT / 'charts/batch-pipeline-worker'
    defaults = yaml.safe_load((chart / 'values.yaml').read_text())
    prod = yaml.safe_load((chart / 'prod_omi_batch-pipeline-worker_values.yaml').read_text())
    dev = yaml.safe_load((chart / 'dev_omi_batch-pipeline-worker_values.yaml').read_text())
    deployment = (chart / 'templates/deployment.yaml').read_text()

    assert (
        '- {name: BATCH_PIPELINE_HEAD_PRIORITY_ENABLED, ' 'value: {{ .Values.worker.headPriorityEnabled | quote }}}'
    ) in deployment
    assert defaults['worker']['headPriorityEnabled'] is False
    assert dev['worker']['headPriorityEnabled'] is False
    assert prod['worker']['headPriorityEnabled'] is True


@pytest.mark.parametrize(
    'name,reader',
    [
        ('BATCH_PIPELINE_AUTHORITATIVE_LABELS_ENABLED', 'authoritative_labels_enabled'),
        ('BATCH_PIPELINE_EMPTY_ASR_RECOVERY_ENABLED', 'empty_asr_recovery_enabled'),
        ('BATCH_PIPELINE_REQUIRE_LIVE_TARGET_ENABLED', 'require_live_target_enabled'),
        ('BATCH_PIPELINE_HEAD_PRIORITY_ENABLED', 'head_priority_enabled'),
        ('BATCH_PIPELINE_ASYNC_PROJECTION_ENABLED', 'async_projection_enabled'),
    ],
)
def test_record_controls_default_off_and_read_at_call_time(monkeypatch, name, reader):
    from config import batch_pipeline

    read = getattr(batch_pipeline, reader)
    monkeypatch.delenv(name, raising=False)
    assert not read()
    monkeypatch.setenv(name, 'true')
    assert read()
    monkeypatch.setenv(name, 'invalid')
    assert not read()
