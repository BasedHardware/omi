"""Deploy boundaries require private membership bindings to remain absent, offline."""

import sys

import pytest
import yaml

from scripts import render_backend_runtime_env as cloud_run
from scripts import render_gke_backend_config as gke
from scripts.runtime_env_validation.manifest import _validate_manifest_shape

KEY = 'SYNC_LINEAGE_RESOLVE_UID_ALLOWLIST'
SERVICES = ('backend', 'backend-sync', 'backend-sync-backfill', 'backend-integration')


@pytest.fixture
def rollout(tmp_path, monkeypatch):
    monkeypatch.setenv('GITHUB_OUTPUT', str(tmp_path / 'github-output'))
    chart = tmp_path / 'listen.yaml'
    chart.write_text(yaml.safe_dump({'env': []}))
    config = {
        'gke': {
            'backend-listen': {'env': {}, 'values_file': str(chart)},
            'config_map': {
                'name': 'prod-backend-config',
                'entries': {'SAFE_SETTING': {'source': 'literal', 'value': '1'}},
            },
        },
        'cloud_run': {'services': {service: {'env': {}} for service in SERVICES}},
    }
    return config, chart


def corrupt(config, chart, defect):
    if defect == 'chart':
        chart.write_text(yaml.safe_dump({'env': [{'name': KEY, 'value': 'SYNTHETIC-OWNER'}]}))
    elif defect == 'gke':
        config['gke']['backend-listen']['env'][KEY] = {'value': ''}
    else:
        service, source = defect.split(':')
        host = config['cloud_run']['services'][service]
        if source == 'secret':
            host['secrets'] = {KEY: {'secret': KEY, 'version': '1'}}
        else:
            host['env'][KEY] = {'value': '' if source == 'empty' else 'SYNTHETIC-OWNER'}


DEFECTS = [f'{service}:{source}' for service in SERVICES for source in ('literal', 'empty', 'secret')]


@pytest.mark.parametrize('boundary', ['cloud_run', 'helm'])
@pytest.mark.parametrize('defect', DEFECTS)
def test_deploy_rejects_reintroduced_allowlist_bindings(rollout, tmp_path, monkeypatch, boundary, defect):
    config, chart = rollout
    corrupt(config, chart, defect)
    manifest = tmp_path / 'runtime.yaml'
    manifest.write_text(yaml.safe_dump({'environments': {'prod': config}}))
    with pytest.raises(ValueError, match=KEY):
        if boundary == 'cloud_run':
            monkeypatch.setattr(sys, 'argv', ['render', '--env', 'prod', '--manifest', str(manifest)])
            cloud_run.main()
        else:
            gke.config_map_entries('prod', manifest)


def test_manifest_validator_rejects_reintroduced_binding(rollout):
    config, chart = rollout
    corrupt(config, chart, 'backend-sync:literal')
    assert any(KEY in error.message for error in _validate_manifest_shape(config, 'prod'))


def test_both_renderers_accept_absent_cohort_keys(rollout, tmp_path, monkeypatch):
    config, _ = rollout
    manifest = tmp_path / 'runtime.yaml'
    manifest.write_text(yaml.safe_dump({'environments': {'prod': config}}))
    monkeypatch.setattr(sys, 'argv', ['render', '--env', 'prod', '--manifest', str(manifest)])
    assert cloud_run.main() == 0
    assert gke.config_map_entries('prod', manifest)[0] == 'prod-backend-config'


def test_helm_keeps_legacy_lineage_binding(rollout, tmp_path, monkeypatch):
    config, chart = rollout
    corrupt(config, chart, 'chart')
    manifest = tmp_path / 'runtime.yaml'
    manifest.write_text(yaml.safe_dump({'environments': {'prod': config}}))
    monkeypatch.setattr(sys, 'argv', ['render', '--env', 'prod', '--manifest', str(manifest)])
    assert cloud_run.main() == 0
    assert gke.config_map_entries('prod', manifest)[0] == 'prod-backend-config'
