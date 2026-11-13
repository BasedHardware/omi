"""Execute workflow-owned scope/mutation commands offline, with no cloud credentials.

Cloud Run and the third-party deploy action are stateful doubles. Traffic
preflight, binding migration, snapshot/restore, and release-vector commands use
the real control scripts; sidecar commands are recorded (their export/replace
contract has its own suite). The shell bodies and conditions come from YAML.
"""

from __future__ import annotations

import copy
import itertools
import json
import os
from pathlib import Path
import re
import subprocess
import sys

import pytest
import yaml

from scripts import backend_deploy_services as scope
from scripts import resolve_service_images as images
from scripts import verify_backend_release_vector as vector
from scripts.runtime_env_validation import manifest as runtime

ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / 'backend/scripts'
ACTION = ROOT / '.github/actions/deploy-backend-stack/action.yml'
ALL = scope.CLOUD_RUN_SERVICES
SUBSETS = [','.join(items) for n in range(1, 5) for items in itertools.combinations(ALL, n)]


@pytest.mark.parametrize(
    'raw',
    [
        ' ',
        ',',
        'backend,',
        ',backend',
        'backend,,backend-sync',
        'all',
        'backend-listen',
        'backend,backend',
        'backend-sync backend',
        'Backend',
        'backend, backend-sync',
        'backend\n',
        'backend;echo bad',
        '$(echo backend)',
    ],
)
def test_malformed_selectors_fail_closed(raw):
    with pytest.raises(ValueError):
        scope.parse_services(raw)


@pytest.mark.parametrize(
    'options',
    [
        dict(mode='build-only'),
        dict(mode='repair-traffic-only'),
        dict(mode='other'),
        dict(profile='auto-dev'),
        dict(targets='all'),
        dict(gateway='true'),
    ],
)
def test_selector_rejects_unsupported_combinations(options):
    args = dict(mode='deploy', profile='manual', targets='cloud-run-only', gateway='false')
    args.update(options)
    with pytest.raises(ValueError):
        scope.validate_scope('backend-sync', **args)


def test_service_images_cannot_escape_scope_before_registry_reads():
    with pytest.raises(ValueError, match='unselected'):
        scope.validate_scope(
            'backend',
            mode='deploy',
            profile='manual',
            targets='cloud-run-only',
            gateway='false',
            service_images='backend-sync=gcr.io/example/backend-workers@sha256:' + 'a' * 64,
        )
    with pytest.raises(images.ServiceImageError, match='unselected'):
        images.resolve(
            'backend-sync=ignored',
            project='example',
            short_sha='abcdef1',
            admitted_sha='a' * 40,
            deploy_targets='cloud-run-only',
            deploy_gateway=False,
            services=('backend',),
            inspect=lambda _: pytest.fail('must reject before inspecting any registry'),
        )


def test_blank_auto_dev_keeps_all_services():
    assert scope.validate_scope('', mode='deploy', profile='auto-dev', targets='all', gateway='false') == ALL
    assert scope.parse_services('backend-sync,backend') == ('backend', 'backend-sync')


def test_routing_mode_enables_only_read_only_lifecycle_steps():
    workflow = Workflow('backend-sync')
    workflow.values['inputs.mode'] = 'routing'
    lifecycle = yaml.safe_load((ROOT / '.github/actions/sync-backfill-lifecycle/action.yml').read_text())
    enabled = [step for step in lifecycle['runs']['steps'] if workflow.enabled(step)]
    assert [step['name'] for step in enabled] == ['Resolve ops-owned backfill queues', 'Resolve backfill service URL']
    assert all('uses' not in step for step in enabled)
    assert 'gcloud projects describe' in enabled[1]['run']
    assert 'SYNC_BACKFILL_TASKS_HANDLER_URL=' in enabled[1]['run']


