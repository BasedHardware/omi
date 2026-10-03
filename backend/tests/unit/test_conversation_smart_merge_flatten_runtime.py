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


def test_smart_merge_flatten_flag_covers_six_hosts_and_charts():
    flag = 'CONVERSATION_SMART_MERGE_FLATTEN_ENABLED'
    expected = {'value': 'true', 'category': 'ops_kill'}
    validator = load_validator()
    manifest = validator._load_yaml(validator.DEFAULT_MANIFEST)

    for env_name in ('dev', 'prod'):
        env_config = validator._get_env_config(manifest, env_name)
        for scope, env_block in _manifest_env_blocks(env_config):
            entry = env_block.get(flag)
            if scope in _SMART_MERGE_FLATTEN_HOSTS:
                assert (
                    entry == expected
                ), f'{env_name}/{scope} runs smart merge; {flag} must be an explicit true, got {entry!r}'
            else:
                assert entry is None, f'{env_name}/{scope} must not carry {flag}'

    for chart_path in (
        ROOT / 'charts/backend-listen/dev_omi_backend_listen_values.yaml',
        ROOT / 'charts/backend-listen/prod_omi_backend_listen_values.yaml',
        ROOT / 'charts/pusher/dev_omi_pusher_values.yaml',
        ROOT / 'charts/pusher/prod_omi_pusher_values.yaml',
    ):
        text = chart_path.read_text(encoding='utf-8')
        entries = parse_env_entries(text)
        assert text.count(f'- name: {flag}\n') == 1, f'{chart_path.name} must declare {flag} exactly once'
        assert entries[flag].value == 'true', f'{chart_path.name} {flag} must be the literal true'
