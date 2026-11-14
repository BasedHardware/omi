"""Execute the backend-only build/consumer contract offline (no Docker or cloud)."""

import copy
import json
import os
from pathlib import Path
import subprocess

import pytest
import yaml

from scripts import backend_deploy_services as scope
from scripts import resolve_service_images as images
from scripts import role_images
from tests.unit.test_backend_deploy_services import Workflow
from tests.unit.test_role_images import FakeRunner, _describe

ROOT = Path(__file__).resolve().parents[3]
SHA = 'a' * 40
DIGEST = 'sha256:' + 'c' * 64


@pytest.mark.parametrize(
    'mode,build_scope,valid',
    [
        ('build-only', 'backend-only', True),
        ('deploy', 'backend-only', False),
        ('repair-traffic-only', 'backend-only', False),
        ('build-only', ' ', False),
        ('build-only', '', False),
        ('build-only', 'backend-api', False),
        ('deploy', 'all', True),
        ('build-only', 'all', True),
    ],
)
def test_build_scope_boundary(mode, build_scope, valid):
    args = dict(mode=mode, build_scope=build_scope, profile='manual', targets='cloud-run-only', gateway='false')
    if valid:
        scope.validate_scope('', **args)
    else:
        with pytest.raises(ValueError):
            scope.validate_scope('', **args)


@pytest.mark.parametrize(
    'build_scope,mode,success',
    [
        ('backend-only', 'build-only', True),
        ('backend-only', 'deploy', False),
        (' ', 'build-only', False),
        ('', 'build-only', False),
        ('all', 'build-only', True),
    ],
)
def test_workflow_boundary_executes_build_scope_validation(build_scope, mode, success):
    jobs = yaml.safe_load((ROOT / '.github/workflows/gcp_backend.yml').read_text())['jobs']
    step = next(s for s in jobs['validate-production-boundary']['steps'] if s['name'].startswith('Validate service'))
    workflow = Workflow('')
    workflow.values.update({'inputs.build_scope': build_scope, 'inputs.mode': mode})
    env = {**os.environ, **{key: workflow.render(value) for key, value in step['env'].items()}}
    result = subprocess.run(['bash', '-e', '-c', step['run']], cwd=ROOT, env=env, capture_output=True, text=True)
    assert (result.returncode == 0) == success, result.stderr


def test_backend_only_build_verify_publish_and_consumer():
    args = role_images.parse_args(
        ['build', '--sha', SHA, '--registry', 'gcr.io/p', '--build-scope', 'backend-only', '--manifest', 'unused.json']
    )
    runner = FakeRunner(
        [(lambda c: c[:4] == ['gcloud', 'container', 'images', 'describe'] or c[1] == 'push', _describe(present=False))]
    )
    manifest = role_images.build(args, run=runner)
    assert [entry['name'] for entry in manifest['images']] == ['backend-api']
    build = runner.commands[0]
    assert build[build.index('--target') + 1] == 'api'
    assert 'OMI_RELEASE_SHA=' + SHA in build
    role_images.verify(manifest, run=runner)
    role_images.publish(manifest, run=runner)
    assert manifest['images'][0]['ref'] == 'gcr.io/p/backend-api@' + DIGEST
    assert [c for c in runner.commands if c[:2] == ['docker', 'push']] == [
        ['docker', 'push', 'gcr.io/p/backend-api:' + SHA[:12]]
    ]
    assert all('listen-edge' not in str(c) and 'backend/Dockerfile' not in c for c in runner.commands)
    line = role_images.service_images_line(manifest)
    assert line == 'backend=gcr.io/p/backend-api@' + DIGEST
    result = images.resolve(
        line,
        project='p',
        short_sha=SHA[:7],
        admitted_sha=SHA,
        deploy_targets='cloud-run-only',
        deploy_gateway=False,
        services=('backend',),
        inspect=lambda _: {'Labels': {'org.opencontainers.image.revision': SHA}, 'Env': ['OMI_ROLE=api']},
    )
    assert result['backend'] == manifest['images'][0]['ref']
    assert result['build_runtime_image'] == 'false'
    workflow = Workflow('backend')
    workflow.values['steps.service-images.outputs.build_runtime_image'] = result['build_runtime_image']
    for name in ('Build runtime image', 'Verify built runtime image before publish', 'Push verified runtime image'):
        assert not workflow.enabled(workflow.step(name))
    # Every legacy deployment still takes the shared build path.
    workflow.values['steps.service-images.outputs.build_runtime_image'] = 'true'
    assert workflow.enabled(workflow.step('Build runtime image'))
    bad = copy.deepcopy(manifest)
    bad['images'].append(copy.deepcopy(bad['images'][0]))
    with pytest.raises(role_images.RoleImageError, match='build scope'):
        role_images.publish(bad, run=runner)