class Workflow:
    """Small evaluator for the trusted YAML expressions exercised by these tests."""

    def __init__(self, raw, environment='development', profile='manual'):
        self.steps = yaml.safe_load(ACTION.read_text())['runs']['steps']
        self.values = {
            'inputs.services': raw,
            'inputs.deploy_profile': profile,
            'inputs.environment': environment,
            'inputs.runtime_env': 'prod' if environment == 'prod' else 'dev',
            'inputs.deploy_targets': 'all' if profile == 'auto-dev' else 'cloud-run-only',
            'inputs.deploy_gateway': 'false',
            'inputs.service_images': '',
            'inputs.service': 'backend',
            'inputs.project_id': 'based-hardware' if environment == 'prod' else 'based-hardware-dev',
            'inputs.region': 'us-central1',
            'inputs.admitted_sha': 'abcdef1' + '0' * 33,
            'inputs.transcription_candidate_tag': 'stt-test',
            'inputs.candidate_tag': 'candidate',
            'github.run_id': '123',
            'github.run_attempt': '1',
            'steps.image-tag.outputs.short_sha': 'abcdef1',
            'steps.image-tag.outputs.revision_suffix': 'abcdef1-123-1',
        }
        self.failed = False

    def expr(self, expression):
        expression = expression.strip()
        if expression.startswith('${{'):
            expression = expression[3:-2].strip()
        expression = re.sub(
            r'\b(?:inputs|steps|github|env|job)\.[\w.-]+', lambda m: repr(self.values.get(m[0], '')), expression
        )
        expression = expression.replace('&&', ' and ').replace('||', ' or ')
        expression = re.sub(r'!(?!=)', ' not ', expression)
        return eval(
            expression,
            {'__builtins__': {}},
            {
                'contains': lambda items, item: item in items,
                'fromJSON': json.loads,
                'join': lambda items, sep: sep.join(items),
                'format': lambda text, *args: text.format(*args),
                'success': lambda: not self.failed,
                'failure': lambda: self.failed,
                'cancelled': lambda: False,
                'always': lambda: True,
                'true': True,
                'false': False,
            },
        )

    def render(self, value):
        return re.sub(r'\$\{\{(.*?)\}\}', lambda m: str(self.expr(m[1])), str(value), flags=re.S)

    def step(self, name):
        return next(step for step in self.steps if step['name'] == name or step.get('id') == name)

    def enabled(self, step):
        return self.expr(step.get('if', '${{ success() }}'))

    def run(self, name, env, cwd):
        step = self.step(name)
        if not self.enabled(step):
            return None
        step_env = {key: self.render(value) for key, value in step.get('env', {}).items()}
        result = subprocess.run(
            ['bash', '-e', '-o', 'pipefail', '-c', self.render(step['run'])],
            env={**env, **step_env},
            cwd=cwd,
            text=True,
            capture_output=True,
            timeout=30,
        )
        assert result.returncode == 0, (name, result.stdout, result.stderr)
        return result


# A real executable double: subprocesses from the actual scripts see this gcloud.
GCLOUD = r'''
import json, os, sys
from pathlib import Path
a = sys.argv[1:]
state_path = Path(os.environ['FAKE_STATE'])
state = json.loads(state_path.read_text())
with open(os.environ['FAKE_CALLS'], 'a') as f:
    f.write(json.dumps(['gcloud', *a]) + '\n')
if a[:3] == ['run', 'services', 'describe']:
    doc = state[a[3]]
    print(doc['status']['latestCreatedRevisionName'] if 'value(status.latestCreatedRevisionName)' in ' '.join(a) else json.dumps(doc))
elif a[:3] == ['run', 'revisions', 'describe']:
    print(json.dumps({'spec': {'containers': [{'image': 'gcr.io/' + os.environ['FAKE_PROJECT'] + '/backend:abcdef1'}]},
                      'status': {'conditions': [{'type': 'Ready', 'status': 'True'}]}}))
elif a[:3] == ['run', 'services', 'update-traffic']:
    doc = state[a[3]]
    for arg in a:
        if arg.startswith('--to-revisions='):
            rev, percent = arg.split('=', 1)[1].rsplit('=', 1)
            doc['spec']['traffic'] = doc['status']['traffic'] = [{'revisionName': rev, 'percent': int(percent)}]
        elif arg.startswith('--remove-tags='):
            doc['tags'].pop(arg.split('=', 1)[1], None)
    state_path.write_text(json.dumps(state))
elif a[:3] == ['run', 'services', 'update']:
    state[a[3]]['migrated'] = True
    state_path.write_text(json.dumps(state))
elif a[:2] == ['secrets', 'describe'] or a[:3] == ['secrets', 'versions', 'list']:
    print('1')
elif a[:3] == ['secrets', 'versions', 'describe']:
    print('ENABLED')
else:
    raise SystemExit('unexpected cloud command: ' + repr(a))
'''

