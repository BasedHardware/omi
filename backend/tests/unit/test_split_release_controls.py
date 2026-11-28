"""Exercise split release guard accounting, recovery custody and checkout lookup."""

from dataclasses import replace
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import yaml

from scripts import cloud_run_split_canary as canary
from scripts import guard_eval, serving_has, serving_revision


def test_sync_guard_counts_unmatched_503s():
    policy = guard_eval.policy_for('backend-sync')
    name = 'sync-local-files'
    candidate = {
        'service': {'2xx': 900, '5xx': 100},
        'routes': {name: {200: 90, 503: 100}},
        'refusal_records': {name: {503: 5}},
    }
    donor = {'service': {'2xx': 1000}, 'routes': {name: {200: 100}}, 'refusal_records': {}}
    assert guard_eval.evaluate(policy, candidate, donor)['verdict'] == 'TRIP'
    candidate['refusal_records'][name][503] = 100
    assert guard_eval.evaluate(policy, candidate, donor)['verdict'] == 'PASS'


def rollback_fixture():
    service = 'backend'
    wire = 'holdback-v1;backend-donor;backend-donor=90,backend-shadow=10;5;7200'
    promoted = {'backend-candidate': 90, 'backend-shadow': 10}
    state = canary.TrafficState('uid', 'etag', promoted, promoted, (('shadow', 'backend-shadow'),))
    transport = Mock(name='cloud')
    transport.name = 'projects/example/locations/us-central1/services/backend'
    transport.read.return_value = state
    receipt = dict(
        target=transport.name,
        binding=hashlib.sha256(wire.encode()).hexdigest(),
        candidate='backend-candidate',
        uid=state.uid,
        etag=state.etag,
        tags=state.tags,
        final_map=promoted,
    )
    return service, wire, transport, receipt


def test_post_promotion_restore_uses_the_admitted_inverse():
    service, wire, transport, receipt = rollback_fixture()
    canary.restore_completed(service, wire, transport, receipt, floor_check=lambda _: True)
    transport.replace.assert_called_once_with(transport.read.return_value, {'backend-donor': 90, 'backend-shadow': 10})


def test_post_promotion_restore_refuses_below_floor_tag():
    service, wire, transport, receipt = rollback_fixture()
    tags = (('preview', 'backend-old'),)
    transport.read.return_value = replace(transport.read.return_value, tags=tags)
    receipt['tags'] = tags

    with pytest.raises(ValueError, match='release_floor_rejected'):
        canary.restore_completed(service, wire, transport, receipt, floor_check=lambda rev: rev != 'backend-old')
    transport.replace.assert_not_called()


@pytest.mark.parametrize(
    'change',
    [
        {'etag': 'changed'},
        {'uid': 'changed'},
        {'tags': ()},
        {'converged': False},
        {'requested': {'backend-candidate': 100}},
        {'observed': {'backend-candidate': 100}},
    ],
)
def test_post_promotion_restore_refuses_changed_state(change):
    service, wire, transport, receipt = rollback_fixture()
    transport.read.return_value = replace(transport.read.return_value, **change)
    with pytest.raises(RuntimeError, match='rollback_traffic_ownership_lost'):
        canary.restore_completed(service, wire, transport, receipt, floor_check=lambda _: True)
    transport.replace.assert_not_called()


