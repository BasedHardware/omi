"""Paid recovery must target the actual sweep owner, with deployable time budgets."""

from pathlib import Path

import pytest
import yaml

from scripts.render_backend_runtime_env import _render_env_vars, _render_cloud_run_state, _render_flags
from scripts.runtime_env_validation.workflows import _extract_workflow_cloud_run_targets
from utils.cloud_tasks import DISPATCH_DEADLINE_SECONDS

ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture(autouse=True)
def fast_safe_yaml(monkeypatch):
    monkeypatch.setattr(yaml, 'safe_load', lambda stream: yaml.load(stream, Loader=yaml.CSafeLoader))


@pytest.mark.parametrize('environment,suffix', [('prod', 'hhibjajaja'), ('dev', 'dt5lrfkkoa')])
def test_recovery_targets_integration_with_declared_platform_timeout(environment, suffix, monkeypatch):
    manifest = yaml.safe_load((ROOT / 'backend/deploy/runtime_env.yaml').read_text())
    config = manifest['environments'][environment]
    services = config['cloud_run']['services']
    integration = services['backend-integration']
    audience = integration['env']['BATCH_PIPELINE_RECOVERY_TASK_AUDIENCE']
    assert audience == {'value': f'https://backend-integration-{suffix}-uc.a.run.app', 'category': 'service_auth'}
    assert _render_env_vars({'BATCH_PIPELINE_RECOVERY_TASK_AUDIENCE': audience}) == (
        f'BATCH_PIPELINE_RECOVERY_TASK_AUDIENCE={audience["value"]}'
    )
    if environment == 'prod':
        assert integration['env']['BATCH_PIPELINE_SERVING_ENABLED']['value'] == 'true'
    for host in services.values():
        if host['env'].get('BATCH_PIPELINE_SERVING_ENABLED', {}).get('value') != 'true':
            continue
        assert host['env']['BATCH_PIPELINE_RECOVERY_TASK_AUDIENCE']['value'] == audience['value']
        assert integration['env']['BATCH_PIPELINE_RECOVERY_MODE']['value'] == 'on'
    timeout = integration['flags']['--timeout']
    assert int(timeout.removesuffix('s')) >= DISPATCH_DEADLINE_SECONDS > 300
    assert f'--timeout={timeout}' in _render_flags(integration['flags'])
    monkeypatch.setenv('CLOUD_RUN_VPC_NETWORK', 'synthetic-network')
    monkeypatch.setenv('CLOUD_RUN_VPC_SUBNET', 'synthetic-subnet')
    # Verify the manifest reaches the deploy action and its validator state.
    for service in services.values():
        for binding in service['env'].values():
            if 'env_var' in binding:
                monkeypatch.setenv(binding['env_var'], str(binding.get('default', 'synthetic-value')))
    for job in config['cloud_run'].get('jobs', {}).values():
        for binding in job.get('env', {}).values():
            if 'env_var' in binding:
                monkeypatch.setenv(binding['env_var'], str(binding.get('default', 'synthetic-value')))
    assert _render_cloud_run_state(config)['services']['backend-integration']['flags']['--timeout'] == timeout
    workflow = yaml.safe_load((ROOT / '.github/workflows/gcp_backend.yml').read_text())
    targets = _extract_workflow_cloud_run_targets(workflow, env=environment, manifest=manifest, workflow_root=ROOT)
    assert targets['services']['backend-integration']['flags']['--timeout'] == timeout
