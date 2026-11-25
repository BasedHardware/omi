"""Run real composite shells against fake transports; never a production writer."""

from pathlib import Path
import json
import os
import re
import subprocess

import pytest
import yaml

from scripts.cloud_run_scope import SERVICES, selected
from scripts import verify_backend_release_vector as vector
from scripts import resolve_service_images as images

ROOT = Path(__file__).resolve().parents[3]
ACTION = yaml.safe_load((ROOT / '.github/actions/deploy-backend-stack/action.yml').read_text())
STEPS = ACTION['runs']['steps']


def step(name):
    return next(s for s in STEPS if s['name'] == name)


def render(script, *, service='all'):
    values = {
        'inputs.project_id': 'based-hardware',
        'inputs.admitted_sha': 'a' * 40,
        'inputs.region': 'us-central1',
        'inputs.runtime_env': 'prod',
        'steps.image-tag.outputs.revision_suffix': 'aabbccd-17-1',
        'inputs.integration_canary': 'false',
        'inputs.deploy_profile': 'manual',
        'inputs.environment': 'prod',
        'inputs.deploy_targets': 'cloud-run-only',
        'inputs.cloud_run_service': service,
        'inputs.deploy_gateway': 'false',
        'inputs.service': 'backend',
        'inputs.integration_only': 'false',
        'inputs.post_wrap_guard': 'internal',
        'inputs.integration_image': '',
        'steps.capture-backend-revision.outputs.revision': 'backend-new',
        'steps.capture-backend-sync-revision.outputs.revision': 'backend-sync-new',
        'steps.sync-backfill.outputs.revision': 'backend-sync-backfill-new',
        'steps.capture-backend-integration-revision.outputs.revision': 'backend-integration-new',
    }

    def sub(match):
        key = match[1].strip()
        if (
            key
            == "inputs.deploy_profile == 'auto-dev' && 'artifacts/dev-backend-cloud-run-pre-promotion-traffic-snapshot.json' || 'artifacts/backend-cloud-run-pre-promotion-traffic-snapshot.json'"
        ):
            return 'artifacts/backend-cloud-run-pre-promotion-traffic-snapshot.json'
        return values[key]

    return re.sub(r'\$\{\{(.*?)\}\}', sub, script)