def test_bound_rollback_paths_request_the_published_release_floor():
    repo = Path(__file__).resolve().parents[3]
    action = yaml.safe_load((repo / '.github/actions/deploy-backend-stack/action.yml').read_text())
    restore = next(step for step in action['runs']['steps'] if step['name'].startswith('Restore admitted inverse'))
    assert (
        '--release-floor-check "$DEPLOY_WORKFLOW_ROOT/.github/scripts/verify_backend_release_floor.py"'
        in restore['run']
    )
    shift = next(step for step in action['runs']['steps'] if step.get('id') == 'shift-cloud-run-traffic')
    assert (
        '--release-floor-check "$DEPLOY_WORKFLOW_ROOT/.github/scripts/verify_backend_release_floor.py"' in shift['run']
    )
    # The verifier needs the restored revision's ancestry, so main is fetched
    # (unshallowing a shallow checkout) before the executor runs.
    assert shift['run'].index('refs/remotes/origin/main') < shift['run'].index('promote \\')
    assert restore['run'].index('refs/remotes/origin/main') < restore['run'].index('restore-completed')
    assert '--unshallow' in restore['run']
    workflow = yaml.safe_load((repo / '.github/workflows/gcp_backend.yml').read_text())
    recovery = workflow['jobs']['recover-bound-split']['steps']
    restore_index = next(i for i, step in enumerate(recovery) if 'recover-run' in step.get('run', ''))
    history_index = next(i for i, step in enumerate(recovery) if 'refs/remotes/origin/main' in step.get('run', ''))
    # The floor verifier needs commit objects and ancestry, so the recovery
    # checkout must deepen history before the restore and never fetch depth 1.
    assert history_index < restore_index
    history_run = recovery[history_index]['run']
    assert '--unshallow' in history_run
    assert '--depth' not in history_run
    assert '--release-floor-check .github/scripts/verify_backend_release_floor.py' in recovery[restore_index]['run']


@pytest.mark.parametrize('refused_revision', [None, 'backend-shadow', 'backend-tagged'])
def test_restore_cli_checks_pinned_sources_for_all_routable_revisions(tmp_path, monkeypatch, capfd, refused_revision):
    service, wire, transport, receipt = rollback_fixture()
    binding = hashlib.sha256(wire.encode()).hexdigest()
    receipt_path = tmp_path / 'backend-holdback-promotion.json'
    tags = (*receipt['tags'], ('preview', 'backend-tagged'))
    transport.read.return_value = replace(transport.read.return_value, tags=tags)
    receipt_path.write_text(json.dumps({**receipt, 'tags': tags}))
    base = [
        'restore-completed',
        '--service',
        service,
        '--plan',
        wire,
        '--binding',
        binding,
        '--project',
        'example',
        '--region',
        'us-central1',
        '--promotion-receipt',
        str(receipt_path),
    ]
    with pytest.raises(SystemExit):
        canary.main(base)
    transport.replace.assert_not_called()

    sources = {'backend-donor': 'a' * 40, 'backend-shadow': 'b' * 40, 'backend-tagged': 'c' * 40}
    image_source = Mock(side_effect=lambda revision, *args, **kwargs: sources[revision])
    monkeypatch.setattr(canary, 'revision_image_source', image_source)
    floor = tmp_path / 'verify_backend_release_floor.py'
    checked = tmp_path / 'checked'
    floor.write_text(
        'from pathlib import Path\n'
        'import sys\n'
        'assert len(sys.argv) == 3 and sys.argv[1] == "--sha"\n'
        f'with Path({str(checked)!r}).open("a") as log:\n'
        '    log.write(sys.argv[2] + "\\n")\n'
        f'if sys.argv[2] == {sources.get(refused_revision)!r}:\n'
        '    sys.exit("ERROR: Backend release floor rejected the target. below floor")\n'
    )
    monkeypatch.setattr(canary, 'CloudRunTraffic', Mock(return_value=transport))
    result = canary.main([*base, '--release-floor-check', str(floor)])
    resolved = [call.args[0] for call in image_source.call_args_list]
    expected = list(sources)
    if refused_revision is None:
        assert result == 0
        transport.replace.assert_called_once_with(
            transport.read.return_value, {'backend-donor': 90, 'backend-shadow': 10}
        )
    else:
        assert result == 1
        expected = expected[: expected.index(refused_revision) + 1]
        assert 'below floor' in capfd.readouterr().err
        transport.replace.assert_not_called()
    assert resolved == expected
    assert checked.read_text().splitlines() == [sources[revision] for revision in expected]


