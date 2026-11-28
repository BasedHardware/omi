"""Exercise split release guard accounting, recovery custody and checkout lookup."""

from dataclasses import replace
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
    canary.restore_completed(service, wire, transport, receipt)
    transport.replace.assert_called_once_with(transport.read.return_value, {'backend-donor': 90, 'backend-shadow': 10})


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
        canary.restore_completed(service, wire, transport, receipt)
    transport.replace.assert_not_called()


def test_post_promotion_restore_checks_the_release_floor_before_moving_traffic():
    service, wire, transport, receipt = rollback_fixture()
    checked = []

    def floor(targets):
        checked.append(tuple(targets))
        raise ValueError('release_floor_refused:backend-shadow')

    with pytest.raises(ValueError, match='release_floor_refused'):
        canary.restore_completed(service, wire, transport, receipt, floor)
    assert checked == [('backend-donor', 'backend-shadow')]
    transport.read.assert_not_called()
    transport.replace.assert_not_called()


def test_release_floor_verifies_every_target_revision(tmp_path):
    script = tmp_path / 'verify_backend_release_floor.py'
    script.write_text('')
    commands = []

    def run(command, **kwargs):
        commands.append(command)
        return SimpleNamespace(
            returncode=1 if command[3] == 'backend-shadow' else 0,
            stderr=(
                'ERROR: Backend release floor rejected the target. below floor\n'
                if command[3] == 'backend-shadow'
                else ''
            ),
        )

    with pytest.raises(ValueError) as refused:
        canary.release_floor(
            ('backend-donor', 'backend-shadow'),
            script=script,
            project='example',
            region='us-central1',
            run=run,
        )
    assert [command[3] for command in commands] == ['backend-donor', 'backend-shadow']
    assert 'release_floor_refused:backend-shadow' in str(refused.value)
    assert 'below floor' in str(refused.value)


def test_bound_rollback_paths_request_the_published_release_floor():
    repo = Path(__file__).resolve().parents[3]
    action = yaml.safe_load((repo / '.github/actions/deploy-backend-stack/action.yml').read_text())
    restore = next(step for step in action['runs']['steps'] if step['name'].startswith('Restore admitted inverse'))
    assert (
        '--release-floor-check "$DEPLOY_WORKFLOW_ROOT/.github/scripts/verify_backend_release_floor.py"'
        in restore['run']
    )
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


def test_release_floor_check_is_required_and_its_reason_is_kept(tmp_path, monkeypatch):
    service, wire, transport, _ = rollback_fixture()
    binding = hashlib.sha256(wire.encode()).hexdigest()
    receipt_path = tmp_path / 'backend-holdback-promotion.json'
    receipt_path.write_text(
        json.dumps(
            dict(
                target=transport.name,
                binding=binding,
                candidate='backend-candidate',
                uid='uid',
                etag='etag',
                tags=[['shadow', 'backend-shadow']],
                final_map={'backend-candidate': 90, 'backend-shadow': 10},
            )
        )
    )
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

    floor = tmp_path / 'verify_backend_release_floor.py'
    floor.write_text(
        'import sys\n'
        'print("ERROR: Backend release floor rejected the target. below floor", file=sys.stderr)\n'
        'sys.exit(1)\n'
    )
    monkeypatch.setattr(canary, 'CloudRunTraffic', Mock(return_value=transport))
    assert canary.main([*base, '--release-floor-check', str(floor)]) == 1
    transport.replace.assert_not_called()


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

    def promote(*args, on_promoted, **kwargs):
        state = transport.read.return_value
        on_promoted(state)
        return state.observed

    monkeypatch.setattr(canary, 'promote', promote)
    target = ['--project', 'example', '--region', 'us-central1', '--promotion-receipt', str(receipt_path)]
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
    floor = tmp_path / 'floor.py'
    floor.write_text('import sys\nsys.exit(0)\n')
    recover = ['recover-run', *target, *identity, '--run-metadata', str(run_path), '--release-floor-check', str(floor)]
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
