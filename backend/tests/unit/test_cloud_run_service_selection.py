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


def render(script):
    values = {
        'inputs.project_id': 'based-hardware',
        'inputs.region': 'us-central1',
        'inputs.runtime_env': 'prod',
        'steps.image-tag.outputs.revision_suffix': 'aabbccd-17-1',
        'inputs.integration_canary': 'false',
        'inputs.deploy_profile': 'manual',
        'inputs.environment': 'prod',
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
        ['bash', '-c', render(step(name)['run'])],
        env=dict(
            os.environ,
            PATH=str(tmp_path) + ':' + os.environ['PATH'],
            CALLS=str(log),
            DEPLOY_CONTROL_SCRIPTS='/controls',
            SELECTED_CLOUD_RUN_SERVICES=' '.join(selected(service)),
            GMP_CANDIDATE_TAG='',
            RUNNER_TEMP=str(tmp_path),
        ),
        text=True,
        capture_output=True,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr
    calls = log.read_text().splitlines() if log.exists() else []
    expected = set(selected(service))
    if name == 'Attach Managed Prometheus to sync and integration candidates':
        expected.discard('backend')
    # Identify actual fixed service arguments, not image/secret content.
    seen = set()
    for line in calls:
        for match in re.finditer(
            r'(?:--service[= ]|--wait-revision-ready |--migrate-legacy-public-binding |update-traffic )(backend(?:-sync(?:-backfill)?|-integration)?)(?=[ =]|$)',
            line,
        ):
            seen.add(match[1])
    assert seen == expected, (calls, expected)
    if name == 'Shift Cloud Run traffic to validated revisions':
        assert len(calls) == len(expected)
        assert all('--to-revisions=' + s + '-new=100' in c for s, c in zip(selected(service), calls))


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


def test_step_census_refuses_an_unclassified_new_step():
    import hashlib

    # Every current writer and recovery/status step has been scoped explicitly.
    # A new step requires updating this census with a target-scope disposition.
    assert (
        hashlib.sha256(json.dumps([s['name'] for s in STEPS]).encode()).hexdigest()
        == "bae83f9b8e212e7fc94d0fbd57ba48b102118de4f5b79bc29a772a072863535c"
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
        SKIP_ELIGIBILITY='false',
        BREAK_GLASS_LOCK='false',
        GITHUB_OUTPUT=str(output),
    )
    env.update(extra)
    result = subprocess.run(['bash', '-c', script], env=env, text=True, capture_output=True, timeout=10)
    assert result.returncode != 0
    assert not output.exists()
