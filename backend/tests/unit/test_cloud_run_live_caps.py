"""Execute the composite actions' real cap resolver with a read-only gcloud double."""

import json
import os
from pathlib import Path
import re
import subprocess

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]


PROD_BRANCH = re.compile(r"^\$\{\{ inputs\.runtime_env == 'prod' && '([^']*)' \|\| '([^']*)' \}\}$")


@pytest.fixture(
    params=[
        ('deploy-backend-stack', 'sync', '50', 'live-max-scale'),
        # 2026-11-20: integration reads its live cap too, so a capacity revision (35 -> 45) is not
        # reset by the next train. Prod fresh-service default stays the former 35 literal.
        ('deploy-backend-stack', 'integration', '35', 'live-integration-max-scale'),
        ('sync-backfill-lifecycle', 'sync-backfill', '40', 'live-max-scale'),
    ]
)
def action(request):
    name, suffix, fallback, step_id = request.param
    steps = yaml.safe_load((ROOT / '.github/actions' / name / 'action.yml').read_text())['runs']['steps']
    resolver = next(step for step in steps if step.get('id') == step_id)
    deploy = next(step for step in steps if step.get('id') == f'deploy-backend-{suffix}')
    assert steps.index(resolver) < steps.index(deploy)
    assert resolver['env']['CLOUD_RUN_SERVICE'] == '${{ inputs.service }}-' + suffix
    assert resolver['env']['CLOUD_RUN_PROJECT'] == '${{ inputs.project_id }}'
    assert resolver['env']['CLOUD_RUN_REGION'] == '${{ inputs.region }}'
    assert f'--max-instances=${{{{ steps.{step_id}.outputs.max_scale }}}}' in deploy['with']['flags']
    if suffix == 'integration':
        # The resolver runs exactly when the deploy it feeds runs; a skipped resolver would
        # hand the deploy an empty cap.
        assert resolver['if'] == deploy['if']
        prod, dev = PROD_BRANCH.match(resolver['env']['DEFAULT_MAX_SCALE']).groups()
        assert (prod, dev) == ('35', '50')
    if suffix == 'sync-backfill':
        # Worker/platform/dispatch retain their cap read; routing must leave
        # the omitted backfill worker uninspected. Exercise the actual shell
        # below under every retained mode without weakening its cap assertions.
        assert resolver['if'] == (
            "${{ inputs.mode == 'worker' || inputs.mode == 'platform' || inputs.mode == 'dispatch' }}"
        )
        assert deploy['if'] == "${{ inputs.mode == 'worker' }}"
        assert '--max=${{ steps.live-max-scale.outputs.max_scale }}' in deploy['with']['flags']
    return resolver, 'custom-' + suffix, fallback


