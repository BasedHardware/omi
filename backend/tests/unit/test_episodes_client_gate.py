"""Episode work needs an admitted uid and a capable client; the episodes API is what marks the client."""

import asyncio
from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from prometheus_client import REGISTRY

from config import episodes as config
from database import redis_db
from routers import episodes as router_module
from utils.conversations import finalizer
from utils.conversations.processing_trigger import ProcessingTrigger
from utils.episodes import client_gate, live, service
from utils.episodes.live import MomentTracker
from utils.episodes.moment import MomentInput
from utils.other import endpoints as auth

T0 = datetime(2026, 10, 20, 10, 0, tzinfo=timezone.utc)
KEY = 'episodes:client_seen:{}'


class FakeRedis:
    """The three marker operations, with a settable clock for TTLs."""

    def __init__(self):
        self.now = 0.0
        self.store = {}
        self.sets = []
        self.fail_writes = False

    def _live(self, key):
        item = self.store.get(key)
        if item is None or item[1] <= self.now:
            self.store.pop(key, None)
            return None
        return item

    def exists(self, key):
        return 1 if self._live(key) else 0

    def ttl(self, key):
        item = self._live(key)
        return -2 if item is None else int(item[1] - self.now)

    def set(self, key, value, ex=None):
        if self.fail_writes:
            raise ConnectionError('redis down')
        self.sets.append((key, ex))
        self.store[key] = (value, self.now + ex)
        return True


@pytest.fixture
def fake_redis(monkeypatch):
    fake = FakeRedis()
    monkeypatch.setattr(redis_db, 'r', fake)
    client_gate.reset_for_tests()
    live.sessions.clear()
    yield fake
    client_gate.reset_for_tests()
    live.sessions.clear()


@pytest.fixture(autouse=True)
def _admitted_by_default(monkeypatch):
    monkeypatch.delenv(config.EPISODES_ENABLED_ENV, raising=False)
    monkeypatch.delenv(config.EPISODES_PERCENT_ENV, raising=False)
    monkeypatch.delenv(config.EPISODES_UID_ALLOWLIST_ENV, raising=False)
    monkeypatch.delenv(config.EPISODES_CLIENT_CHANNELS_ENV, raising=False)


def _sample(name, **labels):
    return REGISTRY.get_sample_value(name, labels) or 0.0


def _moment(conversation_id='c1', trigger='pause'):
    return MomentInput(
        conversation_id=conversation_id,
        source='omi',
        segments=[{'text': 'word ' * 30, 'start': 0.0, 'end': 10.0}],
        started_at=T0,
        ended_at=T0,
        trigger=trigger,
    )


async def _inline(_executor, function, *args, **kwargs):
    return function(*args, **kwargs)


def _run_moment(monkeypatch, uid, moment=None):
    """Drives one ended moment through the live gate; returns the uids record_moment ran for."""
    ran = []
    monkeypatch.setattr(live.executors, 'run_blocking', _inline)
    monkeypatch.setattr(service, 'record_moment', lambda u, m: ran.append(u) or 'applied')
    outcome = asyncio.run(live._moment_if_client_seen(uid, moment or _moment()))
    return ran, outcome


# --------------------------------------------------------------------------- the API sets the marker


@pytest.fixture
def http(monkeypatch):
    app = FastAPI()
    app.include_router(router_module.router)
    app.dependency_overrides[auth.get_current_user_uid] = lambda: 'uid-1'
    for route in app.routes:
        for dependency in getattr(getattr(route, 'dependant', None), 'dependencies', []):
            app.dependency_overrides[dependency.call] = lambda: 'uid-1'
    monkeypatch.setattr(router_module.service, 'live_episode', lambda uid: None)
    monkeypatch.setattr(router_module.service, 'episode_for_conversation', lambda uid, cid: None)
    return TestClient(app, headers={'X-Omi-App-Channel': 'beta'})


