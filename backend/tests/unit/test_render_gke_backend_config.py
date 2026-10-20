from __future__ import annotations

import os
from pathlib import Path

import pytest
import yaml

from scripts.render_gke_backend_config import config_map_entries

BACKEND_ROOT = Path(__file__).resolve().parents[2]


def test_config_map_entries_reads_manifest_metadata(tmp_path: Path) -> None:
    manifest = {
        'environments': {
            'dev': {
                'gke': {
                    'config_map': {
                        'name': 'custom-backend-config',
                        'entries': {
                            'REDIS_DB_HOST': {'source': 'environment'},
                        },
                    }
                }
            }
        }
    }
    manifest_path = tmp_path / 'runtime_env.yaml'
    manifest_path.write_text(yaml.safe_dump(manifest), encoding='utf-8')
    os.environ['REDIS_DB_HOST'] = '10.0.0.1'

    name, entries = config_map_entries('dev', manifest_path)

    assert name == 'custom-backend-config'
    assert entries == {'REDIS_DB_HOST': '10.0.0.1'}


def test_config_map_entries_falls_back_to_legacy_manifest_shape(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest = {
        'environments': {
            'dev': {
                'gke': {
                    'region': 'us-central1',
                }
            }
        }
    }
    manifest_path = tmp_path / 'runtime_env.yaml'
    manifest_path.write_text(yaml.safe_dump(manifest), encoding='utf-8')
    for key in (
        'CONVERSATION_SUMMARIZED_APP_IDS',
        'GOOGLE_CLIENT_ID',
        'MCP_AUTHORIZATION_SERVER_URL',
        'MCP_OAUTH_CHATGPT_CLIENT_ID',
        'MCP_OAUTH_CHATGPT_REDIRECT_URIS',
        'MCP_OAUTH_PUBLIC_CLIENT_ID',
        'MCP_OAUTH_PUBLIC_REDIRECT_URIS',
        'MCP_RESOURCE_URL',
        'RAPID_API_HOST',
        'REDIS_DB_HOST',
        'STT_PRERECORDED_MODEL',
        'STT_SERVICE_MODELS',
        'TYPESENSE_HOST',
        'TWILIO_ACCOUNT_SID',
        'TWILIO_API_KEY_SID',
        'TWILIO_TWIML_APP_SID',
        'X_OAUTH_CLIENT_ID',
        'X_OAUTH_REDIRECT_URI',
    ):
        monkeypatch.setenv(key, f'value-for-{key}')

    name, entries = config_map_entries('dev', manifest_path)

    assert name == 'dev-omi-backend-config'
    assert entries['REDIS_DB_HOST'] == 'value-for-REDIS_DB_HOST'
    assert entries['GOOGLE_CLIENT_ID'] == 'value-for-GOOGLE_CLIENT_ID'


@pytest.mark.parametrize('value', [None, '', 'uid:fixture-a,uid:fixture-b', 'uid:'])
def test_optional_config_map_uses_empty_default(value, monkeypatch, tmp_path):
    key = 'OPTIONAL_FIXTURE'
    if value is None:
        monkeypatch.delenv(key, raising=False)
    else:
        monkeypatch.setenv(key, value)
    manifest = {
        'environments': {
            'dev': {
                'gke': {
                    'config_map': {
                        'name': 'dev-omi-backend-config',
                        'entries': {key: {'source': 'environment', 'default': ''}},
                    }
                }
            }
        }
    }
    path = tmp_path / 'runtime.yaml'
    path.write_text(yaml.safe_dump(manifest))
    assert config_map_entries('dev', path) == ('dev-omi-backend-config', {key: value or ''})


@pytest.fixture(scope='module')
def checked_in_manifest() -> dict:
    return yaml.safe_load((BACKEND_ROOT / 'deploy/runtime_env.yaml').read_text(encoding='utf-8'))


@pytest.mark.parametrize('env', ['dev', 'prod'])
def test_checked_in_manifest_config_map_entries_have_supported_sources(env: str, checked_in_manifest: dict) -> None:
    """A missing `source` fails the deploy-time ConfigMap render after Cloud Run promotion."""
    entries = checked_in_manifest['environments'][env]['gke']['config_map']['entries']
    unsupported = {
        key: entry.get('source') if isinstance(entry, dict) else entry
        for key, entry in entries.items()
        if not isinstance(entry, dict) or entry.get('source') not in ('literal', 'environment')
    }
    assert unsupported == {}


@pytest.mark.parametrize('environment', ['dev', 'prod'])
@pytest.mark.parametrize('bound', [False, True])
def test_api_hosts_render_same_optional_price_authority(monkeypatch, checked_in_manifest, environment, bound):
    from datetime import datetime, timezone
    from config.plan_catalog import (
        LADDER_V1_PRICE_BINDINGS,
        RECOGNIZED_STRIPE_PRICE_PLAN_TYPES,
        resolve_subscription_entitlements,
    )
    from scripts.render_backend_runtime_env import _render_env_entries, _render_desktop_backend_state
    from scripts import render_gke_backend_config as renderer

    # Reuse the real manifest parsed in setup; rendering/entitlement assertions need no repeated YAML parse.
    monkeypatch.setattr(renderer, '_load_yaml', lambda path: checked_in_manifest)
    config = checked_in_manifest['environments'][environment]
    monkeypatch.setenv('SCREEN_VECTOR_STRIPE_READ_SECRET', 'fixture-subscription-reader')
    keys = {row['env_var'] for row in LADDER_V1_PRICE_BINDINGS.values()}
    for key, entry in config['gke']['config_map']['entries'].items():
        if entry['source'] == 'environment' and key not in keys:
            monkeypatch.setenv(key, entry.get('default') or 'fixture-config-value')
    for index, key in enumerate(sorted(keys)):
        if bound:
            monkeypatch.setenv(key, f'price_host_fixture_{index}')
        else:
            monkeypatch.delenv(key, raising=False)
    name, gke = config_map_entries(environment)
    hosts = {
        'backend': {
            entry['name']: entry['value']
            for entry in _render_env_entries(
                {key: entry for key, entry in config['cloud_run']['services']['backend']['env'].items() if key in keys}
            )
        },
        'desktop-backend': {
            entry['name']: entry['value']
            for entry in _render_desktop_backend_state(config)['services']['desktop-backend']['env']
            if entry['name'] in keys
        },
    }
    for host, values in [
        ('backend-listen', f'{environment}_omi_backend_listen_values.yaml'),
        ('pusher', f'{environment}_omi_pusher_values.yaml'),
    ]:
        chart = yaml.safe_load((BACKEND_ROOT / 'charts' / host / values).read_text())
        assert {'configMapRef': {'name': name}} in chart['envFrom']
        hosts[host] = {key: gke[key] for key in keys}
    expected = {key: f'price_host_fixture_{index}' if bound else '' for index, key in enumerate(sorted(keys))}
    assert hosts['backend-listen'] == hosts['pusher'] == expected
    assert hosts['backend'] == hosts['desktop-backend'] == (expected if bound else {})
    for values in hosts.values():
        expiry = datetime.now(timezone.utc).timestamp() + 3600
        assert (
            resolve_subscription_entitlements({'plan': 'basic'}, values)['capabilities']['cloud_screen_vectors']
            is False
        )
        if bound:
            for binding in LADDER_V1_PRICE_BINDINGS.values():
                row = {
                    'plan': binding['plan_id'],
                    'current_period_end': expiry,
                    'current_price_id': values[binding['env_var']],
                }
                assert resolve_subscription_entitlements(row, values)['capabilities']['cloud_screen_vectors'] is (
                    binding['plan_id'] != 'plus'
                )
        for price, plan in RECOGNIZED_STRIPE_PRICE_PLAN_TYPES.items():
            assert (
                resolve_subscription_entitlements(
                    {'plan': plan.value, 'current_period_end': expiry, 'current_price_id': price}, values
                )['capabilities']['cloud_screen_vectors']
                is True
            )


@pytest.mark.parametrize('environment', ['dev', 'prod'])
@pytest.mark.parametrize('configured', [False, True])
def test_standalone_config_refresh_cannot_erase_bound_price_refs(
    monkeypatch, tmp_path, capsys, environment, configured
):
    from config.plan_catalog import LADDER_V1_PRICE_BINDINGS
    from scripts import render_gke_backend_config as renderer
    import json

    keys = [binding['env_var'] for binding in LADDER_V1_PRICE_BINDINGS.values()]
    manifest = {
        'environments': {
            environment: {
                'gke': {
                    'config_map': {
                        'name': f'{environment}-omi-backend-config',
                        'entries': {key: {'source': 'environment', 'default': ''} for key in keys},
                    }
                }
            }
        }
    }
    path = tmp_path / 'manifest.yaml'
    path.write_text(yaml.safe_dump(manifest))
    existing = tmp_path / 'existing.json'
    existing.write_text(json.dumps({'data': {key: f'price_existing_{i}' for i, key in enumerate(keys)}}))
    for i, key in enumerate(keys):
        if configured:
            monkeypatch.setenv(key, f'price_configured_{i}')
        else:
            monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(
        'sys.argv', ['render', '--env', environment, '--manifest', str(path), '--existing-config-map', str(existing)]
    )
    assert renderer.main() == 0
    actual = dict(line.split('=', 1) for line in capsys.readouterr().out.splitlines())
    prefix = 'price_configured' if configured else 'price_existing'
    assert actual == {key: f'{prefix}_{i}' for i, key in enumerate(keys)}
    # No current map is a valid first deployment; optional references stay empty.
    if not configured:
        existing.write_text('')
        assert renderer.main() == 0
        assert dict(line.split('=', 1) for line in capsys.readouterr().out.splitlines()) == {key: '' for key in keys}


def test_config_writers_get_bindings_in_selected_environment_and_preserve_existing():
    from config.plan_catalog import LADDER_V1_PRICE_BINDINGS

    root = BACKEND_ROOT.parent
    expected_steps = {
        'gcp_backend_listen_helm.yml': ['Apply non-secret backend runtime config'],
        'gcp_backend_pusher.yml': [
            'Create isolated proposed production Pusher ConfigMap',
            'Apply non-secret pusher runtime config',
        ],
    }
    for filename, names in expected_steps.items():
        workflow = yaml.safe_load((root / '.github/workflows' / filename).read_text())
        for name in names:
            owners = [
                (job, step)
                for job in workflow['jobs'].values()
                for step in job.get('steps', [])
                if step.get('name') == name
            ]
            assert len(owners) == 1
            job, step = owners[0]
            assert job.get('environment')
            for binding in LADDER_V1_PRICE_BINDINGS.values():
                key = binding['env_var']
                assert step['env'][key] == '${{ vars.' + key + ' }}'
                assert key not in workflow.get('env', {})
    script = (BACKEND_ROOT / 'scripts/deploy-backend-config.sh').read_text()
    assert 'get configmap "$manifest_config_map" --ignore-not-found -o json' in script
    assert '--existing-config-map "$existing_file"' in script
    # The auto pusher lane never rewrites the shared ConfigMap; full-stack caller
    # scoping is covered by the runtime renderer's existing environment guard.
    auto = (root / '.github/workflows/gcp_backend_pusher_auto_deploy.yml').read_text()
    assert 'deploy-backend-config.sh' not in auto


@pytest.mark.parametrize('read_fails', [False, True])
def test_real_config_apply_preserves_refs_and_stops_before_mutation_on_read_failure(monkeypatch, tmp_path, read_fails):
    import json
    import subprocess
    import sys
    from config.plan_catalog import LADDER_V1_PRICE_BINDINGS

    keys = [row['env_var'] for row in LADDER_V1_PRICE_BINDINGS.values()]
    manifest = tmp_path / 'manifest.yaml'
    manifest.write_text(
        yaml.safe_dump(
            {
                'environments': {
                    'dev': {
                        'gke': {
                            'config_map': {
                                'name': 'dev-omi-backend-config',
                                'entries': {key: {'source': 'environment', 'default': ''} for key in keys},
                            }
                        }
                    }
                }
            }
        )
    )
    bin_dir = tmp_path / 'bin'
    bin_dir.mkdir()
    calls, applied = tmp_path / 'calls.jsonl', tmp_path / 'applied.json'
    fake = bin_dir / 'kubectl'
    fake.write_text('#!' + sys.executable + '\n' + '''
import json, os, sys
from pathlib import Path
args = sys.argv[1:]
with Path(os.environ['TEST_CALLS']).open('a') as f: f.write(json.dumps(args) + '\\n')
if 'get' in args:
    if os.environ['TEST_READ_FAILS'] == '1': raise SystemExit(1)
    print(json.dumps({'data': {os.environ['TEST_PRICE_KEY']: 'price_previously_configured'}}))
elif 'create' in args:
    source = next(a.split('=',1)[1] for a in args if a.startswith('--from-env-file='))
    data = dict(line.split('=',1) for line in Path(source).read_text().splitlines())
    print(json.dumps({'data':data}))
elif 'apply' in args:
    Path(os.environ['TEST_APPLIED']).write_text(sys.stdin.read())
else: raise SystemExit(2)
''')
    fake.chmod(0o755)
    for key in keys:
        monkeypatch.delenv(key, raising=False)
    env = {
        **os.environ,
        'PATH': str(bin_dir) + os.pathsep + str(Path(sys.executable).parent) + os.pathsep + os.environ['PATH'],
        'ENVIRONMENT': 'dev',
        'RUNTIME_ENV_MANIFEST': str(manifest),
        'TEST_CALLS': str(calls),
        'TEST_APPLIED': str(applied),
        'TEST_READ_FAILS': str(int(read_fails)),
        'TEST_PRICE_KEY': keys[0],
    }
    result = subprocess.run(
        ['bash', str(BACKEND_ROOT / 'scripts/deploy-backend-config.sh')], env=env, capture_output=True, text=True
    )
    invoked = [json.loads(line) for line in calls.read_text().splitlines()]
    assert invoked[0] == [
        '-n',
        'dev-omi-backend',
        'get',
        'configmap',
        'dev-omi-backend-config',
        '--ignore-not-found',
        '-o',
        'json',
    ]
    if read_fails:
        assert result.returncode != 0 and len(invoked) == 1
        assert not applied.exists()
    else:
        assert result.returncode == 0, result.stderr
        assert json.loads(applied.read_text())['data'] == {
            key: 'price_previously_configured' if key == keys[0] else '' for key in keys
        }
        assert 'price_previously_configured' not in result.stdout
