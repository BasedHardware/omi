"""Execute the omitted-service boundaries without credentials or provider writes."""

from copy import deepcopy
import os
from pathlib import Path
import re
import subprocess

import pytest
import yaml

from scripts import resolve_service_images as resolver
from scripts import verify_backend_release_vector as vector
from scripts.runtime_env_validation import manifest
from scripts import verify_omitted_integration as omitted

ROOT = Path(__file__).resolve().parents[3]
ACTION = ROOT / '.github/actions/deploy-backend-stack/action.yml'
CONSUMERS = ('backend', 'backend-sync', 'backend-sync-backfill')
INTEGRATION = 'backend-integration'
SHA = 'a' * 40


@pytest.fixture(scope='module')
def steps():
    return yaml.safe_load(ACTION.read_text())['runs']['steps']


def step(steps, name):
    return next(s for s in steps if s['name'] == name)


def render(script, scope):
    def value(match):
        expr = match.group(1).strip()
        if expr.startswith('inputs.'):
            key = expr[7:]
            return {
                'cloud_run_scope': scope,
                'integration_canary': 'false',
                'project_id': 'based-hardware',
                'region': 'us-central1',
                'runtime_env': 'prod',
                'deploy_profile': 'manual',
            }[key]
        if expr.startswith('steps.') and expr.endswith('.outputs.revision'):
            key = expr.split('.')[1]
            return {
                'capture-backend-revision': 'backend-new',
                'capture-backend-sync-revision': 'backend-sync-new',
                'sync-backfill': 'backend-sync-backfill-new',
                'capture-backend-integration-revision': 'integration-new',
            }[key]
        raise AssertionError(f'unhandled workflow expression: {expr}')

    return re.sub(r'\$\{\{(.*?)\}\}', value, script)


