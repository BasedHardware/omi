"""Pipeline-free simulation of the 2026-10-28 bench-cascade incident.

Shape (prod, read 07:35-08:20Z): parakeet-window benched at 19:07/19:43Z on
real sustained no-text failures and mass-failovered its sessions onto soniox;
the induced connect-death cluster crossed the burst arm (>=8 recent failures,
CUSUM >= 10) 81 minutes after the last bench and benched soniox at a 1.0%
rate. With every target below stage 100, escape votes fed modulate-velma-2
(a target benched hours earlier at 26%), which promoted 5->25->100 at a 6.2%
rate at 21:18Z and served ~9% failure as the sole primary until 03:31Z. The
same cascade one step shorter happened on 2026-10-20 (restart burst arm at
13:44Z after the 13:10Z parakeet bench).

Each section runs with its kill switch on (fixed) and off (incident).
"""

import json
import random
from dataclasses import replace

import pytest
import fakeredis.aioredis

from config import live_stt_state
from config.live_stt_registry import DEFAULT_TARGETS, assigned
from tests.unit.test_live_cost_router import MemoryRedis, controls, seed_cost_interest  # noqa: F401 -- autouse fixture
from utils.stt import live_health
from utils.stt.live_cost_health import CAS, FAILOVER_SURGE_CENSOR_SECONDS
from utils.stt.live_gate import GateState, begin_trial, transition
from utils.stt.live_router import select

PARAKEET, MODULATE, SONIOX = DEFAULT_TARGETS


def _uid(i: int) -> str:
    return f'cascade-{i:05d}'


def _seed(redis, target, state, languages=('all', 'en')):
    for language in languages:
        redis.data[live_stt_state.cost_key(target, language)] = json.dumps(state.encode())


def _warm_soniox(now: float) -> GateState:
    """A healthy soniox gate: ~2.2% lifetime failures across many users."""
    state = GateState()
    rng = random.Random(7)
    for i in range(400):
        state = transition(state, rng.random() < 0.022, now, witness=f'{i:016x}')
    assert state.stage == 100
    return state


class _Pod:
    """One fleet pod with immediately-drained scheduled writes."""

    def __init__(self, clock):
        self.now = clock
        self.pending = []
        self.pod = live_health.FleetHealth(redis_client=MemoryRedis(clock=clock), clock=clock)
        seed_cost_interest(self.pod, DEFAULT_TARGETS, 'en')
        self.pod.schedule = lambda coroutine, **_labels: self.pending.append(coroutine)

    async def refresh(self):
        await self.pod.refresh_cost_once()

    async def vote(self, target, uid, failed, language='en'):
        self.pod.record_session(
            target,
            language,
            'failover' if failed else 'text',
            None,
            uid,
            'connection_lost' if failed else 'text',
        )
        while self.pending:
            await self.pending.pop()

    def stage(self, target, language='en'):
        return self.pod.cost_stage(target, language)

    def primary(self, language='en'):
        states = self.pod.cost_snapshot(DEFAULT_TARGETS, language)
        return select(DEFAULT_TARGETS, states, 'primary-probe', language)[0].id


# --- 1. A failover surge cannot fuel the burst arm ----------------------------------------


def test_surge_failure_keeps_rate_cusum_and_sustained_breadth():
    plain = transition(GateState(), True, 1000.0, witness='a' * 16)
    surged = transition(GateState(), True, 1000.0, witness='a' * 16, failover_surge=True)
    assert surged.n == plain.n == 1
    assert surged.failures == plain.failures == 1
    assert surged.evidence == plain.evidence  # sustained thresholds keep their input
    assert plain.recent_failures == ('a' * 16,)
    assert surged.recent_failures == ('!' + 'a' * 15,)  # not burst evidence
    assert GateState.decode(surged.encode()) == surged


@pytest.mark.parametrize('score', [0, 1])
def test_sustained_detection_is_unchanged_inside_surge(score):
    evidence = [0.0, 0.0, 0.0]
    evidence[score] = 11.9 if score == 0 else 10.9
    state = GateState(
        n=5664, failures=124, evidence=tuple(evidence), recent_failures=tuple(f'{i:016x}' for i in range(7))
    )
    plain = transition(state, True, 1000, witness='a' * 16)
    surged = transition(state, True, 1000, witness='a' * 16, failover_surge=True)
    assert plain.stage == surged.stage == 0
    assert plain.n == surged.n and plain.failures == surged.failures
    assert plain.evidence == surged.evidence


