"""Owner caching must save reads without turning stale state into custody proof."""

import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from config import home_processing as config
from utils.episodes import home_membership, home_owner_cache as cache, home_processing

NOW = datetime(2026, 11, 8, tzinfo=timezone.utc)
UID = 'owner'
KEY = f'episodes:home_live_owner:v1:{UID}'


class Redis:
    def __init__(self, clock):
        self.clock = clock
        self.values = {}
        self.writes = 0
        self.fail = None

    def get(self, key):
        if self.fail == 'get':
            raise RuntimeError('unavailable')
        value, expiry = self.values.get(key, (None, 0))
        return value if self.clock[0] < expiry else None

    def set(self, key, value, *, ex, nx):
        if self.fail == 'set':
            raise RuntimeError('unavailable')
        assert nx is True
        if self.get(key) is not None:
            return False
        self.values[key] = (value, self.clock[0] + ex)
        self.writes += 1
        return True


@pytest.fixture
def runtime(monkeypatch):
    clock = [1000.0]
    redis = Redis(clock)
    monkeypatch.setattr(cache.time, 'time', lambda: clock[0])
    monkeypatch.setattr(cache, '_redis', lambda: redis)
    monkeypatch.delenv('HOME_LIVE_OWNER_CACHE_ENABLED', raising=False)
    monkeypatch.delenv('HOME_PROCESSING_OWNERSHIP_UIDS', raising=False)
    monkeypatch.setenv('HOME_PROCESSING_OWNERSHIP_ENABLED', 'true')
    monkeypatch.setattr(home_processing, 'episodes_enabled_for', lambda uid: True)
    monkeypatch.setattr(home_processing.client_gate, 'client_seen_cached', lambda uid: True)
    owner = {
        'id': 'e',
        'status': 'live',
        'conversation_ids': ['a', 'b'],
        'started_at': NOW,
        'last_activity_at': NOW + timedelta(minutes=5),
        'title': 'Must never enter Redis',
        'content': 'Must never enter Redis',
    }
    fetch = Mock(return_value=owner)
    monkeypatch.setattr(home_processing.episodes, 'get_current_episode', fetch)
    return SimpleNamespace(clock=clock, redis=redis, owner=owner, fetch=fetch)


def test_miss_hit_expiry_and_uid_isolation(runtime):
    assert home_processing.live_owner_for_home(UID) == runtime.owner
    wire = json.loads(runtime.redis.values[KEY][0])
    assert set(wire['owner']) == set(cache._FIELDS)
    assert wire['valid_until'] == 1030
    assert 'Must never enter Redis' not in runtime.redis.values[KEY][0]
    hit = home_processing.live_owner_for_home(UID)
    assert hit['id'] == 'e'
    row = {'id': 'gap', 'recorded_start': NOW, 'recorded_end': NOW + timedelta(minutes=1)}
    assert home_processing.owns_recording(hit, row)  # ISO dates retain temporal ownership.
    runtime.fetch.assert_called_once_with(UID, firestore_client=None)
    home_processing.live_owner_for_home('different-owner')
    assert runtime.fetch.call_count == 2
    runtime.clock[0] = 1029.99
    home_processing.live_owner_for_home(UID)
    assert runtime.redis.writes == 2  # Hits never refresh TTL.
    runtime.clock[0] = 1030
    home_processing.live_owner_for_home(UID)
    assert runtime.fetch.call_count == 3


@pytest.mark.parametrize('answer', [None, {'id': 'e', 'status': 'closed'}])
def test_no_live_owner_is_cached_without_hiding_rows(runtime, answer):
    runtime.fetch.return_value = answer
    assert home_processing.live_owner_for_home(UID) is None
    assert home_processing.live_owner_for_home(UID) is None
    runtime.fetch.assert_called_once()
    assert json.loads(runtime.redis.values[KEY][0])['owner'] is None
    runtime.clock[0] += cache.TTL_SECONDS
    runtime.fetch.return_value = runtime.owner
    assert home_processing.live_owner_for_home(UID) == runtime.owner


@pytest.mark.parametrize('failure', ['get', 'set'])
def test_redis_error_uses_firestore_not_old_live_state(runtime, failure, monkeypatch):
    home_processing.live_owner_for_home(UID)
    runtime.redis.fail = failure
    runtime.fetch.return_value = None
    if failure == 'set':
        runtime.clock[0] += cache.TTL_SECONDS
    fallback = Mock()
    monkeypatch.setattr(cache, 'record_fallback', fallback)
    assert home_processing.live_owner_for_home(UID) is None
    assert runtime.fetch.call_count == 2
    fallback.assert_called_once()


