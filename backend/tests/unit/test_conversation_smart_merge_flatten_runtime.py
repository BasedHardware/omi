import pytest

from scripts.verify_pusher_cohost_env_diff import parse_env_entries
from tests.unit.test_backend_runtime_env_validator import (
    ROOT,
    _manifest_env_blocks,
    load_validator,
)

_SMART_MERGE_FLATTEN_HOSTS = {
    'gke/backend-listen',
    'gke/pusher',
    'cloud_run/backend',
    'cloud_run/backend-sync',
    'cloud_run/backend-sync-backfill',
    'cloud_run/backend-integration',
}

_FLAG = 'CONVERSATION_SMART_MERGE_FLATTEN_ENABLED'

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
    return env_scopes, charts


def test_smart_merge_flatten_flag_covers_six_hosts_and_charts(manifest_and_charts):
    env_scopes, charts = manifest_and_charts
    expected = {'value': 'true', 'category': 'ops_kill'}

    for env_name, blocks in env_scopes.items():
        for scope, env_block in blocks:
            entry = env_block.get(_FLAG)
            if scope in _SMART_MERGE_FLATTEN_HOSTS:
                assert (
                    entry == expected
                ), f'{env_name}/{scope} runs smart merge; {_FLAG} must be an explicit true, got {entry!r}'
            else:
                assert entry is None, f'{env_name}/{scope} must not carry {_FLAG}'

    for rel_path, text in charts.items():
        entries = parse_env_entries(text)
        name = rel_path.rsplit('/', 1)[-1]
        assert text.count(f'- name: {_FLAG}\n') == 1, f'{name} must declare {_FLAG} exactly once'
        assert entries[_FLAG].value == 'true', f'{name} {_FLAG} must be the literal true'