def test_recovery_checkout_needs_history_to_resolve_an_eligible_release(tmp_path):
    """The recover-bound-split checkout must deepen history before the floor check."""
    verifier = Path(__file__).resolve().parents[3] / '.github/scripts/verify_backend_release_floor.py'
    origin = tmp_path / 'origin'
    origin.mkdir()
    git = ['git', '-C', str(origin), '-c', 'user.name=t', '-c', 'user.email=t@example.com']

    def git_run(*args):
        subprocess.run([*git, *args], check=True, capture_output=True, text=True)

    git_run('init', '-q', '--initial-branch=main')
    (origin / 'backend' / 'deploy').mkdir(parents=True)
    (origin / 'README.md').write_text('base\n')
    git_run('add', '.')
    git_run('commit', '-qm', 'base')
    floor_sha = subprocess.run(
        ['git', '-C', str(origin), 'rev-parse', 'HEAD'], check=True, capture_output=True, text=True
    ).stdout.strip()
    (origin / 'backend' / 'deploy' / 'release_floor.json').write_text(
        json.dumps({'floor': floor_sha, 'reason': 'test floor', 'since': '2026-11-01'})
    )
    git_run('add', '.')
    git_run('commit', '-qm', 'floor')
    (origin / 'README.md').write_text('later\n')
    git_run('add', '.')
    git_run('commit', '-qm', 'later')

    shallow = tmp_path / 'shallow'
    subprocess.run(
        ['git', 'clone', '-q', '--depth=1', '--branch', 'main', origin.as_uri(), str(shallow)],
        check=True,
        capture_output=True,
        text=True,
    )
    assert (
        subprocess.run(
            ['git', '-C', str(shallow), 'rev-parse', '--is-shallow-repository'],
            capture_output=True,
            text=True,
        ).stdout.strip()
        == 'true'
    )

    def verify():
        return subprocess.run(
            [sys.executable, str(verifier), '--sha', floor_sha],
            cwd=shallow,
            capture_output=True,
            text=True,
        )

    refused = verify()
    assert refused.returncode == 1 and 'release floor rejected' in refused.stderr

    subprocess.run(['git', '-C', str(shallow), 'fetch', '-q', '--unshallow', 'origin'], check=True)
    admitted = verify()
    assert admitted.returncode == 0, admitted.stderr


def test_bound_deploys_keep_the_live_runtime_env_and_drift_preflights():
    repo = Path(__file__).resolve().parents[3]
    action = yaml.safe_load((repo / '.github/actions/deploy-backend-stack/action.yml').read_text())
    steps = {step['name']: step for step in action['runs']['steps']}
    assert 'if' not in steps['Validate backend runtime env after deploy']
    assert (
        steps['Report live Cloud Run env drift from manifest']['if']
        == "${{ inputs.integration_only != 'true' && (success()) }}"
    )


