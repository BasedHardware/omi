"""Exercise split release guard accounting, recovery custody and checkout lookup."""

from dataclasses import replace
import hashlib
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

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
