"""Paid recovery must target the actual sweep owner, with deployable time budgets."""

from pathlib import Path
import os
import subprocess

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
        queue = integration['env']['BATCH_PIPELINE_RECOVERY_TASKS_QUEUE']
        assert queue == {'value': 'batch-quarantine-recovery', 'category': 'reliability'}
        assert queue['value'] != integration['env']['SYNC_TASKS_QUEUE']['value']
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
    if environment == 'prod':
        rendered = _render_cloud_run_state(config)['services']['backend-integration']['env']
        assert (
            next(e['value'] for e in rendered if e['name'] == 'BATCH_PIPELINE_RECOVERY_TASKS_QUEUE') == queue['value']
        )
    workflow = yaml.safe_load((ROOT / '.github/workflows/gcp_backend.yml').read_text())
    targets = _extract_workflow_cloud_run_targets(workflow, env=environment, manifest=manifest, workflow_root=ROOT)
    assert targets['services']['backend-integration']['flags']['--timeout'] == timeout


@pytest.mark.parametrize('inventory', ['present', 'present_short', 'absent', 'denied', 'unexpected'])
def test_recovery_queue_provisioning_is_bounded_and_inventory_errors_fail_closed(tmp_path, inventory):
    action = yaml.safe_load((ROOT / '.github/actions/deploy-backend-stack/action.yml').read_text())
    steps = action['runs']['steps']
    index = next(
        i for i, step in enumerate(steps) if step['name'] == 'Configure production batch quarantine recovery queue'
    )
    step = steps[index]
    assert step['if'] == "${{ inputs.runtime_env == 'prod' }}"
    assert index < next(i for i, s in enumerate(steps) if s.get('id') == 'deploy-backend-integration')
    script = (
        step['run']
        .replace('${{ inputs.project_id }}', 'synthetic-project')
        .replace('${{ inputs.region }}', 'synthetic-region')
    )
    trace = tmp_path / 'calls'
    fake = tmp_path / 'gcloud'
    fake.write_text('''#!/bin/bash
printf '%s\\n' "$*" >> "$TRACE"
if [[ "$3" == list ]]; then
  case "$INVENTORY" in
    present) echo projects/synthetic-project/locations/synthetic-region/queues/batch-quarantine-recovery ;;
    present_short) echo batch-quarantine-recovery ;;
    absent) ;;
    denied) exit 1 ;;
    unexpected) echo unexpected ;;
  esac
fi
''')
    fake.chmod(0o755)
    result = subprocess.run(
        ['bash', '-c', script],
        env={**os.environ, 'PATH': f'{tmp_path}:/usr/bin:/bin', 'TRACE': str(trace), 'INVENTORY': inventory},
        capture_output=True,
        text=True,
    )
    calls = trace.read_text().splitlines()
    assert (result.returncode == 0) is (inventory in {'present', 'present_short', 'absent'})
    assert len(calls) == (2 if inventory in {'present', 'present_short', 'absent'} else 1)
    if result.returncode == 0:
        operation = 'update' if inventory in {'present', 'present_short'} else 'create'
        assert calls[1].startswith(f'tasks queues {operation} batch-quarantine-recovery ')
        for option in [
            # 10-19 01:27Z raise; the 07:07Z train reset it to 4/4 and failed the 5% re-qualification.
            '--max-concurrent-dispatches=16',
            '--max-dispatches-per-second=8',
            '--max-attempts=5',
            '--min-backoff=5s',
            '--max-backoff=60s',
        ]:
            assert option in calls[1]


def test_prod_integration_pins_the_ramp_recovery_dispatch_batch(monkeypatch):
    """Set live to 64 during the 10-19 ramp; without the manifest value every train restores 16."""
    import importlib

    overlay = yaml.safe_load((ROOT / 'backend/deploy/runtime_env/prod.overlay.yaml').read_text())
    env = overlay['overlay']['cloud_run']['services']['backend-integration']['env']
    assert env['BATCH_PIPELINE_RECOVERY_DISPATCH_BATCH_SIZE']['value'] == '64'
    batch_pipeline = importlib.import_module('config.batch_pipeline')
    monkeypatch.setenv('BATCH_PIPELINE_RECOVERY_DISPATCH_BATCH_SIZE', '64')
    assert batch_pipeline.recovery_dispatch_batch_size() == 64  # within the code bound, not clamped back to 16
