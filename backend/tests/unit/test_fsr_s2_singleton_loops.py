"""Fleet admission safety and measured document reads on the queue sampler path."""

from __future__ import annotations

import ast
import asyncio
import logging
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from config.listen_quiet_finalization import enabled as quiet_finalization_enabled
from database import durable_queue_age as ages
from utils.other import fsr_leader_lease as leases


class FakeRedis:
    """Atomic SET NX PX, token-CAS renew/release and real expiry semantics."""

    def __init__(self):
        self.now = 0.0
        self.values = {}
        self.expires = {}
        self.calls = 0
        self.error = False

    def advance(self, seconds):
        self.now += seconds

    def get(self, key):
        if self.now >= self.expires.get(key, float('inf')):
            self.values.pop(key, None)
            self.expires.pop(key, None)
        return self.values.get(key)

    def set(self, key, value, ttl_ms):
        self.values[key] = value
        self.expires[key] = self.now + int(ttl_ms) / 1000

    def eval(self, script, count, *args):
        self.calls += 1
        if self.error:
            raise ConnectionError('Redis down')
        keys, argv = args[:count], args[count:]
        owner = self.get(keys[0])
        if 'fsr_admit' in script:
            old_token, new_token, ttl_ms, interval_ms, queue_age = argv
            retained = bool(old_token and owner == old_token)
            if retained:
                self.set(keys[0], old_token, ttl_ms)
                generation = self.get(keys[1])
            elif not queue_age and self.get(keys[2]) is None:
                self.set(keys[0], new_token, ttl_ms)
                generation = (self.get(keys[1]) or 0) + 1
                self.values[keys[1]] = generation
            elif owner is None:
                self.set(keys[0], new_token, ttl_ms)
                generation = (self.get(keys[1]) or 0) + 1
                self.values[keys[1]] = generation
            else:
                retry = self.expires[keys[0]] - self.now
                if not queue_age:
                    retry = min(retry, self.expires[keys[2]] - self.now)
                return [0, 0, 0, int(retry * 1000)]
            if queue_age and not retained:
                self.values.pop(keys[2], None)
            admitted = self.get(keys[2]) is None
            if admitted:
                self.set(keys[2], generation, interval_ms)
            return [generation, int(admitted), int(retained), int((self.expires[keys[2]] - self.now) * 1000)]
        if 'fsr_renew' in script:
            if owner == argv[0]:
                self.set(keys[0], owner, argv[1])
                return 1
            return 0
        if 'fsr_release' in script:
            if owner == argv[0]:
                del self.values[keys[0]]
                if argv[1]:
                    self.values.pop(keys[1], None)
                return 1
            return 0
        raise AssertionError('unexpected Redis script')


@pytest.fixture
def fleet(monkeypatch):
    import utils.durable_queue_metrics  # Prewarm metric definitions outside the test's CPU budget.

    monkeypatch.setenv('FIRESTORE_READ_LEVERS', '{"singleton_loops":100}')
    monkeypatch.delenv('FSR_LEADER_LEASE_TTL_SECONDS', raising=False)
    monkeypatch.delenv('FSR_QUEUE_AGE_LEASE_SECONDS', raising=False)
    monkeypatch.delenv('FSR_LEASE_MAX_HOLD_SECONDS', raising=False)
    monkeypatch.setenv('FSR_QUEUE_AGE_PUBLISHER', '1')
    redis = FakeRedis()
    outcomes = []
    replicas = []
    monkeypatch.setattr(leases, '_count', lambda loop, outcome: outcomes.append((loop, outcome)))

    def replica(loop='test_loop'):
        lease = leases.LeaderLease(loop, redis_client=redis, clock=lambda: redis.now)
        replicas.append(lease)
        return lease

    yield SimpleNamespace(redis=redis, replica=replica, outcomes=outcomes)
    for lease in replicas:
        lease.release()


def test_two_replicas_one_run_each_tick_and_independent_loop_names(fleet):
    one, two = fleet.replica(), fleet.replica()
    runs = []
    for _ in range(10):
        for replica in (one, two):
            replica.run(lambda: runs.append(fleet.redis.now), 300)
        fleet.redis.advance(300)
    assert len(runs) == 10
    assert [outcome for _, outcome in fleet.outcomes].count('acquired') == 10
    assert [outcome for _, outcome in fleet.outcomes].count('skipped') == 10
    assert fleet.replica('other_loop').run(lambda: 'ran', 300) == 'ran'


