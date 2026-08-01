"""Static wiring contract for the blocking Sync Cloud Tasks stack gauntlet.

Behavior is proved by the emulator stack itself.  This test prevents its
package script, high-risk workflow contract, or blocking CI job from silently
disconnecting.
"""

from __future__ import annotations

import json
from pathlib import Path

from utils.cloud_tasks import SYNC_JOB_TASK_PAYLOAD_KEYS

_REPO_ROOT = Path(__file__).resolve().parents[3]


def test_sync_cloud_tasks_stack_gauntlet_has_a_deterministic_hermetic_ci_job() -> None:
    workflow = (_REPO_ROOT / '.github' / 'workflows' / 'backend-hermetic-e2e.yml').read_text(encoding='utf-8')
    package = json.loads((_REPO_ROOT / 'package.json').read_text(encoding='utf-8'))
    contracts = json.loads((_REPO_ROOT / 'backend' / 'testing' / 'workflow_contracts.json').read_text(encoding='utf-8'))

    assert '  sync-cloud-tasks-stack-gauntlet:' in workflow
    job = workflow.split('  sync-cloud-tasks-stack-gauntlet:\n', 1)[1]

    assert 'timeout-minutes: 20' in job
    assert 'needs: scope' in job
    assert "if: needs.scope.outputs.applies == 'true'" in job
    assert 'uses: actions/setup-python@v6' in job
    assert 'uses: astral-sh/setup-uv@ecd24dd710f2fb0dca1693a67af11fc4a5c5ec84' in job
    assert 'uv venv .venv' in job
    assert 'uv pip sync pylock.toml --python .venv/bin/python' in job
    assert 'uses: actions/setup-node@v7' in job
    assert "node-version: '22'" in job
    assert 'cache-dependency-path: package-lock.json' in job
    assert 'npm ci --ignore-scripts' in job
    assert 'uses: actions/setup-java@v5' in job
    assert "java-version: '21'" in job
    assert 'sudo apt-get install --yes redis-server' in job
    assert 'npm run test:sync-cloud-tasks-stack:emulator' in job

    assert package['scripts']['test:sync-cloud-tasks-stack:emulator'] == 'backend/testing/sync_cloud_tasks_stack/run.sh'
    run_script = (_REPO_ROOT / 'backend' / 'testing' / 'sync_cloud_tasks_stack' / 'run.sh').read_text(encoding='utf-8')
    assert 'websocketPort' in run_script
    sync_contract = next(contract for contract in contracts['workflows'] if contract['id'] == 'sync_cloud_tasks')
    assert 'backend/testing/sync_cloud_tasks_stack/**' in sync_contract['sources']
    assert 'tests/unit/test_sync_cloud_tasks_stack_ci_wiring.py' in sync_contract['tests']


def test_gauntlet_recorder_shares_the_production_task_payload_schema() -> None:
    """The recorder must accept every durable field admission can enqueue."""
    recorder = (_REPO_ROOT / 'backend' / 'testing' / 'sync_cloud_tasks_stack' / 'cloud_tasks.py').read_text(
        encoding='utf-8'
    )

    assert 'set(body) != SYNC_JOB_TASK_PAYLOAD_KEYS' in recorder
    assert 'geolocation' in SYNC_JOB_TASK_PAYLOAD_KEYS
