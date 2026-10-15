"""Deploy boundaries reject missing or inconsistent staged lineage gates, offline."""

import sys

import pytest
import yaml

from scripts import render_backend_runtime_env as cloud_run
from scripts import render_gke_backend_config as gke
from scripts.runtime_env_validation.manifest import _validate_manifest_shape

KEY = 'SYNC_LINEAGE_RESOLVE_UID_ALLOWLIST'
SERVICES = ('backend', 'backend-sync', 'backend-sync-backfill', 'backend-integration')


@pytest.fixture
def rollout(tmp_path):
    chart = tmp_path / 'listen.yaml'
    chart.write_text(yaml.safe_dump({'env': [{'name': KEY, 'value': 'SYNTHETIC-OWNER'}]}))
    config = {
        'gke': {
            'backend-listen': {'env': {KEY: {'value': 'SYNTHETIC-OWNER'}}, 'values_file': str(chart)},
            'config_map': {
                'name': 'prod-backend-config',
                'entries': {'SAFE_SETTING': {'source': 'literal', 'value': '1'}},
            },
        },
        'cloud_run': {'services': {service: {'env': {KEY: {'value': 'SYNTHETIC-OWNER'}}} for service in SERVICES}},
    }
    return config, chart


def corrupt(config, chart, defect):
    if defect == 'chart_drift':
        chart.write_text(yaml.safe_dump({'env': [{'name': KEY, 'value': 'OTHER-OWNER'}]}))
    elif defect == 'all_missing':
        for service in config['cloud_run']['services'].values():
            service['env'].pop(KEY)
        config['gke']['backend-listen']['env'].pop(KEY)
    else:
        service, change = defect.split(':')
        entry = config['cloud_run']['services'][service]['env']
        if change == 'missing':
            entry.pop(KEY)
        else:
            entry[KEY]['value'] = 'OTHER-OWNER'


DEFECTS = ['all_missing', 'chart_drift'] + [
    f'{service}:{change}' for service in SERVICES for change in ('missing', 'drift')
]


@pytest.mark.parametrize('boundary', ['cloud_run', 'helm'])
@pytest.mark.parametrize('defect', DEFECTS)
def test_deploy_rejects_missing_or_divergent_allowlists(rollout, tmp_path, monkeypatch, boundary, defect):
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


def test_manifest_validator_rejects_cross_service_drift(rollout):
    config, chart = rollout
    corrupt(config, chart, 'backend-sync:drift')
    assert any(KEY in error.message for error in _validate_manifest_shape(config, 'prod'))


def test_explicit_widening_allows_empty_on_all_hosts(rollout, tmp_path, monkeypatch):
    config, chart = rollout
    for service in config['cloud_run']['services'].values():
        service['env'][KEY]['value'] = ''
    config['gke']['backend-listen']['env'][KEY]['value'] = ''
    chart.write_text(yaml.safe_dump({'env': [{'name': KEY, 'value': ''}]}))
    manifest = tmp_path / 'runtime.yaml'
    manifest.write_text(yaml.safe_dump({'environments': {'prod': config}}))
    monkeypatch.setattr(sys, 'argv', ['render', '--env', 'prod', '--manifest', str(manifest)])
    assert cloud_run.main() == 0
    assert gke.config_map_entries('prod', manifest)[0] == 'prod-backend-config'
