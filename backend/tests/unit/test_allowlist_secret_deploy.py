"""Allowlist identity stays private and survives both deployment update models."""

from copy import deepcopy
import io
import json
import sys
from pathlib import Path
import shutil
import subprocess

import pytest
import yaml

from scripts import render_backend_runtime_env as render
from scripts import verify_k8s_secret_keys
from scripts.render_cloud_run_clone_env import clone_environment

ROOT = Path(__file__).resolve().parents[3]
KEYS = {
    'MOBILE_STANDARD_BATCH_UIDS',
    'OMI_MESSAGING_CHANNELS_UIDS',
    'OMI_MESSAGING_CHANNEL_POLICY',
    'BATCH_PIPELINE_UID_ALLOWLIST',
    'BATCH_PIPELINE_RECOVERY_UID_ALLOWLIST',
    'FIRST_SUMMARY_UID_ALLOWLIST',
    'DREAM_AGENT_UID_ALLOWLIST',
    'SPEAKER_GROUPING_SHADOW_UID_ALLOWLIST',
    'STT_LIVE_DEMAND_UID_ALLOWLIST',
    'SYNC_LEGACY_FRESH_UID_ALLOWLIST',
    'SYNC_LINEAGE_RESOLVE_UID_ALLOWLIST',
    'TRANSCRIPTION_FINAL_PASS_UID_ALLOWLIST',
    'TRANSCRIPTION_SHADOW_UID_ALLOWLIST',
}


@pytest.fixture(scope='module')
def prod():
    return yaml.safe_load((ROOT / 'backend/deploy/runtime_env.yaml').read_text())['environments']['prod']


def test_cloud_run_merge_removes_literals_and_sets_secrets_in_same_deploy(prod):
    stack = yaml.safe_load((ROOT / '.github/actions/deploy-backend-stack/action.yml').read_text())['runs']['steps']
    worker = yaml.safe_load((ROOT / '.github/actions/sync-backfill-lifecycle/action.yml').read_text())['runs']['steps']
    for name, config in prod['cloud_run']['services'].items():
        prefix = name.replace('-', '_')
        refs = {e['name']: e for e in render._render_secret_entries(config['secrets'])}
        names = KEYS & refs.keys()
        assert 'BATCH_PIPELINE_UID_ALLOWLIST' in names
        assert not names & config['env'].keys()
        assert names <= set(render._remove_env_extra(name, config).split(','))
        for key in names:
            assert refs[key] == {'name': key, 'valueFrom': {'secretKeyRef': {'name': key, 'key': 'latest'}}}
        if name == 'backend-sync-backfill':
            call = next(s for s in stack if s.get('id') == 'sync-backfill')['with']
            assert call['remove_env_extra'] == '${{ steps.runtime-env.outputs.backend_sync_backfill_remove_env_extra }}'
            assert call['backfill_secrets'] == '${{ steps.runtime-env.outputs.backend_sync_backfill_secrets }}'
            deploy = next(s for s in worker if s.get('id') == 'deploy-backend-sync-backfill')['with']
            assert '${{ inputs.remove_env_extra }}' in deploy['flags']
            assert deploy['secrets'] == '${{ steps.backfill-runtime.outputs.secrets }}'
            clone = next(s for s in worker if s.get('id') == 'backfill-runtime')
            assert clone['env']['SECRET_OVERLAY'] == '${{ inputs.backfill_secrets }}'
        else:
            deploy = next(s for s in stack if s.get('id') == f'deploy-{name}')['with']
            assert '${{ steps.runtime-env.outputs.' + prefix + '_remove_env_extra }}' in deploy['flags']
            assert deploy['secrets'] == '${{ steps.runtime-env.outputs.' + prefix + '_secrets }}'
        assert deploy['no_traffic'] is True


@pytest.mark.parametrize('chart,filename', [('backend-listen', 'backend_listen'), ('pusher', 'pusher')])
def test_helm_replacement_keeps_required_secret_refs(prod, chart, filename):
    assert shutil.which('helm'), 'Helm required to exercise real chart env-list replacement'
    docs = yaml.safe_load_all(
        subprocess.check_output(
            [
                'helm',
                'template',
                'prod-omi-' + chart,
                str(ROOT / 'backend/charts' / chart),
                '-f',
                str(ROOT / f'backend/charts/{chart}/prod_omi_{filename}_values.yaml'),
                '--set',
                'image.repository=synthetic,image.tag=test,runtimeGcpProjectId=based-hardware',
            ],
            text=True,
        )
    )
    deployment = next(d for d in docs if d and d.get('kind') == 'Deployment')
    rows = deployment['spec']['template']['spec']['containers'][0]['env']
    env = {e['name']: e for e in rows}
    assert len(env) == len(rows)
    for key, entry in prod['gke'][chart]['env'].items():
        if key in KEYS and 'secret' in entry:
            assert env[key] == {'name': key, 'valueFrom': {'secretKeyRef': entry['secret']}}
    if chart == 'backend-listen':
        assert 'BATCH_PIPELINE_UID_ALLOWLIST' in env
    else:
        assert 'BATCH_PIPELINE_UID_ALLOWLIST' not in env
        assert 'BATCH_PIPELINE_ENABLED' not in env
    assert env['BATCH_PIPELINE_LIVE_ADMISSION_ENABLED']['value'] == 'false'


