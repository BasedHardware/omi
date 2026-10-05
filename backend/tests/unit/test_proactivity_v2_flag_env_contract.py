"""Dedicated public flag token on every admission host, independently of shared telemetry."""

import copy
import re
from pathlib import Path

import pytest
import yaml

from scripts.render_backend_runtime_env import _render_cloud_run_state, _render_desktop_backend_state
from scripts.runtime_env_validation.common import _validate_env_entries, validate_proactivity_v2_posthog_token
from scripts.runtime_env_validation.manifest import _validate_proactivity_v2_flag_hosts
from scripts.runtime_env_validation.workflows import _extract_workflow_cloud_run_targets

ROOT = Path(__file__).resolve().parents[3]
TOKEN = 'PROACTIVITY_V2_POSTHOG_TOKEN'
HOST = 'PROACTIVITY_V2_POSTHOG_HOST'
SURFACES = (
    ('gke', 'pusher'),
    ('gke', 'backend-listen'),
    ('llm_gateway',),
    ('desktop_backend',),
    ('cloud_run', 'services', 'backend'),
    ('cloud_run', 'services', 'backend-sync'),
    ('cloud_run', 'services', 'backend-sync-backfill'),
    ('cloud_run', 'services', 'backend-integration'),
)


@pytest.fixture(scope='module')
def deployment_manifest():
    return yaml.safe_load((ROOT / 'backend/deploy/runtime_env.yaml').read_text())


def surface(config, path):
    for name in path:
        config = config[name]
    return config


def public_token():
    swift = (ROOT / 'desktop/macos/Desktop/Sources/PostHogManager.swift').read_text()
    return re.search(r'apiKey = "(phc_[^"]+)"', swift)[1]


@pytest.mark.parametrize('stage', ['dev', 'prod'])
def test_every_host_binds_same_public_token_and_chart_values(stage, deployment_manifest):
    config = deployment_manifest['environments'][stage]
    for path in SURFACES:
        host = surface(config, path)
        assert host['env'][TOKEN] == {'value': public_token(), 'category': 'rollout'}
        assert host['env'][HOST] == {'value': 'https://us.posthog.com', 'category': 'rollout'}
        assert TOKEN not in host.get('secrets', {})
    assert _validate_proactivity_v2_flag_hosts(stage, config) == []
    for chart in ('pusher', 'backend-listen', 'llm-gateway'):
        path = ROOT / f'backend/charts/{chart}/{stage}_omi_{chart.replace("-", "_")}_values.yaml'
        values = yaml.safe_load(path.read_text())
        for name, value in ((TOKEN, public_token()), (HOST, 'https://us.posthog.com')):
            assert [entry for entry in values['env'] if entry['name'] == name] == [{'name': name, 'value': value}]


@pytest.mark.parametrize('stage', ['dev', 'prod'])
@pytest.mark.parametrize('path', SURFACES)
@pytest.mark.parametrize('entry', [None, {'value': 'disabled'}, {'value': 'not-public'}, {'secret': {'key': TOKEN}}])
def test_manifest_rejects_missing_or_invalid_binding_on_each_host(stage, path, entry, deployment_manifest):
    config = copy.deepcopy(deployment_manifest['environments'][stage])
    env = surface(config, path)['env']
    if entry is None:
        del env[TOKEN]
    else:
        env[TOKEN] = entry
    errors = _validate_proactivity_v2_flag_hosts(stage, config)
    scope = '/'.join(name for name in path if name != 'services')
    assert any(TOKEN in error.message and scope in error.scope for error in errors)


@pytest.mark.parametrize(
    'entry',
    [
        {'value': 'disabled'},
        {'value': ''},
        {'value': 'phx_personal'},
        {'valueFrom': {'secretKeyRef': {'name': TOKEN}}},
        {'value': 'phc_token', 'secret': {'key': TOKEN}},
    ],
)
def test_actual_env_contract_rejects_invalid_or_secret_token(entry):
    errors = _validate_env_entries(
        scope='rendered',
        expected={TOKEN: {'value': 'phc_token'}},
        actual={TOKEN: {'name': TOKEN, **entry}},
        strict_provisional=True,
    )
    assert any('plain public phc_' in error.message for error in errors)


def test_plain_token_validation_allows_only_optional_absence():
    assert validate_proactivity_v2_posthog_token(scope='local', env_entries={}) == []
    assert validate_proactivity_v2_posthog_token(scope='prod', env_entries={}, required=True)
    assert validate_proactivity_v2_posthog_token(scope='prod', env_entries={TOKEN: {'value': 'phc_token'}}) == []


@pytest.mark.parametrize('stage', ['dev', 'prod'])
def test_cloud_run_render_and_desktop_workflow_bind_plain_token(stage, monkeypatch, deployment_manifest):
    source = deployment_manifest
    config = source['environments'][stage]
    # Resolve provisional deploy inputs without cloud credentials or live services.
    for host in config['cloud_run']['services'].values():
        for entry in host['env'].values():
            if 'env_var' in entry:
                monkeypatch.setenv(entry['env_var'], str(entry.get('default', 'offline-value')))
    for entry in config['cloud_run']['network']['flags'].values():
        if isinstance(entry, dict) and 'env_var' in entry:
            monkeypatch.setenv(entry['env_var'], 'offline-network')
    for renderer in (_render_cloud_run_state, _render_desktop_backend_state):
        for host in renderer(config)['services'].values():
            actual = {entry['name']: entry for entry in host['env']}
            assert actual[TOKEN] == {'name': TOKEN, 'value': public_token()}
            assert actual[HOST] == {'name': HOST, 'value': 'https://us.posthog.com'}
    filename = 'desktop_backend_prod.yml' if stage == 'prod' else 'desktop_backend_auto_dev.yml'
    workflow = yaml.safe_load((ROOT / '.github/workflows' / filename).read_text())
    targets = _extract_workflow_cloud_run_targets(
        workflow, env=stage, manifest=source, workflow_root=ROOT / '.github/workflows'
    )
    env = targets['services']['desktop-backend']['env_vars']
    assert env[TOKEN] == public_token()
    assert env[HOST] == 'https://us.posthog.com'
    assert TOKEN not in targets['services']['desktop-backend']['secrets']
