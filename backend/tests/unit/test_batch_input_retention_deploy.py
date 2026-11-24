"""The held-input kill switch must reach every existing held-sweep deployment."""

from pathlib import Path
import subprocess

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]
OLD = 'BATCH_HELD_DEAD_LETTER_ENABLED'
NEW = 'BATCH_INPUT_EXPIRING_ENABLED'


def held_envs(node, path=()):
    if not isinstance(node, dict):
        return
    if OLD in node:
        yield path, node
    for key, value in node.items():
        yield from held_envs(value, (*path, key))


@pytest.fixture(scope='module')
def runtime_env_docs():
    # Parse the large runtime env files once, outside the measured call phase.
    load = lambda rel: yaml.load((ROOT / rel).read_text(), Loader=getattr(yaml, 'CSafeLoader', yaml.SafeLoader))
    return (
        load('backend/deploy/runtime_env/_base.yaml'),
        load('backend/deploy/runtime_env/prod.overlay.yaml'),
        load('backend/deploy/runtime_env.yaml'),
    )


def test_runtime_base_and_explicit_prod_overlay_bind_every_sweep_host(runtime_env_docs):
    base, prod, manifest = runtime_env_docs
    found = list(held_envs(base['environment_shared']))
    assert len(found) == 5
    for path, env in found:
        assert env[NEW] == {'value': 'true', 'category': 'ops_kill'}
        overlay = prod['overlay']
        for key in path:
            overlay = overlay[key]
        assert overlay[NEW] == {'value': 'true', 'category': 'ops_kill'}
    assert list(held_envs(manifest))
    for _, env in held_envs(manifest):
        assert env[NEW] == {'value': 'true', 'category': 'ops_kill'}


@pytest.mark.parametrize('environment', ['dev', 'prod'])
def test_listen_chart_binds_switch(environment):
    values = yaml.safe_load(
        (ROOT / f'backend/charts/backend-listen/{environment}_omi_backend_listen_values.yaml').read_text()
    )
    env = {entry['name']: entry for entry in values['env']}
    assert env[OLD]['value'] == 'true'
    assert env[NEW]['value'] == 'true'


@pytest.mark.parametrize('environment', ['dev', 'staging', 'prod'])
def test_worker_chart_renders_default_on_and_off_kill(environment):
    chart = ROOT / 'backend/charts/batch-pipeline-worker'
    values = chart / f'{environment}_omi_batch-pipeline-worker_values.yaml'
    assert yaml.safe_load(values.read_text())['worker']['inputExpiringEnabled'] is True
    for enabled in ('true', 'false'):
        rendered = subprocess.run(
            [
                'helm',
                'template',
                'retention-test',
                str(chart),
                '-f',
                str(values),
                '--namespace',
                f'{environment}-omi-backend',
                '--set',
                f'worker.inputExpiringEnabled={enabled}',
                '--set',
                'image.digest=sha256:' + 'a' * 64,
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        sweep_hosts = 0
        for deployment in yaml.safe_load_all(rendered.stdout):
            if not deployment or deployment.get('kind') != 'Deployment':
                continue
            for container in deployment['spec']['template']['spec']['containers']:
                env = {entry['name']: entry for entry in container.get('env', [])}
                if OLD in env:
                    sweep_hosts += 1
                    assert env[OLD]['value'] == 'true'
                    assert env[NEW]['value'] == enabled
        assert sweep_hosts == (2 if environment == 'prod' else 1)