def test_external_secret_sync_precedes_listen_upgrade_and_checks_all_keys():
    values = ROOT / 'backend/charts/backend-secrets/prod_omi_backend_secrets_values.yaml'
    assert KEYS <= verify_k8s_secret_keys.expected_keys(values)
    chart = yaml.safe_load(values.read_text())
    refs = {e['secretKey']: e['remoteKey'] for e in chart['externalSecret']['secretKeys']}
    assert all(refs[k] == k for k in KEYS)
    action = (ROOT / '.github/actions/deploy-backend-stack/action.yml').read_text()
    assert action.index('name: Deploy backend-secrets to GKE') < action.index('name: Deploy ${{ env.SERVICE }}-listen')
    script = (ROOT / 'backend/scripts/deploy-backend-secrets.sh').read_text()
    assert 'verify_k8s_secret_keys.py' in script


def test_no_nonempty_literal_uid_allowlists_remain_in_prod(prod):
    for host in [*prod['cloud_run']['services'].values(), prod['gke']['backend-listen'], prod['gke']['pusher']]:
        for key, entry in host['env'].items():
            if key.endswith('UID_ALLOWLIST') or key in KEYS:
                assert not entry.get('value'), key
    for name, host in prod['cloud_run']['services'].items():
        assert host['env']['BATCH_PIPELINE_LIVE_ADMISSION_ENABLED']['value'] == 'false'
        assert host['env']['BATCH_PIPELINE_PERCENT']['value'] == '0'
        if name != 'backend':
            assert 'FIRST_SUMMARY_UID_ALLOWLIST' in host['secrets']


def test_lineage_secret_binding_rejects_missing_mixed_or_divergent_hosts(prod):
    assert render.validate_sync_lineage_rollout('prod', prod, check_chart=True) == []
    key = 'SYNC_LINEAGE_RESOLVE_UID_ALLOWLIST'
    for defect in ('missing', 'literal', 'other_secret', 'other_version'):
        config = deepcopy(prod)
        host = config['cloud_run']['services']['backend-sync']
        if defect == 'missing':
            del host['secrets'][key]
        elif defect == 'literal':
            del host['secrets'][key]
            host['env'][key] = {'value': ''}
        else:
            host['secrets'][key]['secret' if defect == 'other_secret' else 'version'] = 'other'
        assert render.validate_sync_lineage_rollout('prod', config), defect


def test_backfill_clone_secret_overlay_removes_inherited_literal(prod):
    config = prod['cloud_run']['services']['backend-sync-backfill']
    inherited = [{'name': key, 'value': 'synthetic-owner'} for key in KEYS]
    inherited.append({'name': 'UNMODELLED', 'value': 'preserved'})
    service = {'spec': {'template': {'spec': {'containers': [{'env': inherited}]}}}}
    literals, secrets = clone_environment(service, '', render._render_secrets(config['secrets']))
    literal_names = {line.partition('=')[0] for line in literals.splitlines()}
    secret_names = {line.partition('=')[0] for line in secrets.splitlines()}
    assert not (KEYS & config['secrets'].keys()) & literal_names
    assert KEYS & config['secrets'].keys() <= secret_names
    assert 'UNMODELLED=preserved' in literals


def test_missing_allowlist_key_blocks_secret_deploy_fallback(monkeypatch, capsys):
    values = ROOT / 'backend/charts/backend-secrets/prod_omi_backend_secrets_values.yaml'
    data = {key: 'c3ludGhldGlj' for key in verify_k8s_secret_keys.expected_keys(values)}
    del data['BATCH_PIPELINE_UID_ALLOWLIST']
    monkeypatch.setattr(sys, 'argv', ['verify', str(values)])
    monkeypatch.setattr(sys, 'stdin', io.StringIO(json.dumps({'data': data})))
    assert verify_k8s_secret_keys.main() == 1
    output = capsys.readouterr()
    assert 'BATCH_PIPELINE_UID_ALLOWLIST' in output.err
    assert 'c3ludGhldGlj' not in output.err + output.out