def test_completed_receipt_can_be_restored_from_another_run(tmp_path, monkeypatch):
    service, wire, transport, _ = rollback_fixture()
    source, control, run_id = 'a' * 40, 'b' * 40, 123
    binding = hashlib.sha256(wire.encode()).hexdigest()
    receipt_path = tmp_path / 'backend-holdback-promotion.json'
    monkeypatch.setattr(canary, 'CloudRunTraffic', Mock(return_value=transport))
    monkeypatch.setattr(canary, 'release_floor_command', Mock(return_value=lambda _: True))

    def promote(*args, on_promoted, **kwargs):
        state = transport.read.return_value
        on_promoted(state)
        return state.observed

    monkeypatch.setattr(canary, 'promote', promote)
    target = [
        '--project',
        'example',
        '--region',
        'us-central1',
        '--promotion-receipt',
        str(receipt_path),
        '--release-floor-check',
        'verify_backend_release_floor.py',
    ]
    identity = ['--run-id', str(run_id)]
    assert (
        canary.main(
            [
                'promote',
                *target,
                *identity,
                '--run-attempt',
                '1',
                '--service',
                service,
                '--plan',
                wire,
                '--binding',
                binding,
                '--source',
                source,
                '--control',
                control,
                '--candidate',
                'backend-candidate',
                '--refresh-floor',
            ]
        )
        == 0
    )
    run_path = tmp_path / 'run.json'
    run = dict(
        id=run_id,
        run_attempt=1,
        head_repository={'full_name': 'BasedHardware/omi'},
        path='.github/workflows/gcp_backend.yml',
        head_branch='main',
        event='workflow_dispatch',
        status='completed',
        conclusion='cancelled',
        head_sha=control,
        display_title=f'Holdback prod/{service} sha={source} by selection:{"0" * 32} plan={binding}',
    )
    run_path.write_text(json.dumps(run))
    recover = ['recover-run', *target, *identity, '--run-metadata', str(run_path)]
    floor_check = Mock(side_effect=lambda revision: revision != 'backend-donor')
    canary.release_floor_command.return_value = floor_check
    assert canary.main(recover) == 1
    floor_check.assert_called_once_with('backend-donor')
    transport.replace.assert_not_called()

    canary.release_floor_command.return_value = lambda _: True
    assert canary.main(recover) == 0
    transport.replace.assert_called_once_with(transport.read.return_value, {'backend-donor': 90, 'backend-shadow': 10})

    transport.reset_mock()
    transport.read.return_value = replace(transport.read.return_value, etag='changed')
    assert canary.main(recover) == 1
    transport.replace.assert_not_called()

    transport.reset_mock()
    for changed_run in ({'conclusion': 'success'}, {'head_sha': 'c' * 40}, {'run_attempt': 2}):
        run_path.write_text(json.dumps({**run, **changed_run}))
        assert canary.main(recover) == 1
    run_path.write_text(json.dumps(run))
    receipt_path.unlink()
    assert canary.main(recover) == 1
    transport.read.assert_not_called()
    transport.replace.assert_not_called()


def test_receipt_is_uploaded_before_acceptance_and_recovered_under_prod_approval():
    repo = Path(__file__).resolve().parents[3]
    action = yaml.safe_load((repo / '.github/actions/deploy-backend-stack/action.yml').read_text())
    steps = action['runs']['steps']
    indices = {step.get('id'): i for i, step in enumerate(steps)}
    upload_id = 'persist-bound-promotion-receipt'
    upload = steps[indices[upload_id]]
    assert indices['shift-cloud-run-traffic'] < indices[upload_id] < indices['verify-serving-release-vector']
    assert "steps.shift-cloud-run-traffic.outputs.promoted == 'true'" in upload['if']
    assert f"steps.{upload_id}.outcome == 'success'" in steps[indices['verify-serving-release-vector']]['if']
    assert upload['with']['path'].endswith('/backend-holdback-promotion.json')
    assert upload['with']['if-no-files-found'] == 'error'
    workflow = yaml.safe_load((repo / '.github/workflows/gcp_backend.yml').read_text())
    recovery = workflow['jobs']['recover-bound-split']
    assert recovery['environment'] == 'prod'
    assert 'prod-train' in workflow['concurrency']['group']
    assert 'refs/heads/main' in recovery['if'] and '!inputs.break_glass_lock' in recovery['if']
    download = recovery['steps'][1]['run']
    assert 'attempts/1' in download
    assert 'backend-holdback-promotion-$ORIGINAL_RUN-1' in download
    assert 'cloud_run_split_canary.py recover-run' in recovery['steps'][-1]['run']