@pytest.mark.parametrize(
    'raw',
    [
        'not-json',
        '[]',
        '{"owner": {}, "valid_until": 1020}',
        '{"owner": null, "valid_until": 999999}',
        '{"owner": null, "valid_until": NaN}',
    ],
)
def test_invalid_cache_falls_back_to_authority(runtime, raw):
    runtime.redis.values[KEY] = (raw, 1030)
    assert home_processing.live_owner_for_home(UID) == runtime.owner
    runtime.fetch.assert_called_once()


@pytest.mark.parametrize('source', ['cached', 'fetched'])
@pytest.mark.parametrize(
    'malformed',
    [
        pytest.param(42, id='non-dict-owner'),
        pytest.param('', id='empty-owner'),
        pytest.param({'id': 42, 'status': 'live', 'conversation_ids': ['a']}, id='non-string-id'),
        pytest.param({'id': '', 'status': 'live', 'conversation_ids': ['a']}, id='empty-id'),
        pytest.param({'id': 'e', 'status': 'closed', 'conversation_ids': ['a']}, id='non-live-status'),
        pytest.param({'id': 'e', 'status': 'live', 'conversation_ids': 'a'}, id='string-members'),
        pytest.param({'id': 'e', 'status': 'live', 'conversation_ids': {'a': True}}, id='dict-members'),
        pytest.param({'id': 'e', 'status': 'live', 'conversation_ids': None}, id='null-members'),
        pytest.param({'status': 'live', 'conversation_ids': ['a']}, id='missing-id'),
        pytest.param({'id': 'e', 'conversation_ids': ['a']}, id='missing-status'),
        pytest.param({'id': 'e', 'status': 'live'}, id='missing-members'),
    ],
)
def test_malformed_owner_matches_fresh_path_without_hiding_rows(runtime, monkeypatch, source, malformed):
    monkeypatch.setattr(home_membership, 'suppress_held_members', lambda uid, rows, held: rows)
    request = SimpleNamespace(
        headers={
            'X-Omi-Home-Ownership': '1',
            'X-Omi-App-Channel': 'beta',
            home_membership.HELD_EPISODES_HEADER: 'e:a',
        },
        query_params={},
    )
    rows = [{'id': 'a', 'status': 'processing', 'episode_id': 'e'}]
    runtime.fetch.return_value = malformed if source == 'fetched' else None
    monkeypatch.setenv('HOME_LIVE_OWNER_CACHE_ENABLED', 'false')
    fresh_rows = home_membership.project_list(UID, rows, request, None, filtered=False)
    monkeypatch.setenv('HOME_LIVE_OWNER_CACHE_ENABLED', 'true')
    if source == 'cached':
        runtime.redis.values[KEY] = (json.dumps({'owner': malformed, 'valid_until': 1030}), 1030)
    cached_rows = home_membership.project_list(UID, rows, request, None, filtered=False)
    assert cached_rows == fresh_rows == rows
    # A second read also exercises metadata filled from a malformed fresh answer.
    assert home_membership.project_list(UID, rows, request, None, filtered=False) == rows
    assert runtime.fetch.call_count >= 2


@pytest.mark.parametrize(
    'value,enabled',
    [(None, True), ('true', True), (' TRUE ', True), ('false', False), ('off', False), ('', False), ('typo', False)],
)
def test_kill_switch_pattern(monkeypatch, value, enabled):
    if value is None:
        monkeypatch.delenv('HOME_LIVE_OWNER_CACHE_ENABLED', raising=False)
    else:
        monkeypatch.setenv('HOME_LIVE_OWNER_CACHE_ENABLED', value)
    assert config.owner_cache_enabled() is enabled


def test_kill_switch_off_restores_each_current_read_exactly(runtime, monkeypatch):
    home_processing.live_owner_for_home(UID)
    monkeypatch.setenv('HOME_LIVE_OWNER_CACHE_ENABLED', 'false')
    forbidden = Mock(side_effect=AssertionError('cache disabled'))
    monkeypatch.setattr(runtime.redis, 'get', forbidden)
    runtime.fetch.return_value = None
    for _ in range(2):
        assert home_processing.live_owner_for_home(UID) is None
    assert runtime.fetch.call_args_list[-2:] == runtime.fetch.call_args_list[:1] * 2
    assert runtime.fetch.call_count == 3
    forbidden.assert_not_called()


