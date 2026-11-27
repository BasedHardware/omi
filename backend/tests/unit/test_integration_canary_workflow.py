"""Exercise the ruled deployment boundary and actual serving-ops composition."""

from copy import deepcopy
from pathlib import Path
import json
import os
import re
import runpy
import shlex
import subprocess

import pytest
import yaml

from scripts.runtime_env_canary_ops import (
    RETIRED_BATCH_ENV,
    PROVIDER,
    QUALITY,
    SERVICES,
    SOURCE,
    RESTORED_DEFAULTS,
    compose,
)
from scripts.runtime_env_validation.cloud_run import _validate_cloud_run
from scripts.runtime_env_validation.manifest import validate_runtime_env
from scripts.runtime_env_validation import workflows as workflow_validation
from scripts.runtime_env_validation import manifest as manifest_validation

ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture(autouse=True)
def action_runner_scope(tmp_path, monkeypatch):
    # Execute snippets with the actual runner's environment-file protocol.
    monkeypatch.setenv('GITHUB_ENV', str(tmp_path / 'github-env'))
    monkeypatch.setenv('SELECTED_CLOUD_RUN_SERVICES', ' '.join(SERVICES))


def snapshot():
    return {
        'source': SOURCE,
        'services': {
            s: {
                'revision': {
                    'spec': {
                        'containers': [
                            {
                                'name': 'app',
                                'ports': [{'containerPort': 8080}],
                                'env': [
                                    {'name': 'SYNC_TASKS_QUEUE', 'value': f'{s}-fresh'},
                                    {'name': 'BATCH_PIPELINE_PERCENT', 'value': '25'},
                                    {
                                        'name': 'SYNC_JOB_SECRET',
                                        'valueFrom': {'secretKeyRef': {'name': 'ops-ref', 'key': '4'}},
                                    },
                                    *({'name': key, 'value': 'false'} for key in sorted(RETIRED_BATCH_ENV)),
                                    {'name': PROVIDER, 'value': 'false'},
                                    {'name': 'UNOWNED', 'value': 'private-live'},
                                ],
                            },
                            {'name': 'collector', 'env': [{'name': 'SYNC_TASKS_QUEUE', 'value': 'wrong-container'}]},
                        ]
                    }
                }
            }
            for s in SERVICES
        },
    }


def config():
    return {
        'cloud_run': {
            'services': {
                s: {
                    'env': {
                        'SYNC_TASKS_QUEUE': {'value': 'stale'},
                        'UNOWNED': {'value': 'source'},
                        'BATCH_PIPELINE_RETIRED': {'value': 'old'},
                    },
                    'secrets': {'SYNC_TASKS_QUEUE': {'secret': 'old', 'version': '1'}},
                    'forbidden_env': ['BATCH_PIPELINE_RETIRED'],
                }
                for s in SERVICES
            }
        }
    }


def test_integration_only_composition_preserves_every_other_service_and_live_binding():
    original, live = config(), snapshot()
    source = 'd' * 40
    live.update(source=source, profile='integration-only')
    live['services'] = {'backend-integration': live['services']['backend-integration']}
    entries = live['services']['backend-integration']['revision']['spec']['containers'][0]['env']
    entries.extend({'name': key, 'value': value} for key, value in RESTORED_DEFAULTS.items())
    before = deepcopy((original, live))
    result = compose(original, live, source)
    assert (original, live) == before
    for service in SERVICES:
        if service != 'backend-integration':
            assert result['cloud_run']['services'][service] == original['cloud_run']['services'][service]
    desired = result['cloud_run']['services']['backend-integration']
    assert desired['env']['UNOWNED']['value'] == 'private-live'
    assert desired['env']['SYNC_TASKS_QUEUE']['value'] == 'backend-integration-fresh'
    assert desired['secrets']['SYNC_JOB_SECRET'] == {'secret': 'ops-ref', 'version': '4'}
    assert set(desired['forbidden_env']) == set(RESTORED_DEFAULTS) | RETIRED_BATCH_ENV | {'BATCH_PIPELINE_RETIRED'}
    assert not (RESTORED_DEFAULTS.keys() | RETIRED_BATCH_ENV) & (set(desired['env']) | set(desired['secrets']))
    assert desired['env']['OMI_BACKEND_RELEASE_SHA']['value'] == source
    entries[-1]['value'] = '20'
    with pytest.raises(ValueError, match='saved inverse'):
        compose(original, live, source)


@pytest.mark.parametrize(
    'changed',
    [
        {},
        {'DEPLOY_TARGETS': 'all'},
        {'SKIP_ELIGIBILITY': 'true'},
        {'BREAK_GLASS_LOCK': 'true'},
        {'RELEASE_SHA': 'main'},
        {'WORKFLOW_MODE': 'build-only'},
        {'SERVICE_IMAGES': 'integration-canary=gcr.io/based-hardware/backend:latest'},
    ],
)
def test_actual_workflow_extension_boundary_binds_native_source_and_immutable_image(tmp_path, changed):
    workflow = yaml.safe_load((ROOT / '.github/workflows/gcp_backend.yml').read_text())
    script = workflow['jobs']['validate-production-boundary']['steps'][0]['run']
    script = re.sub(r'\$\{\{[^}]*\}\}', 'false', script)
    output = tmp_path / 'boundary-output'
    env = dict(
        os.environ,
        DEPLOY_ENVIRONMENT='prod',
        DEPLOY_TARGETS='cloud-run-only',
        WORKFLOW_MODE='deploy',
        REQUESTED_BY='SCA-2283',
        RELEASE_SHA='d' * 40,
        SERVICE_IMAGES='integration-canary=gcr.io/based-hardware/backend@sha256:' + 'a' * 64,
        SKIP_ELIGIBILITY='false',
        BREAK_GLASS_LOCK='false',
        GITHUB_OUTPUT=str(output),
    )
    env.update(changed)
    result = subprocess.run(['bash', '-c', script], env=env, capture_output=True, text=True, timeout=10)
    assert (result.returncode == 0) == (not changed)
    if not changed:
        assert 'integration_only=true' in output.read_text()