@pytest.mark.parametrize(
    'status,promoted,held,upload,vector,smoke,expected',
    [
        ('cancelled', 'true', '', 'success', 'cancelled', 'skipped', True),
        ('cancelled', 'true', '', 'success', 'success', 'cancelled', True),
        ('cancelled', 'true', '', 'success', 'success', 'skipped', True),
        ('cancelled', 'true', '', 'success', 'success', 'success', False),
        ('failure', 'true', '', 'success', 'success', 'failure', True),
        ('failure', 'true', '', 'failure', 'skipped', 'skipped', True),
        ('failure', '', 'true', 'skipped', 'skipped', 'skipped', False),
        ('cancelled', 'true', 'true', 'success', 'cancelled', 'skipped', False),
        ('cancelled', '', '', 'skipped', 'skipped', 'skipped', False),
    ],
)
def test_bound_restore_runs_only_after_completed_promotion(status, promoted, held, upload, vector, smoke, expected):
    repo = Path(__file__).resolve().parents[3]
    action = yaml.safe_load((repo / '.github/actions/deploy-backend-stack/action.yml').read_text())
    step = next(s for s in action['runs']['steps'] if s['name'].startswith('Restore admitted inverse'))
    condition = step['if'].removeprefix('${{').removesuffix('}}').strip()
    values = {
        'failure()': status == 'failure',
        'cancelled()': status == 'cancelled',
        'inputs.selected_split_binding': 'bound',
        'inputs.cloud_run_service': 'backend',
        'steps.shift-cloud-run-traffic.outputs.promoted': promoted,
        'steps.shift-cloud-run-traffic.outputs.held': held,
        'steps.persist-bound-promotion-receipt.outcome': upload,
        'steps.verify-serving-release-vector.outcome': vector,
        'steps.smoke-promoted-production-serving-api.outcome': smoke,
    }
    for token, value in values.items():
        condition = condition.replace(token, repr(value))
    condition = re.sub(r'\s+', ' ', condition).replace('&&', ' and ').replace('||', ' or ')
    assert eval(condition, {'__builtins__': {}}) is expected


def test_serving_default_resolves_the_current_checkout(monkeypatch):
    monkeypatch.delenv('SERVING_HAS_REPO', raising=False)
    monkeypatch.delenv('OMI_WORKSPACE_ROOT', raising=False)
    repo = serving_has.default_repo()
    assert (
        serving_has.resolve(repo, 'HEAD', fetch=False)
        == serving_has.command(['git', '-C', repo, 'rev-parse', 'HEAD']).strip()
    )


def test_serving_revision_accepts_retained_untagged_revision_without_percent():
    service = {
        'status': {
            'traffic': [
                {'revisionName': 'backend-cfg-114caf58b84658fc'},
                {'revisionName': 'backend-outage-543aa7fb', 'percent': 100},
            ],
        },
    }
    assert serving_revision.serving_revision(service) == 'backend-outage-543aa7fb'


def test_serving_contains_uses_local_git_ancestry(monkeypatch):
    repo = serving_has.default_repo()
    current = serving_has.resolve(repo, 'HEAD', fetch=False)
    parent = serving_has.resolve(repo, 'HEAD^', fetch=False)
    opts = SimpleNamespace(repo=repo, latest=False, expected_sha=None, created_after=None, contains=parent)
    monkeypatch.setattr(serving_revision, 'release_of', lambda *_: current)
    revision = {'spec': {'containers': [{}]}}
    assert serving_revision.validate({}, 'backend-revision', revision, opts)[0] == current
    opts.contains = current
    monkeypatch.setattr(serving_revision, 'release_of', lambda *_: parent)
    with pytest.raises(ValueError, match='release_does_not_contain_commit'):
        serving_revision.validate({}, 'backend-revision', revision, opts)


class SplitTransport:
    """Minimal Cloud Run traffic transport that records every write."""

    name = 'projects/example/locations/us-central1/services/backend'

    def __init__(self, state):
        self.state = state
        self.writes = []

    def read(self):
        return self.state

    def replace(self, current, target):
        assert current is self.state
        self.writes.append(dict(target))
        self.state = canary.TrafficState(
            self.state.uid, f'etag{len(self.writes)}', dict(target), dict(target), self.state.tags
        )


def split_transport():
    inverse = {'backend-donor': 90, 'backend-shadow': 10}
    return SplitTransport(canary.TrafficState('uid', 'etag0', dict(inverse), dict(inverse))), inverse