def test_surge_censor_blocks_the_burst_arm_until_the_window_closes():
    state = GateState()
    for i in range(8):  # the 21:04Z cluster: eight users, one death each
        state = transition(state, True, 1000.0 + i, witness=f'{i:016x}', failover_surge=True)
    assert state.stage == 100  # the incident bench does not fire
    assert state.evidence[2] >= 10  # and the sustained evidence survived
    for i in range(8):  # past the window, still-failing breadth benches
        state = transition(state, True, 1000.0 + FAILOVER_SURGE_CENSOR_SECONDS + i, witness=f'{8 + i:016x}')
    assert state.stage == 0


def test_surge_window_math_and_flag(monkeypatch):
    pod = live_health.FleetHealth(redis_client=MemoryRedis(clock=lambda: 1000), clock=lambda: 1000)
    pod._open_failover_surge(PARAKEET.id)
    assert pod._failover_surge_open(SONIOX.id, 1000 + FAILOVER_SURGE_CENSOR_SECONDS - 1)
    assert not pod._failover_surge_open(SONIOX.id, 1000 + FAILOVER_SURGE_CENSOR_SECONDS)
    assert not pod._failover_surge_open(PARAKEET.id, 1000)  # the benched target itself
    monkeypatch.setenv('LISTEN_STT_FAILOVER_SURGE_CENSOR_ENABLED', 'false')
    assert not pod._failover_surge_open(SONIOX.id, 1000)


@pytest.mark.asyncio
async def test_surge_window_reaches_other_pods_through_the_snapshot():
    clock = [10_000.0]
    first = _Pod(lambda: clock[0])
    second = _Pod(lambda: clock[0])
    second.pod._redis = first.pod._redis  # one shared MemoryRedis
    await first.refresh()
    await second.refresh()
    for i in range(8):  # 13:10Z: parakeet benches on pod one
        await first.vote(PARAKEET.id, _uid(i), True)
    assert first.stage(PARAKEET.id) == 0
    clock[0] += 60
    await second.refresh()  # pod two learns the bench only from the snapshot
    clock[0] += 69 * 60  # 14:20Z: the second death pulse, 70 minutes later
    for i in range(8):
        await second.vote(SONIOX.id, _uid(100 + i), True)
    assert second.stage(SONIOX.id) == 100
    assert first.stage(SONIOX.id) == 100


@pytest.mark.asyncio
async def test_failed_votes_see_a_source_bench_before_the_next_snapshot():
    clock = [10_000.0]
    first, second = _Pod(lambda: clock[0]), _Pod(lambda: clock[0])
    second.pod._redis = first.pod._redis
    await first.refresh()
    await second.refresh()
    for i in range(8):
        await first.vote(PARAKEET.id, _uid(i), True)
    assert SONIOX.id not in second.pod._cost_surge_until
    for i in range(8):
        await second.vote(SONIOX.id, _uid(100 + i), True)
    assert second.stage(SONIOX.id) == 100
    assert json.loads(first.pod._redis().data[live_stt_state.cost_key(SONIOX, 'all')])['stage'] == 100


@pytest.mark.parametrize(
    'language,exclude_by', [('ar', 'capability'), ('en', 'ramp'), ('en', 'capacity'), ('en', 'cohort')]
)
@pytest.mark.asyncio
async def test_ineligible_full_share_target_cannot_release_modulate(monkeypatch, language, exclude_by):
    clock = [20_000.0]
    if exclude_by in {'ramp', 'capacity', 'cohort'}:
        parakeet = replace(
            PARAKEET,
            ramp_percent=0 if exclude_by == 'ramp' else 1 if exclude_by == 'cohort' else 100,
            capacity_env='TEST_CASCADE_FULL' if exclude_by == 'capacity' else None,
        )
        monkeypatch.setenv(
            'STT_ROUTING_TARGETS_JSON',
            json.dumps(
                [
                    {key: value for key, value in vars(entry).items() if value is not None}
                    for entry in (parakeet, MODULATE, SONIOX)
                ]
            ),
        )
        if exclude_by == 'capacity':
            monkeypatch.setenv('TEST_CASCADE_FULL', 'true')
    pod = _Pod(lambda: clock[0])
    users = tuple((f'{i:016x}', 3, 0) for i in range(20))
    _seed(
        pod.pod._redis(),
        MODULATE,
        GateState(stage=25, n=60, trial_users=users, trial_started_at=clock[0] - 700),
        ('all', language),
    )
    _seed(pod.pod._redis(), SONIOX, GateState(stage=5), ('all', language))
    await pod.refresh()
    uid = next(
        _uid(i)
        for i in range(4000, 5000)
        if assigned(_uid(i), 'stt-reentry:' + MODULATE.id, 25)
        and (exclude_by != 'cohort' or not assigned(_uid(i), PARAKEET.id, 1))
    )
    await pod.vote(MODULATE.id, uid, False, language)
    assert pod.stage(MODULATE.id, language) == 25
    assert json.loads(pod.pod._redis().data[live_stt_state.cost_key(MODULATE, 'all')])['stage'] == 25