def test_unbound_adapter_preflight_precedes_provider_writers_and_native_repair_is_disabled():
    action = yaml.safe_load((ROOT / '.github/actions/deploy-backend-stack/action.yml').read_text())
    steps = action['runs']['steps']
    prepare = next(i for i, step in enumerate(steps) if step.get('id') == 'integration-transport-prepare')
    assert '--integration-only' in steps[prepare]['run']
    # These are the existing native writer paths, never a replacement executor.
    for step in steps:
        script = step.get('run', '')
        if '--repair-traffic' in script:
            assert 'inputs.integration_only }}" != true' in script
        if step.get('id') in {
            'deploy-backend',
            'sync-backfill',
            'shift-cloud-run-traffic',
            'configure-sync-queue',
            'deploy-backend-sync',
        }:
            assert "inputs.integration_only != 'true'" in step['if']
    recovery = next(step for step in steps if step['name'].startswith('Recover integration-only'))
    assert 'cancelled()' in recovery['if'] and 'failure()' in recovery['if']
    assert 'integration-transport-prepare.outcome' in recovery['if']


@pytest.mark.parametrize('mode', [None, 'internal', 'external', 'disabled'])
def test_actual_external_guard_selection_is_explicit_and_preserves_the_default(tmp_path, mode):
    workflow = yaml.safe_load((ROOT / '.github/workflows/gcp_backend.yml').read_text())
    script = re.sub(r'\$\{\{[^}]*\}\}', 'false', workflow['jobs']['validate-production-boundary']['steps'][0]['run'])
    image = 'gcr.io/based-hardware/backend@sha256:' + 'a' * 64
    selection = 'integration-canary=' + image + ('' if mode is None else ',post_wrap_guard=' + mode)
    output = tmp_path / 'guard-output'
    result = subprocess.run(
        ['bash', '-c', script],
        env=dict(
            os.environ,
            DEPLOY_ENVIRONMENT='prod',
            DEPLOY_TARGETS='cloud-run-only',
            WORKFLOW_MODE='deploy',
            REQUESTED_BY='SCA-2283',
            RELEASE_SHA='d' * 40,
            SERVICE_IMAGES=selection,
            SKIP_ELIGIBILITY='false',
            BREAK_GLASS_LOCK='false',
            GITHUB_OUTPUT=str(output),
        ),
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert (result.returncode == 0) == (mode != 'disabled')
    if result.returncode == 0:
        assert 'post_wrap_guard=' + (mode or 'internal') in output.read_text()
        result = subprocess.run(
            [
                'bash',
                '-c',
                step_script(
                    'Validate deploy profile boundary',
                    {
                        'inputs.integration_only': 'true',
                        'inputs.integration_image': image,
                        'inputs.admitted_sha': 'd' * 40,
                        'inputs.post_wrap_guard': mode or 'internal',
                    },
                ),
            ],
            env=dict(os.environ, SERVICE_IMAGES=selection, GITHUB_WORKSPACE=str(ROOT)),
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0, result.stderr


def test_external_guard_cannot_be_selected_without_integration_only_scope():
    result = subprocess.run(
        ['bash', '-c', step_script('Validate deploy profile boundary', {'inputs.post_wrap_guard': 'external'})],
        env=dict(os.environ, SERVICE_IMAGES='', GITHUB_WORKSPACE=str(ROOT)),
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode != 0


def test_serving_ops_fresh_queue_secret_and_dispositions_are_composed_without_mutating_inputs():
    original, live = config(), snapshot()
    before = deepcopy((original, live))
    result = compose(original, live, SOURCE)
    assert (original, live) == before
    for s in SERVICES:
        role = result['cloud_run']['services'][s]
        env = role['env']
        assert env['SYNC_TASKS_QUEUE']['value'] == f'{s}-fresh'
        assert 'SYNC_TASKS_QUEUE' not in role['secrets']
        assert env['BATCH_PIPELINE_PERCENT']['value'] == '25'
        assert role['secrets']['SYNC_JOB_SECRET'] == {'secret': 'ops-ref', 'version': '4'}
        assert env['UNOWNED']['value'] == 'source'
        assert env['OMI_BACKEND_RELEASE_SHA']['value'] == SOURCE
        assert {k: env[k]['value'] for k in QUALITY} == QUALITY
        assert env[PROVIDER]['value'] == 'false'
        assert not RETIRED_BATCH_ENV.intersection(env)
        assert not RETIRED_BATCH_ENV.intersection(role['secrets'])
        assert RETIRED_BATCH_ENV <= set(role['forbidden_env'])


def test_projection_and_firestore_read_ops_are_preserved_from_serving():
    source, live = config(), snapshot()
    values = {'PFX_SAMPLE_PERCENT': '17', 'FSR_SAMPLE_PERCENT': '23', 'FIRESTORE_READ_SAMPLE_PERCENT': '29'}
    for service in SERVICES:
        source['cloud_run']['services'][service]['env'].update({key: {'value': 'source'} for key in values})
        live['services'][service]['revision']['spec']['containers'][0]['env'].extend(
            {'name': key, 'value': value} for key, value in values.items()
        )
    actual = compose(source, live, SOURCE)
    for service in SERVICES:
        assert {key: actual['cloud_run']['services'][service]['env'][key]['value'] for key in values} == values


@pytest.mark.parametrize('outcome', ['failure', 'cancelled'])
@pytest.mark.parametrize(
    'step_id',
    [
        'shift-cloud-run-traffic',
        'verify-serving-release-vector',
        'smoke-promoted-production-serving-api',
    ],
)
def test_actual_restore_condition_recovers_cancelled_and_failed_steps(step_id, outcome):
    action = yaml.safe_load((ROOT / '.github/actions/deploy-backend-stack/action.yml').read_text())
    condition = [
        s['if']
        for s in action['runs']['steps']
        if s.get('name') == 'Restore Cloud Run traffic snapshot after failed promotion'
    ][-1]
    expression = condition.removeprefix('${{').removesuffix('}}').strip()
    expression = expression.replace("inputs.deploy_profile", repr('manual'))
    expression = expression.replace('inputs.integration_only', repr('false'))
    expression = expression.replace('failure()', str(outcome == 'failure')).replace(
        'cancelled()', str(outcome == 'cancelled')
    )

    def evaluate(snapshot_outcome, binding=''):
        states = {'cloud-run-traffic-snapshot': snapshot_outcome, step_id: outcome}
        rendered = expression.replace('inputs.selected_split_binding', repr(binding))
        rendered = re.sub(r'steps\.([a-z0-9-]+)\.outcome', lambda m: repr(states.get(m[1], 'success')), rendered)
        return eval(rendered.replace('&&', ' and ').replace('||', ' or ').replace('\n', ' '), {'__builtins__': {}})

    assert evaluate('success')
    assert not evaluate('skipped')
    assert not evaluate('success', binding='a' * 64)


@pytest.mark.parametrize('failure', ['source', 'scope', 'duplicate', 'ingress', 'secret', 'quality-conflict'])
def test_bad_snapshot_or_manifest_conflict_refuses(failure):
    source, live = config(), snapshot()
    if failure == 'source':
        live['source'] = 'a' * 40
    elif failure == 'scope':
        del live['services']['backend-sync']
    elif failure == 'duplicate':
        live['services']['backend']['revision']['spec']['containers'][0]['env'] *= 2
    elif failure == 'ingress':
        live['services']['backend']['revision']['spec']['containers'][1]['ports'] = [{'containerPort': 8081}]
    elif failure == 'secret':
        live['services']['backend']['revision']['spec']['containers'][0]['env'][2]['value'] = 'conflicting'
    else:
        source['cloud_run']['services']['backend']['forbidden_env'].append(next(iter(QUALITY)))
    with pytest.raises(ValueError):
        compose(source, live, SOURCE)


def test_workflow_keeps_native_admission_and_exact_pin_selects_canary_without_new_public_mode():
    workflow = yaml.safe_load((ROOT / '.github/workflows/gcp_backend.yml').read_text())
    assert workflow['concurrency']['cancel-in-progress'] is False
    assert 'prod-train' in workflow['concurrency']['group']
    deploy = workflow['jobs']['deploy']
    assert 'firestore_readiness' in deploy['needs']
    assert deploy['environment']
    action = next(s for s in deploy['steps'] if s.get('uses') == './.github/actions/deploy-backend-stack')
    assert SOURCE in action['with']['integration_canary']
    assert "environment == 'prod'" in action['with']['integration_canary']
    boundary = workflow['jobs']['validate-production-boundary']['steps'][0]['run']
    assert SOURCE in boundary and 'SKIP_ELIGIBILITY' in boundary and 'BREAK_GLASS_LOCK' in boundary


def test_workflow_stages_before_first_deploy_and_never_reclones_integration_after_canary():
    action = yaml.safe_load((ROOT / '.github/actions/deploy-backend-stack/action.yml').read_text())
    steps = action['runs']['steps']

    def named(name):
        return next(s for s in steps if s['name'] == name)

    prep = named('Capture ruled integration canary baseline and serving ops')
    first_deploy = next(s for s in steps if s.get('uses') == 'google-github-actions/deploy-cloudrun@v3')
    assert steps.index(prep) < steps.index(first_deploy)
    candidate = named('Create ruled integration candidate by CAS from serving configuration')
    assert 'candidate' in candidate['run'] and 'runtime-state' in candidate['run']
    normal = named('Deploy ${{ inputs.service }}-integration to Cloud Run')
    assert "integration_canary != 'true'" in normal['if']
    attach = named('Attach Managed Prometheus to sync and integration candidates')
    assert 'integration_canary' in attach['run'] and 'continue' in attach['run']
    verify = named('Accept no-traffic Cloud Run candidate')
    assert '--candidate' in verify['run'] and '--cloud-run-only' in verify['run']
    assert 'integration-canary-prepare.outputs.release_vector_args' in verify['run']
    shift = named('Shift Cloud Run traffic to validated revisions')['run']
    assert shift.index('" promote') < shift.index('--to-revisions=${{ steps.capture-backend-integration')
    assert '--state "$RUNNER_TEMP/integration-canary-private.json"' in shift
    assert 'fold' not in shift
    restore = [s for s in steps if s['name'] == 'Restore Cloud Run traffic snapshot after failed promotion'][-1]['run']
    assert ' rollback ' in restore or '" rollback' in restore
    assert '--exclude-service backend-integration' in restore


def test_snapshot_restore_exclusion_does_not_touch_integration():
    module = runpy.run_path(str(ROOT / 'backend/scripts/cloud_run_traffic_snapshot.py'))
    snap = {
        'project': 'based-hardware',
        'region': 'us-central1',
        'services': {
            s: {
                'spec': {'traffic': [{'revisionName': s + '-old', 'percent': 100}]},
                'status': {'latestReadyRevisionName': s + '-old'},
            }
            for s in SERVICES
        },
    }
    calls = []

    def fetcher(**kw):
        s = kw['service']
        calls.append(('read', s))
        return {
            'spec': {'traffic': [{'revisionName': s + '-old', 'percent': 100}]},
            'status': {'traffic': [{'revisionName': s + '-old', 'percent': 100}]},
        }

    result = module['restore_snapshot'](
        snap,
        runner=lambda cmd: calls.append(('write', cmd[4])),
        fetcher=fetcher,
        exclude_services=['backend-integration'],
    )
    assert result['result'] == 'pass'
    assert result['excluded_services'] == ['backend-integration']
    assert all(s != 'backend-integration' for _, s in calls)
    with pytest.raises(ValueError):
        module['restore_snapshot'](snap, exclude_services=['unknown'])


def step_script(name, values=None, *, index=-1):
    action = yaml.safe_load((ROOT / '.github/actions/deploy-backend-stack/action.yml').read_text())
    script = [s['run'] for s in action['runs']['steps'] if s['name'] == name][index]
    context = {
        'inputs.integration_canary': 'true',
        'inputs.integration_only': 'false',
        'inputs.integration_image': '',
        'inputs.post_wrap_guard': 'internal',
        'inputs.rollback_revision': 'backend-integration-provfix-off1114',
        'inputs.deploy_profile': 'manual',
        'inputs.environment': 'prod',
        'inputs.runtime_env': 'prod',
        'inputs.deploy_targets': 'cloud-run-only',
        'inputs.cloud_run_service': 'all',
        'inputs.deploy_gateway': 'false',
        'inputs.service': 'backend',
        'inputs.project_id': 'based-hardware',
        'inputs.region': 'us-central1',
        'inputs.admitted_sha': SOURCE,
        'steps.capture-backend-revision.outputs.revision': 'backend-new',
        'steps.capture-backend-sync-revision.outputs.revision': 'sync-new',
        'steps.sync-backfill.outputs.revision': 'backfill-new',
        'steps.capture-backend-integration-revision.outputs.revision': 'integration-new',
    }
    context.update(values or {})
    rendered = re.sub(r'\$\{\{\s*(.*?)\s*\}\}', lambda match: context[match[1]], script)
    if name == 'Validate deploy profile boundary':
        rendered = 'ROLLBACK_REVISION=' + shlex.quote(context['inputs.rollback_revision']) + '\n' + rendered
    return rendered


@pytest.mark.parametrize(
    'changed',
    [
        {'inputs.environment': 'development'},
        {'inputs.admitted_sha': 'a' * 40},
        {'inputs.project_id': 'other'},
        {'inputs.integration_canary': 'yes'},
        {'inputs.deploy_targets': 'all'},
    ],
)
def test_actual_profile_shell_refuses_unruled_scope(changed, tmp_path):
    result = subprocess.run(
        ['bash', '-c', step_script('Validate deploy profile boundary', changed)],
        env=dict(os.environ, SERVICE_IMAGES='', GITHUB_WORKSPACE=str(ROOT)),
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode != 0
    assert 'Invalid ruled integration canary boundary.' in result.stderr


def test_actual_profile_shell_accepts_ruled_normal_admission():
    result = subprocess.run(
        ['bash', '-c', step_script('Validate deploy profile boundary')],
        env=dict(os.environ, SERVICE_IMAGES='', GITHUB_WORKSPACE=str(ROOT)),
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize('canary', ['true', 'false'])
@pytest.mark.parametrize('backend_exit', [0, 1])
def test_actual_traffic_shell_routes_only_through_controller_for_ruled_source(canary, backend_exit, tmp_path):
    # Execute the actual action shell with fake transport executables. This
    # exercises branch/order and fail-fast behavior, without any provider IO.
    log = tmp_path / 'calls'
    for executable in ('gcloud', 'python3'):
        path = tmp_path / executable
        path.write_text(
            '#!/bin/sh\nprintf "%s\\n" "$0 $*" >> "$CALLS"\n'
            'case "$1" in */promote_selected_backend.py) exit "$BACKEND_EXIT";; esac\n'
        )
        path.chmod(0o700)
    result = subprocess.run(
        [
            'bash',
            '-c',
            step_script('Shift Cloud Run traffic to validated revisions', {'inputs.integration_canary': canary}),
        ],
        env=dict(
            os.environ,
            PATH=str(tmp_path) + ':' + os.environ['PATH'],
            CALLS=str(log),
            DEPLOY_CONTROL_SCRIPTS='/controls',
            RUNNER_TEMP=str(tmp_path),
            PROJECT='based-hardware',
            REGION='us-central1',
            BACKEND='backend-new',
            ADMITTED_SOURCE='a' * 40,
            WORKFLOW_CONTROL='b' * 40,
            DEPLOY_STACK_STARTED='10000',
            DEPLOY_STACK_TIMEOUT_MINUTES='90',
            BACKEND_EXIT=str(backend_exit),
        ),
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == backend_exit, result.stderr
    calls = log.read_text().splitlines()
    assert 'promote_selected_backend.py --scope all' in calls[0]
    assert '--inverse' not in calls[0]
    if backend_exit:
        assert len(calls) == 1
        return
    assert len(calls) == 4
    assert all('update-traffic ' + role in calls[i] for i, role in enumerate(SERVICES[1:3], start=1))
    if canary == 'true':
        assert 'integration_canary_controller.py promote --state' in calls[-1]
        assert not any('update-traffic backend-integration' in call for call in calls)
    else:
        assert 'update-traffic backend-integration' in calls[-1] and 'integration-new=100' in calls[-1]


@pytest.mark.parametrize('binding', ['', 'bound'])
def test_selected_production_backend_shift_uses_only_the_admitted_controller(tmp_path, binding):
    script = step_script('Shift Cloud Run traffic to validated revisions', {'inputs.cloud_run_service': 'backend'})
    log = tmp_path / 'calls'
    output = tmp_path / 'github-output'
    python = tmp_path / 'python3'
    python.write_text(
        '#!/bin/sh\n'
        'printf "%s\\n" "$*" >> "$CALLS"\n'
        """case "$1" in */cloud_run_split_canary.py) printf '%s\\n' '{"backend-new": 90}';; esac\n"""
    )
    python.chmod(0o700)
    # No test command can reach the live traffic writer.
    (tmp_path / 'gcloud').symlink_to(python)
    jq = tmp_path / 'jq'
    jq.write_text("""#!/bin/sh\nread -r result\n[ "$result" = '{"backend-new": 90}' ] && printf "90\\n"\n""")
    jq.chmod(0o700)
    result = subprocess.run(
        ['bash', '-c', script],
        env=dict(
            os.environ,
            PATH=str(tmp_path) + ':' + os.environ['PATH'],
            CALLS=str(log),
            GITHUB_OUTPUT=str(output),
            GITHUB_RUN_ID='17',
            GITHUB_RUN_ATTEMPT='1',
            RUNNER_TEMP=str(tmp_path),
            SELECTED_CLOUD_RUN_SERVICES='backend',
            DEPLOY_CONTROL_SCRIPTS='/controls',
            SERVICE='backend',
            PLAN='split-plan',
            BINDING=binding,
            PROJECT='based-hardware',
            REGION='us-central1',
            BACKEND='backend-new',
            PROMOTION_INVERSE='backend-old',
            ADMITTED_SOURCE='a' * 40,
            WORKFLOW_CONTROL='b' * 40,
            DEPLOY_STACK_STARTED='10000',
            DEPLOY_STACK_TIMEOUT_MINUTES='90',
        ),
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr
    calls = log.read_text().splitlines()
    if binding:
        assert len(calls) == 2
        assert calls[0] == '-I - /controls'
        assert calls[1].startswith(
            '/controls/cloud_run_split_canary.py promote --service backend --plan split-plan --binding bound '
            '--candidate backend-new '
        )
        assert output.read_text().splitlines() == ['promoted=true', 'serving_percent=90']
    else:
        assert len(calls) == 1
        assert calls[0].startswith('/controls/promote_selected_backend.py --scope backend --inverse backend-old ')


@pytest.mark.parametrize('shallow', ['true', 'false'])
@pytest.mark.parametrize('auto_dev', [False, True])
def test_failed_promotion_restore_checks_release_floor(tmp_path, shallow, auto_dev):
    log = tmp_path / 'calls'
    path = tmp_path / 'python3'
    path.write_text(
        '#!/bin/sh\nprintf "%s\\n" "$*" >> "$CALLS"\n'
        'case "$1" in *integration_canary_controller.py) exit 42;; esac\n'
    )
    path.chmod(0o700)
    git = tmp_path / 'git'
    git.write_text(
        '#!/bin/sh\nprintf "%s\\n" "git $*" >> "$CALLS"\n'
        'case "$1" in rev-parse) printf "%s\\n" "$SHALLOW";; fetch) exit 0;; *) exit 1;; esac\n'
    )
    git.chmod(0o700)
    script = step_script('Restore Cloud Run traffic snapshot after failed promotion', index=0 if auto_dev else -1)
    result = subprocess.run(
        ['bash', '-c', script],
        env=dict(
            os.environ,
            PATH=str(tmp_path) + ':' + os.environ['PATH'],
            CALLS=str(log),
            SHALLOW=shallow,
            DEPLOY_CONTROL_SCRIPTS='/controls',
            DEPLOY_WORKFLOW_ROOT='/workflow',
            RUNNER_TEMP=str(tmp_path),
        ),
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == (0 if auto_dev else 42)
    calls = log.read_text().splitlines()
    if not auto_dev:
        assert 'integration_canary_controller.py rollback' in calls.pop(0)
    assert len(calls) == 3
    assert calls[0] == 'git rev-parse --is-shallow-repository'
    unshallow = ' --unshallow' if shallow == 'true' else ''
    assert calls[1] == f'git fetch --no-tags{unshallow} origin +refs/heads/main:refs/remotes/origin/main'
    assert 'cloud_run_traffic_snapshot.py restore' in calls[2]
    assert ('--exclude-service backend-integration' in calls[2]) == (not auto_dev)
    assert '--release-floor-check /workflow/.github/scripts/verify_backend_release_floor.py' in calls[2]


def test_integration_prepare_unshallows_before_the_release_floor_check():
    """The floor verifier needs the rollback revision's history (review desk, 2026-11-19)."""
    prepare = next(
        step
        for step in yaml.safe_load((ROOT / '.github/actions/deploy-backend-stack/action.yml').read_text())['runs'][
            'steps'
        ]
        if step.get('id') == 'integration-transport-prepare'
    )
    script = prepare['run']
    shallow = script.index('git rev-parse --is-shallow-repository')
    fetch = script.index('git fetch --no-tags "${history_args[@]}" origin +refs/heads/main:refs/remotes/origin/main')
    floor = script.index('verify_backend_release_floor.py')
    assert shallow < fetch < floor
    assert 'history_args=(--unshallow)' in script[shallow:fetch]


def test_actual_renderer_and_native_cloud_validator_share_same_canary_composition(monkeypatch, tmp_path):
    module = runpy.run_path(str(ROOT / 'backend/scripts/render_backend_runtime_env.py'))
    base = config()
    for role in base['cloud_run']['services'].values():
        role['env'].pop('BATCH_PIPELINE_RETIRED')
    module['main'].__globals__['_load_yaml'] = lambda path: {'environments': {'prod': base}}
    snapshot_path = tmp_path / 'private.json'
    snapshot_path.write_text(json.dumps(snapshot()))
    state_path, output = tmp_path / 'state.json', tmp_path / 'output'
    monkeypatch.setenv('GITHUB_OUTPUT', str(output))
    monkeypatch.setattr(
        'sys.argv',
        [
            'render',
            '--env',
            'prod',
            '--state-output',
            str(state_path),
            '--integration-canary-state',
            str(snapshot_path),
            '--integration-canary-source',
            SOURCE,
        ],
    )
    assert module['main']() == 0
    state = json.loads(state_path.read_text())
    for s in SERVICES:
        entries = {entry['name']: entry for entry in state['services'][s]['env']}
        assert entries['SYNC_TASKS_QUEUE']['value'] == s + '-fresh'
        assert entries['OMI_BACKEND_RELEASE_SHA']['value'] == SOURCE
        assert state['services'][s]['forbidden_env']
    effective = compose(base, snapshot(), SOURCE)
    assert not _validate_cloud_run(effective, state, strict_provisional=True)


@pytest.fixture(scope='module')
def parsed_canary_validation_inputs():
    """Parse immutable repository inputs once, not once per provenance case.

    Every test still runs the complete validator. Each loader call gets its own
    copy, so the negative workflow mutation cannot contaminate another case.
    This follows the renderer suite's parsed-manifest fixture pattern without
    changing the CPU guard or replacing any validation behavior.
    """
    manifest_path = ROOT / 'backend/deploy/runtime_env.yaml'
    load = workflow_validation._load_yaml
    manifest = load(manifest_path)
    prod = manifest['environments']['prod']
    paths = {ROOT / path for path in prod['cloud_run']['workflow_files']}
    paths.update(ROOT / service['values_file'] for service in prod['gke'].values() if 'values_file' in service)
    paths.add(ROOT / 'backend/charts/llm-gateway/prod_omi_llm_gateway_values.yaml')
    paths.update((ROOT / '.github/actions').glob('*/action.yml'))
    paths.update((ROOT / '.github/actions').glob('*/action.yaml'))
    return {manifest_path: manifest, **{path: load(path) for path in paths}}


@pytest.fixture
def composed_canary_runtime(tmp_path, monkeypatch, parsed_canary_validation_inputs):
    original_load = workflow_validation._load_yaml

    def load_parsed_input(path):
        if path in parsed_canary_validation_inputs:
            return deepcopy(parsed_canary_validation_inputs[path])
        return original_load(path)

    monkeypatch.setattr(workflow_validation, '_load_yaml', load_parsed_input)
    monkeypatch.setattr(manifest_validation, '_load_yaml', load_parsed_input)
    private = tmp_path / 'private.json'
    private.write_text(json.dumps(snapshot()))
    state = tmp_path / 'state.json'
    output = tmp_path / 'github-output'
    environment = dict(
        os.environ,
        GITHUB_OUTPUT=str(output),
        CLOUD_RUN_VPC_NETWORK='omi-prod-vpc',
        CLOUD_RUN_VPC_SUBNET='omi-prod-subnet',
    )
    manifest = parsed_canary_validation_inputs[ROOT / 'backend/deploy/runtime_env.yaml']
    for job in manifest['environments']['prod']['cloud_run']['jobs'].values():
        for entry in job.get('env', {}).values():
            if isinstance(entry, dict) and entry.get('env_var'):
                environment[entry['env_var']] = str(entry.get('default', 'offline-value'))
    for service in manifest['environments']['prod']['cloud_run']['services'].values():
        for entry in service.get('env', {}).values():
            if isinstance(entry, dict) and entry.get('env_var') and not entry.get('provisional'):
                environment[entry['env_var']] = str(entry.get('default', 'offline-value'))
    result = subprocess.run(
        [
            'python3',
            str(ROOT / 'backend/scripts/render_backend_runtime_env.py'),
            '--env',
            'prod',
            '--state-output',
            str(state),
            '--integration-canary-state',
            str(private),
            '--integration-canary-source',
            SOURCE,
        ],
        env=environment,
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 0, result.stderr
    return private, state


def test_full_validator_checks_composed_state_and_bound_workflow_provenance(composed_canary_runtime):
    private, state = composed_canary_runtime
    errors = validate_runtime_env(
        env='prod',
        cloud_run_state_path=state,
        check_workflows=True,
        workflow_root=ROOT,
        integration_canary_state=private,
        integration_canary_source=SOURCE,
    )
    assert not errors, [str(e) for e in errors]


def test_full_validator_checks_selected_integration_composition_and_ignores_no_consumer_write(
    composed_canary_runtime, parsed_canary_validation_inputs
):
    private, state = composed_canary_runtime
    rendered = json.loads(state.read_text())
    selected = snapshot()
    selected.update(profile='integration-only', source='d' * 40)
    selected['services'] = {'backend-integration': selected['services']['backend-integration']}
    selected['services']['backend-integration']['revision']['spec']['containers'][0]['env'] = deepcopy(
        rendered['services']['backend-integration']['env']
    )
    # The runtime manifest now carries cadence explicitly. Replace those values
    # for this retained inverse instead of duplicating their env names.
    env = selected['services']['backend-integration']['revision']['spec']['containers'][0]['env']
    env[:] = [entry for entry in env if entry['name'] not in RESTORED_DEFAULTS]
    env.extend({'name': key, 'value': value} for key, value in RESTORED_DEFAULTS.items())
    assert len({entry['name'] for entry in env}) == len(env)
    private.write_text(json.dumps(selected))
    renderer = runpy.run_path(str(ROOT / 'backend/scripts/render_backend_runtime_env.py'))
    original = parsed_canary_validation_inputs[ROOT / 'backend/deploy/runtime_env.yaml']['environments']['prod']
    effective = compose(original, selected, selected['source'])
    # Pure renderer path for the selected service has no unresolved env vars:
    # all literals and secret bindings originate in the retained snapshot.
    selected_render = renderer['_render_cloud_run_state'](
        {'cloud_run': {'services': {'backend-integration': effective['cloud_run']['services']['backend-integration']}}}
    )
    rendered['services'] = {'backend-integration': rendered['services']['backend-integration']}
    rendered['services']['backend-integration']['env'] = selected_render['services']['backend-integration']['env']
    state.write_text(json.dumps(rendered))
    errors = validate_runtime_env(
        env='prod',
        cloud_run_state_path=state,
        check_workflows=True,
        workflow_root=ROOT,
        integration_canary_state=private,
        integration_canary_source=selected['source'],
    )
    assert not errors, [str(e) for e in errors]
    for entry in rendered['services']['backend-integration']['env']:
        if entry['name'] == 'OMI_BACKEND_RELEASE_SHA':
            entry['value'] = 'unbound'
    state.write_text(json.dumps(rendered))
    errors = validate_runtime_env(
        env='prod',
        cloud_run_state_path=state,
        integration_canary_state=private,
        integration_canary_source=selected['source'],
    )
    assert any('OMI_BACKEND_RELEASE_SHA' in str(error) for error in errors)


def test_full_canary_validator_refuses_wrong_rendered_source(composed_canary_runtime):
    private, state = composed_canary_runtime
    rendered = json.loads(state.read_text())
    for entry in rendered['services']['backend']['env']:
        if entry['name'] == 'OMI_BACKEND_RELEASE_SHA':
            entry['value'] = 'wrong-source'
    state.write_text(json.dumps(rendered))
    assert validate_runtime_env(
        env='prod',
        cloud_run_state_path=state,
        check_workflows=True,
        workflow_root=ROOT,
        integration_canary_state=private,
        integration_canary_source=SOURCE,
    )


def test_full_canary_validator_refuses_wrong_workflow_source(composed_canary_runtime, monkeypatch):
    private, state = composed_canary_runtime
    load = workflow_validation._load_yaml

    def corrupt_provenance(path):
        doc = load(path)
        if path == ROOT / '.github/actions/deploy-backend-stack/action.yml':
            for step in doc['runs']['steps']:
                values = step.get('with', {}).get('env_vars')
                if isinstance(values, str):
                    step['with']['env_vars'] = values.replace(
                        'OMI_BACKEND_RELEASE_SHA=${{ inputs.admitted_sha }}',
                        'OMI_BACKEND_RELEASE_SHA=wrong-workflow-source',
                    )
        return doc

    monkeypatch.setattr(workflow_validation, '_load_yaml', corrupt_provenance)
    errors = validate_runtime_env(
        env='prod',
        cloud_run_state_path=state,
        check_workflows=True,
        workflow_root=ROOT,
        integration_canary_state=private,
        integration_canary_source=SOURCE,
    )
    assert any('cloud_run_workflow/backend' in str(e) and 'OMI_BACKEND_RELEASE_SHA' in str(e) for e in errors)


@pytest.mark.parametrize('external', [False, True])
def test_receipt_exports_only_metadata_never_private_snapshot_or_intent_bodies(tmp_path, external):
    state = {
        'source': SOURCE,
        'image': 'gcr.io/based-hardware/backend@sha256:' + 'a' * 64,
        'phase': 'traffic_25',
        'services': {'env': 'not-for-artifacts'},
        'intent': {'kind': 'traffic_100', 'status': 'uncertain', 'before': {'env': 'not-for-artifacts'}},
        'baseline': {'end': 1800, 'share': 0.005, 'cpu_p95': 0.8, 'rows': ['not-for-artifacts']},
        'health': {'state': 'immature', 'provider_body': 'not-for-artifacts'},
        'moves': [{'percent': 25, 'verified_at': 2000, 'extra': 'not-for-artifacts'}],
    }
    if external:
        state.update(
            profile='integration-only',
            post_wrap_guard='external',
            phase='external_guard_pending',
            external_handoff={
                'revision': 'integration-receiving',
                'revision_uid': 'receiving-uid',
                'sweep_page_rows': 100,
                'tick_seconds': 20,
                'env': 'not-for-artifacts',
            },
            discovery={'state': 'external_pending', 'owner': 'SCA-2015', 'rollback_executor': 'SCA-2283'},
        )
    (tmp_path / 'integration-canary-private.json').write_text(json.dumps(state))
    result = subprocess.run(
        ['bash', '-c', step_script('Record ruled integration canary metadata receipt')],
        env=dict(os.environ, RUNNER_TEMP=str(tmp_path)),
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr
    text = (tmp_path / 'artifacts/integration-canary-receipt.json').read_text()
    assert 'not-for-artifacts' not in text + result.stdout + result.stderr
    receipt = json.loads(text)
    assert receipt['source'] == SOURCE and receipt['health']['state'] == 'immature'
    assert 'services' not in receipt and 'rows' not in receipt['baseline']
    assert receipt['intent']['status'] == 'uncertain' and 'before' not in receipt['intent']
    if external:
        assert receipt['post_wrap_guard'] == 'external'
        assert receipt['discovery']['state'] == 'external_pending'
        assert receipt['external_handoff']['revision_uid'] == 'receiving-uid'
        assert receipt['external_handoff']['sweep_page_rows'] == 100
        assert receipt['phase'] == 'external_guard_pending'


@pytest.mark.parametrize(
    'predecessor',
    [
        'backend-integration-575e695-imgonly1',
        '',
        'latest',
        'backend-sync-other',
        'backend-integration-UPPER',
        'backend-integration-' + 'x' * 50,
    ],
)
def test_actual_workflow_binds_explicit_saved_predecessor_end_to_end(tmp_path, predecessor):
    workflow = yaml.safe_load((ROOT / '.github/workflows/gcp_backend.yml').read_text())
    script = re.sub(r'\$\{\{[^}]*\}\}', 'false', workflow['jobs']['validate-production-boundary']['steps'][0]['run'])
    image = 'gcr.io/based-hardware/backend@sha256:' + 'a' * 64
    selection = f'integration-canary={image},post_wrap_guard=external,rollback_revision={predecessor}'
    output = tmp_path / 'predecessor-output'
    env = dict(
        os.environ,
        DEPLOY_ENVIRONMENT='prod',
        DEPLOY_TARGETS='cloud-run-only',
        WORKFLOW_MODE='deploy',
        REQUESTED_BY='SCA-2283',
        RELEASE_SHA='d' * 40,
        SERVICE_IMAGES=selection,
        SKIP_ELIGIBILITY='false',
        BREAK_GLASS_LOCK='false',
        GITHUB_OUTPUT=str(output),
    )
    result = subprocess.run(['bash', '-c', script], env=env, capture_output=True, text=True, timeout=10)
    valid = predecessor == 'backend-integration-575e695-imgonly1'
    assert (result.returncode == 0) == valid
    if valid:
        assert f'rollback_revision={predecessor}' in output.read_text()
        result = subprocess.run(
            [
                'bash',
                '-c',
                step_script(
                    'Validate deploy profile boundary',
                    {
                        'inputs.integration_only': 'true',
                        'inputs.integration_image': image,
                        'inputs.admitted_sha': 'd' * 40,
                        'inputs.post_wrap_guard': 'external',
                        'inputs.rollback_revision': predecessor,
                    },
                ),
            ],
            env=dict(env, GITHUB_WORKSPACE=str(ROOT)),
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0, result.stderr
        prepare = next(
            step
            for step in yaml.safe_load((ROOT / '.github/actions/deploy-backend-stack/action.yml').read_text())['runs'][
                'steps'
            ]
            if step.get('id') == 'integration-transport-prepare'
        )
        assert prepare['env']['ROLLBACK_REVISION'] == '${{ inputs.rollback_revision }}'
        assert '--rollback-revision "$ROLLBACK_REVISION"' in prepare['run']
        assert (
            workflow['jobs']['validate-production-boundary']['outputs']['rollback_revision']
            == '${{ steps.boundary.outputs.rollback_revision }}'
        )


def test_composite_rejects_predecessor_that_was_not_in_operator_selection():
    image = 'gcr.io/based-hardware/backend@sha256:' + 'a' * 64
    result = subprocess.run(
        [
            'bash',
            '-c',
            step_script(
                'Validate deploy profile boundary',
                {
                    'inputs.integration_only': 'true',
                    'inputs.integration_image': image,
                    'inputs.admitted_sha': 'd' * 40,
                    'inputs.post_wrap_guard': 'external',
                    'inputs.rollback_revision': 'backend-integration-575e695-imgonly1',
                },
            ),
        ],
        env=dict(
            os.environ,
            SERVICE_IMAGES=f'integration-canary={image},post_wrap_guard=external',
            GITHUB_WORKSPACE=str(ROOT),
        ),
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode != 0