@pytest.fixture
def interrupted_promotion(tmp_path, monkeypatch):
    wire = 'holdback-v1;backend-donor;backend-donor=100;5;7200'
    inverse = {'backend-donor': 100}
    run_id, source, control = 456, 'a' * 40, 'b' * 40
    binding = hashlib.sha256(wire.encode()).hexdigest()
    target = 'projects/example/locations/us-central1/services/backend'
    tag = dict(type=canary.REVISION_TARGET, revision='backend-tagged', tag='retained')
    donor = dict(type=canary.REVISION_TARGET, revision='backend-donor', percent=100)
    doc = dict(
        name=target,
        uid='service-uid',
        etag='original',
        generation='7',
        observedGeneration='7',
        annotations={'example.net/other': 'preserved'},
        traffic=[donor, tag],
        trafficStatuses=[donor, tag],
    )
    writes = []
    crash = True

    def request(method, url, *, timeout, body=None):
        nonlocal crash
        if method == 'GET':
            return doc
        writes.append(body)
        mask = 'traffic,annotations' if 'traffic' in body else 'annotations'
        assert url.endswith(f'?updateMask={mask}')
        assert body['etag'] == doc['etag']
        generation = str(int(doc['generation']) + 1)
        doc.update(body, generation=generation, etag=f'etag-{generation}')
        if crash:
            crash = False
            doc['reconciling'] = True
            raise ConnectionError('runner lost after Cloud Run accepted PATCH')
        doc.update(observedGeneration=generation, trafficStatuses=doc['traffic'], reconciling=False)

    transport = canary.CloudRunTraffic('example', 'us-central1', 'backend', request)
    transport.promotion = dict(
        schema=1,
        service='backend',
        plan=wire,
        inverse=inverse,
        source=source,
        control=control,
        run_id=run_id,
        run_attempt=1,
        target=target,
        binding=binding,
        candidate='backend-candidate',
    )
    with pytest.raises(ConnectionError):
        transport.replace(transport.read(), {'backend-candidate': 95, 'backend-donor': 5})
    assert doc['trafficStatuses'] == [donor, tag]
    assert canary.RECOVERY_ANNOTATION in writes[0]['annotations']

    run = dict(
        id=run_id,
        run_attempt=1,
        head_repository={'full_name': 'BasedHardware/omi'},
        path='.github/workflows/gcp_backend.yml',
        head_branch='main',
        event='workflow_dispatch',
        status='completed',
        conclusion='cancelled',
        head_sha=control,
        display_title=f'Holdback prod/backend sha={source} by selection:{"0" * 32} plan={binding}',
    )
    run_path = tmp_path / 'run.json'
    run_path.write_text(json.dumps(run))
    monkeypatch.setattr(canary, 'gcloud_json', request)
    args = [
        'recover-run',
        '--project',
        'example',
        '--region',
        'us-central1',
        '--release-floor-check',
        str(tmp_path / 'floor.py'),
        '--run-id',
        str(run_id),
        '--run-metadata',
        str(run_path),
    ]
    return doc, writes, args, transport


def test_recover_run_restores_interrupted_move_without_completed_receipt(interrupted_promotion, monkeypatch):
    doc, writes, args, _ = interrupted_promotion
    floor = Mock(return_value=True)
    monkeypatch.setattr(canary, 'release_floor_command', Mock(return_value=floor))

    assert canary.main(args) == 0
    assert len(writes) == 2
    assert writes[1]['etag'] == 'etag-8'
    assert doc['annotations'] == {'example.net/other': 'preserved'}
    assert [(entry['revision'], entry['percent']) for entry in doc['traffic']] == [
        ('backend-tagged', 0),
        ('backend-donor', 100),
    ]
    assert [call.args[0] for call in floor.call_args_list] == ['backend-donor', 'backend-tagged']