def test_startup_restart_does_not_bypass_tick_cooldown_and_shutdown_releases(fleet):
    leader = fleet.replica()
    runs = []
    leader.run(lambda: runs.append('startup'), 300)
    leader.release()
    assert fleet.redis.get(leader.keys[0]) is None
    replacement = fleet.replica()
    replacement.run(lambda: runs.append('replacement boot'), 300)
    assert runs == ['startup']
    fleet.redis.advance(300)
    replacement.run(lambda: runs.append('next tick'), 300)
    assert runs == ['startup', 'next tick']


def test_leader_dies_takeover_at_one_interval_and_old_epoch_is_fenced(fleet):
    one, two = fleet.replica(), fleet.replica()
    permits = []
    one.run(lambda: permits.append(leases._current_permit.get()), 300)
    old = permits[0]
    fleet.redis.advance(299)
    assert two.run(lambda: 'too early', 300) is None
    fleet.redis.advance(1)  # Tick expires before the owner's 600s TTL.
    two.run(lambda: permits.append(leases._current_permit.get()), 300)
    assert permits[1].generation > old.generation
    with pytest.raises(leases.LeaseLost):
        old.check()
    current_token = fleet.redis.get(two.keys[0])
    one.release()  # A former owner cannot delete the replacement's lease.
    assert fleet.redis.get(two.keys[0]) == current_token


def test_renewal_does_not_resurrect_a_replaced_token(fleet):
    one, two = fleet.replica(), fleet.replica()
    old = []
    one.run(lambda: old.append(leases._current_permit.get()), 300)
    fleet.redis.set(one.keys[0], 'different-owner', 600000)
    with pytest.raises(leases.LeaseLost):
        old[0].check()
    assert fleet.redis.get(one.keys[0]) == 'different-owner'


def test_staggered_death_retries_at_expiry_without_extra_scan_interval(fleet, monkeypatch):
    one, two = fleet.replica('reconcile_listen_finalization_jobs'), fleet.replica('reconcile_listen_finalization_jobs')
    held = []
    one.run(lambda: held.append(leases._current_permit.get()), 300)
    fleet.redis.advance(50)
    held[0].check()  # Last heartbeat before dying at t=50; expiry is t=650.
    fleet.redis.advance(249)
    assert two.run(lambda: pytest.fail('early takeover'), 300) is None
    monkeypatch.setattr(leases, 'loop_lease', lambda _: two)
    assert leases.poll_delay(300) == 1
    fleet.redis.advance(leases.poll_delay(300))
    assert two.run(lambda: 'takeover', 300) == 'takeover'
    assert fleet.redis.now - 50 == 250


def test_heartbeat_cannot_block_takeover_after_admission_tick_expires(fleet):
    one, two = fleet.replica(), fleet.replica()

    def long_scan():
        fleet.redis.advance(200)
        leases.check_leader_lease()
        assert two.run(lambda: pytest.fail('early takeover'), 300) is None
        fleet.redis.advance(100)
        assert two.run(lambda: 'replacement', 300) == 'replacement'
        with pytest.raises(leases.LeaseLost):
            leases.check_leader_lease()

    one.run(long_scan, 300)