def test_an_api_call_sets_the_marker_once_and_polling_does_not_rewrite_it(fake_redis, http):
    assert http.get('/v1/episodes/live').json() == {'enabled': True, 'episode': None}
    assert fake_redis.sets == [(KEY.format('uid-1'), config.CLIENT_SEEN_TTL_SECONDS)]
    assert client_gate.client_seen('uid-1') is True
    # The app polls every 30 s while a live surface is on screen: no further writes this hour.
    for _ in range(5):
        http.get('/v1/episodes/live')
    http.get('/v1/episodes/by-conversation/c1')
    assert len(fake_redis.sets) == 1


def test_refresh_is_at_most_hourly_across_replicas(fake_redis):
    assert client_gate.note_client_seen('u', now=0) is True
    assert client_gate.note_client_seen('u', now=config.CLIENT_SEEN_REFRESH_SECONDS - 1) is False
    # Another replica (no memo) within the hour sees a fresh TTL and skips the write.
    client_gate.reset_for_tests()
    fake_redis.now = 600
    assert client_gate.note_client_seen('u', now=600) is False
    # An hour after that replica's check, the next call refreshes the 14-day TTL.
    fake_redis.now = 600 + config.CLIENT_SEEN_REFRESH_SECONDS
    assert client_gate.note_client_seen('u', now=fake_redis.now) is True
    assert fake_redis.ttl(KEY.format('u')) == config.CLIENT_SEEN_TTL_SECONDS
    assert len(fake_redis.sets) == 2


def test_the_marker_expires_without_calls(fake_redis):
    client_gate.note_client_seen('u', now=0)
    fake_redis.now = config.CLIENT_SEEN_TTL_SECONDS + 1
    assert client_gate.client_seen('u') is False


def test_a_failed_write_is_retried_on_the_next_call(fake_redis):
    fake_redis.fail_writes = True
    assert client_gate.note_client_seen('u', now=0) is False
    fake_redis.fail_writes = False
    assert client_gate.note_client_seen('u', now=30) is True


def test_an_unadmitted_caller_leaves_no_marker(fake_redis, http, monkeypatch):
    monkeypatch.setenv(config.EPISODES_ENABLED_ENV, 'off')
    assert http.get('/v1/episodes/live').json() == {'enabled': False, 'episode': None}
    assert fake_redis.sets == []


# --------------------------------------------------------------------------- the client channel is the cohort


@pytest.mark.parametrize(
    'headers', [{'X-Omi-App-Channel': 'store'}, {'X-Omi-App-Channel': 'nightly'}, {'X-Omi-App-Channel': ''}, None]
)
def test_store_missing_or_unknown_channels_see_no_episodes_and_leave_no_marker(fake_redis, http, monkeypatch, headers):
    monkeypatch.setattr(router_module.service, 'live_episode', lambda uid: pytest.fail('must not read'))
    request = {'headers': headers} if headers is not None else {}
    if headers is None:
        http.headers.pop('X-Omi-App-Channel', None)
    assert http.get('/v1/episodes/live', **request).json() == {'enabled': False, 'episode': None}
    assert http.get('/v1/episodes/by-conversation/c1', **request).json() == {'enabled': False, 'episode': None}
    assert http.post('/v1/episodes/e1/wrap-up', json={}, **request).status_code == 404
    assert fake_redis.sets == []
    assert client_gate.client_seen('uid-1') is False


def test_beta_channel_is_admitted_by_default_and_store_by_config(fake_redis, http, monkeypatch):
    beta = _sample('omi_episode_client_requests_total', channel='beta', outcome='admitted')
    store_closed = _sample('omi_episode_client_requests_total', channel='store', outcome='channel_closed')
    assert http.get('/v1/episodes/live', headers={'X-Omi-App-Channel': 'BETA'}).json()['enabled'] is True
    assert http.get('/v1/episodes/live', headers={'X-Omi-App-Channel': 'store'}).json()['enabled'] is False
    assert _sample('omi_episode_client_requests_total', channel='beta', outcome='admitted') == beta + 1
    assert _sample('omi_episode_client_requests_total', channel='store', outcome='channel_closed') == store_closed + 1
    monkeypatch.setenv(config.EPISODES_CLIENT_CHANNELS_ENV, 'beta,store')
    assert http.get('/v1/episodes/live', headers={'X-Omi-App-Channel': 'store'}).json()['enabled'] is True