@pytest.mark.parametrize('reason', ['newer-generation', 'held', 'different-run', 'below-floor'])
def test_recover_run_refuses_when_interrupted_move_isnt_owned_or_eligible(interrupted_promotion, monkeypatch, reason):
    doc, writes, args, transport = interrupted_promotion
    floor = Mock(return_value=reason != 'below-floor')
    monkeypatch.setattr(canary, 'release_floor_command', Mock(return_value=floor))
    if reason == 'newer-generation':
        doc['generation'] = '9'
    elif reason == 'held':
        doc.update(observedGeneration=doc['generation'], trafficStatuses=doc['traffic'], reconciling=False)
        transport.leave_held(transport.read())
        assert canary.RECOVERY_ANNOTATION not in doc['annotations']
        assert 'traffic' not in writes[-1]
    elif reason == 'different-run':
        args[args.index('--run-id') + 1] = '457'

    assert canary.main(args) == 1
    assert len(writes) == (2 if reason == 'held' else 1)
    assert floor.called == (reason == 'below-floor')


def test_failed_hold_marker_cleanup_does_not_unwind_an_intentional_hold(interrupted_promotion, monkeypatch):
    doc, writes, _, transport = interrupted_promotion
    doc.update(traffic=doc['trafficStatuses'], observedGeneration=doc['generation'], reconciling=False)
    del doc['annotations'][canary.RECOVERY_ANNOTATION]
    writes.clear()
    monkeypatch.setattr(transport, 'leave_held', Mock(side_effect=ConnectionError('metadata write failed')))
    now, sleep = advancing_clock()
    with pytest.raises(ConnectionError, match='metadata write failed'):
        canary.promote(
            'backend',
            transport.promotion['plan'],
            transport.promotion['candidate'],
            transport,
            lambda *_: 'NO_COMPARATOR',
            floor_check=lambda _: True,
            recovery_identity=transport.promotion,
            now=now,
            sleep=sleep,
        )

    assert len(writes) == 1
    assert transport.read().requested == {'backend-candidate': 95, 'backend-donor': 5}


def trip_guard(service, candidate, donor, start, end):
    return 'TRIP'


def advancing_clock():
    """Guard windows settle only after the sleep they request."""
    clock = [datetime(2030, 1, 1, tzinfo=timezone.utc)]

    def now():
        return clock[0]

    def sleep(seconds):
        clock[0] += timedelta(seconds=seconds)

    return now, sleep


def test_promote_refuses_an_ineligible_inverse_before_any_traffic_move():
    transport, _ = split_transport()
    checked = []

    def floor(revision):
        checked.append(revision)
        return revision != 'backend-shadow'

    now, sleep = advancing_clock()
    with pytest.raises(ValueError, match='release_floor_rejected'):
        canary.promote(
            'backend',
            holdback_wire(),
            'backend-candidate',
            transport,
            trip_guard,
            sleep=sleep,
            now=now,
            floor_check=floor,
        )
    assert checked == ['backend-donor', 'backend-shadow']
    assert transport.writes == []
    assert transport.state.requested == {'backend-donor': 90, 'backend-shadow': 10}


def test_promote_restores_an_eligible_inverse_after_a_guard_trip():
    transport, inverse = split_transport()
    checked = []

    def floor(revision):
        checked.append(revision)
        return True

    now, sleep = advancing_clock()
    with pytest.raises(RuntimeError, match='holdback_guard_tripped'):
        canary.promote(
            'backend',
            holdback_wire(),
            'backend-candidate',
            transport,
            trip_guard,
            sleep=sleep,
            now=now,
            floor_check=floor,
        )
    # Checked before the first move and again before the restore.
    assert checked == ['backend-donor', 'backend-shadow', 'backend-candidate', 'backend-donor', 'backend-shadow']
    assert transport.writes[-1] == inverse
    assert transport.state.requested == inverse


def test_promote_refuses_to_restore_when_the_floor_moves_during_the_guard():
    transport, inverse = split_transport()
    calls = []

    def floor(revision):
        calls.append(revision)
        return len(calls) <= 3

    now, sleep = advancing_clock()
    with pytest.raises(ValueError, match='release_floor_rejected'):
        canary.promote(
            'backend',
            holdback_wire(),
            'backend-candidate',
            transport,
            trip_guard,
            sleep=sleep,
            now=now,
            floor_check=floor,
        )
    assert calls == ['backend-donor', 'backend-shadow', 'backend-candidate', 'backend-donor']
    assert inverse not in transport.writes
    assert transport.state.requested != inverse