@pytest.mark.parametrize('loop,max_hold,heartbeat', [('test_loop', 900, 200), (leases.QUEUE_AGE_LOOP, 240, 40)])
def test_hung_callback_expires_at_max_hold_and_second_pod_acquires(fleet, caplog, loop, max_hold, heartbeat):
    one, two = fleet.replica(loop), fleet.replica(loop)
    entered, resume = threading.Event(), threading.Event()
    held = []
    withdrawals = []

    def hung():
        held.append(leases._current_permit.get())
        entered.set()
        assert resume.wait(5)
        leases.check_leader_lease()  # A resumed stale holder is fenced.
        pytest.fail('stale callback acted')

    worker = threading.Thread(target=lambda: one.run(hung, 300, on_skip=lambda: withdrawals.append(True)))
    worker.start()
    try:
        assert entered.wait(2)
        permit = held[0]
        # Drive the same check used by the heartbeat while the callback stays hung.
        while fleet.redis.now + heartbeat < max_hold:
            fleet.redis.advance(heartbeat)
            permit.check()
            if loop == leases.QUEUE_AGE_LOOP:
                assert two.run(lambda: pytest.fail('early takeover'), 300) is None
        fleet.redis.advance(max_hold - fleet.redis.now)
        with caplog.at_level(logging.WARNING, logger=leases.__name__):
            with pytest.raises(leases.LeaseLost):
                permit.check()
            with pytest.raises(leases.LeaseLost):
                permit.check()
        assert worker.is_alive()
        assert fleet.redis.get(one.keys[0]) is None
        assert two.run(lambda: 'replacement', 300) == 'replacement'
        successor = fleet.redis.get(two.keys[0])
        assert successor != permit.token
        assert fleet.outcomes.count((loop, 'max_hold_exceeded')) == 1
        assert f'loop={loop} outcome=max_hold_exceeded elapsed_seconds={max_hold:.3f}' in caplog.text
    finally:
        resume.set()
        worker.join(timeout=2)
    assert not worker.is_alive()
    assert withdrawals == [True]
    one.release()
    assert fleet.redis.get(two.keys[0]) == successor


def test_max_hold_env_default_override_and_interval_floor(monkeypatch):
    monkeypatch.delenv('FSR_LEASE_MAX_HOLD_SECONDS', raising=False)
    assert leases._max_hold_seconds(300) == 900
    assert leases._max_hold_seconds(600) == 1200
    for configured, expected in [('1500', 1500), ('bad', 900), ('0', 600), ('-1', 600)]:
        monkeypatch.setenv('FSR_LEASE_MAX_HOLD_SECONDS', configured)
        assert leases._max_hold_seconds(300) == expected


def test_oversized_ttl_cannot_extend_ownership_past_max_hold(fleet, monkeypatch):
    monkeypatch.setenv('FSR_LEADER_LEASE_TTL_SECONDS', '7200')
    held = []
    owner, follower = fleet.replica(), fleet.replica()
    owner.run(lambda: held.append(leases._current_permit.get()), 300)
    assert held[0].ttl_ms == 900000
    fleet.redis.advance(899)
    held[0].check()
    assert held[0].heartbeat_delay() == 1
    fleet.redis.advance(1)
    assert follower.run(lambda: 'replacement', 300) == 'replacement'
    with pytest.raises(leases.LeaseLost):
        held[0].check()


def test_completed_queue_sample_restores_idle_ttl_after_nearing_hold_cap(fleet):
    owner = fleet.replica(leases.QUEUE_AGE_LOOP)

    def slow_sample():
        for _ in range(5):
            fleet.redis.advance(40)
            leases.check_leader_lease()
        fleet.redis.advance(39)
        leases.check_leader_lease(require_ownership=True)
        assert owner._idle_permit.deadline == 240

    owner.run(slow_sample, 300)
    assert owner._idle_permit.max_hold_deadline is None
    assert owner._idle_permit.deadline == 359
    fleet.redis.advance(40)
    owner._idle_permit.check()
    assert not owner._idle_permit.lost


def test_queue_max_hold_restarts_per_admission_and_does_not_cap_idle_owner(fleet, monkeypatch):
    monkeypatch.setenv('FSR_LEASE_MAX_HOLD_SECONDS', '1')  # Queue uses twice its own TTL.
    owner = fleet.replica(leases.QUEUE_AGE_LOOP)
    samples = []
    for tick in range(5):
        owner.run(lambda: samples.append(leases._current_permit.get().max_hold_deadline), 300)
        for _ in range(6):
            fleet.redis.advance(50)
            owner._idle_permit.check()
    assert samples == [tick * 300 + 240 for tick in range(5)]
    assert not any(outcome == 'max_hold_exceeded' for _, outcome in fleet.outcomes)


def test_paused_admission_never_starts_callback(fleet, monkeypatch):
    original = fleet.redis.eval

    def paused(script, *args):
        result = original(script, *args)
        if 'fsr_admit' in script:
            fleet.redis.advance(601)
        return result

    monkeypatch.setattr(fleet.redis, 'eval', paused)
    assert fleet.replica().run(lambda: pytest.fail('stale admission acted'), 300) is None


