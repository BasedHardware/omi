"""Offline checks for the Cloud Run hold-back executor, guard and serving helpers.

No test reaches Cloud Run, Cloud Logging or GMP: transports, guards and floor
checks are in-memory fakes, and git fixtures are throwaway repositories.
"""

from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import subprocess
from types import SimpleNamespace

import pytest

from scripts import cloud_run_split_canary as canary
from scripts import guard_eval
from scripts import serving_has
from scripts import serving_revision

ROOT = Path(__file__).resolve().parents[3]


def git(repo, *args):
    return subprocess.run(
        ['git', '-C', str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
        env=dict(
            os.environ,
            GIT_AUTHOR_NAME='t',
            GIT_AUTHOR_EMAIL='t@example.invalid',
            GIT_COMMITTER_NAME='t',
            GIT_COMMITTER_EMAIL='t@example.invalid',
            GIT_CONFIG_GLOBAL='/dev/null',
            GIT_CONFIG_NOSYSTEM='1',
        ),
    ).stdout.strip()


@pytest.fixture
def history(tmp_path):
    repo = tmp_path / 'repo'
    repo.mkdir()
    git(repo, 'init', '-q')
    git(repo, 'commit', '-q', '--allow-empty', '-m', 'first')
    first = git(repo, 'rev-parse', 'HEAD')
    git(repo, 'commit', '-q', '--allow-empty', '-m', 'second')
    second = git(repo, 'rev-parse', 'HEAD')
    return repo, first, second


# serving_has.default_repo


def test_default_repo_falls_back_to_checkout_containing_script(monkeypatch, history):
    repo, _, _ = history
    script = repo / 'backend' / 'scripts' / 'serving_has.py'
    script.parent.mkdir(parents=True)
    monkeypatch.delenv('SERVING_HAS_REPO', raising=False)
    monkeypatch.delenv('OMI_WORKSPACE_ROOT', raising=False)
    monkeypatch.setattr(serving_has, '__file__', str(script))
    assert Path(serving_has.default_repo()).resolve() == repo.resolve()


def test_default_repo_without_git_uses_script_repository_root(monkeypatch, tmp_path):
    script = tmp_path / 'a' / 'checkout' / 'backend' / 'scripts' / 'serving_has.py'
    script.parent.mkdir(parents=True)
    monkeypatch.delenv('SERVING_HAS_REPO', raising=False)
    monkeypatch.delenv('OMI_WORKSPACE_ROOT', raising=False)
    monkeypatch.setattr(serving_has, '__file__', str(script))
    monkeypatch.setattr(serving_has, 'GIT', str(tmp_path / 'missing-git'))
    assert Path(serving_has.default_repo()) == (tmp_path / 'a' / 'checkout').resolve()


def test_default_repo_prefers_explicit_repository(monkeypatch, tmp_path):
    monkeypatch.setenv('SERVING_HAS_REPO', str(tmp_path))
    assert serving_has.default_repo() == str(tmp_path)


# serving_revision --contains


def test_contains_accepts_exact_and_ancestor_releases(history):
    repo, first, second = history
    assert serving_revision.contains_commit(str(repo), second, second)
    assert serving_revision.contains_commit(str(repo), first, second)
    assert serving_revision.contains_commit(str(repo), first[:12], second)


@pytest.mark.parametrize('commit', ['', 'HEAD', '--all', '0' * 40, 'g' * 40])
def test_contains_refuses_descendants_and_unresolved_commits(history, commit):
    repo, first, second = history
    assert not serving_revision.contains_commit(str(repo), second, first)
    assert not serving_revision.contains_commit(str(repo), commit, second)


def test_validate_contains_exact_serving_release_passes(monkeypatch, history):
    repo, _, second = history
    monkeypatch.setattr(serving_revision, 'release_of', lambda *_args: second)
    opts = SimpleNamespace(
        repo=str(repo), latest=False, expected_sha=None, created_after=None, contains=second, service='backend'
    )
    release, _, _ = serving_revision.validate({}, 'backend-1', {'spec': {'containers': [{'env': []}]}}, opts)
    assert release == second
    opts.contains = 'f' * 40
    with pytest.raises(ValueError, match='release_does_not_contain_commit'):
        serving_revision.validate({}, 'backend-1', {'spec': {'containers': [{'env': []}]}}, opts)


# cloud_run_split_canary release floor


class FakeTransport:
    def __init__(self, traffic, tags=()):
        self.tags = tuple(tags)
        self.state = canary.TrafficState('uid', 'etag-0', dict(traffic), dict(traffic), self.tags)
        self.moves = []

    def read(self, timeout=15):
        return self.state

    def replace(self, state, target):
        assert state.etag == self.state.etag
        self.moves.append(dict(target))
        etag = f'etag-{len(self.moves)}'
        self.state = canary.TrafficState('uid', etag, dict(target), dict(target), self.tags)


PLAN = 'holdback-v1;backend-old;backend-old=100;5;7200'
NOW = datetime(2026, 11, 26, 12, 0, tzinfo=timezone.utc)


def run_promote(transport, guard_verdict, floor):
    checked = []

    def floor_check(revision):
        checked.append(revision)
        return floor(revision)

    clock = [NOW]

    def sleep(seconds):
        clock[0] += timedelta(seconds=max(seconds, 0))

    result = None
    error = None
    try:
        result = canary.promote(
            'backend',
            PLAN,
            'backend-new',
            transport,
            lambda *_args: guard_verdict,
            floor_check=floor_check,
            sleep=sleep,
            now=lambda: clock[0],
        )
    except (ValueError, RuntimeError) as exc:
        error = exc
    return result, error, checked


def test_inverse_below_release_floor_refuses_before_any_traffic_move():
    transport = FakeTransport({'backend-old': 100})
    _, error, checked = run_promote(transport, 'TRIP', lambda revision: revision != 'backend-old')
    assert str(error) == 'release_floor_rejected'
    assert checked == ['backend-old']
    assert transport.moves == []


def test_candidate_below_release_floor_refuses_before_any_traffic_move():
    transport = FakeTransport({'backend-old': 100})
    _, error, checked = run_promote(transport, 'PASS', lambda revision: revision != 'backend-new')
    assert str(error) == 'release_floor_rejected'
    assert checked == ['backend-old', 'backend-new']
    assert transport.moves == []


@pytest.mark.parametrize('answer', [None, 1, 'true'])
def test_floor_check_must_answer_exactly_true(answer):
    transport = FakeTransport({'backend-old': 100})
    _, error, _ = run_promote(transport, 'PASS', lambda _revision: answer)
    assert str(error) == 'release_floor_rejected'
    assert transport.moves == []


def test_trip_restores_only_a_floor_checked_inverse():
    transport = FakeTransport({'backend-old': 100})
    _, error, checked = run_promote(transport, 'TRIP', lambda _revision: True)
    assert str(error) == 'holdback_guard_tripped'
    assert checked == ['backend-old', 'backend-new']
    assert transport.moves == [{'backend-new': 95, 'backend-old': 5}, {'backend-old': 100}]


def test_pass_promotes_after_floor_checks():
    transport = FakeTransport({'backend-old': 100})
    result, error, checked = run_promote(transport, 'PASS', lambda _revision: True)
    assert error is None and result == {'backend-new': 100}
    assert checked == ['backend-old', 'backend-new']


def test_below_floor_zero_percent_tagged_revision_refuses_before_any_move():
    # Cloud Run keeps a 0% tagged revision routable through its tag URL, and replace() preserves tags.
    transport = FakeTransport({'backend-old': 100}, tags=(('pinned', 'backend-ancient'), ('stable', 'backend-old')))
    _, error, checked = run_promote(transport, 'PASS', lambda revision: revision != 'backend-ancient')
    assert str(error) == 'release_floor_rejected'
    assert checked == ['backend-ancient']
    assert transport.moves == []


def test_tagged_revisions_are_floor_checked_before_promotion():
    transport = FakeTransport({'backend-old': 100}, tags=(('pinned', 'backend-ancient'),))
    result, error, checked = run_promote(transport, 'PASS', lambda _revision: True)
    assert error is None and result == {'backend-new': 100}
    assert checked == ['backend-ancient', 'backend-old', 'backend-new']


VERIFIER = ROOT / '.github' / 'scripts' / 'verify_backend_release_floor.py'
IMAGE = 'us-central1-docker.pkg.dev/proj/backend/backend@sha256:' + 'a' * 64


@pytest.fixture
def floored(tmp_path):
    """Repository with below -> floor -> above and origin/main publishing the floor."""
    repo = tmp_path / 'floored'
    repo.mkdir()
    git(repo, 'init', '-q')
    git(repo, 'commit', '-q', '--allow-empty', '-m', 'below')
    below = git(repo, 'rev-parse', 'HEAD')
    git(repo, 'commit', '-q', '--allow-empty', '-m', 'floor')
    floor = git(repo, 'rev-parse', 'HEAD')
    (repo / 'backend' / 'deploy').mkdir(parents=True)
    (repo / 'backend' / 'deploy' / 'release_floor.json').write_text(
        json.dumps({'floor': floor, 'reason': 'test floor', 'since': '2026-11-18'})
    )
    git(repo, 'add', '.')
    git(repo, 'commit', '-q', '-m', 'above')
    above = git(repo, 'rev-parse', 'HEAD')
    git(repo, 'update-ref', 'refs/remotes/origin/main', above)
    return repo, below, floor, above


class FakeRegistry:
    def __init__(self, sources):
        self.sources = sources

    def revision(self, image):
        if image not in self.sources:
            raise serving_has.Unknown('image_revision_label_missing')
        return self.sources[image], 'label'


def revision_document(name, image, stamp):
    env = [{'name': 'OMI_BACKEND_RELEASE_SHA', 'value': stamp}]
    return {'metadata': {'name': name}, 'spec': {'containers': [{'image': image, 'env': env}]}}


def floor_check_for(repo, documents, sources, monkeypatch):
    monkeypatch.chdir(repo)
    return canary.release_floor_command(
        VERIFIER,
        'proj',
        'us-central1',
        repo=repo,
        describe=lambda name: documents[name],
        registry=FakeRegistry(sources),
    )


def test_floor_qualified_env_stamp_on_below_floor_image_is_refused(floored, monkeypatch):
    repo, below, _floor, above = floored
    documents = {'backend-stale': revision_document('backend-stale', IMAGE, above)}
    check = floor_check_for(repo, documents, {IMAGE: below}, monkeypatch)
    assert check('backend-stale') is False


def test_floor_passes_on_proven_image_source_even_with_a_stale_stamp(floored, monkeypatch):
    repo, below, floor, above = floored
    documents = {
        'backend-at-floor': revision_document('backend-at-floor', IMAGE, below),
        'backend-above': revision_document('backend-above', IMAGE.replace('a' * 64, 'b' * 64), below),
    }
    sources = {IMAGE: floor, IMAGE.replace('a' * 64, 'b' * 64): above}
    check = floor_check_for(repo, documents, sources, monkeypatch)
    assert check('backend-at-floor') is True
    assert check('backend-above') is True


@pytest.mark.parametrize(
    'document',
    [
        revision_document('backend-other', IMAGE, 'f' * 40),  # describe answered for another revision
        revision_document('backend-x', IMAGE.replace('a' * 64, 'c' * 64), 'f' * 40),  # registry proves nothing
        revision_document('backend-x', 'us-central1-docker.pkg.dev/proj/backend/backend:latest', 'f' * 40),
        {'metadata': {'name': 'backend-x'}, 'spec': {'containers': []}},
    ],
)
def test_unprovable_image_source_fails_closed(floored, monkeypatch, document):
    repo, _below, _floor, above = floored
    check = floor_check_for(repo, {'backend-x': document}, {IMAGE: above}, monkeypatch)
    assert check('backend-x') is False


def test_unresolvable_image_source_commit_fails_closed(floored, monkeypatch):
    repo, *_ = floored
    monkeypatch.setattr(serving_has, 'GIT', 'git')
    documents = {'backend-x': revision_document('backend-x', IMAGE, 'f' * 40)}
    check = floor_check_for(repo, documents, {IMAGE: 'e' * 40}, monkeypatch)
    assert check('backend-x') is False


def test_release_floor_command_passes_only_the_image_source_to_the_verifier(floored):
    repo, below, _floor, above = floored
    calls = []

    def run(argv, timeout):
        calls.append(argv)
        return SimpleNamespace(returncode=0)

    check = canary.release_floor_command(
        Path('/w/verify_backend_release_floor.py'),
        'proj',
        'us-central1',
        repo=repo,
        run=run,
        describe=lambda name: revision_document(name, IMAGE, below),
        registry=FakeRegistry({IMAGE: above}),
    )
    assert check('backend-ok') is True
    assert calls == [[calls[0][0], '-I', '/w/verify_backend_release_floor.py', '--sha', above]]

    def broken(argv, timeout):
        raise subprocess.TimeoutExpired(argv, timeout)

    timed_out = canary.release_floor_command(
        Path('/w/v.py'),
        'proj',
        'us-central1',
        repo=repo,
        run=broken,
        describe=lambda name: revision_document(name, IMAGE, below),
        registry=FakeRegistry({IMAGE: above}),
    )
    assert timed_out('backend-x') is False


def test_promote_cli_requires_release_floor_check():
    with pytest.raises(SystemExit) as exit_info:
        canary.main(
            [
                'promote',
                '--service',
                'backend',
                '--plan',
                PLAN,
                '--binding',
                'x',
                '--candidate',
                'backend-new',
                '--project',
                'p',
                '--region',
                'r',
            ]
        )
    assert exit_info.value.code == 2


# guard_eval sampling and refusals


def side(service_classes, service_logs, routes):
    return {'service': service_classes, 'service_logs': service_logs, 'routes': routes}


def sampled(true_success, true_429, errors):
    """Return (GMP classes, 4xx/5xx service logs, route logs) for one revision's true counts."""
    classes = {'2xx': true_success, '4xx': true_429, '5xx': errors}
    logs = {'500': errors, **({'429': true_429 // 10} if true_429 else {})}
    route = {'200': true_success // 10, **logs}
    return classes, logs, route


def test_identical_5xx_rates_with_different_429_mix_do_not_trip():
    policy = guard_eval.policy_for('backend', ['from-segments'])
    cand = sampled(50_000, 49_000, 1_000)
    inv = sampled(99_000, 0, 1_000)
    result = guard_eval.evaluate(
        policy,
        side(cand[0], cand[1], {'from-segments': cand[2]}),
        side(inv[0], inv[1], {'from-segments': inv[2]}),
    )
    assert result['verdict'] == 'PASS', result
    route = result['checks']['from-segments']
    assert route['candidate']['requests'] == route['inverse']['requests'] == 100_000
    assert route['candidate']['4xx'] == 49_000


def test_real_5xx_regression_still_trips_with_429_mix():
    policy = guard_eval.policy_for('backend', ['from-segments'])
    cand = sampled(46_000, 49_000, 5_000)
    inv = sampled(99_000, 0, 1_000)
    result = guard_eval.evaluate(
        policy,
        side(cand[0], cand[1], {'from-segments': cand[2]}),
        side(inv[0], inv[1], {'from-segments': inv[2]}),
    )
    assert result['verdict'] == 'TRIP', result


def test_guard_policy_requires_rate_limited_log_weight(monkeypatch, tmp_path):
    config = json.loads(guard_eval.CONFIG.read_text())
    assert config['rate_limited_log_weight'] == 10
    del config['rate_limited_log_weight']
    broken = tmp_path / 'guard.json'
    broken.write_text(json.dumps(config))
    monkeypatch.setattr(guard_eval, 'CONFIG', broken)
    with pytest.raises(KeyError):
        guard_eval.policy_for('backend')


def test_sync_dispatch_503s_stay_in_the_error_population():
    config = json.loads(guard_eval.CONFIG.read_text())
    assert 'refusal_statuses' not in config['services']['backend-sync']['sync-local-files']
    policy = guard_eval.policy_for('backend-sync', ['sync-local-files'])
    candidate = side({'5xx': 1_000}, {'503': 1_000}, {'sync-local-files': {'503': 1_000}})
    inverse = side({'2xx': 1_000}, {}, {'sync-local-files': {'200': 100}})
    result = guard_eval.evaluate(policy, candidate, inverse)
    assert result['verdict'] != 'PASS', result
    assert result['verdict'] == 'TRIP'
    assert result['checks']['sync-local-files']['candidate']['excluded_5xx'] == 0
