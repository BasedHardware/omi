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
    def __init__(self, traffic):
        self.state = canary.TrafficState('uid', 'etag-0', dict(traffic), dict(traffic))
        self.moves = []

    def read(self, timeout=15):
        return self.state

    def replace(self, state, target):
        assert state.etag == self.state.etag
        self.moves.append(dict(target))
        etag = f'etag-{len(self.moves)}'
        self.state = canary.TrafficState('uid', etag, dict(target), dict(target))


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


def test_release_floor_command_runs_reviewed_verifier():
    calls = []

    def run(argv, timeout):
        calls.append(argv)
        return SimpleNamespace(returncode=0 if argv[-5] == 'backend-ok' else 1)

    check = canary.release_floor_command(Path('/w/verify_backend_release_floor.py'), 'proj', 'us-central1', run=run)
    assert check('backend-ok') is True
    assert check('backend-old') is False
    assert calls[0][1:] == [
        '-I',
        '/w/verify_backend_release_floor.py',
        '--revision',
        'backend-ok',
        '--project',
        'proj',
        '--region',
        'us-central1',
    ]

    def broken(argv, timeout):
        raise subprocess.TimeoutExpired(argv, timeout)

    assert canary.release_floor_command(Path('/w/v.py'), 'proj', 'us-central1', run=broken)('backend-x') is False


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
