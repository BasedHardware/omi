"""Execute the composite actions' real cap resolver with a read-only gcloud double."""

import json
import os
from pathlib import Path
import subprocess

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture(params=[('deploy-backend-stack', 'sync', '50'), ('sync-backfill-lifecycle', 'sync-backfill', '40')])
def action(request):
    name, suffix, fallback = request.param
    steps = yaml.safe_load((ROOT / '.github/actions' / name / 'action.yml').read_text())['runs']['steps']
    resolver = next(step for step in steps if step.get('id') == 'live-max-scale')
    deploy = next(step for step in steps if step.get('id') == f'deploy-backend-{suffix}')
    assert steps.index(resolver) < steps.index(deploy)
    assert resolver['env']['CLOUD_RUN_SERVICE'] == '${{ inputs.service }}-' + suffix
    assert resolver['env']['CLOUD_RUN_PROJECT'] == '${{ inputs.project_id }}'
    assert resolver['env']['CLOUD_RUN_REGION'] == '${{ inputs.region }}'
    assert '--max-instances=${{ steps.live-max-scale.outputs.max_scale }}' in deploy['with']['flags']
    if suffix == 'sync-backfill':
        assert 'if' not in resolver  # Must also run when reconciling platform/dispatch.
        assert deploy['if'] == "${{ inputs.mode == 'worker' }}"
        assert '--max=${{ steps.live-max-scale.outputs.max_scale }}' in deploy['with']['flags']
    return resolver, 'custom-' + suffix, fallback


def resolve(tmp_path, action, *, service_cap=None, revision_cap=None, missing=False, exit_code=0, payload=None):
    resolver, service, _fallback = action
    if payload is None:
        payload = (
            []
            if missing
            else [
                {
                    'metadata': {'name': service, 'annotations': {'run.googleapis.com/maxScale': service_cap}},
                    'spec': {
                        'template': {'metadata': {'annotations': {'autoscaling.knative.dev/maxScale': revision_cap}}}
                    },
                }
            ]
        )
    (tmp_path / 'response.json').write_text(json.dumps(payload))
    executable = tmp_path / 'gcloud'
    executable.write_text(
        '#!/bin/bash\n'
        'printf "%s\\n" "$@" > "$CAP_TEST_DIR/args"\n'
        'cat "$CAP_TEST_DIR/response.json"\n'
        'exit "$CAP_TEST_EXIT"\n'
    )
    executable.chmod(0o755)
    output = tmp_path / 'output'
    env = dict(os.environ, PATH=str(tmp_path) + os.pathsep + os.environ['PATH'])
    env.update(
        CLOUD_RUN_SERVICE=service,
        CLOUD_RUN_PROJECT='test-project',
        CLOUD_RUN_REGION='us-central1',
        GITHUB_OUTPUT=str(output),
        CAP_TEST_DIR=str(tmp_path),
        CAP_TEST_EXIT=str(exit_code),
    )
    result = subprocess.run(['bash', '-c', resolver['run']], env=env, capture_output=True, text=True)
    args = (tmp_path / 'args').read_text().splitlines()
    assert args[:3] == ['run', 'services', 'list']
    assert '--project=test-project' in args
    assert '--region=us-central1' in args
    assert f'--filter=metadata.name={service}' in args
    return result, output.read_text() if output.exists() else ''


@pytest.mark.parametrize('cap', ['8', '16', '32', '80'])
def test_service_cap_wins_over_stale_revision(tmp_path, action, cap):
    result, output = resolve(tmp_path, action, service_cap=cap, revision_cap='40')
    assert result.returncode == 0, result.stderr
    assert output.splitlines()[0] == f'max_scale={cap}'


def test_legacy_revision_cap_is_preserved(tmp_path, action):
    result, output = resolve(tmp_path, action, revision_cap='73')
    assert result.returncode == 0, result.stderr
    assert output.splitlines()[0] == 'max_scale=73'


@pytest.mark.parametrize('missing', [True, False])
def test_unset_cap_uses_existing_default(tmp_path, action, missing):
    result, output = resolve(tmp_path, action, missing=missing)
    assert result.returncode == 0, result.stderr
    assert output.splitlines()[0] == f'max_scale={action[2]}'


def test_unrelated_service_does_not_supply_cap(tmp_path, action):
    payload = [{'metadata': {'name': 'other', 'annotations': {'run.googleapis.com/maxScale': '999'}}}]
    result, output = resolve(tmp_path, action, payload=payload)
    assert result.returncode == 0, result.stderr
    assert output.splitlines()[0] == f'max_scale={action[2]}'


@pytest.mark.parametrize('cap', ['', '0', '-1', '1.5', 'unlimited', '80\nmax_scale=999', 80])
def test_invalid_live_cap_stops_deploy(tmp_path, action, cap):
    result, output = resolve(tmp_path, action, service_cap=cap, revision_cap='40')
    assert result.returncode != 0
    assert output == ''


def test_lookup_failure_cannot_use_default(tmp_path, action):
    result, output = resolve(tmp_path, action, missing=True, exit_code=1)
    assert result.returncode != 0
    assert output == ''


@pytest.mark.parametrize('cap', ['500', '501', '9' * 40, '9' * 400])
def test_cap_ceiling_before_shell_arithmetic(tmp_path, action, cap):
    result, output = resolve(tmp_path, action, service_cap=cap)
    assert result.returncode == 0, result.stderr
    expected = cap if cap == '500' else action[2]
    assert output.splitlines()[0] == f'max_scale={expected}'