def test_non_home_read_stays_fresh_even_with_warm_cache(runtime):
    home_processing.live_owner_for_home(UID)
    runtime.fetch.return_value = None
    assert home_processing.live_owner(UID) is None
    assert runtime.fetch.call_count == 2


@pytest.mark.parametrize('gate', ['ownership', 'episodes', 'client'])
def test_warm_cache_cannot_bypass_existing_gates(runtime, monkeypatch, gate):
    home_processing.live_owner_for_home(UID)
    if gate == 'ownership':
        monkeypatch.setenv('HOME_PROCESSING_OWNERSHIP_ENABLED', 'false')
    elif gate == 'episodes':
        monkeypatch.setattr(home_processing, 'episodes_enabled_for', lambda uid: False)
    else:
        monkeypatch.setattr(home_processing.client_gate, 'client_seen_cached', lambda uid: False)
    assert home_processing.live_owner_for_home(UID) is None
    runtime.fetch.assert_called_once()


@pytest.mark.parametrize('delay', [5, 31])
def test_slow_firestore_does_not_extend_stale_window(runtime, delay):
    def fetch(*args, **kwargs):
        runtime.clock[0] += delay
        return runtime.owner

    runtime.fetch.side_effect = fetch
    home_processing.live_owner_for_home(UID)
    if delay > cache.TTL_SECONDS:
        assert runtime.redis.writes == 0
    else:
        assert json.loads(runtime.redis.values[KEY][0])['valid_until'] == 1030
        runtime.clock[0] = 1030
        home_processing.live_owner_for_home(UID)
        assert runtime.fetch.call_count == 2  # Embedded deadline beats Redis's later expiry.


@pytest.mark.parametrize('echo', ['', 'other:a', 'e:b', 'malformed', 'e:a'])
def test_stale_live_answer_requires_exact_ack_and_expires(runtime, monkeypatch, echo):
    monkeypatch.setattr(home_membership, 'suppress_held_members', lambda uid, rows, held: rows)
    home_processing.live_owner_for_home(UID)
    runtime.fetch.return_value = None  # Episode closed immediately after the cache fill.
    request = SimpleNamespace(
        headers={
            'X-Omi-Home-Ownership': '1',
            'X-Omi-App-Channel': 'beta',
            home_membership.HELD_EPISODES_HEADER: echo,
        },
        query_params={},
    )
    rows = [{'id': 'a', 'status': 'processing', 'episode_id': 'e'}]
    runtime.clock[0] = 1029.99
    assert home_membership.project_list(UID, rows, request, None, filtered=False) == ([] if echo == 'e:a' else rows)
    runtime.clock[0] = 1030
    assert home_membership.project_list(UID, rows, request, None, filtered=False) == rows


@pytest.mark.parametrize('redis_failure', [False, True])
def test_firestore_error_never_caches_or_hides_a_row(runtime, monkeypatch, redis_failure):
    runtime.fetch.side_effect = RuntimeError('authority unavailable')
    if redis_failure:
        runtime.redis.fail = 'get'
    monkeypatch.setattr(home_membership, 'suppress_held_members', lambda uid, rows, held: rows)
    request = SimpleNamespace(
        headers={
            'X-Omi-Home-Ownership': '1',
            'X-Omi-App-Channel': 'beta',
            home_membership.HELD_EPISODES_HEADER: 'e:a',
        },
        query_params={},
    )
    rows = [{'id': 'a', 'status': 'processing', 'episode_id': 'e'}]
    assert home_membership.project_list(UID, rows, request, None, filtered=False) == rows
    assert runtime.redis.writes == 0


def test_aggregate_lookup_counts_capture_hits_outages_and_bypass(runtime, monkeypatch):
    labels = Mock()
    monkeypatch.setattr(cache, 'LOOKUPS', SimpleNamespace(labels=labels))
    home_processing.live_owner_for_home(UID)  # Cold miss.
    home_processing.live_owner_for_home(UID)  # Hit.
    runtime.redis.fail = 'get'
    home_processing.live_owner_for_home(UID)  # Outage falls back.
    monkeypatch.setenv('HOME_LIVE_OWNER_CACHE_ENABLED', 'false')
    home_processing.live_owner_for_home(UID)  # Rollback.
    assert [call.kwargs['source'] for call in labels.call_args_list] == ['firestore', 'cache', 'firestore', 'firestore']


def test_measured_synthetic_five_second_poll_miss_rate(runtime):
    for second in range(0, 86400, 5):
        runtime.clock[0] = 1000 + second
        home_processing.live_owner_for_home(UID)
    assert runtime.fetch.call_count == 2880
    assert runtime.redis.writes == 2880