def resolve(
    tmp_path,
    action,
    *,
    service_cap=None,
    revision_cap=None,
    missing=False,
    exit_code=0,
    payload=None,
    traffic=None,
    revisions=None,
    revision_exit=0,
    branch='prod',
    registered_cap='',
):
    resolver, service, _fallback = action
    serving = action[1].endswith('-integration')
    if serving and traffic is None:
        # Integration reads the cap of the revision receiving traffic, never the latest template.
        # Without a revision cap in a shared case, no revision receives traffic, so the service cap
        # (or the default) is the only input.
        traffic = (
            [{'revisionName': 'serving-rev', 'percent': 100}, {'revisionName': 'candidate-rev', 'percent': 0}]
            if revision_cap is not None
            else []
        )
        revisions = {'serving-rev': revision_cap, 'candidate-rev': '35'} if revisions is None else revisions
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
                    'status': {'traffic': traffic or []},
                }
            ]
        )
    (tmp_path / 'response.json').write_text(json.dumps(payload))
    for name, cap in (revisions or {}).items():
        annotations = {} if cap is None else {'autoscaling.knative.dev/maxScale': cap}
        (tmp_path / f'rev-{name}.json').write_text(json.dumps({'metadata': {'annotations': annotations}}))
    executable = tmp_path / 'gcloud'
    executable.write_text(
        '#!/bin/bash\n'
        'printf "%s\\n" "$@" > "$CAP_TEST_DIR/args"\n'
        'printf "%s\\n" "$*" >> "$CAP_TEST_DIR/calls"\n'
        'if [[ "$2" == revisions ]]; then cat "$CAP_TEST_DIR/rev-$4.json"; exit "$CAP_TEST_REVISION_EXIT"; fi\n'
        'cp "$CAP_TEST_DIR/args" "$CAP_TEST_DIR/list-args"\n'
        'cat "$CAP_TEST_DIR/response.json"\n'
        'exit "$CAP_TEST_EXIT"\n'
    )
    executable.chmod(0o755)
    output = tmp_path / 'output'
    env = dict(os.environ, PATH=str(tmp_path) + os.pathsep + os.environ['PATH'])
    default = resolver['env'].get('DEFAULT_MAX_SCALE', '')
    match = PROD_BRANCH.match(default)
    env.update(
        DEFAULT_MAX_SCALE=match.group(1 if branch == 'prod' else 2) if match else default,
        CLOUD_RUN_SERVICE=service,
        CLOUD_RUN_PROJECT='test-project',
        CLOUD_RUN_REGION='us-central1',
        GITHUB_OUTPUT=str(output),
        REGISTERED_MAX_SCALE=registered_cap,
        CAP_TEST_DIR=str(tmp_path),
        CAP_TEST_EXIT=str(exit_code),
        CAP_TEST_REVISION_EXIT=str(revision_exit),
    )
    result = subprocess.run(['bash', '-c', resolver['run']], env=env, capture_output=True, text=True)
    args = (tmp_path / 'list-args').read_text().splitlines()
    assert (tmp_path / 'calls').read_text().splitlines()[0].startswith('run services list ')
    assert args[:3] == ['run', 'services', 'list']
    assert '--project=test-project' in args
    assert '--region=us-central1' in args
    assert f'--filter=metadata.name={service}' in args
    return result, output.read_text() if output.exists() else ''


@pytest.mark.parametrize('cap', ['8', '16', '32', '80'])
def test_service_cap_takes_precedence_over_stale_revision(tmp_path, action, cap):
    result, output = resolve(tmp_path, action, service_cap=cap, revision_cap='40')
    assert result.returncode == 0, result.stderr
    # Integration mirrors the headroom gate: min(service cap, receiving revision caps).
    expected = str(min(int(cap), 40)) if action[1].endswith('-integration') else cap
    assert output.splitlines()[0] == f'max_scale={expected}'


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


