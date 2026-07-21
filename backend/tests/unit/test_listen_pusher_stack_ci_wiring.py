"""Static wiring contracts for the backend hermetic CI gate."""

from __future__ import annotations

import json
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]


def test_listen_pusher_stack_gauntlet_has_a_deterministic_hermetic_ci_job() -> None:
    workflow = (_REPO_ROOT / '.github' / 'workflows' / 'backend-hermetic-e2e.yml').read_text(encoding='utf-8')
    package = json.loads((_REPO_ROOT / 'package.json').read_text(encoding='utf-8'))
    contracts = json.loads((_REPO_ROOT / 'backend' / 'testing' / 'workflow_contracts.json').read_text(encoding='utf-8'))

    assert '  listen-pusher-stack-gauntlet:' in workflow
    job = workflow.split('  listen-pusher-stack-gauntlet:\n', 1)[1]

    assert 'timeout-minutes: 20' in job
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
    assert 'npm run test:listen-pusher-stack:emulator -- --state-dir "$RUNNER_TEMP/listen-pusher-stack"' in job
    assert 'name: Show listen gauntlet backend logs on failure' in job
    assert 'if: failure()' in job
    assert 'find "$state_dir" -type f -name backend.log -print -exec tail -n 160 {} \\;' in job

    assert package['scripts']['test:listen-pusher-stack:emulator'] == 'backend/testing/listen_pusher_stack/run.sh'
    listen_contract = next(
        contract for contract in contracts['workflows'] if contract['id'] == 'listen_pusher_pipeline'
    )
    assert 'backend/testing/listen_pusher_stack/**' in listen_contract['sources']
    assert 'tests/unit/test_listen_pusher_stack_ci_wiring.py' in listen_contract['tests']

    # Static wiring tripwire only: the emulator stack proves behavior. This
    # keeps #10000's REST admission/restart scenario in the blocking command.
    runner = (_REPO_ROOT / 'backend' / 'testing' / 'listen_pusher_stack' / 'run.py').read_text(encoding='utf-8')
    task_seam = (_REPO_ROOT / 'backend' / 'testing' / 'listen_pusher_stack' / 'cloud_tasks.py').read_text(
        encoding='utf-8'
    )
    listener_entrypoint = (_REPO_ROOT / 'backend' / 'testing' / 'listen_pusher_stack' / 'listener_app.py').read_text(
        encoding='utf-8'
    )
    assert '_rest_finalization_survives_listener_restart' in runner
    assert "state_dir / 'cloud-rest-restart'" in runner
    assert "'task_already_exists'" in task_seam
    assert 'OMI_STACK_FINALIZATION_RACE_PARTIES' in listener_entrypoint


def test_backend_hermetic_gate_is_always_reported_and_fails_closed() -> None:
    workflow = (_REPO_ROOT / '.github' / 'workflows' / 'backend-hermetic-e2e.yml').read_text(encoding='utf-8')
    trigger = workflow.split('jobs:', 1)[0]

    assert "  pull_request:\n    branches: main\n" in trigger
    assert "  merge_group:\n    types: [checks_requested]\n" in trigger
    assert 'paths:' not in trigger

    assert '  scope:\n' in workflow
    scope = workflow.split('  scope:\n', 1)[1].split('\n  hermetic-e2e:\n', 1)[0]
    assert 'github.event.pull_request.base.sha' in scope
    assert 'github.event.merge_group.base_sha' in scope
    assert 'git diff --name-only "$base_sha"...HEAD' in scope
    assert "^(backend/|package\\.json$|package-lock\\.json$|\\.github/workflows/backend-hermetic-e2e\\.yml$)" in scope

    for job_name in ('hermetic-e2e', 'listen-pusher-stack-gauntlet', 'sync-cloud-tasks-stack-gauntlet'):
        job = workflow.split(f'  {job_name}:\n', 1)[1]
        assert 'needs: scope' in job
        assert "if: needs.scope.outputs.applies == 'true'" in job

    gate = workflow.split('  merge-gate:\n', 1)[1]
    assert 'name: Backend Hermetic Merge Gate' in gate
    assert 'if: ${{ always() }}' in gate
    assert 'needs: [scope, hermetic-e2e, listen-pusher-stack-gauntlet, sync-cloud-tasks-stack-gauntlet]' in gate
    assert "true) required_result='success'" in gate
    assert "false) required_result='skipped'" in gate
    for result_name in (
        'SCOPE_RESULT',
        'SCOPE_APPLIES',
        'HERMETIC_E2E_RESULT',
        'LISTEN_PUSHER_RESULT',
        'SYNC_CLOUD_TASKS_RESULT',
    ):
        assert result_name in gate