def test_redis_error_runs_both_replicas_and_counts_fail_open(fleet):
    fleet.redis.error = True
    runs = []
    for replica in (fleet.replica(), fleet.replica()):
        replica.run(lambda: runs.append(True), 300)
    assert len(runs) == 2
    assert [outcome for _, outcome in fleet.outcomes] == ['redis_error', 'redis_error']


def test_redis_error_during_renewal_is_fail_open(fleet, monkeypatch):
    original = fleet.redis.eval

    def fail_renew(script, *args):
        if 'fsr_renew' in script:
            raise ConnectionError('renewal outage')
        return original(script, *args)

    monkeypatch.setattr(fleet.redis, 'eval', fail_renew)
    assert fleet.replica().run(lambda: 'ran', 300) == 'ran'
    assert ('test_loop', 'redis_error') in fleet.outcomes


def test_lever_off_preserves_every_call_and_never_contacts_redis(fleet, monkeypatch):
    monkeypatch.delenv('FIRESTORE_READ_LEVERS')
    fleet.redis.error = True
    runs = []
    for _ in range(10):
        for replica in (fleet.replica(), fleet.replica()):
            replica.run(lambda: runs.append(True), 300)
    assert len(runs) == 20
    assert fleet.redis.calls == 0
    assert fleet.outcomes == []


class CountingFirestore:
    """Count returned Firestore documents at the actual queue query boundary."""

    def __init__(self):
        self.reads = 0
        self.queries = 0

    def collection_group(self, _):
        return self

    def where(self, **_):
        return self

    def select(self, _):
        return self

    def limit(self, _):
        return self

    def stream(self):
        self.queries += 1
        self.reads += 2
        return [
            {
                'created_at': datetime(2026, 1, 1, tzinfo=timezone.utc),
                'queued_at': datetime(2026, 1, 1, tzinfo=timezone.utc),
                'event_type': 'vector_repair_purge',
                'status': 'pending',
            }
            for _ in range(2)
        ]


def test_read_count_five_replicas_ten_ticks_1000_to_200_documents(fleet, monkeypatch):
    counts = []
    for enabled in (False, True):
        monkeypatch.setenv('FIRESTORE_READ_LEVERS', '{"singleton_loops":100}' if enabled else '{}')
        fleet.redis.values.clear()
        fleet.redis.expires.clear()
        fleet.redis.now = 0.0
        replicas = [fleet.replica('queue_age_proof') for _ in range(5)]
        client = CountingFirestore()
        for _ in range(10):
            for replica in replicas:
                replica.run(
                    lambda: ages.publish_all_queue_oldest_ready_ages(firestore_client=client, finalization_summary={}),
                    300,
                )
            fleet.redis.advance(300)
        counts.append((client.queries, client.reads))
    assert counts == [(500, 1000), (100, 200)]  # 80% fewer actual document reads.


def test_queue_scan_stops_and_never_publishes_after_lease_loss(fleet, monkeypatch):
    one = fleet.replica()
    client = CountingFirestore()
    original_stream = client.stream
    published = []
    import utils.durable_queue_metrics as metrics

    def stream_and_pause():
        result = original_stream()
        fleet.redis.advance(601)
        return result

    monkeypatch.setattr(client, 'stream', stream_and_pause)
    monkeypatch.setattr(metrics, 'publish_sampled_queue_oldest_ready_ages', published.append)
    one.run(lambda: ages.publish_all_queue_oldest_ready_ages(firestore_client=client, finalization_summary={}), 300)
    assert client.queries == 1
    assert published == []


@pytest.mark.parametrize('recovers,replaced,expected', [(True, False, 1), (True, True, 0), (False, False, 0)])
def test_queue_publish_reconfirms_ownership_after_mid_scan_redis_error(
    fleet, monkeypatch, recovers, replaced, expected
):
    import utils.durable_queue_metrics as metrics

    owner = fleet.replica(leases.QUEUE_AGE_LOOP)
    client = CountingFirestore()
    original_stream = client.stream
    published = []
    monkeypatch.setattr(metrics, 'publish_sampled_queue_oldest_ready_ages', published.append)

    def stream():
        result = original_stream()
        if client.queries == 1:
            if replaced:
                fleet.redis.set(owner.keys[0], 'successor-before-outage', 120000)
            fleet.redis.error = True
            leases.check_leader_lease()
            assert leases._current_permit.get().fail_open
        if client.queries == 10:
            fleet.redis.error = not recovers
        return result

    monkeypatch.setattr(client, 'stream', stream)
    owner.run(lambda: ages.publish_all_queue_oldest_ready_ages(firestore_client=client, finalization_summary={}), 300)
    assert client.queries == 10
    assert len(published) == expected


