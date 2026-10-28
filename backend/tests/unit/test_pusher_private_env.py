"""Pusher privateEnv: a protected-environment secret reaches the pusher like backend-listen's (David-approved
2026-10-28, for the MEDIA_NOISE serve digest).

Only the requested MEDIA_NOISE digest name is allowed, so private values cannot replace shared runtime controls.
The chart renders that privateEnv name exactly once, replacing a chart literal of the same name; the prod workflow
materializes PUSHER_PRIVATE_VALUES_YAML once, validates and masks it, and hands the SAME file to the isolated canary
and to the release, so the canary qualifies exactly what ships.
"""

from __future__ import annotations

from pathlib import Path
import os
import shutil
import subprocess

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]
CHART = ROOT / 'backend' / 'charts' / 'pusher'
WORKFLOW = ROOT / '.github' / 'workflows' / 'gcp_backend_pusher.yml'
DIGEST = 'sha256:' + 'a' * 64


def _render(tmp_path: Path, private_env=None) -> subprocess.CompletedProcess:
    helm = shutil.which('helm')
    if helm is None:
        pytest.skip('helm is not installed')
    argv = [helm, 'template', 'prod-omi-pusher', str(CHART), '-f', str(CHART / 'prod_omi_pusher_values.yaml')]
    if private_env is not None:
        private = tmp_path / 'private.yaml'
        private.write_text(yaml.safe_dump({'privateEnv': private_env}), encoding='utf-8')
        argv += ['-f', str(private)]
    argv += [
        '--set-string',
        'image.repository=gcr.io/test/pusher',
        '--set-string',
        f'image.digest={DIGEST}',
        '--set-string',
        'image.tag=',
        '--set-string',
        'image.pullPolicy=IfNotPresent',
    ]
    return subprocess.run(argv, capture_output=True, text=True, check=False)


def _container_env(rendered: str) -> list[dict]:
    deployment = next(d for d in yaml.safe_load_all(rendered) if isinstance(d, dict) and d.get('kind') == 'Deployment')
    container = next(c for c in deployment['spec']['template']['spec']['containers'] if c['name'] == 'pusher')
    return container.get('env') or []


def test_without_private_env_the_render_is_the_values_env(tmp_path):
    proc = _render(tmp_path)
    assert proc.returncode == 0, proc.stderr
    names = [e['name'] for e in _container_env(proc.stdout)]
    values = yaml.safe_load((CHART / 'prod_omi_pusher_values.yaml').read_text(encoding='utf-8'))
    assert names == [e['name'] for e in values.get('env') or []]


def test_private_env_adds_the_digest_once(tmp_path):
    proc = _render(tmp_path, {'MEDIA_NOISE_MODE_SERVE_UID_SHA256S': 'fixture-digest'})
    assert proc.returncode == 0, proc.stderr
    env = _container_env(proc.stdout)
    names = [e['name'] for e in env]
    assert len(names) == len(set(names))  # duplicate names break strategic-merge upgrades
    by_name = {e['name']: e for e in env}
    assert by_name['MEDIA_NOISE_MODE_SERVE_UID_SHA256S'] == {
        'name': 'MEDIA_NOISE_MODE_SERVE_UID_SHA256S',
        'value': 'fixture-digest',
    }


@pytest.mark.parametrize('name', ['BATCH_PIPELINE_PERCENT', 'GOOGLE_CLOUD_PROJECT', 'UNRELATED_SETTING'])
def test_private_env_cannot_override_shared_runtime_or_unrelated_settings(tmp_path, name):
    proc = _render(tmp_path, {name: '100'})
    assert proc.returncode != 0
    assert 'allows only MEDIA_NOISE_MODE_SERVE_UID_SHA256S' in proc.stderr


@pytest.mark.parametrize('private_env', [{'lower_case': 'x'}, {'1BAD': 'x'}, {'MEDIA_NOISE_MODE_SERVE_UID_SHA256S': 3}])
def test_private_env_rejects_bad_names_and_non_strings(tmp_path, private_env):
    proc = _render(tmp_path, private_env)
    assert proc.returncode != 0
    assert 'privateEnv' in proc.stderr


def test_prod_workflow_materializes_once_and_canary_and_release_take_the_same_file():
    text = WORKFLOW.read_text(encoding='utf-8')
    steps = yaml.safe_load(text)['jobs']['deploy']['steps']
    names = [s.get('name') for s in steps]
    materialize = names.index('Materialize private pusher values (prod only)')
    canary = names.index('Create isolated production Pusher and listener canary')
    release = names.index('Deploy Pusher to GKE cluster using Helm')
    cleanup = names.index('Remove private pusher values file')
    assert materialize < canary < release < cleanup
    step = steps[materialize]
    assert step['if'] == "env.SERVICE == 'pusher' && github.event.inputs.environment == 'prod'"
    assert step['env'] == {'PUSHER_PRIVATE_VALUES_YAML': '${{ secrets.PUSHER_PRIVATE_VALUES_YAML }}'}
    # the secret appears nowhere else in the workflow
    assert text.count('secrets.PUSHER_PRIVATE_VALUES_YAML') == 1
    run = step['run']
    assert 'umask 077' in run and 'unset PUSHER_PRIVATE_VALUES_YAML' in run
    assert run.index('PUSHER_PRIVATE_VALUES_FILE=') < run.index('listen_helm_env_overrides.py')  # cleanup-able first
    assert '--private-values-file' in run and 'set -x' not in run and 'cat ' not in run
    for index in (canary, release):
        assert '"${private_values[@]}"' in steps[index]['run'], names[index]
        assert 'private_values=(-f "$PUSHER_PRIVATE_VALUES_FILE")' in steps[index]['run'], names[index]
    assert steps[cleanup]['if'] == "${{ always() && env.PUSHER_PRIVATE_VALUES_FILE != '' }}"
    assert steps[cleanup]['run'] == 'rm -f "$PUSHER_PRIVATE_VALUES_FILE"'


def test_dependency_installer_child_cannot_observe_private_values(tmp_path):
    steps = yaml.safe_load(WORKFLOW.read_text())['jobs']['deploy']['steps']
    materialize = next(s for s in steps if s.get('name') == 'Materialize private pusher values (prod only)')
    install = next(line.strip() for line in materialize['run'].splitlines() if 'pip install' in line)
    child = tmp_path / 'python3'
    child.write_text('#!/bin/bash\n[[ -z "${PUSHER_PRIVATE_VALUES_YAML+x}" ]]\n')
    child.chmod(0o755)
    env = dict(
        os.environ,
        PATH=str(tmp_path) + os.pathsep + os.environ['PATH'],
        PUSHER_PRIVATE_VALUES_YAML='synthetic-private-fixture',
    )
    actual = subprocess.run(['bash', '-c', install], env=env, capture_output=True)
    assert actual.returncode == 0
    # Red-check the precise unsafe form: the installer inherits the secret without env -u.
    unsafe = subprocess.run(['bash', '-c', 'python3 -m pip install -q pyyaml'], env=env, capture_output=True)
    assert unsafe.returncode != 0