def test_promote_requires_the_release_floor_on_the_cli(tmp_path):
    base = [
        'promote',
        '--service',
        'backend',
        '--plan',
        holdback_wire(),
        '--binding',
        hashlib.sha256(holdback_wire().encode()).hexdigest(),
        '--candidate',
        'backend-candidate',
        '--project',
        'example',
        '--region',
        'us-central1',
        '--promotion-receipt',
        str(tmp_path / 'receipt.json'),
        '--source',
        'a' * 40,
        '--control',
        'b' * 40,
        '--run-id',
        '1',
        '--run-attempt',
        '1',
    ]
    with pytest.raises(SystemExit):
        canary.main(base)


def holdback_wire():
    return 'holdback-v1;backend-donor;backend-donor=90,backend-shadow=10;5;7200'


def published_floor(*, eligible, refresh_ok, calls):
    round_number = 0

    def run(command, **kwargs):
        nonlocal round_number
        assert command == list(canary.FLOOR_REFRESH)
        round_number += 1
        calls.append('refresh')
        return SimpleNamespace(returncode=0 if refresh_ok(round_number) else 1)

    def check(revision):
        calls.append(revision)
        return eligible(round_number)

    return lambda: canary.refresh_release_floor(run=run), check


def test_promote_enforces_a_floor_published_during_the_guard():
    transport, inverse = split_transport()
    calls = []
    refresh, floor = published_floor(
        eligible=lambda round_: round_ == 1,
        refresh_ok=lambda round_: True,
        calls=calls,
    )
    now, sleep = advancing_clock()
    with pytest.raises(ValueError, match='release_floor_rejected'):
        canary.promote(
            'backend',
            holdback_wire(),
            'backend-candidate',
            transport,
            trip_guard,
            sleep=sleep,
            now=now,
            floor_check=floor,
            refresh_floor=refresh,
        )
    # The restore-time round refreshed origin/main again, then refused.
    assert calls == ['refresh', 'backend-donor', 'backend-shadow', 'backend-candidate', 'refresh', 'backend-donor']
    assert inverse not in transport.writes
    assert transport.state.requested != inverse


def test_failed_floor_refresh_prevents_the_inverse_write():
    transport, inverse = split_transport()
    calls = []
    refresh, floor = published_floor(
        eligible=lambda round_: True,
        refresh_ok=lambda round_: round_ == 1,
        calls=calls,
    )
    now, sleep = advancing_clock()
    with pytest.raises(ValueError, match='release_floor_refresh_failed'):
        canary.promote(
            'backend',
            holdback_wire(),
            'backend-candidate',
            transport,
            trip_guard,
            sleep=sleep,
            now=now,
            floor_check=floor,
            refresh_floor=refresh,
        )
    assert calls == ['refresh', 'backend-donor', 'backend-shadow', 'backend-candidate', 'refresh']
    assert inverse not in transport.writes
    assert transport.state.requested != inverse


def test_promote_requires_the_floor_refresh_on_the_cli(tmp_path):
    base = [
        'promote',
        '--service',
        'backend',
        '--plan',
        holdback_wire(),
        '--binding',
        hashlib.sha256(holdback_wire().encode()).hexdigest(),
        '--candidate',
        'backend-candidate',
        '--project',
        'example',
        '--region',
        'us-central1',
        '--promotion-receipt',
        str(tmp_path / 'receipt.json'),
        '--source',
        'a' * 40,
        '--control',
        'b' * 40,
        '--run-id',
        '1',
        '--run-attempt',
        '1',
        '--release-floor-check',
        str(tmp_path / 'floor.py'),
    ]
    with pytest.raises(SystemExit):
        canary.main(base)