@pytest.mark.parametrize(
    'action', [('sync-backfill-lifecycle', 'sync-backfill', '40', 'live-max-scale')], indirect=True
)
@pytest.mark.parametrize('cap,expected', [('1', 6), ('8', 48), ('16', 90), ('40', 90), ('501', 90)])
@pytest.mark.parametrize('exists', [True, False])
def test_backfill_queue_create_and_update_obey_live_capacity(tmp_path, action, cap, expected, exists):
    result, output = resolve(tmp_path, action, service_cap=cap)
    assert result.returncode == 0, result.stderr
    outputs = dict(line.split('=', 1) for line in output.splitlines())
    assert int(outputs['max_concurrent_dispatches']) == expected
    assert 1 <= expected <= min(90, int(outputs['max_scale']) * 6)
    steps = yaml.safe_load((ROOT / '.github/actions/sync-backfill-lifecycle/action.yml').read_text())['runs']['steps']
    queue = next(step for step in steps if step['name'] == 'Reconcile bounded sync backfill queue')
    assert queue['env']['BACKFILL_MAX_CONCURRENT_DISPATCHES'] == (
        '${{ steps.live-max-scale.outputs.max_concurrent_dispatches }}'
    )
    # Execute the actual queue shell too, checking the argument passed to each mutation branch.
    executable = tmp_path / 'gcloud'
    executable.write_text(
        '#!/bin/bash\n'
        'printf "%s\\n" "$*" >> "$CAP_TEST_DIR/queue-args"\n'
        'if [[ "$3" == describe ]]; then exit "$CAP_TEST_DESCRIBE_EXIT"; fi\n'
    )
    executable.chmod(0o755)
    env = dict(os.environ, PATH=str(tmp_path) + os.pathsep + os.environ['PATH'])
    env.update(
        CAP_TEST_DIR=str(tmp_path),
        CAP_TEST_DESCRIBE_EXIT='0' if exists else '1',
        BACKFILL_MAX_CONCURRENT_DISPATCHES=outputs['max_concurrent_dispatches'],
    )
    script = (
        queue['run'].replace('${{ inputs.region }}', 'us-central1').replace('${{ inputs.project_id }}', 'test-project')
    )
    result = subprocess.run(['bash', '-c', script], env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    calls = (tmp_path / 'queue-args').read_text().splitlines()
    # The backfill queue reconcile (describe + create/update) plus the
    # update-only max-attempts reconciliation of the main sync-jobs queue
    # that the fallback route and fresh lane deliver through: its describe
    # succeeds under the same double, so update-only adds describe+update
    # when the queue exists and just the failed describe when it does not
    # (create is deliberately omitted — another team owns that queue).
    assert len(calls) == (4 if exists else 3)
    assert calls[1].startswith('tasks queues ' + ('update' if exists else 'create') + ' sync-backfill ')
    assert f'--max-concurrent-dispatches={expected}' in calls[1]
    assert '--max-dispatches-per-second=15' in calls[1]
    assert calls[2] == 'tasks queues describe sync-jobs --location=us-central1 --project=test-project'
    if exists:
        assert (
            calls[3] == 'tasks queues update sync-jobs --location=us-central1 --project=test-project --max-attempts=5'
        )


INTEGRATION = ('deploy-backend-stack', 'integration', '35', 'live-integration-max-scale')


@pytest.mark.parametrize('action', [INTEGRATION], indirect=True)
def test_integration_ignores_no_traffic_candidate_cap(tmp_path, action):
    # A failed or held train leaves a no-traffic candidate as the latest template; its cap
    # must not replace the cap of the revision actually serving (panel F1, 2026-11-20).
    traffic = [{'revisionName': 'cap45', 'percent': 100}, {'revisionName': 'candidate', 'percent': 0}]
    result, output = resolve(tmp_path, action, traffic=traffic, revisions={'cap45': '45', 'candidate': '35'})
    assert result.returncode == 0, result.stderr
    assert output.splitlines()[0] == 'max_scale=45'
    calls = (tmp_path / 'calls').read_text()
    assert 'revisions describe cap45 ' in calls
    assert 'candidate' not in calls


@pytest.mark.parametrize('action', [INTEGRATION], indirect=True)
def test_integration_split_traffic_keeps_smallest_receiving_cap(tmp_path, action):
    traffic = [{'revisionName': 'a', 'percent': 90}, {'revisionName': 'b', 'percent': 10}]
    result, output = resolve(tmp_path, action, traffic=traffic, revisions={'a': '45', 'b': '40'})
    assert result.returncode == 0, result.stderr
    assert output.splitlines()[0] == 'max_scale=40'


@pytest.mark.parametrize('action', [INTEGRATION], indirect=True)
@pytest.mark.parametrize('branch,expected', [('prod', '35'), ('dev', '50')])
def test_integration_without_serving_revision_uses_branch_default(tmp_path, action, branch, expected):
    result, output = resolve(tmp_path, action, traffic=[], revisions={}, branch=branch)
    assert result.returncode == 0, result.stderr
    assert output.splitlines()[0] == f'max_scale={expected}'


@pytest.mark.parametrize('action', [INTEGRATION], indirect=True)
def test_integration_dev_fresh_service_uses_dev_default(tmp_path, action):
    result, output = resolve(tmp_path, action, missing=True, branch='dev')
    assert result.returncode == 0, result.stderr
    assert output.splitlines()[0] == 'max_scale=50'


@pytest.mark.parametrize('action', [INTEGRATION], indirect=True)
def test_integration_revision_read_failure_stops_deploy(tmp_path, action):
    result, output = resolve(tmp_path, action, revision_cap='45', revision_exit=1)
    assert result.returncode != 0
    assert output == ''


@pytest.mark.parametrize('action', [INTEGRATION], indirect=True)
@pytest.mark.parametrize('name', ['Bad_Name', 'a b', '-x', 7])
def test_integration_invalid_serving_revision_stops_deploy(tmp_path, action, name):
    # A resolvable cap file exists for the bogus name, so only the name validation can stop it.
    result, output = resolve(
        tmp_path, action, traffic=[{'revisionName': name, 'percent': 100}], revisions={str(name): '45'}
    )
    assert result.returncode != 0
    assert output == ''
    assert 'revisions describe' not in (tmp_path / 'calls').read_text()


@pytest.mark.parametrize('action', [INTEGRATION], indirect=True)
@pytest.mark.parametrize('branch,expected', [('prod', '35'), ('dev', '45')])
def test_integration_uncapped_receiving_revision_counts_as_default(tmp_path, action, branch, expected):
    # lead2 FIX-FIRST 2026-11-20: 50/50 uncapped + cap45 must give min(default, 45), not 45.
    traffic = [{'revisionName': 'uncapped', 'percent': 50}, {'revisionName': 'cap45', 'percent': 50}]
    result, output = resolve(
        tmp_path, action, traffic=traffic, revisions={'uncapped': None, 'cap45': '45'}, branch=branch
    )
    assert result.returncode == 0, result.stderr
    assert output.splitlines()[0] == f'max_scale={expected}'


@pytest.mark.parametrize('action', [INTEGRATION], indirect=True)
@pytest.mark.parametrize('service_cap,revision_cap', [('45\n3', None), ('45', '45\n3'), ('', None), ('45', '')])
def test_integration_rejects_a_cap_that_is_not_one_whole_number(tmp_path, action, service_cap, revision_cap):
    # Panel F2/F6: a multi-line or empty cap fails as a whole instead of splitting into caps.
    traffic = [{'revisionName': 'serving', 'percent': 100}] if revision_cap is not None else []
    result, output = resolve(
        tmp_path, action, service_cap=service_cap, traffic=traffic, revisions={'serving': revision_cap}
    )
    assert result.returncode != 0
    assert output == ''
    assert 'Invalid Cloud Run maxScale' in result.stderr


@pytest.mark.parametrize('action', [INTEGRATION], indirect=True)
@pytest.mark.parametrize('service_cap,revision_cap,expected', [('50', '35', '35'), ('40', '45', '40')])
def test_integration_service_and_revision_caps_take_the_minimum(tmp_path, action, service_cap, revision_cap, expected):
    # Panel F3: matches deploy_headroom caps(), which takes min(service cap, receiving revision caps).
    traffic = [{'revisionName': 'serving', 'percent': 100}]
    result, output = resolve(
        tmp_path, action, service_cap=service_cap, traffic=traffic, revisions={'serving': revision_cap}
    )
    assert result.returncode == 0, result.stderr
    assert output.splitlines()[0] == f'max_scale={expected}'


@pytest.mark.parametrize(
    'live,registered', [('66', '45'), ('55', '45'), ('45', '45'), ('60', '50'), ('50', '50'), ('45', '55')]
)
def test_registered_cap_cannot_change_live_capacity(tmp_path, action, live, registered):
    if action[1].endswith('-sync-backfill'):
        pytest.skip('registered dispatch covers integration and sync only')
    result, output = resolve(tmp_path, action, revision_cap=live, registered_cap=registered)
    if live == registered:
        assert result.returncode == 0, result.stderr
        assert output == f'max_scale={registered}\n'
    else:
        assert result.returncode != 0
        assert 'differs from live' in result.stderr
        assert not output


@pytest.mark.parametrize('live', [None, '999'])
def test_registered_dispatch_refuses_live_cap_fallback(tmp_path, action, live):
    if action[1].endswith('-sync-backfill'):
        pytest.skip('registered dispatch covers integration and sync only')
    result, output = resolve(tmp_path, action, service_cap=live, registered_cap=action[2])
    assert result.returncode != 0
    assert not output