@pytest.mark.asyncio
async def test_custom_modulate_and_soniox_ids_keep_the_family_guard(monkeypatch):
    modulate, soniox = replace(MODULATE, id='modulate-prod'), replace(SONIOX, id='soniox-prod')
    monkeypatch.setenv(
        'STT_ROUTING_TARGETS_JSON',
        json.dumps(
            [{key: value for key, value in vars(entry).items() if value is not None} for entry in (modulate, soniox)]
        ),
    )
    clock = [20_000.0]
    pod = _Pod(lambda: clock[0])
    users = tuple((f'{i:016x}', 3, 0) for i in range(20))
    _seed(pod.pod._redis(), modulate, GateState(stage=25, n=60, trial_users=users, trial_started_at=clock[0] - 700))
    _seed(pod.pod._redis(), soniox, GateState(stage=5))
    await pod.refresh()
    await pod.vote(modulate.id, 'custom-user', False)
    assert pod.stage(modulate.id) == 25


@pytest.mark.parametrize('enabled', [True, False])
@pytest.mark.asyncio
async def test_sim_1028_parakeet_bench_failover_surge_cannot_burst_bench_soniox(monkeypatch, enabled):
    monkeypatch.setenv('LISTEN_STT_FAILOVER_SURGE_CENSOR_ENABLED', 'true' if enabled else 'false')
    monkeypatch.setenv('LISTEN_STT_ESCAPE_EXCLUDES_BENCHED_ENABLED', 'true')
    clock = [10_000.0]
    pod = _Pod(lambda: clock[0])
    _seed(pod.pod._redis(), SONIOX, _warm_soniox(clock[0]))
    _seed(pod.pod._redis(), MODULATE, GateState(stage=0, n=100, failures=40, strikes=4, until=clock[0] + 14_400))
    await pod.refresh()
    for i in range(8):  # 19:43Z: the parakeet bench that mass-failovers onto soniox
        await pod.vote(PARAKEET.id, _uid(i), True)
    assert pod.stage(PARAKEET.id) == 0
    clock[0] += 81 * 60  # 21:04Z: the induced cluster arrives, inside the window
    for i in range(8):
        await pod.vote(SONIOX.id, _uid(100 + i), True)
    if enabled:
        assert pod.stage(SONIOX.id) == 100  # soniox stays primary; modulate stays benched
        assert pod.primary() == SONIOX.id
        clock[0] += 11 * 60  # past the window, a still-failing soniox benches again
        for i in range(8):
            await pod.vote(SONIOX.id, _uid(200 + i), True)
        assert pod.stage(SONIOX.id) == 0
    else:
        assert pod.stage(SONIOX.id) == 0  # the incident: the burst bench at a 1.0% rate


# --- 2. A held target never becomes the only stage-100 primary ------------------------------


def test_sole_primary_blocked_rule():
    blocked = live_health.FleetHealth(redis_client=MemoryRedis())._sole_primary_blocked
    assert blocked(MODULATE.id, {SONIOX.id: 5, PARAKEET.id: 0})
    assert not blocked(MODULATE.id, {SONIOX.id: 100})  # another full share: not sole
    assert not blocked(MODULATE.id, {PARAKEET.id: 0})  # guard below stage 5
    assert not blocked(MODULATE.id, {})  # guard absent: the pair rule is void
    assert not blocked(SONIOX.id, {MODULATE.id: 5})  # only the held target is held