PYTHON = r'''
import json, os, sys
from pathlib import Path
script = Path(sys.argv[1]).name
with open(os.environ['FAKE_CALLS'], 'a') as f:
    f.write(json.dumps(['python3', script, *sys.argv[2:]]) + '\n')
if script in ('backend_deploy_services.py', 'preflight-cloud-run-deploy.py', 'cloud_run_traffic_snapshot.py',
              'verify_backend_release_vector.py'):
    os.execv(os.environ['REAL_PYTHON'], [os.environ['REAL_PYTHON'], *sys.argv[1:]])
'''


@pytest.mark.parametrize('raw', ['', *SUBSETS])
@pytest.mark.parametrize('environment', ['development', 'prod'])
def test_workflow_commands_mutate_only_selected_services_and_rollback(tmp_path, raw, environment):
    workflow = Workflow(raw, environment)
    selected = scope.parse_services(raw)
    state = {}
    for service in ALL:
        state[service] = {
            'spec': {
                'traffic': [{'revisionName': service + '-drifted', 'percent': 100}],
                'template': {
                    'spec': {
                        'timeoutSeconds': 300,
                        'containers': [
                            {
                                'image': 'old-image',
                                'env': [
                                    {
                                        'name': 'GOOGLE_CLIENT_ID',
                                        'valueFrom': {'secretKeyRef': {'name': 'GOOGLE_CLIENT_ID'}},
                                    },
                                    {'name': 'OMI_ENV_STAGE', 'value': workflow.values['inputs.runtime_env']},
                                ],
                            }
                        ],
                    }
                },
            },
            'status': {
                'traffic': [{'revisionName': service + '-old', 'percent': 100}],
                'latestReadyRevisionName': service + '-abcdef1-123-1',
                'latestCreatedRevisionName': service + '-abcdef1-123-1',
            },
            'tags': {'stt-test': service + '-old', 'stable': service + '-old'},
            'iam': {'invoker': 'unchanged'},
            'sidecar': {'image': 'old-sidecar'},
        }
    original = copy.deepcopy(state)
    state_file = tmp_path / 'state.json'
    state_file.write_text(json.dumps(state))
    calls = tmp_path / 'calls.jsonl'
    for name, body in [('gcloud', GCLOUD), ('python3', PYTHON)]:
        path = tmp_path / name
        path.write_text(f'#!{sys.executable}\n' + body)
        path.chmod(0o755)
    output = tmp_path / 'output'
    github_env = tmp_path / 'env'
    env = {
        **os.environ,
        'PATH': str(tmp_path) + os.pathsep + os.environ['PATH'],
        'REAL_PYTHON': sys.executable,
        'FAKE_STATE': str(state_file),
        'FAKE_CALLS': str(calls),
        'FAKE_PROJECT': workflow.values['inputs.project_id'],
        'GITHUB_ACTION_PATH': str(ACTION.parent),
        'GITHUB_WORKSPACE': str(ROOT),
        'DEPLOY_CONTROL_SCRIPTS': str(SCRIPTS),
        'GITHUB_OUTPUT': str(output),
        'GITHUB_ENV': str(github_env),
        'RUNNER_TEMP': str(tmp_path),
        'DEPLOY_WORKFLOW_ROOT': str(ROOT),
    }
    workflow.run('service-scope', env, tmp_path)
    for line in output.read_text().splitlines():
        key, value = line.split('=', 1)
        workflow.values['steps.service-scope.outputs.' + key] = value
    env.update(line.split('=', 1) for line in github_env.read_text().splitlines())
    assert env['BACKEND_DEPLOY_SERVICES'].split() == list(selected)

    # Native deploy actions use their real YAML conditions and exact inputs.
    deployed = set()
    for step in workflow.steps:
        if step.get('uses') == 'google-github-actions/deploy-cloudrun@v3' and workflow.enabled(step):
            service = workflow.render(step['with']['service'])
            assert step['with']['no_traffic'] is True
            assert '--revision-suffix=' in step['with']['flags']
            deployed.add(service)
    if workflow.enabled(workflow.step('sync-backfill')):
        lifecycle = yaml.safe_load((ROOT / '.github/actions/sync-backfill-lifecycle/action.yml').read_text())
        worker = next(s for s in lifecycle['runs']['steps'] if s.get('id') == 'deploy-backend-sync-backfill')
        assert worker['with']['no_traffic'] is True
        deployed.add('backend-sync-backfill')
    assert deployed == set(selected)
    assert workflow.enabled(workflow.step('sync-routing')) == (
        'backend-sync' in selected and 'backend-sync-backfill' not in selected
    )
    if raw:
        for name in (
            'Provision sync-backfill lane',
            'Configure production conversation-finalization Cloud Tasks queue',
            'Configure production batch quarantine recovery queue',
            'Deploy backend-secrets to GKE',
            'Apply non-secret backend runtime config',
        ):
            assert not workflow.enabled(workflow.step(name)), name

    # Real preflight performs traffic repair and legacy binding migration only in scope.
    workflow.run('Preflight Cloud Run deploy', env, tmp_path)
    workflow.run('Migrate legacy public Cloud Run bindings', env, tmp_path)
    workflow.run('Attach Managed Prometheus sidecar to ${{ inputs.service }} candidate', env, tmp_path)
    workflow.run('Attach Managed Prometheus to sync and integration candidates', env, tmp_path)
    workflow.run('Wait for Cloud Run revisions to become ready', env, tmp_path)
    # Give the verifier the image and environment a successful native deploy reports.
    state = json.loads(state_file.read_text())
    for service in selected:
        state[service]['spec']['template']['spec']['containers'][0][
            'image'
        ] = f"gcr.io/{workflow.values['inputs.project_id']}/backend:abcdef1"
    state_file.write_text(json.dumps(state))
    workflow.run('Validate backend runtime env after deploy', env, tmp_path)
    workflow.run('Report live Cloud Run env drift from manifest', env, tmp_path)
    workflow.run('Accept no-traffic Cloud Run candidate', env, tmp_path)
    workflow.run('Capture Cloud Run pre-promotion traffic snapshot', env, tmp_path)
    workflow.run('Verify validated revisions are still current', env, tmp_path)
    workflow.run('Shift Cloud Run traffic to validated revisions', env, tmp_path)
    workflow.run('Verify serving backend release vector', env, tmp_path)
    workflow.run('Remove passed transcription candidate tag', env, tmp_path)
    evidence = json.loads((tmp_path / 'artifacts/backend-serving-release-vector.json').read_text())
    assert set(evidence['cloud_run']) == set(selected)
    assert evidence['result'] == 'pass'
    snapshot = json.loads((tmp_path / 'artifacts/backend-cloud-run-pre-promotion-traffic-snapshot.json').read_text())
    assert set(snapshot['services']) == set(selected)

    workflow.failed = True
    workflow.values.update(
        {
            'steps.cloud-run-traffic-snapshot.outcome': 'success',
            'steps.verify-serving-release-vector.outcome': 'failure',
        }
    )
    restore = [s for s in workflow.steps if s['name'] == 'Restore Cloud Run traffic snapshot after failed promotion'][
        -1
    ]
    result = subprocess.run(
        ['bash', '-e', '-o', 'pipefail', '-c', workflow.render(restore['run'])],
        env=env,
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert workflow.enabled(restore)
    assert result.returncode == 0, result.stderr
    final = json.loads(state_file.read_text())
    for service in ALL:
        if service not in selected:
            assert final[service] == original[service]  # image/env/traffic/tags/sidecar/IAM, byte for byte
        else:
            assert final[service]['status']['traffic'] == [{'revisionName': service + '-old', 'percent': 100}]
    records = [json.loads(line) for line in calls.read_text().splitlines()]
    assert {
        args[4]
        for args in records
        if args[:3] == ['gcloud', 'run', 'services'] and args[3] in ('update', 'update-traffic')
    } == set(selected)
    for script in ('validate-backend-runtime-env.py', 'check_cloud_run_env_drift.py'):
        command = next(args for args in records if args[:2] == ['python3', script])
        assert {command[i + 1] for i, item in enumerate(command) if item == '--service'} == set(selected)
    sidecars = [args for args in records if args[:2] == ['python3', 'attach_cloud_run_gmp_sidecar.py']]
    assert {next(arg.split('=', 1)[1] for arg in args if arg.startswith('--service=')) for args in sidecars} == set(
        selected
    )


def test_live_runtime_validation_filters_only_live_scope(monkeypatch):
    seen = []

    def fetch(config):
        seen.extend(config['cloud_run']['services'])
        return {'services': {}}

    monkeypatch.setattr(runtime, '_fetch_live_cloud_run_state', fetch)
    errors = runtime.validate_runtime_env(env='dev', check_live_cloud_run=True, services=['backend-integration'])
    assert seen == ['backend-integration']
    assert any(error.scope == 'cloud_run/backend-integration' for error in errors)
    assert not any(error.scope == 'cloud_run/backend' for error in errors)


def test_subset_verifier_rejects_unselected_images_and_empty_scope():
    args = dict(
        commit_sha='a' * 40,
        deploy_run_id='1',
        deploy_run_attempt='1',
        project='test',
        region='us-central1',
        environment='dev',
    )
    for services in ([], ['backend', 'backend'], ['backend-listen']):
        with pytest.raises(ValueError):
            vector.build_expectation(**args, services=services)
    with pytest.raises(ValueError):
        vector.build_expectation(**args, services=['backend'], service_images={'backend-sync': 'test@sha256:abc'})


@pytest.mark.parametrize(
    'raw,mode,targets',
    [
        ('backend,', 'deploy', 'cloud-run-only'),
        ('backend', 'build-only', 'cloud-run-only'),
        ('backend', 'repair-traffic-only', 'cloud-run-only'),
        ('backend', 'deploy', 'all'),
    ],
)
def test_workflow_boundary_executes_rejection_for_every_lane(tmp_path, raw, mode, targets):
    document = yaml.safe_load((ROOT / '.github/workflows/gcp_backend.yml').read_text())
    steps = document['jobs']['validate-production-boundary']['steps']
    assert steps[0]['with']['ref'] == '${{ github.workflow_sha }}'
    step = next(item for item in steps if item['name'] == 'Validate service selection before side effects')
    env = {
        **os.environ,
        'SERVICES': raw,
        'WORKFLOW_MODE': mode,
        'TARGETS': targets,
        'GATEWAY': 'false',
        'SERVICE_IMAGES': '',
    }
    # Use the actual YAML command; no cloud setup is present in the validation job.
    command = step['run'].replace('python3 ', f'"{sys.executable}" ', 1)
    result = subprocess.run(
        ['bash', '-e', '-o', 'pipefail', '-c', command], env=env, cwd=ROOT, capture_output=True, text=True, timeout=10
    )
    assert result.returncode != 0
    assert 'services' in result.stderr
    assert document['jobs']['repair-traffic']['needs'] == 'validate-production-boundary'
    deploy = next(
        item
        for item in document['jobs']['deploy']['steps']
        if item.get('uses') == './.github/actions/deploy-backend-stack'
    )
    assert deploy['with']['services'] == '${{ github.event.inputs.services }}'
