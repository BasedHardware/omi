"""Redis ports must survive the actual Cloud Run deploy rendering boundary."""

from copy import deepcopy
from pathlib import Path

import pytest
import yaml

from scripts.render_backend_runtime_env import _render_env_vars
from scripts.runtime_env_validation import manifest as validator
from scripts.runtime_env_validation.manifest import _validate_manifest_shape

SERVICES = ('backend', 'backend-integration', 'backend-sync', 'backend-sync-backfill')


@pytest.fixture(scope='module')
def manifest():
    path = Path(__file__).resolve().parents[2] / 'deploy/runtime_env.yaml'
    return yaml.load(path.read_text(), Loader=yaml.CSafeLoader)


@pytest.mark.parametrize('environment', ['dev', 'prod'])
@pytest.mark.parametrize('service', SERVICES)
def test_deploy_renderer_retains_live_redis_port(manifest, environment, service, monkeypatch):
    config = manifest['environments'][environment]['cloud_run']['services'][service]
    for name, binding in config['env'].items():
        if 'env_var' in binding:
            monkeypatch.setenv(binding['env_var'], str(binding.get('default', 'test-value')))
    # Assert what deploy-cloudrun receives, rather than only a source YAML field.
    rendered = _render_env_vars(config['env'])
    assert 'REDIS_DB_PORT=13151' in rendered.splitlines()


@pytest.mark.parametrize('environment', ['dev', 'prod'])
@pytest.mark.parametrize('service', SERVICES)
def test_managed_cloud_run_service_cannot_lose_carried_redis_port(manifest, environment, service):
    config = deepcopy(manifest['environments'][environment])
    config['cloud_run']['services'][service]['env'].pop('REDIS_DB_PORT', None)
    errors = _validate_manifest_shape(config, environment)
    assert any(e.scope == f'{environment}/cloud_run/{service}' and 'REDIS_DB_PORT' in e.message for e in errors)


@pytest.mark.parametrize('surface', ['services', 'jobs'])
@pytest.mark.parametrize('host_kind', ['env', 'secrets'])
def test_declared_redis_host_requires_port_on_other_cloud_run_targets(manifest, surface, host_kind):
    config = deepcopy(manifest['environments']['dev'])
    target = {host_kind: {'REDIS_DB_HOST': {'value': 'test-host'} if host_kind == 'env' else {'secret': 'test-host'}}}
    config['cloud_run'].setdefault(surface, {})['additional-worker'] = target
    errors = _validate_manifest_shape(config, 'dev')
    assert any('additional-worker' in e.scope and 'REDIS_DB_PORT' in e.message for e in errors)


@pytest.mark.parametrize('port', ['', '0', '65536', 'not-a-port'])
def test_declared_port_must_be_a_valid_nonempty_tcp_port(manifest, port):
    config = deepcopy(manifest['environments']['dev'])
    config['cloud_run']['services']['backend']['env']['REDIS_DB_PORT'] = {'value': port}
    errors = _validate_manifest_shape(config, 'dev')
    assert any(e.scope == 'dev/cloud_run/backend' and 'REDIS_DB_PORT' in e.message for e in errors)


@pytest.mark.parametrize('environment', ['dev', 'prod'])
def test_repo_redis_bindings_validate(manifest, environment):
    assert _validate_manifest_shape(manifest['environments'][environment], environment) == []


def test_gke_declared_host_requires_port_in_helm_values(monkeypatch):
    config = {
        'gke': {
            'worker': {
                'values_file': 'test-values.yaml',
                'env': {'REDIS_DB_HOST': {'value': 'test-host'}},
            }
        }
    }
    values = {'env': [{'name': 'REDIS_DB_HOST', 'value': 'test-host'}]}
    monkeypatch.setattr(validator, '_load_yaml', lambda _: values)
    errors = validator._validate_gke(config, strict_provisional=False)
    assert any(e.scope == 'gke/worker' and 'REDIS_DB_PORT' in e.message for e in errors)
    values['env'].append({'name': 'REDIS_DB_PORT', 'value': '13151'})
    assert validator._validate_gke(config, strict_provisional=False) == []