def test_redis_stall_falls_through_to_firestore_with_the_fresh_result(runtime, monkeypatch):
    monkeypatch.setattr(home_membership, 'suppress_held_members', lambda uid, rows, held: rows)
    request = SimpleNamespace(
        headers={
            'X-Omi-Home-Ownership': '1',
            'X-Omi-App-Channel': 'beta',
            home_membership.HELD_EPISODES_HEADER: 'e:a',
        },
        query_params={},
    )
    rows = [{'id': 'a', 'status': 'processing', 'episode_id': 'e'}]
    monkeypatch.setenv('HOME_LIVE_OWNER_CACHE_ENABLED', 'false')
    fresh_rows = home_membership.project_list(UID, rows, request, None, filtered=False)
    monkeypatch.setenv('HOME_LIVE_OWNER_CACHE_ENABLED', 'true')

    def stalled(*args, **kwargs):
        raise TimeoutError('redis stalled')

    monkeypatch.setattr(runtime.redis, 'get', stalled)
    monkeypatch.setattr(runtime.redis, 'set', stalled)
    before = runtime.fetch.call_count
    assert home_membership.project_list(UID, rows, request, None, filtered=False) == fresh_rows
    assert runtime.fetch.call_count > before


def test_owner_cache_uses_one_bounded_redis_client(monkeypatch):
    calls = []
    sentinel = object()
    monkeypatch.setattr(cache, '_client', None)
    monkeypatch.setattr(
        cache.redis_db, 'create_bounded_redis_client', lambda timeout: calls.append(timeout) or sentinel
    )
    assert cache._redis() is sentinel
    assert cache._redis() is sentinel
    assert calls == [0.1]


def test_kill_switch_off_never_gets_or_sets_and_uses_fresh_owner(runtime, monkeypatch):
    home_processing.live_owner_for_home(UID)
    monkeypatch.setenv('HOME_LIVE_OWNER_CACHE_ENABLED', 'false')
    get = Mock(side_effect=AssertionError('cache get disabled'))
    set_value = Mock(side_effect=AssertionError('cache set disabled'))
    monkeypatch.setattr(runtime.redis, 'get', get)
    monkeypatch.setattr(runtime.redis, 'set', set_value)
    fresh_owner = dict(runtime.owner, id='new-episode')
    runtime.fetch.side_effect = [fresh_owner, None]
    assert home_processing.live_owner_for_home(UID) is fresh_owner
    assert home_processing.live_owner_for_home(UID) is None
    assert runtime.fetch.call_count == 3
    get.assert_not_called()
    set_value.assert_not_called()
    assert runtime.redis.writes == 1  # Only the initial warm-up wrote metadata.


@pytest.mark.parametrize('delay', [5, 31])
def test_delayed_redis_fill_after_newer_read_cannot_extend_suppression(runtime, monkeypatch, delay):
    monkeypatch.setattr(home_membership, 'suppress_held_members', lambda uid, rows, held: rows)
    set_value = runtime.redis.set

    def delayed_set(key, value, **kwargs):
        runtime.clock[0] = 1001
        runtime.fetch.return_value = None  # The episode closes while the old SET is in flight.
        assert home_processing.live_owner(UID) is None
        runtime.clock[0] = 1000 + delay
        return set_value(key, value, **kwargs)

    monkeypatch.setattr(runtime.redis, 'set', delayed_set)
    assert home_processing.live_owner_for_home(UID) == runtime.owner
    runtime.fetch.assert_called_with(UID, firestore_client=None)
    assert runtime.fetch.call_count == 2
    wire, expiry = runtime.redis.values[KEY]
    assert json.loads(wire)['valid_until'] == 1030
    assert expiry == 1030 + delay
    request = SimpleNamespace(
        headers={
            'X-Omi-Home-Ownership': '1',
            'X-Omi-App-Channel': 'beta',
            home_membership.HELD_EPISODES_HEADER: 'e:a',
        },
        query_params={},
    )
    rows = [{'id': 'a', 'status': 'processing', 'episode_id': 'e'}]
    runtime.clock[0] = max(1030, 1000 + delay)
    assert runtime.redis.get(KEY) == wire  # Redis still retains the delayed stale fill.
    assert home_membership.project_list(UID, rows, request, None, filtered=False) == rows
    assert runtime.fetch.call_count >= 3  # The newer read and project_list's own reads; the stale fill never serves.
    assert runtime.redis.writes == 1
