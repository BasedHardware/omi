"""Wiring contract for the listen-to-pusher stack gauntlet in PR CI."""

from __future__ import annotations

import json
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]


def test_listen_pusher_stack_gauntlet_has_a_deterministic_hermetic_ci_job() -> None:
    workflow = (_REPO_ROOT / '.github' / 'workflows' / 'backend-hermetic-e2e.yml').read_text(encoding='utf-8')
    package = json.loads((_REPO_ROOT / 'package.json').read_text(encoding='utf-8'))
    contracts = json.loads((_REPO_ROOT / 'backend' / 'testing' / 'workflow_contracts.json').read_text(encoding='utf-8'))

    assert "- 'package.json'" in workflow
    assert "- 'package-lock.json'" in workflow
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
    assert 'npm run test:listen-pusher-stack:emulator' in job

    assert package['scripts']['test:listen-pusher-stack:emulator'] == 'backend/testing/listen_pusher_stack/run.sh'
    listen_contract = next(
        contract for contract in contracts['workflows'] if contract['id'] == 'listen_pusher_pipeline'
    )
    assert 'backend/testing/listen_pusher_stack/**' in listen_contract['sources']
    assert 'tests/unit/test_listen_pusher_stack_ci_wiring.py' in listen_contract['tests']