def test_channel_config_parsing(monkeypatch):
    monkeypatch.delenv(config.EPISODES_CLIENT_CHANNELS_ENV, raising=False)
    assert config.episodes_client_channels() == {'beta'}
    monkeypatch.setenv(config.EPISODES_CLIENT_CHANNELS_ENV, '  ')
    assert config.episodes_client_channels() == {'beta'}
    monkeypatch.setenv(config.EPISODES_CLIENT_CHANNELS_ENV, ' Beta , STORE, unknown ')
    assert config.episodes_client_channels() == {'beta', 'store'}
    monkeypatch.setenv(config.EPISODES_CLIENT_CHANNELS_ENV, 'nonsense')
    assert config.episodes_client_channels() == frozenset()
    assert config.client_channel_admitted('beta') is False
    monkeypatch.setenv(config.EPISODES_CLIENT_CHANNELS_ENV, 'beta')
    assert config.client_channel_admitted(None) is False
    assert config.client_channel_admitted('unknown') is False
    assert config.app_channel(' Store ') == 'store'
    assert config.app_channel('x' * 500) == 'unknown'


# --------------------------------------------------------------------------- listen spends only with a marker


def test_no_marker_means_no_moment_work(fake_redis, monkeypatch):
    skipped = _sample('omi_episode_moments_skipped_no_client_total', trigger='pause')
    ran, outcome = _run_moment(monkeypatch, 'old-client')
    assert ran == [] and outcome == 'skipped_no_client'
    assert _sample('omi_episode_moments_skipped_no_client_total', trigger='pause') == skipped + 1


def test_marker_and_admission_mean_moment_work(fake_redis, monkeypatch):
    client_gate.note_client_seen('new-client', now=0)
    ran, outcome = _run_moment(monkeypatch, 'new-client')
    assert ran == ['new-client'] and outcome == 'applied'


def _run_attach(monkeypatch, uid):
    attached = []
    monkeypatch.setattr(live.executors, 'run_blocking', _inline)
    monkeypatch.setattr(service, 'attach_conversation', lambda u, cid, source, **k: attached.append(cid) or 'opened')
    return attached, asyncio.run(live._attach_if_client_seen(uid, 'c1', 'omi', T0))


def test_attach_counts_the_session_and_needs_the_marker(fake_redis, monkeypatch):
    unseen = _sample('omi_episode_live_sessions_total', client_seen='false')
    skipped = _sample('omi_episode_moments_skipped_no_client_total', trigger='attach')
    assert _run_attach(monkeypatch, 'old-client') == ([], 'skipped_no_client')
    assert _sample('omi_episode_live_sessions_total', client_seen='false') == unseen + 1
    assert _sample('omi_episode_moments_skipped_no_client_total', trigger='attach') == skipped + 1
    client_gate.note_client_seen('new-client', now=0)
    seen = _sample('omi_episode_live_sessions_total', client_seen='true')
    assert _run_attach(monkeypatch, 'new-client') == (['c1'], 'opened')
    assert _sample('omi_episode_live_sessions_total', client_seen='true') == seen + 1


def test_the_capability_read_is_cached_briefly(fake_redis, monkeypatch):
    reads = []
    real = client_gate.client_seen
    monkeypatch.setattr(client_gate, 'client_seen', lambda uid: reads.append(uid) or real(uid))
    assert client_gate.client_seen_cached('u', now=0) is False
    assert client_gate.client_seen_cached('u', now=client_gate.SEEN_CACHE_SECONDS - 1) is False
    assert reads == ['u']
    assert client_gate.client_seen_cached('u', now=client_gate.SEEN_CACHE_SECONDS) is False
    assert reads == ['u', 'u']


