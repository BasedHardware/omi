"""Execute GKE workflow admission against real local Git histories, never cloud.

Merged pins must select the intended closure; mutable refs, unrelated commits
and mismatched listen images cannot turn an old pin into current-main code.
"""

from __future__ import annotations

import os
from pathlib import Path
import re
import shutil
import subprocess

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]
WORKFLOWS = ('gcp_backend_pusher.yml', 'gcp_backend_listen_helm.yml')
BASH = shutil.which('bash')
pytestmark = pytest.mark.usefixtures('isolated_git_env')


def git(root, *args):
    return subprocess.check_output(
        ['git', '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.test', *args],
        cwd=root,
        text=True,
        stderr=subprocess.PIPE,
        timeout=10,
    ).strip()


def step(workflow, name):
    doc = yaml.safe_load((ROOT / '.github/workflows' / workflow).read_text())
    return next(s for job in doc['jobs'].values() for s in job.get('steps', []) if s.get('name') == name)['run']


def rendered(script, environment='prod'):
    values = {
        'github.event.inputs.environment': environment,
        'github.event_name': 'workflow_dispatch',
        'vars.ENV': 'prod',
        'vars.GCP_PROJECT_ID': 'fixture-project',
    }
    return re.sub(r'\$\{\{\s*(.*?)\s*\}\}', lambda match: values[match[1]], script)


@pytest.fixture
def history(tmp_path):
    author = tmp_path / 'author'
    author.mkdir()
    git(author, 'init', '-b', 'main')
    for path in (
        'backend/scripts/verify_pusher_source_closure.py',
        'backend/pusher/Dockerfile',
        'backend/Dockerfile.roles',
    ):
        target = author / path
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / path, target)
    (author / 'backend/utils').mkdir()
    (author / 'backend/utils/closure.py').write_text('pinned\n')
    git(author, 'add', '.')
    git(author, 'commit', '-m', 'pin')
    pin = git(author, 'rev-parse', 'HEAD')
    (author / 'backend/utils/closure.py').write_text('later main\n')
    git(author, 'add', '.')
    git(author, 'commit', '-m', 'advance main closure')
    main = git(author, 'rev-parse', 'HEAD')
    remote = tmp_path / 'remote.git'
    git(tmp_path, 'clone', '--bare', str(author), str(remote))
    repo = tmp_path / 'repo'
    git(tmp_path, 'clone', str(remote), str(repo))
    return repo, pin, main


def run_admission(history, workflow, ref, *, environment='prod', expected='', mode='deploy'):
    repo, *_ = history
    envfile = repo.parent / 'env'
    output = repo.parent / 'output'
    envfile.write_text('')
    output.write_text('')
    env = {
        **os.environ,
        'DEPLOY_ENVIRONMENT': environment,
        'DEPLOY_REF': ref,
        'DEPLOY_MODE': mode,
        'EXPECTED_SHA': expected,
        'GITHUB_ENV': str(envfile),
        'GITHUB_OUTPUT': str(output),
    }
    result = subprocess.run(
        [BASH, '-c', rendered(step(workflow, 'Admit checked-out production source and image identity'), environment)],
        cwd=repo,
        env=env,
        capture_output=True,
        text=True,
        timeout=15,
    )
    return result, envfile.read_text()


@pytest.mark.parametrize('workflow', WORKFLOWS)
def test_full_merged_pin_selects_exact_tree_and_image_identity(history, workflow):
    repo, pin, main = history
    result, receipt = run_admission(history, workflow, pin, expected=pin)
    assert result.returncode == 0, result.stderr
    assert git(repo, 'rev-parse', 'HEAD') == pin != main
    assert f'CHECKED_OUT_SHA={pin}' in receipt
    assert f'IMAGE_TAG={pin[:7]}' in receipt


@pytest.mark.parametrize('workflow', WORKFLOWS)
@pytest.mark.parametrize('ref', ['feature', 'HEAD', '1234567', 'A' * 40, '0' * 40, 'f' * 40, 'main; exit 0'])
def test_invalid_or_missing_source_refuses_before_image_identity(history, workflow, ref):
    result, receipt = run_admission(history, workflow, ref)
    assert result.returncode != 0
    assert 'CHECKED_OUT_SHA=' not in receipt


@pytest.mark.parametrize('workflow', WORKFLOWS)
def test_commit_not_on_fresh_main_is_refused(history, workflow):
    repo, *_ = history
    git(repo, 'checkout', '-b', 'unmerged')
    (repo / 'unmerged').write_text('no\n')
    git(repo, 'add', '.')
    git(repo, 'commit', '-m', 'not merged')
    result, receipt = run_admission(history, workflow, git(repo, 'rev-parse', 'HEAD'))
    assert result.returncode != 0
    assert 'CHECKED_OUT_SHA=' not in receipt


