"""Pipeline-free simulation of the 2026-10-20 listen rolling-restart incident.

Shape (prod, listen 5482752): a 13:37Z roll produced a burst of Soniox
``connection_lost`` deaths on draining pods; the CUSUM burst detector benched
Soniox at a 2.2% lifetime failure rate; the cooldown left it at stage 5 with
parakeet-window at 5 and Modulate benched at 0. With no target at stage 100
the availability escape put every target, benched Modulate included, in every
chain, and trial votes from outside the 5% re-entry cohort were discarded, so
Soniox could not promote for hours. Exhaustion stayed ~10%, partly Soniox
connect blips with no permitted successor.

Each section runs with its kill switch on (fixed) and off (incident).
"""

import hashlib
import json
import random
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from config import live_stt_state
from config.live_stt_registry import DEFAULT_TARGETS
from tests.unit.test_live_cost_router import MemoryRedis, controls, seed_cost_interest  # noqa: F401 -- autouse fixture
from utils.stt import live_chain, live_health, live_recovery, pod_drain, streaming as st
from utils.stt.live_gate import GateState, transition
from utils.stt.live_outcome import LiveLegOutcome
from utils.stt.live_retry import same_target_retry_allowed
from utils.stt.live_router import propose, select
from utils.stt.live_signal import provider_observation
from utils.stt import provider_resilience
from utils.stt.provider_resilience import ProviderCircuitBreaker

PARAKEET, MODULATE, SONIOX = DEFAULT_TARGETS
INCIDENT_STATES = {
    'soniox': GateState(stage=5),
    'parakeet-window': GateState(stage=5),
    'modulate-velma-2': GateState(stage=0),
}


def _uid(i: int) -> str:
    return f'sim-user-{i:05d}'


@pytest.fixture
def anyio_backend():
    return 'asyncio'


@pytest.fixture
def draining(monkeypatch):
    monkeypatch.setattr(pod_drain, '_draining', False)
    return pod_drain


# --- 1. A restart drain cannot bench a healthy provider -----------------------------------


def _warm_soniox(now: float) -> GateState:
    """A healthy Soniox gate: ~2.2% lifetime failures across many users."""
    state = GateState()
    rng = random.Random(7)
    for i in range(400):
        state = transition(state, rng.random() < 0.022, now, witness=f'{i:016x}')
    assert state.stage == 100
    return state


def _restart_burst(draining_module, state: GateState, deaths: int, now: float) -> GateState:
    """Every in-flight Soniox leg on the draining pods dies with connection_lost."""
    box = {'state': state}

    def record(target, language, outcome, generations, uid, reason):
        failed = provider_observation(outcome, reason)
        if failed is not None:
            box['state'] = transition(box['state'], failed, now, witness=hashlib.sha256(uid.encode()).hexdigest()[:16])
        return True

    draining_module.mark_draining()
    for i in range(deaths):
        leg = LiveLegOutcome('soniox', 'en', _uid(i), None, record)
        leg.observe_death()
        leg.claim('connection_lost')
        leg.settle()
    return box['state']


@pytest.mark.parametrize('enabled', [True, False])
def test_sim_restart_burst_does_not_bench_soniox(monkeypatch, draining, enabled):
    monkeypatch.setenv('LISTEN_STT_DRAIN_DEATH_CENSOR_ENABLED', 'true' if enabled else 'false')
    state = _restart_burst(draining, _warm_soniox(1000.0), deaths=40, now=1000.0)
    if enabled:
        assert state.stage == 100 and state.strikes == 0
    else:
        assert state.stage == 0  # the incident: a 2.2% provider benched by our own roll


def test_a_death_observed_before_sigterm_stays_evidence(draining):
    seen = []
    leg = LiveLegOutcome('soniox', 'en', _uid(1), None, lambda *args: seen.append(args) or True)
    leg.observe_death()
    draining.mark_draining()
    leg.claim('connection_lost')
    leg.settle()
    assert [args[2:] for args in seen] == [('failover', None, _uid(1), 'connection_lost')]


def test_drain_censors_connect_rejections_too(draining):
    seen = []
    draining.mark_draining()
    leg = LiveLegOutcome('soniox', 'en', _uid(1), None, lambda *args: seen.append(args) or True)
    assert leg.claim('timeout', connect=True) == 'normal_close'
    leg.settle()
    assert provider_observation(seen[0][2], seen[0][5]) is None


