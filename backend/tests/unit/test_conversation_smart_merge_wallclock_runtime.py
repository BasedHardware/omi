import json

import pytest
import yaml

from scripts.verify_pusher_cohost_env_diff import parse_env_entries
from tests.unit.test_backend_runtime_env_validator import (
    ROOT,
    _manifest_env_blocks,
    load_validator,
)

_SMART_MERGE_WALLCLOCK_HOSTS = {
    'gke/backend-listen',
    'gke/pusher',
    'cloud_run/backend',
    'cloud_run/backend-sync',
    'cloud_run/backend-sync-backfill',
    'cloud_run/backend-integration',
}

_FLAG = 'CONVERSATION_SMART_MERGE_WALLCLOCK_GAP_MODE'

_CHART_PATHS = (
    'charts/backend-listen/dev_omi_backend_listen_values.yaml',
    'charts/backend-listen/prod_omi_backend_listen_values.yaml',
    'charts/pusher/dev_omi_pusher_values.yaml',
    'charts/pusher/prod_omi_pusher_values.yaml',
)


@pytest.fixture(scope='module')
def manifest_and_charts():
    validator = load_validator()
    manifest = validator._load_yaml(validator.DEFAULT_MANIFEST)
    env_scopes = {
        env_name: [
            (scope, env_block)
            for scope, env_block in _manifest_env_blocks(validator._get_env_config(manifest, env_name))
        ]
        for env_name in ('dev', 'prod')
    }
    charts = {path: (ROOT / path).read_text(encoding='utf-8') for path in _CHART_PATHS}
    base = validator._load_yaml(ROOT / 'deploy/runtime_env/_base.yaml')
    return env_scopes, charts, base


def _base_env_blocks(base):
    shared = base['environment_shared']
    for scope, body in shared['gke'].items():
        if isinstance(body, dict) and isinstance(body.get('env'), dict):
            yield f'gke/{scope}', body['env']
    for scope, body in shared['cloud_run']['services'].items():
        if isinstance(body, dict) and isinstance(body.get('env'), dict):
            yield f'cloud_run/{scope}', body['env']


def test_base_defaults_to_off_on_the_six_hosts_only(manifest_and_charts):
    _, _, base = manifest_and_charts
    for scope, env_block in _base_env_blocks(base):
        entry = env_block.get(_FLAG)
        if scope in _SMART_MERGE_WALLCLOCK_HOSTS:
            assert entry == {
                'value': 'off',
                'category': 'rollout',
            }, f'base {scope} runs smart merge; {_FLAG} must be an explicit off, got {entry!r}'
        else:
            assert entry is None, f'base {scope} must not carry {_FLAG}'


def test_overlays_run_shadow_on_the_six_hosts_only(manifest_and_charts):
    env_scopes, _, _ = manifest_and_charts
    expected = {'value': 'shadow', 'category': 'rollout'}
    for env_name, blocks in env_scopes.items():
        for scope, env_block in blocks:
            entry = env_block.get(_FLAG)
            if scope in _SMART_MERGE_WALLCLOCK_HOSTS:
                assert entry == expected, f'{env_name}/{scope} runs smart merge; {_FLAG} must be shadow, got {entry!r}'
            else:
                assert entry is None, f'{env_name}/{scope} must not carry {_FLAG}'


def test_charts_carry_the_literal_shadow(manifest_and_charts):
    _, charts, _ = manifest_and_charts
    for rel_path, text in charts.items():
        entries = parse_env_entries(text)
        name = rel_path.rsplit('/', 1)[-1]
        assert text.count(f'- name: {_FLAG}\n') == 1, f'{name} must declare {_FLAG} exactly once'
        assert entries[_FLAG].value == 'shadow', f'{name} {_FLAG} must be the literal shadow'


def test_registry_declares_the_flag():
    registry = yaml.safe_load((ROOT.parent / 'config/feature-flags.yaml').read_text())
    rows = [row for row in registry['flags'] if row.get('key') == _FLAG]
    assert len(rows) == 1
    assert rows[0]['lifecycle'] == 'rollout' and rows[0]['fail'] == 'open'
    assert rows[0]['surfaces'] == ['backend'] and rows[0]['decision'] == 'keep'
    classification = json.loads((ROOT.parent / 'config/deployment-setting-classification.json').read_text())
    assert _FLAG in classification['kinds']['config']