@pytest.mark.parametrize('scope', ['all', 'consumers'])
def test_actual_promotion_shell_mutates_exactly_the_selected_services(steps, tmp_path, scope):
    log = tmp_path / 'calls'
    fake = tmp_path / 'gcloud'
    fake.write_text('#!/bin/bash\nprintf "%s\\n" "$*" >> "$CALL_LOG"\n')
    fake.chmod(0o755)
    result = subprocess.run(
        ['bash', '-c', render(step(steps, 'Shift Cloud Run traffic to validated revisions')['run'], scope)],
        env={**os.environ, 'PATH': f'{tmp_path}:{os.environ["PATH"]}', 'CALL_LOG': str(log)},
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert result.returncode == 0, result.stderr
    calls = log.read_text().splitlines()
    assert [line.split()[3] for line in calls] == list(CONSUMERS) + ([INTEGRATION] if scope == 'all' else [])
    assert all('--to-revisions=' in line and '=100' in line for line in calls)


def test_excluded_integration_has_no_deploy_or_candidate_or_sidecar_writer(steps):
    deploy = step(steps, 'Deploy ${{ inputs.service }}-integration to Cloud Run')
    assert "inputs.cloud_run_scope == 'all'" in deploy['if']
    candidate = step(steps, 'Create ruled integration candidate by CAS from serving configuration')
    assert candidate['if'] == "${{ inputs.integration_canary == 'true' }}"
    boundary = step(steps, 'Validate deploy profile boundary')['run']
    assert '"${{ inputs.integration_canary }}" == false' in boundary
    assert '"${{ inputs.deploy_targets }}" == cloud-run-only' in boundary
    sidecar = step(steps, 'Attach Managed Prometheus to sync and integration candidates')['run']
    assert '"${{ inputs.cloud_run_scope }}" == consumers) ]]; then continue; fi' in sidecar
    migration = step(steps, 'Migrate legacy public Cloud Run bindings')['run']
    assert "inputs.cloud_run_scope == 'all' && '--migrate-legacy-public-binding backend-integration'" in migration


def test_failure_restore_snapshot_excludes_integration_and_does_not_delete_it(steps):
    capture = step(steps, 'Capture Cloud Run pre-promotion traffic snapshot')['run']
    assert "inputs.cloud_run_scope == 'all' && '--service backend-integration'" in capture
    restore = [s for s in steps if s['name'] == 'Restore Cloud Run traffic snapshot after failed promotion'][-1]
    assert '--delete-missing' not in restore['run']
    from scripts import cloud_run_traffic_snapshot as traffic

    snapshot = {
        'schema_version': 1,
        'project': 'based-hardware',
        'region': 'us-central1',
        'services': {s: {'spec': {'traffic': [{'revisionName': s + '-old', 'percent': 100}]}} for s in CONSUMERS},
        'missing_services': [],
    }
    # The real restore writes only snapshot members, even on a failed rollout.
    calls = []
    live = {
        s: {
            'spec': {'traffic': [{'revisionName': s + '-old', 'percent': 100}]},
            'status': {'traffic': [{'revisionName': s + '-old', 'percent': 100}]},
        }
        for s in CONSUMERS
    }
    # A rollback-eligible integration has unrelated template and serving values;
    # neither is fetched or changed by the actual restore transport.
    live[INTEGRATION] = {
        'template': {'page_rows': 200, 'tick_seconds': 10},
        'traffic': {'backend-integration-provfix-off1114': 100},
    }
    retained = deepcopy(live[INTEGRATION])
    result = traffic.restore_snapshot(
        snapshot, runner=lambda command: calls.append(command), fetcher=lambda **kw: live[kw['service']]
    )
    assert result['result'] == 'pass'
    assert [command[4] for command in calls] == list(CONSUMERS)
    assert live[INTEGRATION] == retained


def expectation(scope='consumers'):
    return vector.build_expectation(
        commit_sha=SHA,
        deploy_run_id='12',
        deploy_run_attempt='1',
        project='based-hardware',
        region='us-central1',
        environment='prod',
        cloud_run_scope=scope,
    )


def test_selected_vector_retains_readiness_identity_image_and_traffic_failures():
    expected = expectation()
    commands = vector.build_read_only_commands(expected, include_listener=False, include_revision_documents=True)
    assert len(commands) == 6
    assert not any(INTEGRATION in key for key in commands)
    documents = {}
    for service, revision in expected.revisions.items():
        documents[f'cloud_run/{service}'] = {
            'spec': {
                'template': {
                    'spec': {
                        'timeoutSeconds': 300,
                        'containers': [{'image': expected.image, 'env': [{'name': 'OMI_ENV_STAGE', 'value': 'prod'}]}],
                    }
                }
            },
            'status': {
                'latestCreatedRevisionName': revision,
                'latestReadyRevisionName': revision,
                'traffic': [{'revisionName': revision, 'percent': 100}],
            },
        }
        documents[f'cloud_run_revision/{service}'] = {
            'spec': {'containers': [{'image': expected.image}]},
            'status': {'conditions': [{'type': 'Ready', 'status': 'True'}]},
        }
    assert not vector.evaluate(expected, documents, include_listener=False)
    receipt = vector.evidence(expected, documents, [], include_listener=False)
    assert set(receipt['cloud_run']) == set(CONSUMERS)
    for key, mutation in [
        ('cloud_run/backend', lambda d: d['status']['traffic'][0].update(percent=25)),
        ('cloud_run/backend', lambda d: d['status'].update(latestCreatedRevisionName='other')),
        ('cloud_run/backend', lambda d: d['spec']['template']['spec']['containers'][0].update(image='wrong')),
    ]:
        bad = deepcopy(documents)
        mutation(bad[key])
        assert vector.evaluate(expected, bad, include_listener=False)
    candidate = deepcopy(documents)
    for service in CONSUMERS:
        candidate[f'cloud_run/{service}']['status']['traffic'] = []
    assert not vector.evaluate(expected, candidate, include_listener=False, require_serving_traffic=False)
    candidate['cloud_run_revision/backend']['status']['conditions'][0]['status'] = 'False'
    assert vector.evaluate(expected, candidate, include_listener=False, require_serving_traffic=False)


@pytest.mark.parametrize('scope', ['', 'backend', 'integration', 'ALL', 'consumers,all'])
def test_unknown_or_partial_scope_refuses(scope):
    with pytest.raises(ValueError):
        expectation(scope)


def test_scope_does_not_infer_keep_current_from_role_image_pairs():
    args = dict(
        project='based-hardware',
        short_sha='aaaaaaa',
        admitted_sha=SHA,
        deploy_targets='cloud-run-only',
        deploy_gateway=False,
    )
    selected = resolver.resolve('scope=consumers', cloud_run_scope='consumers', **args)
    assert INTEGRATION.replace('-', '_') not in selected
    assert selected['backend'] == 'gcr.io/based-hardware/backend:aaaaaaa'
    assert resolver.resolve('', **args)['backend_integration'].endswith(':aaaaaaa')
    with pytest.raises(resolver.ServiceImageError, match='excluded|consumer'):
        resolver.resolve(
            'scope=consumers ' + INTEGRATION + '=gcr.io/based-hardware/backend-workers@sha256:' + 'b' * 64,
            cloud_run_scope='consumers',
            **args,
        )


def test_live_env_scope_is_narrow_and_static_checks_are_not_removed(steps):
    validator = step(steps, 'Validate backend runtime env after deploy')['run']
    assert '--check-workflows' in validator and '--check-live-cloud-run ${CLOUD_RUN_SCOPE_ARGS:-}' in validator
    before = step(steps, 'Validate backend runtime env before deploy')['run']
    assert '--check-workflows' in before and 'CLOUD_RUN_SCOPE_ARGS' not in before
    assert (
        manifest.validate_runtime_env(env='dev', cloud_run_scope='consumers')[0].message
        == 'invalid Cloud Run validation scope'
    )
    assert (
        manifest.validate_runtime_env(env='prod', cloud_run_scope='unknown')[0].message
        == 'invalid Cloud Run validation scope'
    )


def omitted_service():
    return {
        'metadata': {'name': INTEGRATION, 'uid': 'stable-uid', 'resourceVersion': '45'},
        'spec': {
            'template': {
                'spec': {
                    'containers': [
                        {
                            'image': 'old-image',
                            'env': [
                                {'name': 'BATCH_PIPELINE_SERVING_SWEEP_PAGE_ROWS', 'value': '200'},
                                {'name': 'BATCH_PIPELINE_SERVING_TICK_SECONDS', 'value': '10'},
                            ],
                        }
                    ]
                }
            },
            'traffic': [{'revisionName': 'backend-integration-provfix-off1114', 'percent': 100}],
        },
        'status': {
            'latestReadyRevisionName': 'backend-integration-provfix-off1114',
            'latestCreatedRevisionName': 'previous-failed-template',
            'conditions': [{'type': 'Ready', 'status': 'False'}],
            'traffic': [{'revisionName': 'backend-integration-provfix-off1114', 'percent': 100}],
        },
    }


@pytest.mark.parametrize(
    'mutate',
    [
        lambda d: d['metadata'].update(resourceVersion='46'),
        lambda d: d['metadata'].update(uid='replacement'),
        lambda d: d['spec']['template']['spec']['containers'][0].update(image='new-image'),
        lambda d: d['spec']['template']['spec']['containers'][0]['env'][0].update(value='100'),
        lambda d: d['spec']['traffic'][0].update(revisionName='other'),
        lambda d: d['status']['traffic'][0].update(revisionName='other'),
    ],
)
def test_omitted_service_drift_refuses_without_repair_write(mutate):
    before = omitted_service()
    expected = omitted.fingerprint(before)
    changed = deepcopy(before)
    mutate(changed)
    try:
        actual = omitted.fingerprint(changed)
    except ValueError:
        return
    assert actual != expected


def test_omitted_guard_cli_binds_run_and_does_not_export_configuration(monkeypatch, tmp_path):
    state = tmp_path / 'guard.json'
    doc = omitted_service()
    monkeypatch.setattr(omitted, 'observe', lambda: omitted.fingerprint(doc))
    monkeypatch.setenv('GITHUB_RUN_ID', '123')
    monkeypatch.setenv('GITHUB_RUN_ATTEMPT', '1')
    monkeypatch.setattr('sys.argv', ['guard', 'capture', '--state', str(state)])
    assert omitted.main() == 0
    assert state.stat().st_mode & 0o777 == 0o600
    assert 'BATCH_PIPELINE' not in state.read_text() and 'old-image' not in state.read_text()
    monkeypatch.setattr('sys.argv', ['guard', 'verify', '--state', str(state)])
    assert omitted.main() == 0
    monkeypatch.setenv('GITHUB_RUN_ATTEMPT', '2')
    assert omitted.main() == 1
    monkeypatch.setenv('GITHUB_RUN_ATTEMPT', '1')
    doc['spec']['template']['spec']['containers'][0]['env'][1]['value'] = '20'
    assert omitted.main() == 1


def test_read_failure_and_incomplete_identity_never_become_unchanged(monkeypatch):
    def fail(_):
        raise omitted.Refused('command_failed')

    monkeypatch.setattr(omitted, 'command', fail)
    with pytest.raises(ValueError):
        omitted.observe()
    with pytest.raises(ValueError):
        omitted.fingerprint({'metadata': {}, 'spec': {}, 'status': {}})


def test_guard_runs_before_promotion_and_after_failure_or_cancellation(steps):
    names = [s['name'] for s in steps]
    assert names.index('Capture omitted integration identity before mutations') < names.index(
        'Migrate legacy public Cloud Run bindings'
    )
    assert names.index('Verify omitted integration remains unchanged before promotion') < names.index(
        'Shift Cloud Run traffic to validated revisions'
    )
    final = step(steps, 'Verify omitted integration remains unchanged after rollout or recovery')
    assert 'always()' in final['if'] and "steps.omitted-integration.outcome == 'success'" in final['if']
    assert names.index(final['name']) > max(
        i for i, n in enumerate(names) if n == 'Restore Cloud Run traffic snapshot after failed promotion'
    )
