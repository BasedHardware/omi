from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import subprocess
import sys

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]
WORKFLOW_PATH = ROOT / '.github/workflows/gcp_backend_auto_dev.yml'


def _load_admission_script():
    path = ROOT / '.github/scripts/verify_auto_backend_release_admission.py'
    spec = importlib.util.spec_from_file_location('verify_auto_backend_release_admission', path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _scope_job() -> dict:
    workflow = yaml.safe_load(WORKFLOW_PATH.read_text(encoding='utf-8'))
    return workflow['jobs']['scope']


def _git(repo: Path, *args: str) -> str:
    return subprocess.check_output(['git', *args], cwd=repo, text=True).strip()


def _commit(repo: Path, relative_path: str) -> str:
    path = repo / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f'{relative_path}\n', encoding='utf-8')
    _git(repo, 'add', relative_path)
    _git(repo, 'commit', '-m', f'change {relative_path}')
    return _git(repo, 'rev-parse', 'HEAD')


def _run_scope(repo: Path, sha: str) -> tuple[dict[str, str], str]:
    output = repo / 'github-output.txt'
    summary = repo / 'github-summary.md'
    scope_step = next(step for step in _scope_job()['steps'] if step.get('id') == 'scope')
    result = subprocess.run(
        ['bash', '-c', scope_step['run']],
        cwd=repo,
        check=False,
        capture_output=True,
        env={
            **os.environ,
            'RELEASE_SHA': sha,
            'GITHUB_OUTPUT': str(output),
            'GITHUB_STEP_SUMMARY': str(summary),
        },
        text=True,
    )
    assert result.returncode == 0, result.stderr
    values = dict(line.split('=', 1) for line in output.read_text(encoding='utf-8').splitlines())
    return values, summary.read_text(encoding='utf-8')


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    _git(tmp_path, 'init')
    _git(tmp_path, 'config', 'user.email', 'scope-test@example.invalid')
    _git(tmp_path, 'config', 'user.name', 'Scope Test')
    _commit(tmp_path, 'README.md')
    return tmp_path


def test_unrelated_desktop_change_exits_as_a_green_no_op(git_repo: Path) -> None:
    desktop_sha = _commit(git_repo, 'desktop/macos/README.md')

    outputs, summary = _run_scope(git_repo, desktop_sha)

    assert outputs == {'applies': 'false'}
    assert 'Green no-op' in summary


@pytest.mark.parametrize(
    'relative_path',
    ('backend/main.py', '.github/actions/sync-backfill-lifecycle/action.yml'),
)
def test_backend_source_or_deploy_input_change_proceeds(git_repo: Path, relative_path: str) -> None:
    relevant_sha = _commit(git_repo, relative_path)

    outputs, _summary = _run_scope(git_repo, relevant_sha)

    assert outputs == {'applies': 'true'}


def test_stale_relevant_sha_reaches_and_fails_the_existing_admission_guard(git_repo: Path) -> None:
    relevant_sha = _commit(git_repo, 'backend/main.py')
    outputs, _summary = _run_scope(git_repo, relevant_sha)
    admission = _load_admission_script()

    assert outputs == {'applies': 'true'}
    with pytest.raises(admission.AutomaticReleaseAdmissionError, match='still equal current main'):
        admission.validate(
            admission.AutomaticReleaseIdentity(
                sha=relevant_sha,
                main_sha='a' * 40,
                checkout_sha='a' * 40,
                run_attempt='1',
            )
        )


def test_scope_job_is_unprivileged_and_gates_admission_before_cloud_steps() -> None:
    workflow = yaml.safe_load(WORKFLOW_PATH.read_text(encoding='utf-8'))
    scope = workflow['jobs']['scope']
    readiness = workflow['jobs']['firestore_readiness']
    checkout = next(step for step in scope['steps'] if step.get('uses') == 'actions/checkout@v7')

    assert scope['permissions'] == {'contents': 'read'}
    assert 'environment' not in scope
    assert checkout['with'] == {'ref': '${{ github.event.workflow_run.head_sha }}', 'fetch-depth': 2}
    assert "needs.scope.outputs.applies == 'true'" in readiness['if']
    assert 'google-github-actions/auth' not in str(scope)
    assert 'gcloud' not in str(scope)