def test_realtime_batches_reach_the_gate_only_when_admitted(fake_redis, monkeypatch):
    client_gate.note_client_seen('u', now=0)
    tracker = MomentTracker()
    monkeypatch.setattr(live, 'tracker', tracker)
    scheduled = {}
    monkeypatch.setattr(live.executors, 'start_background_task', lambda coro, *, name: scheduled.setdefault(name, coro))
    live.sessions.clear()
    tracker.observe('u', [{'text': 'word ' * 30}], 'c1', 'omi', now=0)
    monkeypatch.setattr(live.time, 'time', lambda: 1000.0)
    asyncio.run(live.on_realtime_segments('u', [{'text': 'more'}], 'c2', 'omi'))
    assert sorted(scheduled) == ['episode_attach', 'episode_moment']
    scheduled.pop('episode_attach').close()
    ran = []
    monkeypatch.setattr(live.executors, 'run_blocking', _inline)
    monkeypatch.setattr(service, 'record_moment', lambda u, m: ran.append(u) or 'applied')
    asyncio.run(scheduled['episode_moment'])
    assert ran == ['u']


def test_the_allowlist_bypasses_the_percentage_but_not_the_marker(fake_redis, monkeypatch):
    monkeypatch.setenv(config.EPISODES_PERCENT_ENV, '0')
    monkeypatch.setenv(config.EPISODES_UID_ALLOWLIST_ENV, 'david')
    assert config.episodes_enabled_for('david') is True
    assert client_gate.episode_work_enabled('david') is False
    assert _run_moment(monkeypatch, 'david')[0] == []
    client_gate.note_client_seen('david', now=0)
    assert client_gate.episode_work_enabled('david') is True
    assert _run_moment(monkeypatch, 'david')[0] == ['david']


def test_a_redis_fault_reads_as_no_capable_client(monkeypatch):
    class Down:
        def exists(self, key):
            raise ConnectionError('redis down')

    monkeypatch.setattr(redis_db, 'r', Down())
    assert client_gate.client_seen('u') is False


# --------------------------------------------------------------------------- the finalizer spends only with a marker


def test_finalization_without_a_marker_skips_tail_and_reconciliation(fake_redis, monkeypatch):
    monkeypatch.setattr(
        service.episodes_db, 'get_episode_for_conversation', lambda *a, **k: pytest.fail('must not read')
    )
    skipped = _sample('omi_episode_moments_skipped_no_client_total', trigger='finalize')
    row = {'id': 'c1', 'transcript_segments': [{'text': 'hello', 'start': 0, 'end': 1}], 'started_at': T0}
    assert service.on_conversation_finalized('u', 'c1', row, trigger='capture_end') == 'skipped_no_client'
    assert _sample('omi_episode_moments_skipped_no_client_total', trigger='finalize') == skipped + 1


def test_absorb_without_a_marker_reads_no_donor(fake_redis, monkeypatch):
    reads = []

    async def recorder(_executor, function, *args, **kwargs):
        if function is finalizer.conversations_db.get_conversation:
            reads.append(args)
            return None
        return function(*args, **kwargs)

    monkeypatch.setattr(finalizer, 'run_blocking', recorder)
    asyncio.run(finalizer._episode_after_absorb('u', 'n', ProcessingTrigger.CAPTURE_END))
    assert reads == []
    client_gate.note_client_seen('u', now=0)
    asyncio.run(finalizer._episode_after_absorb('u', 'n', ProcessingTrigger.CAPTURE_END))
    assert reads == [('u', 'n')]


def test_mentor_state_needs_a_capable_client(fake_redis, monkeypatch):
    monkeypatch.setattr(service, 'live_episode', lambda uid: pytest.fail('must not read'))
    assert service.mentor_episode_state('u') is None