# --- 2. The escape never re-admits a benched target beside a stage>0 one -----------------


@pytest.mark.parametrize('enabled', [True, False])
def test_sim_escape_keeps_benched_modulate_out_of_the_chain(monkeypatch, enabled):
    monkeypatch.setenv('LISTEN_STT_ESCAPE_EXCLUDES_BENCHED_ENABLED', 'true' if enabled else 'false')
    health = SimpleNamespace(
        cached_snapshot=lambda *_: {},
        cost_snapshot=lambda targets, _language: {t.id: INCIDENT_STATES[t.id] for t in targets},
        prefer_recovery=lambda *_: None,
    )
    users = [_uid(i) for i in range(200)]
    with_modulate = 0
    for uid in users:
        last_resorts, decision = [], {}
        proposed = propose(
            health,
            ['parakeet', 'modulate', 'soniox'],
            uid,
            'en',
            'parakeet',
            {},
            (),
            {'parakeet': 'parakeet-window'},
            last_resorts,
            decision=decision,
        )
        assert decision['escape'] is True
        chain = [t.id for t in (*proposed, *last_resorts)]
        stages = [INCIDENT_STATES[t].stage for t in chain]
        assert stages == sorted(stages, reverse=True)  # strictly stage-ordered
        with_modulate += 'modulate-velma-2' in chain
    assert with_modulate == (0 if enabled else len(users))


def test_escape_still_serves_a_benched_target_when_it_is_the_only_one(monkeypatch):
    states = {'modulate-velma-2': GateState(stage=0), 'soniox': GateState(stage=0)}
    result = select([MODULATE, SONIOX], states, _uid(3), 'en')
    assert [t.id for t in result] == ['modulate-velma-2', 'soniox']


@pytest.mark.asyncio
async def test_escape_configured_tail_does_not_reappend_benched_family(monkeypatch):
    monkeypatch.setenv('STT_ROUTING_MODE', 'on')
    monkeypatch.setenv('STT_ROUTING_ON_PERCENT', '100')
    monkeypatch.setattr(
        live_chain.health,
        'cost_snapshot',
        lambda targets, _language: {t.id: INCIDENT_STATES[t.id] for t in targets},
    )
    dead = SimpleNamespace(is_connection_dead=True, finish=lambda: None, death_reason=None, typed_death_reason=None)
    soniox = AsyncMock(return_value=dead)
    modulate = AsyncMock(return_value=SimpleNamespace(is_connection_dead=False, finish=lambda: None))
    monkeypatch.setenv('LISTEN_STT_SAME_TARGET_RETRY_ENABLED', 'false')
    with pytest.raises(live_chain.LiveChainExhausted):
        await live_chain.connect_configured_chain(
            primary_service=st.STTService.soniox,
            connect_primary=soniox,
            callbacks={st.STTService.modulate: modulate},
            failed=set(),
            models=['soniox', 'modulate-velma-2'],
            routing_uid=_uid(4),
            routing_language='ja',
        )
    modulate.assert_not_called()


# --- 3. A recovering provider promotes from votes the escape already collects ----------------


async def _minutes_to_full(monkeypatch, enabled: bool, horizon_minutes: int = 30) -> float | None:
    monkeypatch.setenv('LISTEN_STT_ESCAPE_TRIAL_VOTES_ENABLED', 'true' if enabled else 'false')
    now = [10_000.0]
    redis = MemoryRedis(clock=lambda: now[0])
    for target, state in (
        (SONIOX, GateState(stage=5, generation=1, trial_started_at=now[0])),
        (PARAKEET, GateState(stage=5, generation=1, trial_started_at=now[0])),
        (MODULATE, GateState(stage=0, generation=1, until=now[0] + 14_400)),
    ):
        for lang in ('all', 'en'):
            redis.data[live_stt_state.cost_key(target, lang)] = json.dumps(state.encode())
    pod = live_health.FleetHealth(redis_client=redis, clock=lambda: now[0])
    seed_cost_interest(pod, DEFAULT_TARGETS, 'en')
    await pod.refresh_cost_once()
    pending = []
    pod.schedule = lambda coroutine, **_labels: pending.append(coroutine)
    rng = random.Random(11)
    # ~6 Soniox sessions a minute on this slice of the fleet; 2% provider failures.
    for step in range(horizon_minutes * 6):
        now[0] += 10
        uid = _uid(rng.randrange(3000))
        failed = rng.random() < 0.02
        generations = pod.cost_generations('soniox', 'en')
        pod.record_session(
            'soniox', 'en', 'failover' if failed else 'text', generations, uid, 'connection_lost' if failed else 'text'
        )
        while pending:
            await pending.pop()
        if step % 6 == 5:  # pods MGET the shared state periodically
            await pod.refresh_cost_once()
        if pod.cost_stage('soniox', 'en') == 100:
            return (step + 1) / 6
    return None


