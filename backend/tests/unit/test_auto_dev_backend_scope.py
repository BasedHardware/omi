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
GIT_LAYOUT_PARENT_LIMIT = 3


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


def _find_git_bash(git_exec_path: Path) -> Path:
    for parent in tuple(git_exec_path.parents)[:GIT_LAYOUT_PARENT_LIMIT]:
        for relative_path in ('bin/bash.exe', 'usr/bin/bash.exe'):
            candidate = parent / relative_path
            if candidate.is_file():
                return candidate
    raise FileNotFoundError(f'Git Bash was not found above {git_exec_path}')


def _bash(*, platform_name: str | None = None, git_exec_path: Path | None = None) -> str:
    if (platform_name or os.name) != 'nt':
        return 'bash'
    return str(_find_git_bash(git_exec_path or Path(_git(ROOT, '--exec-path'))))


def _bash_path(path: Path) -> str:
    if os.name != 'nt':
        return str(path)
    return subprocess.check_output(
        [_bash(), '-c', 'cygpath -u "$1"', 'bash', path],
        text=True,
    ).strip()


def _commit(repo: Path, relative_path: str) -> str:
    path = repo / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f'{relative_path}\n', encoding='utf-8')
    _git(repo, 'add', relative_path)
    _git(repo, 'commit', '-m', f'change {relative_path}')
    return _git(repo, 'rev-parse', 'HEAD')


def _run_scope(repo: Path, sha: str, *, main_sha: str | None = None) -> tuple[dict[str, str], str]:
    output = repo / 'github-output.txt'
    summary = repo / 'github-summary.md'
    fake_bin = repo / 'fake-bin'
    fake_bin.mkdir()
    # The scope step intentionally needs two GitHub API proofs before it may
    # no-op a stale run. Model those proofs locally instead of relying on a
    # real token/network in unit tests.
    curl = fake_bin / 'curl'
    curl.write_text(
        '''#!/usr/bin/env bash
set -euo pipefail
output=''
for ((i = 1; i <= $#; i++)); do
  if [[ "${!i}" == '--output' ]]; then
    j=$((i + 1)); output="${!j}"
  fi
done
url="${!#}"
if [[ "$url" == */git/ref/heads/main ]]; then
  printf '{"ref":"refs/heads/main","object":{"type":"commit","sha":"%s"}}' "$MOCK_MAIN_SHA" > "$output"
elif [[ "$url" == */compare/* ]]; then
  status=identical
  [[ "$RELEASE_SHA" != "$MOCK_MAIN_SHA" ]] && status=behind
  printf '{"base_commit":{"sha":"%s"},"head_commit":{"sha":"%s"},"status":"%s"}' "$RELEASE_SHA" "$MOCK_MAIN_SHA" "$status" > "$output"
else
  exit 1
fi
printf '200'
''',
        encoding='utf-8',
    )
    curl.chmod(0o755)
    if os.name == 'nt':
        # Git for Windows does not ship jq, so model the two exact API
        # identities while Linux continues to exercise the real jq filters.
        jq = fake_bin / 'jq'
        jq.write_text(
            '''#!/usr/bin/env bash
set -euo pipefail
payload="$(<"${!#}")"
status=identical
[[ "$RELEASE_SHA" != "$MOCK_MAIN_SHA" ]] && status=behind
expected_ref='{"ref":"refs/heads/main","object":{"type":"commit","sha":"'"$MOCK_MAIN_SHA"'"}}'
expected_compare='{"base_commit":{"sha":"'"$RELEASE_SHA"'"},"head_commit":{"sha":"'"$MOCK_MAIN_SHA"'"},"status":"'"$status"'"}'
if [[ "$payload" == "$expected_ref" ]]; then
  printf '%s\\n' "$MOCK_MAIN_SHA"
elif [[ "$payload" == "$expected_compare" ]]; then
  printf '%s\\n' "$status"
else
  exit 1
fi
''',
            encoding='utf-8',
        )
        jq.chmod(0o755)
    scope_step = next(step for step in _scope_job()['steps'] if step.get('id') == 'scope')
    scope_script = f'export PATH="$OMI_TEST_FAKE_BIN:$PATH"\n{scope_step["run"]}'
    result = subprocess.run(
        [_bash(), '-c', scope_script],
        cwd=repo,
        check=False,
        capture_output=True,
        env={
            **os.environ,
            'OMI_TEST_FAKE_BIN': _bash_path(fake_bin),
            'GH_TOKEN': 'test-token',
            'GITHUB_REPOSITORY': 'BasedHardware/omi',
            'RELEASE_SHA': sha,
            'MOCK_MAIN_SHA': main_sha or sha,
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


def test_windows_bash_resolution_uses_the_active_git_installation(tmp_path: Path) -> None:
    git_root = tmp_path / 'Git'
    git_exec_path = git_root / 'mingw64/libexec/git-core'
    git_exec_path.mkdir(parents=True)
    git_bash = git_root / 'bin/bash.exe'
    git_bash.parent.mkdir()
    git_bash.touch()

    assert _bash(platform_name='nt', git_exec_path=git_exec_path) == str(git_bash)


def test_unrelated_desktop_change_exits_as_a_green_no_op(git_repo: Path) -> None:
    desktop_sha = _commit(git_repo, 'desktop/macos/README.md')

    outputs, summary = _run_scope(git_repo, desktop_sha, main_sha=_git(git_repo, 'rev-parse', f'{desktop_sha}^'))

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