@pytest.mark.parametrize('workflow', WORKFLOWS)
def test_full_sha_of_tag_object_is_not_a_commit_pin(history, workflow):
    repo, *_ = history
    git(repo, 'tag', '-a', 'annotated', '-m', 'tag object')
    result, receipt = run_admission(history, workflow, git(repo, 'rev-parse', 'annotated'))
    assert result.returncode != 0
    assert 'CHECKED_OUT_SHA=' not in receipt


@pytest.mark.parametrize('workflow', WORKFLOWS)
def test_main_default_and_development_checkout_keep_their_contract(history, workflow):
    repo, pin, main = history
    git(repo, 'checkout', '--detach', pin)
    git(repo, 'update-ref', 'refs/remotes/origin/main', pin)
    result, _ = run_admission(history, workflow, 'main')
    assert result.returncode == 0, result.stderr
    assert git(repo, 'rev-parse', 'HEAD') == main
    git(repo, 'checkout', '--detach', pin)
    result, _ = run_admission(history, workflow, 'development-branch', environment='development')
    assert result.returncode == 0, result.stderr
    assert git(repo, 'rev-parse', 'HEAD') == pin


def test_listen_expected_pin_is_still_enforced_and_rollback_stays_main_only(history):
    _, pin, main = history
    result, _ = run_admission(history, WORKFLOWS[1], pin, expected=main)
    assert result.returncode != 0
    result, _ = run_admission(history, WORKFLOWS[1], pin, mode='rollback')
    assert result.returncode != 0


@pytest.mark.parametrize('repository', ['gcr.io/based-hardware-dev/pusher', 'gcr.io/based-hardware-dev/backend-pusher'])
def test_actual_pusher_closure_qualifies_selected_pin_and_refuses_changed_tree(history, repository):
    repo, pin, main = history
    # Execute the actual extractor and comparison fragment, with no GH/cloud stage.
    script = step(WORKFLOWS[0], 'Select development-qualified Pusher digest for production')
    script = (
        script[script.index('          python3 backend/scripts/verify_pusher_source_closure.py') :]
        if '          python3 backend/scripts/' in script
        else script[script.index('python3 backend/scripts/verify_pusher_source_closure.py') :]
    )
    script = script[: script.index('          {')] if '          {' in script else script[: script.index('\n{')]
    for selected, succeeds in ((pin, True), (main, False)):
        git(repo, 'checkout', '--detach', selected)
        result = subprocess.run(
            [BASH, '-c', 'set -euo pipefail\n' + script],
            cwd=repo,
            env={
                **os.environ,
                'QUALIFICATION_DIR': str(repo.parent),
                'DEV_PUSHER_REPOSITORY': repository,
                'QUALIFIED_SOURCE_SHA': pin,
                'CHECKED_OUT_SHA': selected,
            },
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert (result.returncode == 0) == succeeds, result.stderr


@pytest.mark.parametrize('tag_kind', ['matching', 'different', 'missing', 'mutable'])
def test_listen_pin_requires_matching_image_before_cloud_read(history, tag_kind):
    repo, pin, main = history
    admitted, _ = run_admission(history, WORKFLOWS[1], pin)
    assert admitted.returncode == 0
    tags = {'matching': pin[:7], 'different': main[:7], 'missing': '', 'mutable': 'main'}
    fakebin = repo.parent / 'bin'
    fakebin.mkdir()
    calls = repo.parent / 'calls'
    for command in ('gcloud', 'kubectl'):
        executable = fakebin / command
        executable.write_text('#!/bin/sh\necho "$0 $*" >> "$CALLS"\necho gcr.io/fixture-project/backend:old\n')
        executable.chmod(0o755)
    output = repo.parent / 'env'
    script = rendered(step(WORKFLOWS[1], 'Resolve backend-listen image tag'))
    result = subprocess.run(
        [BASH, '-c', script],
        cwd=repo,
        capture_output=True,
        text=True,
        timeout=10,
        env={
            **os.environ,
            'PATH': str(fakebin) + os.pathsep + os.environ['PATH'],
            'CALLS': str(calls),
            'PINNED_GKE_SOURCE_SHA': pin,
            'CHECKED_OUT_SHA': pin,
            'REQUESTED_TAG': tags[tag_kind],
            'GITHUB_ENV': str(output),
            'GITHUB_OUTPUT': str(repo.parent / 'output'),
        },
    )
    assert (result.returncode == 0) == (tag_kind == 'matching'), result.stderr
    if tag_kind == 'matching':
        assert f'BACKEND_LISTEN_SOURCE_SHA={pin}' in output.read_text()
    else:
        assert not calls.exists()
