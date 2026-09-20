"""Behavioral routing/health contracts; no provider or network access."""

from dataclasses import replace
from unittest.mock import Mock

import fakeredis
import pytest

from config.stt_routing import Preference, RoutingRequest, STREAMING_REGISTRY, rank_candidates
from utils.stt.routing import LiveSTTRoute
from utils.stt.routing_health import Health, RedisHealthStore, claim, fail, transcribed


@pytest.fixture
def anyio_backend():
    return 'asyncio'


@pytest.mark.parametrize('seed', range(64))
def test_selection_properties(seed):
    registry = STREAMING_REGISTRY
    configured = frozenset(spec.provider for spec in registry.values())
    request = RoutingRequest('en', configured)
    policy = tuple(Preference(token, 0, index + 1) for index, token in enumerate(registry))
    first = rank_candidates(request, registry, policy, {'modulate': False}, seed)
    assert first == rank_candidates(request, registry, policy, {'modulate': False}, seed)
    providers = [candidate.provider for candidate in first.candidates]
    assert len(providers) == len(set(providers))
    assert set(providers) == {'soniox', 'deepgram_cloud', 'parakeet'}
    assert ('modulate', 'circuit_open') in first.skipped
    ineligible = rank_candidates(replace(request, channels=2), registry, policy, {}, seed)
    assert not ineligible.candidates
    assert len(ineligible.skipped) == len(policy)


def test_config_order_and_every_skipped_leg_are_explicit():
    policy = tuple(Preference(token, i) for i, token in enumerate(('soniox', 'parakeet', 'dg-nova-3', 'typo')))
    request = RoutingRequest('vi', frozenset({'soniox', 'parakeet'}))
    selection = rank_candidates(request, STREAMING_REGISTRY, policy, {}, 0)
    assert [spec.service for spec in selection.candidates] == ['soniox']
    assert selection.skipped == (
        ('parakeet', 'capability_mismatch'),
        ('deepgram_cloud', 'config_incomplete'),
        ('unknown', 'config_incomplete'),
    )
    english = replace(request, language='en', configured=frozenset({'soniox', 'parakeet', 'deepgram_cloud'}))
    assert [spec.service for spec in rank_candidates(english, STREAMING_REGISTRY, policy, {}, 1).candidates] == [
        'soniox',
        'parakeet',
        'deepgram',
    ]


@pytest.mark.parametrize('reason', ['budget', 'payment', 'quota', 'auth'])
def test_hard_health_immediately_blocks_and_one_transcript_closes_half_open(reason):
    state = fail(Health(), reason, now=100, jitter=0.2)
    assert state.state == 'hard'
    assert not claim(state, now=459, owner='a')[1]
    state, allowed = claim(state, now=460, owner='a')
    assert allowed and state.state == 'half_open'
    assert not claim(state, now=460, owner='b')[1]
    assert transcribed(state, generation=0, owner='a') == state
    assert transcribed(state, generation=state.generation, owner='b') == state
    assert transcribed(state, generation=state.generation, owner='a').state == 'closed'


def test_transient_threshold_probe_lease_and_stale_success_fence():
    state = Health()
    for i in range(3):
        state = fail(state, 'timeout', now=100, jitter=0)
        assert state.state == ('open' if i == 2 else 'closed')
    assert transcribed(state, generation=0, owner='old') == state
    probe, allowed = claim(state, now=130, owner='a')
    assert allowed
    assert not claim(probe, now=159, owner='b')[1]
    second, allowed = claim(probe, now=160, owner='b')
    assert allowed
    assert transcribed(second, generation=second.generation, owner='a') == second


def test_redis_shared_probe_and_failure_fence():
    client = fakeredis.FakeRedis()
    a = RedisHealthStore(client, namespace='test:managed:streaming')
    b = RedisHealthStore(client, namespace='test:managed:streaming')
    a.failure('soniox', 'budget', now=0, jitter=0)
    assert not b.acquire('soniox', now=1, owner='b')[1]
    state, admitted = a.acquire('soniox', now=300, owner='a')
    assert admitted
    assert not b.acquire('soniox', now=300, owner='b')[1]
    b.transcript('soniox', generation=0, owner='old')
    assert not b.acquire('soniox', now=301, owner='b')[1]
    a.transcript('soniox', generation=state.generation, owner='a')
    assert b.acquire('soniox', now=301, owner='b')[1]
    assert 0 < client.ttl('test:managed:streaming:soniox') <= 900


class Socket:
    def __init__(self):
        self.is_connection_dead = False
        self.typed_death_reason = None
        self.finished = False

    def finish(self):
        self.finished = True