def test_queue_acquisition_outage_still_fails_open_and_publishes(fleet, monkeypatch):
    import utils.durable_queue_metrics as metrics

    client = CountingFirestore()
    published = []
    monkeypatch.setattr(metrics, 'publish_sampled_queue_oldest_ready_ages', published.append)
    fleet.redis.error = True
    fleet.replica(leases.QUEUE_AGE_LOOP).run(
        lambda: ages.publish_all_queue_oldest_ready_ages(firestore_client=client, finalization_summary={}), 300
    )
    assert len(published) == 1
    assert client.reads == 20


def test_follower_withdraws_previous_samples_only_when_ownership_is_lost(fleet):
    one, two = fleet.replica(), fleet.replica()
    withdrawals = []
    one.run(lambda: None, 300, on_skip=lambda: withdrawals.append('one'))
    one.run(lambda: None, 300, on_skip=lambda: withdrawals.append('cooldown'))
    two.run(lambda: None, 300, on_skip=lambda: withdrawals.append('two'))
    assert withdrawals == ['two']


def _main_loop_functions():
    """Execute unchanged production function ASTs without importing every router."""
    tree = ast.parse((Path(__file__).parents[2] / 'main.py').read_text())
    names = {
        '_run_fsr_loop',
        '_listen_finalization_reconcile_interval_seconds',
        '_deletion_wipe_reconcile_interval_seconds',
        '_periodic_listen_finalization_reconcile',
        '_periodic_deletion_wipe_reconcile',
        '_periodic_durable_queue_age_publish',
        '_drain_listen_finalization_jobs',
        '_drain_pending_deletion_wipes',
        '_drain_stale_processing_conversations',
        '_drain_stale_in_progress_conversations',
        '_drain_abandoned_byok_finalization_jobs',
    }
    module = ast.Module(
        body=[
            node
            for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in names
        ],
        type_ignores=[],
    )
    namespace = {
        'os': os,
        'asyncio': asyncio,
        'db_executor': None,
        'logger': logging.getLogger('fsr_s2'),
        'quiet_finalization_enabled': quiet_finalization_enabled,
    }
    exec(compile(module, 'main_loop_functions', 'exec'), namespace)
    return namespace


@pytest.mark.parametrize('periodic', [False, True])
def test_real_startup_and_periodic_bodies_are_leased_and_attributed(fleet, monkeypatch, periodic):
    from database.firestore_read_origin import current_read_origin

    namespace = _main_loop_functions()
    calls = []
    replicas = [{}, {}]
    current = [0]

    def lease_for(loop):
        return replicas[current[0]].setdefault(loop, fleet.replica(loop))

    monkeypatch.setattr(leases, 'loop_lease', lease_for)
    loops = leases._LOOPS
    for loop in loops:
        namespace[loop] = lambda loop=loop: calls.append((loop, current_read_origin())) or {}

    async def run_blocking(_, callback, *args):
        return callback(*args)

    namespace['run_blocking'] = run_blocking

    class StopLoop(Exception):
        pass

    sleep_calls = [0]

    async def sleep(_):
        sleep_calls[0] += 1
        if sleep_calls[0] > 1:
            raise StopLoop

    namespace['asyncio'] = SimpleNamespace(sleep=sleep)
    for index in range(2):
        current[0] = index
        if periodic:
            for function in (
                '_periodic_deletion_wipe_reconcile',
                '_periodic_listen_finalization_reconcile',
                '_periodic_durable_queue_age_publish',
            ):
                sleep_calls[0] = int(function == '_periodic_durable_queue_age_publish')
                with pytest.raises(StopLoop):
                    asyncio.run(namespace[function]())
        else:
            for function in (
                '_drain_pending_deletion_wipes',
                '_drain_listen_finalization_jobs',
                '_drain_stale_processing_conversations',
                '_drain_stale_in_progress_conversations',
                '_drain_abandoned_byok_finalization_jobs',
            ):
                namespace[function]()
    expected = set(loops if periodic else loops[:-1])
    assert {name for name, _ in calls} == expected
    assert len(calls) == len(expected)
    assert all(origin == f'job:{name}' for name, origin in calls)


