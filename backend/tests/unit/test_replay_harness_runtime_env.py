"""Runtime config is an explicit rollout-only input, never a credential source."""

import json

import pytest

from testing.replay_harness.runtime_env import RuntimeEnv, allowed, load_runtime_env, parse_selector, select_entries


@pytest.mark.parametrize(
    'name',
    ['FSR_SUBSCRIPTION_TTL_SECONDS', 'FIRESTORE_READ_LEVERS', 'FOO_PERCENT', 'CACHE_TTL_SECONDS', 'FEATURE_ENABLED'],
)
def test_allowlisted_rollout_names(name):
    assert allowed(name)


@pytest.mark.parametrize(
    'name',
    [
        'OPENAI_API_KEY',
        'GOOGLE_CLOUD_PROJECT',
        'FIRESTORE_EMULATOR_HOST',
        'REDIS_DB_HOST',
        'FSR_API_KEY',
        'FSR_ENDPOINT',
        'FSR_HOST_ENABLED',
        'FIRESTORE_READ_PROJECT_ID',
        'FSR_SECRET_TTL_SECONDS',
        'FSR_TOKEN',
        'FSR_URL',
        'NOT_A_ROLLOUT',
    ],
)
def test_credentials_and_connections_never_pass_prefix_allowlist(name):
    assert not allowed(name)


@pytest.mark.parametrize(
    'entry',
    [
        {'value': 'PRIVATE-CANARY', 'secret': True},
        {'valueFrom': {'secretKeyRef': {'name': 'PRIVATE-CANARY'}}},
        {'valueSource': {'secretKeyRef': {'secret': 'PRIVATE-CANARY'}}},
        {'value': 'PRIVATE-CANARY', 'category': 'secret'},
        {'value': 'PRIVATE-CANARY', 'category': 'secret_manager'},
        {'value': 'PRIVATE-CANARY', 'category': 'auth'},
        {'value': 'PRIVATE-CANARY', 'category': 'identity'},
        {'env_var': 'PRIVATE-CANARY', 'default': 'PRIVATE-CANARY'},
        {'value': {'secret': 'PRIVATE-CANARY'}},
        {'value': 'PRIVATE-CANARY', 'source': {'secretManagerRef': 'PRIVATE-CANARY'}},
    ],
)
def test_secret_or_indirect_entries_are_dropped(entry):
    runtime = select_entries('backend', 'prod', [('FSR_TEST_ENABLED', entry)])
    assert runtime.values == {} and runtime.dropped_count == 1
    assert 'PRIVATE-CANARY' not in json.dumps(runtime.report())
    assert 'PRIVATE-CANARY' not in repr(runtime)


def test_report_is_names_only_and_disallowed_values_are_not_retained():
    runtime = select_entries(
        'backend',
        'prod',
        [
            ('FSR_TEST_ENABLED', {'value': 'true'}),
            ('GOOGLE_CLOUD_PROJECT', {'value': 'PRIVATE-CANARY'}),
            ('FSR_SECRET_ENABLED', {'secret': 'PRIVATE-CANARY'}),
        ],
    )
    assert runtime.report() == dict(service='backend', env='prod', applied_keys=['FSR_TEST_ENABLED'], dropped_count=2)
    assert 'PRIVATE-CANARY' not in repr(runtime) + json.dumps(runtime.report())


def test_hermetic_conflicts_refuse_atomically():
    runtime = RuntimeEnv('backend', 'prod', {'FSR_TEST_ENABLED': 'true', 'MEMORY_ENABLED': 'off'}, 0)
    settings = {'MEMORY_ENABLED': 'on', 'GOOGLE_CLOUD_PROJECT': 'demo-omi-isolated-tests'}
    before = settings.copy()
    with pytest.raises(ValueError, match='conflicts'):
        runtime.apply(settings)
    assert settings == before
    RuntimeEnv('backend', 'prod', {'MEMORY_ENABLED': 'on'}, 0).apply(settings)
    assert settings == before


@pytest.mark.parametrize(
    'selector', ['backend:', 'backend:prod:dev', '../backend', 'backend:staging', 'backend:unknown']
)
def test_invalid_selectors_refuse(selector):
    with pytest.raises(ValueError):
        parse_selector(selector)


def test_unknown_service_refuses_without_emulator_or_cloud():
    with pytest.raises(ValueError, match='render failed'):
        load_runtime_env('not-a-service')