@pytest.mark.asyncio
async def test_sim_soniox_promotes_within_twenty_minutes_of_the_escape(monkeypatch):
    fixed = await _minutes_to_full(monkeypatch, enabled=True)
    print(f'sim promotion: stage 5 -> 100 in {fixed} min with escape votes')
    assert fixed is not None and fixed <= 20  # 5 min at stage 5, 10 min at stage 25, plus votes
    # The incident: cohort-only votes starve promotion for hours.
    assert await _minutes_to_full(monkeypatch, enabled=False, horizon_minutes=20) is None


@pytest.mark.asyncio
async def test_out_of_cohort_votes_stay_dropped_when_a_stage_100_target_serves(monkeypatch):
    # Pre-existing contract: outside the escape, only the re-entry cohort votes.
    redis = MemoryRedis()
    trial = GateState(stage=5, generation=1)
    for lang in ('all', 'en'):
        redis.data[live_stt_state.cost_key(PARAKEET, lang)] = json.dumps(trial.encode())
    pod = live_health.FleetHealth(redis_client=redis, clock=lambda: 1000)
    seed_cost_interest(pod, DEFAULT_TARGETS, 'en')
    await pod.refresh_cost_once()
    pending = []
    pod.schedule = lambda coroutine, **_labels: pending.append(coroutine)
    for i in range(60):
        pod.record_session('parakeet-window', 'en', 'text', {'all': 1, 'en': 1}, _uid(i))
        await pending.pop()
    assert pod._cost_cached[('parakeet-window', 'all')].n < 60


# --- 4. One jittered same-target retry turns connect blips into service ----------------------


async def _exhaustion_rate(monkeypatch, enabled: bool, sessions: int = 300, blip: float = 0.10) -> float:
    monkeypatch.setenv('LISTEN_STT_SAME_TARGET_RETRY_ENABLED', 'true' if enabled else 'false')
    monkeypatch.setattr(live_chain, 'retry_jitter_seconds', lambda: 0.0)
    monkeypatch.setattr(provider_resilience, 'STT_FALLBACK_LIVENESS_GRACE_SECONDS', 0)
    rng = random.Random(23)
    exhausted = 0

    async def connect():
        if rng.random() < blip:
            return SimpleNamespace(
                is_connection_dead=True, finish=lambda: None, death_reason=None, typed_death_reason=None
            )
        return SimpleNamespace(is_connection_dead=False, finish=lambda: None)

    for _ in range(sessions):
        # Each session sees a fresh pod-local circuit; blips are independent.
        monkeypatch.setattr(st, '_soniox_circuit', ProviderCircuitBreaker(failure_threshold=3, cooldown_seconds=30))
        try:
            # ja: Parakeet cannot serve it and Modulate is benched, so Soniox
            # has no permitted successor (the 15:05Z soniox->unavailable mode).
            await live_chain.connect_configured_chain(
                primary_service=st.STTService.soniox,
                connect_primary=connect,
                callbacks={},
                failed=set(),
                models=['soniox'],
                routing_uid=None,
                routing_language='ja',
            )
        except (live_chain.LiveChainExhausted, RuntimeError):
            exhausted += 1
    return exhausted / sessions


@pytest.mark.asyncio
async def test_sim_same_target_retry_cuts_exhaustion(monkeypatch):
    without = await _exhaustion_rate(monkeypatch, enabled=False)
    with_retry = await _exhaustion_rate(monkeypatch, enabled=True)
    print(f'sim exhaustion: {without:.1%} without retry, {with_retry:.1%} with retry')
    assert 0.06 <= without <= 0.14  # ~blip rate: every blip exhausts
    assert with_retry <= without / 3  # ~blip^2


