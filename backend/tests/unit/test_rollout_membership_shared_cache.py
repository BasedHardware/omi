"""Shared observations retain the source lease, including replica-local reuse."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from database import rollout_membership_cache as cache
from utils import rollout_cohorts as runtime


class Redis:
    def __init__(self):
        self.now = 100_000
        self.values = {}
        self.fail = False

    def eval(self, script, keys, key, *args):
        if self.fail:
            raise ConnectionError('unavailable')
        if script == cache._READ:
            value, expiry = self.values.get(key, ('', 0))
            return [value if expiry > self.now else '', self.now]
        assert script == cache._PUBLISH
        value, deadline = args
        if deadline > self.now and (key not in self.values or self.values[key][1] <= self.now):
            self.values[key] = (value, deadline)
            return 1
        return 0


@pytest.fixture
def state(monkeypatch):
    redis = Redis()
    clock = [0.0]
    monkeypatch.setattr(cache, '_redis', lambda: redis)
    monkeypatch.setattr(cache.time, 'monotonic', lambda: clock[0])
    monkeypatch.setenv('ENCRYPTION_SECRET', 'test-membership-cache-secret')
    monkeypatch.delenv('FIRESTORE_EMULATOR_HOST', raising=False)
    monkeypatch.delenv('OMI_ROLLOUT_MEMBERSHIP_SHARED_CACHE_ENABLED', raising=False)
    return redis, clock, SimpleNamespace(project='fixture-project', _database='(default)')


@pytest.mark.parametrize('members', [{}, {'prod': {'batch-pipeline': True, 'first-summary': False}}])
def test_cross_replica_reuse_does_not_renew_sixty_second_expiry(state, monkeypatch, members):
    redis, clock, client = state
    fetch = Mock(return_value=members)
    first = cache.read_memberships_cached('owner', client, fetch)
    assert first == members and first.deadline == 60
    assert all('owner' not in key for key in redis.values)
    assert all(b'batch-pipeline' not in value for value, _ in redis.values.values())
    redis.now += 59_000
    clock[0] = 59
    second = cache.read_memberships_cached('owner', client, fetch)
    assert second == first and second.deadline == 60
    assert fetch.call_count == 1
    # A new process must not add its own sixty-second TTL to a shared hit.
    local = runtime._TTLReads(lambda uid: cache.read_memberships_cached(uid, client, fetch))
    assert local.get('owner') == members
    assert local.entries['owner'].expires == 60
    redis.now += 1000
    clock[0] = 60
    fetch.return_value = {'prod': {'batch-pipeline': False}}
    assert local.get('owner') == fetch.return_value
    assert fetch.call_count == 2


def test_scope_tamper_disabled_and_outage_never_replace_authority(state, monkeypatch):
    redis, clock, client = state
    fetch = Mock(return_value={'prod': {'batch-pipeline': True}})
    cache.read_memberships_cached('owner', client, fetch)
    first_key = next(iter(redis.values))
    cache.read_memberships_cached('other', client, fetch)
    second_key = next(key for key in redis.values if key != first_key)
    redis.values[second_key] = redis.values[first_key]
    fetch.return_value = {}
    assert cache.read_memberships_cached('other', client, fetch) == {}
    assert fetch.call_count == 3
    redis.values[first_key] = ('{"members":{"prod":{"batch-pipeline":true}}}', 160_000)
    assert cache.read_memberships_cached('owner', client, fetch) == {}
    redis.fail = True
    assert cache.read_memberships_cached('owner', client, fetch) == {}
    monkeypatch.setenv('OMI_ROLLOUT_MEMBERSHIP_SHARED_CACHE_ENABLED', 'false')
    assert cache.read_memberships_cached('owner', client, fetch) == {}
    assert fetch.call_count == 6


def test_errors_are_not_shared_and_slow_fills_do_not_extend_age(state):
    redis, clock, client = state
    failed = Mock(side_effect=ValueError('invalid cohort document'))
    with pytest.raises(ValueError):
        cache.read_memberships_cached('owner', client, failed)
    assert not redis.values

    def slow():
        redis.now += 61_000
        clock[0] += 61
        return {}

    value = cache.read_memberships_cached('owner', client, slow)
    assert value.deadline < clock[0] and not redis.values


def test_missing_secret_or_unknown_plane_bypasses_shared_data(state, monkeypatch):
    redis, clock, client = state
    monkeypatch.delenv('ENCRYPTION_SECRET')
    fetch = Mock(return_value={})
    assert cache.read_memberships_cached('owner', client, fetch) == {}
    assert not redis.values
    assert cache.read_memberships_cached('owner', object(), fetch) == {}
    assert fetch.call_count == 2


def test_emulator_planes_do_not_share_matching_project_and_uid(state, monkeypatch):
    redis, clock, client = state
    fetch = Mock(return_value={'prod': {'batch-pipeline': True}})
    for endpoint in ('localhost:8081', 'localhost:8082'):
        monkeypatch.setenv('FIRESTORE_EMULATOR_HOST', endpoint)
        assert cache.read_memberships_cached('owner', client, fetch) == fetch.return_value
    assert fetch.call_count == 2 and not redis.values