def test_renderer_uses_selected_tree_and_no_ambient_inputs(tmp_path, monkeypatch):
    # A tiny archived renderer proves path selection independently of this checkout.
    deploy = tmp_path / 'backend/deploy'
    deploy.mkdir(parents=True)
    (deploy / 'compose_runtime_env.py').write_text('''import os
from pathlib import Path
def compose_environment(env):
    assert env == 'dev'
    assert not any(name in os.environ for name in ('GOOGLE_APPLICATION_CREDENTIALS', 'CLOUDSDK_CONFIG', 'CLOUDSDK_AUTH_CREDENTIAL_FILE_OVERRIDE', 'FSR_AMBIENT_ENABLED'))
    return {'cloud_run': {'services': {'backend': {
        'env': {'FSR_SUBSCRIPTION_TTL_SECONDS': {'value': Path(__file__).with_name('ttl').read_text()},
                'FSR_CACHE_ENABLED': {'value': 'PRIVATE-CANARY'}},
        'secrets': {'FSR_CACHE_ENABLED': {'secret': 'PRIVATE-CANARY'}}}}}}
''')
    (deploy / 'ttl').write_text('55')
    for name in (
        'GOOGLE_APPLICATION_CREDENTIALS',
        'CLOUDSDK_CONFIG',
        'CLOUDSDK_AUTH_CREDENTIAL_FILE_OVERRIDE',
        'FSR_AMBIENT_ENABLED',
    ):
        monkeypatch.setenv(name, 'PRIVATE-CANARY')
    first = load_runtime_env('backend:dev', backend=deploy.parent)
    assert first.values == {'FSR_SUBSCRIPTION_TTL_SECONDS': '55'}
    assert first.dropped_count == 1
    (deploy / 'ttl').write_text('60')
    assert load_runtime_env('backend:dev', backend=deploy.parent).values == {'FSR_SUBSCRIPTION_TTL_SECONDS': '60'}
    assert parse_selector('backend') == ('backend', 'prod')


def test_render_errors_do_not_echo_values(tmp_path):
    deploy = tmp_path / 'backend/deploy'
    deploy.mkdir(parents=True)
    (deploy / 'compose_runtime_env.py').write_text("raise ValueError('PRIVATE-CANARY')")
    with pytest.raises(ValueError) as caught:
        load_runtime_env('backend', backend=deploy.parent)
    assert 'PRIVATE-CANARY' not in str(caught.value)


def test_gke_helm_render_drops_secret_refs_and_envfrom(tmp_path, monkeypatch):
    import sys

    document = {
        'kind': 'Deployment',
        'metadata': {'name': 'prod-omi-backend-listen'},
        'spec': {
            'template': {
                'spec': {
                    'containers': [
                        {
                            'name': 'backend-listen',
                            'env': [
                                {'name': 'FSR_SUBSCRIPTION_TTL_SECONDS', 'value': '55'},
                                {
                                    'name': 'FSR_SECRET_ENABLED',
                                    'valueFrom': {'secretKeyRef': {'name': 'PRIVATE-CANARY', 'key': 'key'}},
                                },
                                {'name': 'GOOGLE_CLOUD_PROJECT', 'value': 'PRIVATE-CANARY'},
                            ],
                            'envFrom': [{'secretRef': {'name': 'PRIVATE-CANARY'}}],
                        }
                    ]
                }
            }
        },
    }
    helm = tmp_path / 'helm'
    helm.write_text(
        f'#!{sys.executable}\nimport sys\nassert sys.argv[1:3] == ["template", "prod-omi-backend-listen"]\nprint({json.dumps(document)!r})\n'
    )
    helm.chmod(0o700)
    monkeypatch.setenv('PATH', str(tmp_path))
    runtime = load_runtime_env('backend-listen')
    assert runtime.values == {'FSR_SUBSCRIPTION_TTL_SECONDS': '55'}
    assert runtime.dropped_count == 3
    assert 'PRIVATE-CANARY' not in json.dumps(runtime.report())


def test_helm_cannot_erase_source_secret_metadata(tmp_path):
    from testing.replay_harness.runtime_env import indirect_chart_names

    default_values = tmp_path / 'values.yaml'
    overlay = tmp_path / 'prod.yaml'
    default_values.write_text(
        json.dumps(
            {
                'env': [
                    {'name': 'FSR_MARKED_ENABLED', 'value': 'PRIVATE-CANARY', 'category': 'secret'},
                    {'name': 'FSR_LITERAL_ENABLED', 'value': 'true'},
                    {'name': 'FSR_REFERENCED_ENABLED', 'valueFrom': {'secretKeyRef': {'name': 'PRIVATE-CANARY'}}},
                ]
            }
        )
    )
    overlay.write_text(json.dumps({'privateEnv': {'FSR_PRIVATE_ENABLED': 'PRIVATE-CANARY'}}))
    denied = indirect_chart_names([default_values, overlay, tmp_path / 'absent.yaml'])
    assert denied == {'FSR_MARKED_ENABLED', 'FSR_REFERENCED_ENABLED', 'FSR_PRIVATE_ENABLED'}
    assert 'PRIVATE-CANARY' not in repr(denied)