@pytest.mark.parametrize(
    'reason,text_seen,stage,circuit_open,already,expected',
    [
        ('connection_lost', False, 100, False, False, True),
        ('timeout', False, 5, False, False, True),
        ('send_failed', False, 25, False, False, True),
        ('connection_lost', True, 100, False, False, False),  # died after text: ordinary failover
        ('connection_lost', None, 100, False, False, False),  # unknown text state
        ('connection_lost', False, 0, False, False, False),  # benched
        ('connection_lost', False, 100, True, False, False),  # circuit open
        ('connection_lost', False, 100, False, True, False),  # once only
        ('provider_5xx', False, 100, False, False, False),
        ('provider_429', False, 100, False, False, False),
        ('capacity_full', False, 100, False, False, False),
    ],
)
def test_same_target_retry_policy(reason, text_seen, stage, circuit_open, already, expected):
    assert (
        same_target_retry_allowed(
            reason, text_seen=text_seen, stage=stage, circuit_open=circuit_open, already_retried=already
        )
        is expected
    )


def _dead_managed_receiver(reason='connection_lost', text_seen=False):
    socket = SimpleNamespace(
        routing_target='soniox',
        leg_outcome=SimpleNamespace(text_seen=lambda: text_seen),
        normalized_death_reason=reason,
    )
    recovery = SimpleNamespace(granted=[], jitter={})
    recovery.grant_transient_retry = lambda identity: recovery.granted.append(identity) or True
    recovery.note_retry_jitter = lambda identity, seconds: recovery.jitter.__setitem__(identity, seconds)
    return SimpleNamespace(
        stt_socket=socket,
        host=SimpleNamespace(language='ja'),
        recovery=recovery,
        _stt_failed_providers={'soniox'},
        _stt_failed_targets={'soniox'},
    )


def test_mid_session_transport_death_before_text_readmits_once(monkeypatch):
    receiver = _dead_managed_receiver()
    assert live_recovery.allow_same_target_retry(receiver, 'soniox', 'connection_lost', managed=True)
    assert 'soniox' not in receiver._stt_failed_providers and 'soniox' not in receiver._stt_failed_targets
    assert receiver.recovery.granted == ['soniox'] and 0.1 <= receiver.recovery.jitter['soniox'] <= 0.5
    receiver._stt_failed_providers.add('soniox')
    assert not live_recovery.allow_same_target_retry(receiver, 'soniox', 'connection_lost', managed=True)


@pytest.mark.parametrize('switch,text_seen', [('false', False), ('true', True)])
def test_mid_session_retry_respects_switch_and_text(monkeypatch, switch, text_seen):
    monkeypatch.setenv('LISTEN_STT_SAME_TARGET_RETRY_ENABLED', switch)
    receiver = _dead_managed_receiver(text_seen=text_seen)
    assert not live_recovery.allow_same_target_retry(receiver, 'soniox', 'connection_lost', managed=True)
    assert 'soniox' in receiver._stt_failed_providers


@pytest.mark.asyncio
async def test_a_failed_same_target_retry_is_one_health_vote_not_two(monkeypatch):
    monkeypatch.setattr(live_chain, 'retry_jitter_seconds', lambda: 0.0)
    monkeypatch.setattr(provider_resilience, 'STT_FALLBACK_LIVENESS_GRACE_SECONDS', 0)
    votes = []
    monkeypatch.setattr(live_chain.health, 'record_session', lambda *args, **_kwargs: votes.append(args[2:]) or True)

    dials = []

    async def blip():
        dials.append(1)
        return SimpleNamespace(is_connection_dead=True, finish=lambda: None, death_reason=None, typed_death_reason=None)

    with pytest.raises((live_chain.LiveChainExhausted, RuntimeError)):
        await live_chain.connect_configured_chain(
            primary_service=st.STTService.soniox,
            connect_primary=blip,
            callbacks={},
            failed=set(),
            models=['soniox'],
            routing_uid=_uid(7),
            routing_language='ja',
        )
    failures = [vote for vote in votes if provider_observation(vote[0], vote[3]) is True]
    assert len(dials) == 2 and len(failures) == 1  # retried, but one vote