@pytest.mark.parametrize('service', ['all', *SERVICES])
@pytest.mark.parametrize('stamp', ['a' * 40, 'b' * 40])
def test_created_revision_source_stamp_is_checked_only_for_selected_services(tmp_path, service, stamp):
    fake = tmp_path / 'gcloud'
    fake.write_text('''#!/usr/bin/env python3
import json, os, sys
n = sys.argv[4]
with open(os.environ['CALLS'], 'a') as out: out.write(n + '\\n')
# Real gcloud drops `spec` entirely for `spec.containers.env` on multi-container revisions.
fmt = next(a for a in sys.argv if a.startswith('--format='))
if 'spec.containers[].env' not in fmt:
    print(json.dumps({'metadata': {'name': n}}))
    sys.exit(0)
# Prod revisions run the backend container plus the telemetry collector sidecar.
print(json.dumps({'metadata': {'name': n, 'labels': {'serving.knative.dev/service': n.removesuffix('-aabbccd-17-1')}}, 'spec': {'containers': [{'env': [{'name': 'OMI_BACKEND_RELEASE_SHA', 'value': os.environ['STAMP']}]}, {}]}}))
''')
    fake.chmod(0o700)
    log = tmp_path / 'calls'
    result = subprocess.run(
        ['bash', '-c', render(step('Verify ${{ inputs.service }} release provenance')['run'])],
        env=dict(
            os.environ,
            PATH=str(tmp_path) + ':' + os.environ['PATH'],
            CALLS=str(log),
            STAMP=stamp,
            SELECTED_CLOUD_RUN_SERVICES=' '.join(selected(service)),
        ),
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert (result.returncode == 0) == (stamp == 'a' * 40), result.stderr
    seen = log.read_text().splitlines()
    assert all(n.removesuffix('-aabbccd-17-1') in selected(service) for n in seen)
    if stamp == 'a' * 40:
        assert seen == [s + '-aabbccd-17-1' for s in selected(service)]


def test_every_role_explicitly_stamps_the_admitted_source():
    for name, key in [
        ('Deploy ${{ inputs.service }} to Cloud Run', 'env_vars'),
        ('Deploy ${{ inputs.service }}-sync to Cloud Run', 'env_vars'),
        ('Deploy ${{ inputs.service }}-integration to Cloud Run', 'env_vars'),
        ('Deploy sync-backfill worker', 'backfill_env_vars'),
    ]:
        assert 'OMI_BACKEND_RELEASE_SHA=${{ inputs.admitted_sha }}' in step(name)['with'][key]


@pytest.mark.parametrize('service', ['all', *SERVICES])
@pytest.mark.parametrize(
    'name',
    [
        'Migrate legacy public Cloud Run bindings',
        'Attach Managed Prometheus to sync and integration candidates',
        'Wait for Cloud Run revisions to become ready',
        'Capture Cloud Run pre-promotion traffic snapshot',
        'Shift Cloud Run traffic to validated revisions',
    ],
)
def test_actual_shared_shell_never_targets_omitted_services(tmp_path, service, name):
    log = tmp_path / 'calls'
    fake = tmp_path / 'python3'
    fake.write_text('#!/bin/sh\nprintf "%s\\n" "$*" >> "$CALLS"\n')
    fake.chmod(0o700)
    (tmp_path / 'gcloud').symlink_to(fake)
    result = subprocess.run(
        ['bash', '-c', render(step(name)['run'], service=service)],
        env=dict(
            os.environ,
            PATH=str(tmp_path) + ':' + os.environ['PATH'],
            CALLS=str(log),
            DEPLOY_CONTROL_SCRIPTS='/controls',
            SELECTED_CLOUD_RUN_SERVICES=' '.join(selected(service)),
            CLOUD_RUN_SERVICE=service,
            ROLLBACK_REVISION=f'{service}-old',
            PROMOTION_PROJECT='based-hardware',
            PROMOTION_REGION='us-central1',
            PROMOTION_CANDIDATE='backend-new',
            PROMOTION_INVERSE='backend-old',
            PROMOTION_SOURCE='a' * 40,
            PROMOTION_CONTROL='b' * 40,
            DEPLOY_STACK_STARTED='10000',
            DEPLOY_STACK_TIMEOUT_MINUTES='90',
            GMP_CANDIDATE_TAG='',
            RUNNER_TEMP=str(tmp_path),
        ),
        text=True,
        capture_output=True,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr
    calls = log.read_text().splitlines() if log.exists() else []
    staged = name == 'Shift Cloud Run traffic to validated revisions' and service in ('backend', 'all')
    if staged:
        inverse = ' --inverse backend-old' if service == 'backend' else ''
        assert calls[0] == (
            f'/controls/promote_selected_backend.py --scope {service}{inverse} '
            '--project based-hardware --region us-central1 '
            f"--candidate backend-new --source {'a' * 40} --control {'b' * 40} "
            '--workflow-started 10000 --workflow-timeout-minutes 90 '
            '--snapshot artifacts/backend-cloud-run-pre-promotion-traffic-snapshot.json '
            '--receipt artifacts/backend-promotion-stages.json'
        )
        assert not any('update-traffic backend ' in call for call in calls)
    expected = set(selected(service))
    if name == 'Attach Managed Prometheus to sync and integration candidates':
        expected.discard('backend')
    # Identify actual fixed service arguments, not image/secret content.
    seen = {'backend'} if staged else set()
    for line in calls:
        for match in re.finditer(
            r'(?:--service[= ]|--wait-revision-ready |--migrate-legacy-public-binding |update-traffic )(backend(?:-sync(?:-backfill)?|-integration)?)(?=[ =]|$)',
            line,
        ):
            seen.add(match[1])
    assert seen == expected, (calls, expected)
    if name == 'Capture Cloud Run pre-promotion traffic snapshot':
        assert len(calls) == 1
        if service == 'all':
            assert '--expected-serving-revision' not in calls[0]
        else:
            assert f'--expected-serving-revision {service}-old' in calls[0]
    if name == 'Shift Cloud Run traffic to validated revisions':
        assert len(calls) == len(expected)
        direct_services = selected(service)[1:] if staged else selected(service)
        direct_calls = calls[1:] if staged else calls
        assert all('--to-revisions=' + s + '-new=100' in c for s, c in zip(direct_services, direct_calls))


@pytest.mark.parametrize('service', SERVICES)
def test_vector_commands_have_only_selected_revision_and_service(service):
    expected = vector.build_expectation(
        commit_sha='a' * 40,
        deploy_run_id='17',
        deploy_run_attempt='1',
        project='based-hardware',
        region='us-central1',
        environment='prod',
        cloud_run_service=service,
    )
    assert set(expected.revisions) == {service}
    commands = vector.build_read_only_commands(expected, include_listener=False, include_revision_documents=True)
    assert set(commands) == {'cloud_run/' + service, 'cloud_run_revision/' + service}
    assert commands['cloud_run/' + service][4] == service
    assert commands['cloud_run_revision/' + service][4] == expected.revisions[service]


@pytest.mark.parametrize('service', SERVICES)
def test_omitted_image_opt_in_refuses_before_registry_transport(service):
    other = next(s for s in SERVICES if s != service)
    with pytest.raises(images.ServiceImageError, match='scope mismatch'):
        images.resolve(
            other + '=untrusted',
            project='based-hardware',
            short_sha='a' * 7,
            admitted_sha='a' * 40,
            deploy_targets='cloud-run-only',
            deploy_gateway=False,
            cloud_run_service=service,
            inspect=lambda _: pytest.fail('out-of-scope image was inspected'),
        )


def test_global_lock_and_closed_default_remain_unchanged():
    workflow = yaml.safe_load((ROOT / '.github/workflows/gcp_backend.yml').read_text())
    assert workflow['concurrency'] == {
        'group': "${{ github.event.inputs.environment == 'prod' && github.event.inputs.break_glass_lock != 'true' && 'prod-train' || format('deploy-backend-stack-{0}', github.event.inputs.environment) }}",
        'cancel-in-progress': False,
    }
    assert ACTION['inputs']['cloud_run_service']['default'] == 'all'
    with pytest.raises(ValueError):
        selected('backend-listen')
    assert selected() == SERVICES


def test_production_promotion_budget_uses_the_same_timeout_as_the_runner_step():
    workflow = yaml.safe_load((ROOT / '.github/workflows/gcp_backend.yml').read_text())
    deploy = workflow['jobs']['deploy']
    start, _, stack, *_ = deploy['steps']
    assert start['id'] == 'deploy-start'
    assert 'time.monotonic()' in start['run']
    assert '&& 90 || 360' in deploy['env']['DEPLOY_STACK_TIMEOUT_MINUTES']
    assert stack['timeout-minutes'] == '${{ fromJSON(env.DEPLOY_STACK_TIMEOUT_MINUTES) }}'
    assert stack['env']['DEPLOY_STACK_STARTED'] == '${{ steps.deploy-start.outputs.monotonic }}'
    shift = step('Shift Cloud Run traffic to validated revisions')['run']
    assert '--workflow-started "$DEPLOY_STACK_STARTED"' in shift
    assert '--workflow-timeout-minutes "$DEPLOY_STACK_TIMEOUT_MINUTES"' in shift


def test_step_census_refuses_an_unclassified_new_step():
    import hashlib

    # Every current writer and recovery/status step has been scoped explicitly.
    # A new step requires updating this census with a target-scope disposition.
    # Added routing composition is local-only, sync-scoped, and exercised by the
    # actual-shell test below; it never invokes a production transport.
    # 2026-11-20 `Resolve live integration maxScale`: read-only (services list and
    # revisions describe), integration-scoped with the integration deploy's exact `if`;
    # its shell is exercised in test_cloud_run_live_caps.py.
    # `Resolve production backend memory` reads local ops config and writes only
    # step outputs. It runs for the production backend/sync deploy paths.
    # SCA-3681 removes the manual development datastore smoke from the census.
    memory = step('Resolve production backend memory')
    assert memory['if'] == (
        "${{ inputs.runtime_env == 'prod' && inputs.integration_only != 'true' && "
        "(inputs.cloud_run_service == 'all' || inputs.cloud_run_service == 'backend' || "
        "inputs.cloud_run_service == 'backend-sync') }}"
    )
    assert (
        hashlib.sha256(json.dumps([s['name'] for s in STEPS]).encode()).hexdigest()
        == "5e6374a62dc5795f042318f5f355a5ec8b27d99d535d292097f960557f05853b"
    )


@pytest.mark.parametrize('service', SERVICES)
def test_each_role_writer_requires_its_exact_scope_on_success_failure_and_cancel(service):
    role_steps = {
        'backend': ['deploy-backend', 'attach-backend-gmp-sidecar', 'capture-backend-revision'],
        'backend-sync': ['deploy-backend-sync', 'capture-backend-sync-revision'],
        'backend-sync-backfill': ['sync-backfill'],
        'backend-integration': ['deploy-backend-integration', 'capture-backend-integration-revision'],
    }
    for role, identifiers in role_steps.items():
        for ident in identifiers:
            condition = next(s['if'] for s in STEPS if s.get('id') == ident)
            # Test the real expression's closed role predicate independently of
            # success/failure/cancelled status: an omitted role can never run.
            predicate = condition[3:-2].strip().split(' && ', 1)[0]
            predicate = predicate.replace('inputs.cloud_run_service', repr(service)).replace('||', 'or')
            assert eval(predicate, {'__builtins__': {}}) == (service == role)


def test_custody_artifact_is_bound_to_the_native_serving_gate_and_contains_no_environment():
    record = step('Record verified Cloud Run selection custody')
    upload = step('Upload verified Cloud Run selection custody')
    assert (
        record['if'] == upload['if'] == "${{ success() && steps.verify-serving-release-vector.outcome == 'success' }}"
    )
    assert upload['uses'] == 'actions/upload-artifact@v7'
    assert upload['with']['path'] == 'artifacts/cloud-run-selection.json'
    assert set(record['env']) == {'ADMITTED_SOURCE', 'WORKFLOW_CONTROL', 'CLOUD_RUN_SELECTION'}
    assert record['env']['WORKFLOW_CONTROL'] == '${{ github.workflow_sha }}'


def test_named_service_does_not_reconcile_shared_dispatch_queues():
    # Dispatch reconciliation also writes the sync-jobs queue. Leave shared
    # provisioning to the retained all-service path, not an isolated worker roll.
    assert step('Provision sync-backfill lane')['if'].startswith("${{ inputs.cloud_run_service == 'all' &&")
    summary = step('Generate deployment summary')
    assert (
        summary['with']['service']
        == "${{ inputs.cloud_run_service != 'all' && inputs.cloud_run_service || inputs.service }}"
    )


@pytest.mark.parametrize(
    'extra',
    [
        {'BREAK_GLASS_LOCK': 'true'},
        {'SKIP_ELIGIBILITY': 'true'},
        {'WORKFLOW_MODE': 'build-only'},
        {'DEPLOY_ENVIRONMENT': 'development'},
    ],
)
def test_selected_workflow_refuses_lock_or_source_bypass_before_side_effects(tmp_path, extra):
    workflow = yaml.safe_load((ROOT / '.github/workflows/gcp_backend.yml').read_text())
    script = workflow['jobs']['validate-production-boundary']['steps'][0]['run']
    script = script.replace("${{ github.event.inputs.deploy_gateway }}", 'false')
    assert '${{' not in script
    output = tmp_path / 'outputs'
    env = dict(
        os.environ,
        DEPLOY_ENVIRONMENT='prod',
        DEPLOY_TARGETS='cloud-run-only',
        WORKFLOW_MODE='deploy',
        CLOUD_RUN_SERVICE='backend-sync',
        SERVICE_IMAGES='',
        REQUESTED_BY='fixture',
        RELEASE_SHA='a' * 40,
        SELECTED_ROLLBACK_REVISION='backend-sync-old',
        SKIP_ELIGIBILITY='false',
        BREAK_GLASS_LOCK='false',
        GITHUB_OUTPUT=str(output),
    )
    env.update(extra)
    result = subprocess.run(['bash', '-c', script], env=env, text=True, capture_output=True, timeout=10)
    assert result.returncode != 0
    assert not output.exists()


@pytest.mark.parametrize('service', SERVICES)
@pytest.mark.parametrize('inverse_kind', ['missing', 'wrong_service', 'admitted'])
def test_selected_workflow_binds_admitted_inverse(tmp_path, service, inverse_kind):
    inverse = dict(missing='', wrong_service='other-service-old', admitted=f'{service}-old')[inverse_kind]
    workflow = yaml.safe_load((ROOT / '.github/workflows/gcp_backend.yml').read_text())
    jobs = workflow['jobs']
    script = jobs['validate-production-boundary']['steps'][0]['run']
    script = script.replace("${{ github.event.inputs.deploy_gateway }}", 'false')
    output = tmp_path / 'outputs'
    result = subprocess.run(
        ['bash', '-c', script],
        env=dict(
            os.environ,
            DEPLOY_ENVIRONMENT='prod',
            DEPLOY_TARGETS='cloud-run-only',
            WORKFLOW_MODE='deploy',
            CLOUD_RUN_SERVICE=service,
            SERVICE_IMAGES='',
            REQUESTED_BY='selection:fixture',
            RELEASE_SHA='a' * 40,
            SKIP_ELIGIBILITY='false',
            BREAK_GLASS_LOCK='false',
            SELECTED_ROLLBACK_REVISION=inverse,
            GITHUB_OUTPUT=str(output),
        ),
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert (result.returncode == 0) == (inverse_kind == 'admitted'), result.stderr
    if result.returncode == 0:
        emitted = dict(line.split('=', 1) for line in output.read_text().splitlines())
        assert emitted['rollback_revision'] == inverse
        assert 'inputs.selected_rollback_revision' in workflow['run-name']
        assert (
            'needs.validate-production-boundary.outputs.rollback_revision'
            in next(step for step in jobs['deploy']['steps'] if step['name'] == 'Deploy backend stack')['with'][
                'rollback_revision'
            ]
        )
        boundary = subprocess.run(
            ['bash', '-c', render(step('Validate deploy profile boundary')['run'])],
            env=dict(
                os.environ,
                CLOUD_RUN_SERVICE=service,
                SERVICE_IMAGES='',
                ROLLBACK_REVISION=emitted['rollback_revision'],
                GITHUB_WORKSPACE=str(ROOT),
                GITHUB_ENV=str(tmp_path / 'runner-env'),
            ),
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert boundary.returncode == 0, boundary.stderr
    else:
        assert not output.exists()


@pytest.mark.parametrize('routing_enabled', [True, False])
@pytest.mark.parametrize('failure', ['', 'ops', 'project', 'empty-project', 'queue'])
def test_selected_sync_routing_uses_control_ops_without_backfill_writes(tmp_path, failure, routing_enabled):
    import shutil
    import sys

    lifecycle = yaml.safe_load((ROOT / '.github/actions/sync-backfill-lifecycle/action.yml').read_text())
    routing = step('Resolve selected sync routing')
    assert routing['with']['mode'] == 'routing'
    assert routing['uses'].startswith('./.deploy-workflow-source/')
    assert "inputs.cloud_run_service == 'backend-sync'" in routing['if']
    deploy = next(s for s in STEPS if s.get('id') == 'deploy-backend-sync')
    assert '${{ steps.sync-routing.outputs.sync_backfill_env_vars }}' in deploy['with']['env_vars']
    assert 'steps.sync-backfill.outputs.sync_backfill_env_vars' not in deploy['with']['env_vars']
    # Evaluate the actual helper mode gates: only its two read-only producers run.
    active = []
    for nested in lifecycle['runs']['steps']:
        condition = nested['if'][3:-2].replace('inputs.mode', repr('routing'))
        condition = condition.replace('||', 'or').replace('&&', 'and')
        condition = re.sub(r'inputs\.[a-z_]+', repr('false'), condition)
        if eval(condition, {'__builtins__': {}}):
            active.append(nested)
    assert [s['id'] for s in active] == ['ops-queues', 'backfill-service']
    controls = tmp_path / 'control' / 'scripts'
    controls.mkdir(parents=True)
    shutil.copy(ROOT / 'backend/scripts/ops_train.py', controls / 'ops_train.py')
    opsdir = controls.parent / 'deploy' / 'ops'
    opsdir.mkdir(parents=True)
    ops = yaml.safe_load((ROOT / 'backend/deploy/ops/prod.yaml').read_text())
    ops['cloud_run']['backend-sync-backfill']['env']['SYNC_BACKFILL_TASKS_QUEUE'] = 'control-current'
    if failure != 'ops':
        (opsdir / 'prod.yaml').write_text(yaml.safe_dump(ops))
    # No network/package operation in the offline probe; execute the REAL copied
    # ops renderer for every other call, against a deliberately different queue.
    python = tmp_path / 'python3'
    python.write_text(
        '#!/bin/bash\nif [[ "$1 $2" == "-m pip" ]]; then exit 0; fi\nexec ' + str(sys.executable) + ' "$@"\n'
    )
    python.chmod(0o700)
    gcloud = tmp_path / 'gcloud'
    gcloud.write_text('''#!/bin/bash
printf '%s\\n' "$*" >> "$CALLS"
if [[ "$*" == "tasks queues describe control-current --project=based-hardware --location=us-central1 --format=value(name)" ]]; then
  [[ "$FAILURE" != queue ]] || exit 3
  echo projects/based-hardware/locations/us-central1/queues/control-current
elif [[ "$*" == "projects describe based-hardware --format=value(projectNumber)" ]]; then
  [[ "$FAILURE" != project ]] || exit 3
  [[ "$FAILURE" != empty-project ]] || exit 0
  echo 123456
else exit 99; fi
''')
    gcloud.chmod(0o700)
    output = tmp_path / 'output'
    output.touch()
    calls = tmp_path / 'calls'
    env = dict(
        os.environ,
        PATH=str(tmp_path) + ':' + os.environ['PATH'],
        GITHUB_OUTPUT=str(output),
        DEPLOY_CONTROL_SCRIPTS=str(controls),
        BACKFILL_ENV='SYNC_BACKFILL_TASKS_QUEUE=manifest-retired',
        REQUIRE_EXISTING_QUEUE='true',
        SYNC_ENV='SYNC_BACKFILL_ROUTING_ENABLED=' + str(routing_enabled).lower(),
        FAILURE=failure,
        CALLS=str(calls),
    )
    result = None
    for nested in active:
        script = nested['run'].replace('${{ inputs.project_id }}', 'based-hardware')
        script = script.replace('${{ inputs.service }}', 'backend').replace('${{ inputs.region }}', 'us-central1')
        result = subprocess.run(['bash', '-c', script], env=env, capture_output=True, text=True, timeout=10)
        if result.returncode:
            break
        if nested['id'] == 'ops-queues':
            env['BACKFILL_QUEUE'] = next(
                line.split('=', 1)[1] for line in output.read_text().splitlines() if line.startswith('backfill_queue=')
            )
    should_fail = bool(failure and (failure != 'queue' or routing_enabled))
    assert (result.returncode == 0) == (not should_fail), result.stderr
    text = output.read_text()
    if should_fail:
        assert 'sync_backfill_env_vars<<' not in text
    else:
        assert 'backfill_queue=control-current\n' in text
        assert 'SYNC_BACKFILL_TASKS_QUEUE=control-current\n' in text
        assert 'manifest-retired' not in text
        url = 'https://backend-sync-backfill-123456.us-central1.run.app/v2/sync-jobs/run'
        assert f'SYNC_BACKFILL_TASKS_HANDLER_URL={url}\n' in text
        assert f'SYNC_BACKFILL_TASKS_OIDC_AUDIENCE={url}\n' in text
    observed = calls.read_text().splitlines() if calls.exists() else []
    expected = [] if failure == 'ops' else ['projects describe based-hardware --format=value(projectNumber)']
    if failure in ('', 'queue') and routing_enabled:
        expected.append(
            'tasks queues describe control-current --project=based-hardware --location=us-central1 --format=value(name)'
        )
    assert observed == expected


def test_real_sync_routing_step_composes_only_local_expectations(tmp_path):
    routing = step('Compose exact selected sync routing expectations')
    assert "inputs.cloud_run_service == 'backend-sync'" in routing['if']
    assert STEPS.index(routing) < STEPS.index(next(s for s in STEPS if s.get('id') == 'deploy-backend-sync'))
    state = {
        'services': {
            service: {
                'env': [
                    {'name': 'UNCHANGED', 'value': service},
                    {'name': 'SYNC_BACKFILL_TASKS_QUEUE', 'value': 'manifest-retired'},
                ]
            }
            for service in SERVICES
        }
    }
    path = tmp_path / 'backend-runtime-env-state.json'
    path.write_text(json.dumps(state))
    overlay = (
        'SYNC_BACKFILL_TASKS_QUEUE=control-current\n'
        'SYNC_BACKFILL_TASKS_HANDLER_URL=https://backfill.example.invalid/v2/sync-jobs/run\n'
        'SYNC_BACKFILL_TASKS_OIDC_AUDIENCE=https://backfill.example.invalid/v2/sync-jobs/run'
    )
    completed = subprocess.run(
        ['bash', '-c', routing['run']],
        env=dict(
            os.environ,
            RUNNER_TEMP=str(tmp_path),
            DEPLOY_CONTROL_SCRIPTS=str(ROOT / 'backend/scripts'),
            SYNC_ROUTING_ENV=overlay,
        ),
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert completed.returncode == 0, completed.stderr
    updated = json.loads(path.read_text())
    for name in SERVICES:
        if name != 'backend-sync':
            assert updated['services'][name] == state['services'][name]
    bindings = {e['name']: e for e in updated['services']['backend-sync']['env']}
    assert bindings['SYNC_BACKFILL_TASKS_QUEUE']['value'] == 'control-current'
    assert (tmp_path / 'sync-routing.env').read_text().strip() == overlay
    validation = step('Validate backend runtime env after deploy')['run']
    assert '--sync-routing-env-file' in validation