@pytest.mark.parametrize('enabled', [True, False])
@pytest.mark.asyncio
async def test_sim_1028_modulate_never_becomes_sole_primary_while_soniox_trials(monkeypatch, enabled):
    monkeypatch.setenv('LISTEN_STT_SOLE_PRIMARY_HOLD_ENABLED', 'true' if enabled else 'false')
    monkeypatch.setenv('LISTEN_STT_ESCAPE_EXCLUDES_BENCHED_ENABLED', 'true')
    monkeypatch.setenv('LISTEN_STT_ESCAPE_BEST_RATE_PRIMARY_ENABLED', 'true')
    clock = [20_000.0]
    pod = _Pod(lambda: clock[0])
    _seed(pod.pod._redis(), SONIOX, GateState(stage=5, generation=1, trial_started_at=clock[0]))
    _seed(pod.pod._redis(), PARAKEET, GateState(stage=0, generation=1, strikes=5, until=clock[0] + 14_400))
    _seed(pod.pod._redis(), MODULATE, GateState(stage=25, generation=1, trial_started_at=clock[0]))
    await pod.refresh()
    # Soniox collects a proven trial sample below the 300 s dwell, so it cannot
    # promote yet but its ~0% rate outranks a worse-rate stage-25 lead.
    for i in range(10):
        for user in range(3 * i, 3 * i + 3):
            await pod.vote(SONIOX.id, _uid(1000 + user), False)
        clock[0] += 20
    assert pod.stage(SONIOX.id) == 5 and pod.pod.cost_snapshot(DEFAULT_TARGETS, 'en')[SONIOX.id].n >= 30
    # 21:18Z-equivalent: modulate's escape votes at a ~6% rate, all promotion
    # bars met (n >= 60, 20+ users, dwell, user rate within the gate).
    clock[0] += 700
    primaries = set()
    for i in range(4):  # users 0-3: one failure and two successes each
        await pod.vote(MODULATE.id, _uid(i), True)
        await pod.vote(MODULATE.id, _uid(i), False)
        await pod.vote(MODULATE.id, _uid(i), False)
    for i in range(4, 25):  # users 4-24: three successes each
        for _ in range(3):
            await pod.vote(MODULATE.id, _uid(i), False)
        primaries.add(pod.primary())
    if enabled:
        assert primaries == {SONIOX.id}  # no Modulate-primary outcome at any step
        assert pod.stage(MODULATE.id) == 25  # the hold: sole primary is refused
        # Soniox resolves first: stage 5 -> 25 -> 100 on its own escape votes.
        for i in range(10):
            await pod.vote(SONIOX.id, _uid(1100 + i), False)
        assert pod.stage(SONIOX.id) == 25
        clock[0] += 700
        for i in range(25):
            for _ in range(3):
                await pod.vote(SONIOX.id, _uid(1200 + i), False)
        assert pod.stage(SONIOX.id) == 100
        # With a full-share provider back, normal cohort admission resumes.
        uid = next(_uid(i) for i in range(2000, 3000) if assigned(_uid(i), 'stt-reentry:' + MODULATE.id, 25))
        await pod.vote(MODULATE.id, uid, False)  # the hold lifts: not sole anymore
        assert pod.stage(MODULATE.id) == 100
        assert pod.primary() in {SONIOX.id, MODULATE.id}
    else:
        assert pod.stage(MODULATE.id) == 100  # the incident: sole primary at a 6.2% rate
        assert pod.primary() == MODULATE.id


# --- 3. The escape never leads with a worse-failure-rate target ------------------------------


def _escape_uid(states):
    return next(
        str(i)
        for i in range(1000)
        if not any(assigned(str(i), 'stt-reentry:' + target_id, state.stage) for target_id, state in states.items())
    )


@pytest.mark.parametrize('enabled', [True, False])
def test_escape_lead_is_never_a_worse_rate_target(monkeypatch, enabled):
    monkeypatch.setenv('LISTEN_STT_ESCAPE_EXCLUDES_BENCHED_ENABLED', 'true')
    monkeypatch.setenv('LISTEN_STT_ESCAPE_BEST_RATE_PRIMARY_ENABLED', 'true' if enabled else 'false')
    states = {
        PARAKEET.id: GateState(stage=0, n=20, failures=13),
        MODULATE.id: GateState(stage=25, n=64, failures=4),  # 6.2%, freshly promoted
        SONIOX.id: GateState(stage=5, n=30, failures=0),  # the healthy trial
    }
    primary = select(DEFAULT_TARGETS, states, _escape_uid(states), 'en')[0].id
    assert primary == (SONIOX.id if enabled else MODULATE.id)