def test_cadence_defaults_overrides_and_ttl_floor(monkeypatch):
    monkeypatch.delenv('LISTEN_QUIET_FINALIZATION_ENABLED', raising=False)
    namespace = _main_loop_functions()
    for key, function in [
        ('LISTEN_FINALIZATION_RECONCILE_INTERVAL_SECONDS', '_listen_finalization_reconcile_interval_seconds'),
        ('DELETION_WIPE_RECONCILE_INTERVAL_SECONDS', '_deletion_wipe_reconcile_interval_seconds'),
    ]:
        monkeypatch.delenv(key, raising=False)
        expected = 60 if key == 'LISTEN_FINALIZATION_RECONCILE_INTERVAL_SECONDS' else 300
        assert namespace[function]() == expected
        monkeypatch.setenv(key, '17')
        assert namespace[function]() == 17
        monkeypatch.setenv(key, 'bad')
        assert namespace[function]() == expected
    monkeypatch.setenv('LISTEN_QUIET_FINALIZATION_ENABLED', 'false')
    assert namespace['_listen_finalization_reconcile_interval_seconds']() == 300
    monkeypatch.setenv('FSR_LEADER_LEASE_TTL_SECONDS', '2')
    assert leases._ttl_ms(300) > 300000


@pytest.mark.parametrize('ttl', [30, 120])
@pytest.mark.parametrize('death_offset', [0, 0.5])
@pytest.mark.parametrize('sample_fraction', [0, 1])
def test_queue_dead_owner_replaced_and_real_sample_published_within_240s(
    fleet, monkeypatch, ttl, death_offset, sample_fraction
):
    import utils.durable_queue_metrics as metrics

    monkeypatch.setenv('FSR_QUEUE_AGE_LEASE_SECONDS', str(ttl))
    sample_seconds = ttl * sample_fraction  # Finish within the new per-admission 2 x TTL cap.
    owner, follower = fleet.replica(leases.QUEUE_AGE_LOOP), fleet.replica(leases.QUEUE_AGE_LOOP)
    client = CountingFirestore()
    published = []
    monkeypatch.setattr(
        metrics, 'publish_sampled_queue_oldest_ready_ages', lambda sample: published.append(fleet.redis.now)
    )

    def publish():
        ages.publish_all_queue_oldest_ready_ages(firestore_client=client, finalization_summary={})

    owner.run(publish, 300)
    assert published == [0]
    fleet.redis.advance(ttl * death_offset)
    owner._idle_permit.check()  # Last heartbeat immediately before process death.
    died_at = fleet.redis.now
    owner._stop_idle_heartbeat()  # Simulate death: no release and no more heartbeats.
    assert fleet.redis.get(owner.keys[2]) is not None  # 300s cooldown remains.
    original_stream = client.stream

    def slow_sample():
        fleet.redis.advance(sample_seconds / 10)  # Ten actual status queries per sample.
        return original_stream()

    monkeypatch.setattr(client, 'stream', slow_sample)
    monkeypatch.setattr(leases, 'loop_lease', lambda _: follower)
    namespace = _main_loop_functions()
    namespace[leases.QUEUE_AGE_LOOP] = publish

    async def run_blocking(_, callback, *args):
        return callback(*args)

    class SamplePublished(Exception):
        pass

    async def sleep(delay):
        if len(published) == 2:
            raise SamplePublished
        assert 0 < delay <= ttl
        fleet.redis.advance(delay)

    namespace['run_blocking'] = run_blocking
    namespace['asyncio'] = SimpleNamespace(sleep=sleep)
    with pytest.raises(SamplePublished):
        asyncio.run(namespace['_periodic_durable_queue_age_publish'](300))
    assert published[1] - died_at == ttl + sample_seconds
    assert published[1] - died_at <= 240
    assert published[1] - sample_seconds < 300  # Never waited for the dead owner's cooldown.
    assert client.reads == 40  # Two actual 20-document samples.