@pytest.mark.anyio
async def test_connect_and_mid_session_consume_same_list_and_recover_only_on_content(monkeypatch):
    events = []
    monkeypatch.setattr('utils.stt.routing.record_fallback', lambda **event: events.append(event))
    candidates = tuple(STREAMING_REGISTRY[token] for token in ('modulate-velma-2', 'soniox', 'dg-nova-3'))
    route = LiveSTTRoute(candidates, language='en')
    callbacks, attempts, content = {}, [], []

    async def connect(spec, callback):
        attempts.append(spec.service)
        callbacks[spec.service] = callback
        if spec.service == 'modulate':
            raise TimeoutError()
        return Socket()

    socket, provider = await route.connect(connect, content.extend)
    assert provider.service == 'soniox'
    assert not any(event['outcome'] == 'recovered' for event in events)
    callbacks['soniox']([{'text': '   '}])
    assert not any(event['outcome'] == 'recovered' for event in events)
    callbacks['soniox']([{'text': 'first words'}])
    callbacks['soniox']([{'text': 'more words'}])
    assert sum(event['outcome'] == 'recovered' for event in events) == 1
    socket.is_connection_dead = True
    _, provider = await route.connect(connect, content.extend)
    assert provider.service == 'deepgram'
    callbacks['soniox']([{'text': 'late preserved tail'}])
    assert content[-1]['text'] == 'late preserved tail'
    assert sum(event['outcome'] == 'recovered' for event in events) == 1
    callbacks['deepgram']([{'text': 'recovered'}])
    assert sum(event['outcome'] == 'recovered' for event in events) == 2
    assert attempts == ['modulate', 'soniox', 'deepgram']


@pytest.mark.anyio
async def test_known_down_is_never_connected_and_redis_outage_fails_open(monkeypatch):
    events = []
    monkeypatch.setattr('utils.stt.routing_health.record_fallback', lambda **event: events.append(event))
    client = fakeredis.FakeRedis()
    health = RedisHealthStore(client, namespace='test:managed:streaming')
    health.failure('modulate', 'budget', now=0, jitter=0)
    candidates = tuple(STREAMING_REGISTRY[token] for token in ('modulate-velma-2', 'soniox'))
    attempts = []

    async def connect(spec, callback):
        attempts.append(spec.service)
        return Socket()

    route = LiveSTTRoute(candidates, language='en', health=health, clock=lambda: 1)
    await route.connect(connect, lambda segments: None)
    assert attempts == ['soniox']
    broken = Mock()
    broken.pipeline.side_effect = ConnectionError('offline test')
    route = LiveSTTRoute(candidates, language='en', health=RedisHealthStore(broken, namespace='test'), clock=lambda: 1)
    await route.connect(connect, lambda segments: None)
    assert attempts == ['soniox', 'modulate']
    assert any(event['to_mode'] == 'config_order' and event['outcome'] == 'degraded' for event in events)


@pytest.mark.anyio
async def test_open_socket_does_not_close_probe_but_transcript_receipt_does():
    client = fakeredis.FakeRedis()
    health = RedisHealthStore(client, namespace='test:managed:streaming')
    health.failure('soniox', 'budget', now=0, jitter=0)
    route = LiveSTTRoute((STREAMING_REGISTRY['soniox'],), language='en', health=health, clock=lambda: 300)
    callbacks = []

    async def connect(spec, callback):
        callbacks.append(callback)
        return Socket()

    await route.connect(connect, lambda segments: None)
    assert not health.acquire('soniox', now=301, owner='other')[1]
    callbacks[0]([{'text': ''}])
    await route.flush_health_receipts()
    assert not health.acquire('soniox', now=301, owner='other')[1]
    callbacks[0]([{'text': 'proof'}])
    await route.flush_health_receipts()
    assert health.acquire('soniox', now=301, owner='other')[1]


def test_transient_late_failure_cannot_shorten_budget_quarantine():
    hard = fail(Health(), 'budget', now=100, jitter=0)
    assert fail(hard, 'provider_error', now=101, jitter=0) == hard


def test_typed_account_failures_are_health_inputs():
    from types import SimpleNamespace
    from utils.stt.routing import failure_reason

    from utils.stt.stream_close import PROVIDER_AUTH_REJECTED, PROVIDER_BUDGET_EXHAUSTED

    assert failure_reason(SimpleNamespace(typed_death_reason=PROVIDER_BUDGET_EXHAUSTED)) == 'budget'
    assert failure_reason(SimpleNamespace(status_code=402)) == 'payment'
    assert failure_reason(SimpleNamespace(status_code=401)) == 'auth'
    assert failure_reason(SimpleNamespace(typed_death_reason=PROVIDER_AUTH_REJECTED)) == 'auth'