@pytest.mark.parametrize('extra', [['--baseline'], ['--images', 'backend-api']])
def test_backend_only_rejects_other_image_controls(extra):
    args = role_images.parse_args(
        [
            'build',
            '--sha',
            SHA,
            '--registry',
            'gcr.io/p',
            '--build-scope',
            'backend-only',
            '--manifest',
            'unused.json',
            *extra,
        ]
    )
    runner = FakeRunner()
    with pytest.raises(role_images.RoleImageError):
        role_images.build(args, run=runner)
    assert not runner.commands


@pytest.mark.parametrize('build_scope,expected', [('backend-only', False), ('all', True), ('', True)])
def test_real_workflow_predicates_and_build_command(tmp_path, build_scope, expected):
    workflow = Workflow('')
    workflow.values.update(
        {
            'github.ref': 'refs/heads/main',
            'github.event.inputs.mode': 'build-only',
            'github.event.inputs.build_scope': build_scope,
            'needs.validate-production-boundary.result': 'success',
            'needs.firestore_readiness.result': 'success',
            'needs.record_break_glass.result': 'skipped',
        }
    )
    # Workflow.expr intentionally handles only trusted keys used by the composite.
    # Render workflow-level event/needs keys into the same evaluator.
    jobs = yaml.safe_load((ROOT / '.github/workflows/gcp_backend.yml').read_text())['jobs']

    def enabled(job):
        expression = jobs[job]['if']
        for key in sorted(workflow.values, key=len, reverse=True):
            expression = expression.replace(key, repr(workflow.values[key]))
        return workflow.expr(expression)

    assert enabled('build-image') == expected
    assert enabled('build-role-images')
    assert not enabled('deploy')
    assert not enabled('repair-traffic')
    for name in ('build-image', 'build-role-images'):
        assert jobs[name]['environment']
        assert jobs[name]['needs'] == ['validate-production-boundary', 'firestore_readiness', 'record_break_glass']
    step = next(s for s in jobs['build-role-images']['steps'] if s['name'].startswith('Build role images'))
    (tmp_path / '.deploy-control/backend/scripts').mkdir(parents=True)
    (tmp_path / '.deploy-control/backend/scripts/role_images.py').write_text(
        'import json,sys\nfrom pathlib import Path\nPath("args.json").write_text(json.dumps(sys.argv[1:]))\n'
    )
    bin_dir = tmp_path / 'bin'
    bin_dir.mkdir()
    git = bin_dir / 'git'
    git.write_text('#!/bin/sh\nprintf "%s\\n" "$ADMITTED_SHA"\n')
    git.chmod(0o755)
    subprocess.run(
        ['bash', '-e', '-o', 'pipefail', '-c', step['run']],
        cwd=tmp_path,
        env={
            **os.environ,
            'PATH': str(bin_dir) + os.pathsep + os.environ['PATH'],
            'ADMITTED_SHA': SHA,
            'BUILD_SCOPE': build_scope or 'all',
            'PROJECT_ID': 'p',
            'MANIFEST': 'role-images.json',
        },
        check=True,
    )
    args = json.loads((tmp_path / 'args.json').read_text())
    if build_scope == 'backend-only':
        assert args[args.index('--build-scope') + 1] == 'backend-only'
        assert '--baseline' not in args
    else:
        assert '--baseline' in args
        assert '--build-scope' not in args
