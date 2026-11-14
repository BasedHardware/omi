"""Conversation batch purges and erasures get their own Cloud Tasks queue, apart from account wipes.

2026-11-14: a 533-conversation cleanup queued ~760 purge units on the shared
`account-deletion` queue (4 dispatches); users' accepted deletes and account
deletions waited up to 40 minutes behind them.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest
import yaml

from scripts import runtime_env_durable_dispatch_contracts as contracts

ROOT = Path(__file__).resolve().parents[3]
STEP = 'Configure production conversation-erasure Cloud Tasks queue'


def _steps():
    action = yaml.safe_load((ROOT / '.github/actions/deploy-backend-stack/action.yml').read_text())
    return action['runs']['steps']


def test_queue_is_provisioned_on_every_prod_deploy_before_traffic_moves():
    steps = _steps()
    index = next(i for i, step in enumerate(steps) if step['name'] == STEP)
    assert steps[index]['if'] == "${{ inputs.runtime_env == 'prod' }}"
    assert index < next(
        i for i, step in enumerate(steps) if step['name'] == 'Shift Cloud Run traffic to validated revisions'
    )
    assert index < next(
        i for i, step in enumerate(steps) if step['name'].startswith('Deploy ${{ env.SERVICE }}-listen')
    )


@pytest.mark.parametrize('inventory', ['present', 'present_short', 'absent', 'denied', 'unexpected'])
def test_queue_provisioning_is_bounded_and_inventory_errors_fail_closed(tmp_path, inventory):
    step = next(step for step in _steps() if step['name'] == STEP)
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
    present) echo projects/synthetic-project/locations/synthetic-region/queues/conversation-erasure ;;
    present_short) echo conversation-erasure ;;
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
    ok = inventory in {'present', 'present_short', 'absent'}
    assert (result.returncode == 0) is ok
    assert len(calls) == (2 if ok else 1)
    if ok:
        operation = 'update' if inventory.startswith('present') else 'create'
        assert calls[1].startswith(f'tasks queues {operation} conversation-erasure ')
        for option in [
            '--max-concurrent-dispatches=20',
            '--max-dispatches-per-second=5',
            '--max-attempts=5',
            '--min-backoff=5s',
            '--max-backoff=300s',
        ]:
            assert option in calls[1]
    assert not any('account-deletion' in call for call in calls)  # the wipe queue is never touched


def test_every_prod_dispatcher_names_the_queue_and_wipes_keep_theirs():
    manifest = yaml.safe_load((ROOT / 'backend/deploy/runtime_env.yaml').read_text())
    prod = manifest['environments']['prod']
    hosts = {'gke/backend-listen': prod['gke']['backend-listen']['env']}
    for service in ('backend', 'backend-sync', 'backend-sync-backfill', 'backend-integration'):
        hosts[f'cloud_run/{service}'] = prod['cloud_run']['services'][service]['env']
    for scope, env in hosts.items():
        assert env['CONVERSATION_ERASURE_TASKS_QUEUE']['value'] == 'conversation-erasure', scope
        assert env['ACCOUNT_DELETION_TASKS_QUEUE']['value'] == 'account-deletion', scope

    chart = yaml.safe_load((ROOT / 'backend/charts/backend-listen/prod_omi_backend_listen_values.yaml').read_text())
    chart_env = {entry['name']: entry.get('value') for entry in chart['env']}
    assert chart_env['CONVERSATION_ERASURE_TASKS_QUEUE'] == 'conversation-erasure'

    staging = yaml.safe_load((ROOT / 'backend/deploy/runtime_env/staging.overlay.yaml').read_text())
    assert staging['cloud_run']['queue_map']['conversation-erasure'] == 'staging-conversation-erasure'
    assert '"staging-conversation-erasure|' in (ROOT / 'backend/deploy/staging/create_queues.sh').read_text()


def test_prod_contract_rejects_erasure_units_on_the_wipe_queue():
    prod = yaml.safe_load((ROOT / 'backend/deploy/runtime_env.yaml').read_text())['environments']['prod']
    assert contracts.validate_account_deletion_dispatch_contract('prod', prod) == []

    entry = prod['cloud_run']['services']['backend-sync']['env']['CONVERSATION_ERASURE_TASKS_QUEUE']
    entry['value'] = 'account-deletion'
    assert contracts.ValidationError(
        'prod/cloud_run/backend-sync',
        "account-deletion env CONVERSATION_ERASURE_TASKS_QUEUE must be literal 'conversation-erasure'",
    ) in contracts.validate_account_deletion_dispatch_contract('prod', prod)