def test_unproven_lead_yields_to_a_proven_candidate(monkeypatch):
    monkeypatch.setenv('LISTEN_STT_ESCAPE_BEST_RATE_PRIMARY_ENABLED', 'true')
    states = {
        MODULATE.id: GateState(stage=25),  # freshly promoted, no sample yet
        SONIOX.id: GateState(stage=5, n=30, failures=1),
    }
    assert select((SONIOX, MODULATE), states, _escape_uid(states), 'en')[0].id == SONIOX.id


def test_proven_better_lead_keeps_stage_order(monkeypatch):
    monkeypatch.setenv('LISTEN_STT_ESCAPE_BEST_RATE_PRIMARY_ENABLED', 'true')
    states = {
        MODULATE.id: GateState(stage=5, n=30, failures=6),  # 20% trial
        SONIOX.id: GateState(stage=25, n=64, failures=0),  # proven clean, higher stage
    }
    chain = select((SONIOX, MODULATE), states, _escape_uid(states), 'en')
    assert [target.id for target in chain] == [SONIOX.id, MODULATE.id]


# --- 4. The 2026-10-20 replay ---------------------------------------------------------------


@pytest.mark.parametrize('enabled', [True, False])
@pytest.mark.asyncio
async def test_sim_1020_restart_burst_after_parakeet_bench_keeps_soniox_primary(monkeypatch, enabled):
    monkeypatch.setenv('LISTEN_STT_FAILOVER_SURGE_CENSOR_ENABLED', 'true' if enabled else 'false')
    monkeypatch.setenv('LISTEN_STT_ESCAPE_EXCLUDES_BENCHED_ENABLED', 'true')
    monkeypatch.setenv('LISTEN_STT_ESCAPE_BEST_RATE_PRIMARY_ENABLED', 'true')
    clock = [10_000.0]
    pod = _Pod(lambda: clock[0])
    _seed(pod.pod._redis(), SONIOX, _warm_soniox(clock[0]))
    _seed(pod.pod._redis(), MODULATE, GateState(stage=0, n=100, failures=40, strikes=6, until=clock[0] + 14_400))
    await pod.refresh()
    for i in range(8):  # 13:10Z: the parakeet bench
        await pod.vote(PARAKEET.id, _uid(i), True)
    clock[0] += 34 * 60  # 13:44Z: the connection_lost burst, 34 minutes later
    for i in range(8):
        await pod.vote(SONIOX.id, _uid(100 + i), True)
    if enabled:
        assert pod.stage(SONIOX.id) == 100  # no bench, no escape at all
    else:
        assert pod.stage(SONIOX.id) == 0  # the 13:44Z incident bench at a 2.2% rate
    assert pod.primary() == SONIOX.id  # and never a Modulate-primary outcome


@pytest.mark.asyncio
async def test_1020_recorded_sustained_bench_still_escapes_to_proven_soniox():
    # The actual report logged score=11.257 on the 16% alternative, so this
    # bench must survive the burst-only censor. Replay the routing trap after
    # the 13:49Z re-entry too, rather than pretending censoring fixes it.
    now = 10_000.0
    before = GateState(
        n=5664,
        failures=124,
        evidence=(0.0, 10.9, 0.0),
        recent_failures=tuple(f'{i:016x}' for i in range(7)),
    )
    benched = transition(before, True, now, witness='a' * 16, failover_surge=True)
    assert benched.stage == 0 and benched.n == 5665 and benched.failures == 125
    soniox = begin_trial(benched, benched.until)
    for i in range(30):
        soniox = transition(soniox, False, benched.until + i, witness=f'{100 + i:016x}')
    assert soniox.stage == 5
    states = {
        SONIOX.id: soniox,
        PARAKEET.id: GateState(stage=5, n=30, failures=4),
        MODULATE.id: GateState(stage=0, n=100, failures=40),
    }
    for uid in map(str, range(100)):
        chain = select(DEFAULT_TARGETS, states, uid, 'en')
        assert chain[0].id == SONIOX.id
        assert MODULATE not in chain