@pytest.mark.asyncio
async def test_no_same_target_retry_while_the_pod_drains(monkeypatch, draining):
    monkeypatch.setattr(live_chain, 'retry_jitter_seconds', lambda: 0.0)
    monkeypatch.setattr(provider_resilience, 'STT_FALLBACK_LIVENESS_GRACE_SECONDS', 0)
    draining.mark_draining()
    connect = AsyncMock(
        return_value=SimpleNamespace(
            is_connection_dead=True, finish=lambda: None, death_reason=None, typed_death_reason=None
        )
    )
    with pytest.raises((live_chain.LiveChainExhausted, RuntimeError)):
        await live_chain.connect_configured_chain(
            primary_service=st.STTService.soniox,
            connect_primary=connect,
            callbacks={},
            failed=set(),
            models=['soniox'],
        )
    assert connect.await_count == 1
    assert not live_recovery.allow_same_target_retry(
        _dead_managed_receiver(), 'soniox', 'connection_lost', managed=True
    )


@pytest.mark.asyncio
async def test_a_failed_mid_session_retry_redial_does_not_vote_again(monkeypatch):
    """The serving leg's pre-text death voted; the granted redial is the same blip."""
    from utils.stt.recovery_state import LiveRecoveryController, current_recovery

    monkeypatch.setenv('STT_FAILOVER_RECOVERY_ENABLED', 'true')
    monkeypatch.setattr(provider_resilience, 'STT_FALLBACK_LIVENESS_GRACE_SECONDS', 0)
    votes = []
    monkeypatch.setattr(live_chain.health, 'record_session', lambda *args, **_kwargs: votes.append(args[2:]) or True)
    controller = LiveRecoveryController(SimpleNamespace(state=SimpleNamespace(active=True)))
    controller.begin(family='soniox')
    controller.attempted_targets.add('soniox')
    assert controller.grant_transient_retry('soniox') and controller.is_retry_dial('soniox')
    dials = []

    async def blip():
        dials.append(1)
        return SimpleNamespace(is_connection_dead=True, finish=lambda: None, death_reason=None, typed_death_reason=None)

    token = current_recovery.set(controller)
    try:
        with pytest.raises((live_chain.LiveChainExhausted, RuntimeError)):
            await live_chain.connect_configured_chain(
                primary_service=st.STTService.soniox,
                connect_primary=blip,
                callbacks={},
                failed=set(),
                models=['soniox'],
                routing_uid=_uid(8),
                routing_language='ja',
            )
    finally:
        current_recovery.reset(token)
    assert len(dials) == 1  # the slot is spent; no in-chain second retry
    assert not [vote for vote in votes if provider_observation(vote[0], vote[3]) is True]


def test_retry_slot_is_separate_from_the_soniox_rescue_reentry():
    from utils.stt.recovery_state import LiveRecoveryController

    controller = LiveRecoveryController(SimpleNamespace())
    controller.attempted_targets = {'modulate-velma-2', 'soniox'}
    assert controller.grant_transient_retry('modulate-velma-2')
    assert controller.reserve('modulate-velma-2')
    assert not controller.reserve('modulate-velma-2')  # one retry per identity
    assert controller.grant_soniox_reentry('soniox')  # the rescue slot is untouched
    assert controller.reserve('soniox')


def test_jitter_is_consumed_once_by_the_dial():
    from utils.stt.recovery_state import LiveRecoveryController

    controller = LiveRecoveryController(SimpleNamespace())
    controller.note_retry_jitter('soniox', 0.3)
    assert controller.take_retry_jitter('soniox') == 0.3
    assert controller.take_retry_jitter('soniox') == 0.0


def test_sigterm_marker_chains_the_previous_handler(monkeypatch):
    import signal

    calls = []
    installed = {}
    monkeypatch.setattr(pod_drain, '_installed', False)
    monkeypatch.setattr(pod_drain, '_draining', False)
    monkeypatch.setattr(signal, 'getsignal', lambda _sig: lambda *args: calls.append(args))
    monkeypatch.setattr(signal, 'signal', lambda sig, handler: installed.__setitem__(sig, handler))
    pod_drain.install_drain_signal_marker()
    installed[signal.SIGTERM](signal.SIGTERM, None)
    assert pod_drain.is_draining() and calls == [(signal.SIGTERM, None)]