def test_queue_live_owner_heartbeat_preserves_cooldown_beyond_short_ttl(fleet):
    owner, follower = fleet.replica(leases.QUEUE_AGE_LOOP), fleet.replica(leases.QUEUE_AGE_LOOP)
    samples = []
    owner.run(lambda: samples.append(fleet.redis.now), 300)
    assert owner._idle_renewal.is_alive()  # Heartbeat survives callback completion.
    for _ in range(7):
        fleet.redis.advance(40)
        owner._idle_permit.check()
        assert follower.run(lambda: pytest.fail('live owner replaced'), 300) is None
        owner.run(lambda: pytest.fail('cooldown bypassed'), 300)
    fleet.redis.advance(20)
    owner.run(lambda: samples.append(fleet.redis.now), 300)
    assert samples == [0, 300]
    assert owner._idle_renewal.is_alive()


@pytest.mark.parametrize('eligible', [None, '0', 'true'])
def test_queue_ineligible_never_contends_samples_or_publishes_even_on_redis_failure(fleet, monkeypatch, eligible):
    if eligible is None:
        monkeypatch.delenv('FSR_QUEUE_AGE_PUBLISHER')
    else:
        monkeypatch.setenv('FSR_QUEUE_AGE_PUBLISHER', eligible)
    withdrawals = []
    monkeypatch.setattr(ages, 'withdraw_queue_oldest_ready_ages', lambda: withdrawals.append(True))
    fleet.redis.error = True
    namespace = _main_loop_functions()
    monkeypatch.setattr(leases, 'loop_lease', lambda _: fleet.replica(leases.QUEUE_AGE_LOOP))
    namespace['_run_fsr_loop'](leases.QUEUE_AGE_LOOP, lambda: pytest.fail('ineligible callback'), 300)
    ages.publish_all_queue_oldest_ready_ages(firestore_client=object())  # Also fences direct calls.
    assert withdrawals == [True, True]
    assert fleet.redis.calls == 0


def test_queue_owner_losing_eligibility_releases_and_withdraws(fleet, monkeypatch):
    owner = fleet.replica(leases.QUEUE_AGE_LOOP)
    withdrawals = []
    owner.run(lambda: None, 300)
    monkeypatch.delenv('FSR_QUEUE_AGE_PUBLISHER')
    owner.run(lambda: pytest.fail('ineligible callback'), 300, on_skip=lambda: withdrawals.append(True))
    assert withdrawals == [True]
    assert fleet.redis.get(owner.keys[0]) is None
    assert not owner._idle_renewal.is_alive()


def test_queue_lever_off_ignores_eligibility_and_ttl_and_uses_original_periodic_path(fleet, monkeypatch):
    monkeypatch.delenv('FIRESTORE_READ_LEVERS')
    monkeypatch.delenv('FSR_QUEUE_AGE_PUBLISHER')
    monkeypatch.setenv('FSR_QUEUE_AGE_LEASE_SECONDS', '1')
    client = CountingFirestore()
    for _ in range(2):
        fleet.replica(leases.QUEUE_AGE_LOOP).run(
            lambda: ages.publish_all_queue_oldest_ready_ages(firestore_client=client, finalization_summary={}), 300
        )
    assert client.reads == 40
    assert fleet.redis.calls == 0
    assert leases.poll_delay(300, queue_age=True) == 300
    namespace = _main_loop_functions()

    class StopLoop(Exception):
        pass

    async def sleep(delay):
        assert delay == 300
        raise StopLoop

    async def run_blocking(*_):
        pytest.fail('separate publisher must not sample with lever off')

    namespace['run_blocking'] = run_blocking
    namespace['asyncio'] = SimpleNamespace(sleep=sleep)
    with pytest.raises(StopLoop):
        asyncio.run(namespace['_periodic_durable_queue_age_publish']())


def test_queue_ttl_default_override_and_safety_ceiling_do_not_change_other_loops(fleet, monkeypatch):
    assert leases.queue_age_lease_seconds() == 120
    for value, expected in [('30', 30), ('bad', 120), ('0', 1), ('900', 120)]:
        monkeypatch.setenv('FSR_QUEUE_AGE_LEASE_SECONDS', value)
        assert leases.queue_age_lease_seconds() == expected
    assert leases._ttl_ms(300) == 600000


def test_ineligible_queue_host_can_still_win_all_five_recovery_leases(fleet, monkeypatch):
    monkeypatch.delenv('FSR_QUEUE_AGE_PUBLISHER')
    for loop in leases._LOOPS[:-1]:
        assert fleet.replica(loop).run(lambda: 'ran', 300) == 'ran'