@pytest.mark.asyncio
async def test_shared_surge_deadline_survives_cold_pod_and_source_reentry():
    clock = [10_000.0]
    first = _Pod(lambda: clock[0])
    await first.refresh()
    for i in range(8):
        await first.vote(PARAKEET.id, _uid(i), True)
    redis = first.pod._redis()
    deadline = float(redis.data[live_stt_state.cost_surge_key(PARAKEET)])
    assert deadline == clock[0] + FAILOVER_SURGE_CENSOR_SECONDS
    clock[0] += 301
    first.pod.prefer_recovery(PARAKEET.id, 'en')
    await first.refresh()
    assert first.stage(PARAKEET.id) == 5
    second = _Pod(lambda: clock[0])
    second.pod._redis = first.pod._redis
    await second.refresh()
    assert second.pod._cost_surge_until[SONIOX.id] == deadline
    clock[0] += 20 * 60
    await second.refresh()
    assert second.pod._cost_surge_until[SONIOX.id] == deadline
    clock[0] = deadline
    await second.refresh()
    assert not second.pod._failover_surge_open(SONIOX.id, clock[0])


def test_escape_tied_custom_targets_are_stable():
    a = replace(SONIOX, id='soniox-a')
    b = replace(SONIOX, id='soniox-b')
    states = {a.id: GateState(stage=5, n=30), b.id: GateState(stage=5, n=30)}
    assert select((a, b), states, 'u', 'en')[0] == a


@pytest.mark.asyncio
async def test_real_lua_cas_persists_surge_only_with_winning_bench():
    async with fakeredis.aioredis.FakeRedis(decode_responses=True) as redis:
        key, surge_key = live_stt_state.cost_key(PARAKEET, 'all'), live_stt_state.cost_surge_key(PARAKEET)
        before = GateState()
        benched = GateState(stage=0, until=1300)
        await redis.set(key, json.dumps(before.encode()))
        # A CAS loser cannot open a window.
        assert await redis.eval(CAS, 2, key, surge_key, 'stale', json.dumps(benched.encode()), 0, 5400) == 0
        assert await redis.get(surge_key) is None
        assert (
            await redis.eval(CAS, 2, key, surge_key, json.dumps(before.encode()), json.dumps(benched.encode()), 0, 5400)
            == 1
        )
        seconds, micros = await redis.time()
        deadline = float(await redis.get(surge_key))
        assert 5398 < deadline - (seconds + micros / 1_000_000) <= 5400
        assert 5398 <= await redis.ttl(surge_key) <= 5400
        # Recovery must not extend or erase the window, or expire the bench.
        assert await redis.ttl(key) == -1
        assert (
            await redis.eval(CAS, 1, key, json.dumps(benched.encode()), json.dumps(GateState(stage=5).encode()), 0) == 1
        )
        assert float(await redis.get(surge_key)) == deadline


@pytest.mark.parametrize(
    'soniox_stage,parakeet_stage,held', [(5, 0, True), (25, 5, True), (0, 5, False), (100, 0, False), (5, 100, False)]
)
@pytest.mark.asyncio
async def test_real_lua_promotion_hold_reads_current_shared_stages(soniox_stage, parakeet_stage, held):
    async with fakeredis.aioredis.FakeRedis(decode_responses=True) as redis:
        key = live_stt_state.cost_key(MODULATE, 'all')
        others = [PARAKEET, SONIOX]
        keys = [key, *(live_stt_state.cost_key(target, lang) for target in others for lang in ('all', 'en'))]
        old = json.dumps(GateState(stage=25).encode())
        promoted = json.dumps(GateState(stage=100).encode())
        held_state = json.dumps(GateState(stage=25, n=61).encode())
        await redis.set(key, old)
        for target, stage in [(PARAKEET, parakeet_stage), (SONIOX, soniox_stage)]:
            for lang in ('all', 'en'):
                await redis.set(live_stt_state.cost_key(target, lang), json.dumps(GateState(stage=stage).encode()))
        result = await redis.eval(CAS, len(keys), *keys, old, promoted, 900, 'hold', held_state, json.dumps([4]))
        assert result == (2 if held else 1)
        state = GateState.decode(json.loads(await redis.get(key)))
        assert state.stage == (25 if held else 100)
        assert state.n == (61 if held else 0)
        assert await redis.ttl(key) == (-1 if held else 900)
