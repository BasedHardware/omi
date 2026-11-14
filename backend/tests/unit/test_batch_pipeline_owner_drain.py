"""Per-owner projection drain, read-ahead and deferred indexing (Phase 1).

The drain runs the real ``Projector`` walk, ``OwnerDrains`` scheduler and
``Serving.reconcile_async`` on the ``ResultLog`` contract model. Ordering stays
with the predecessor fence: ``ResultLog``'s ``persist_empty`` reruns it, as the
assignment transaction does, even when a walk skips the pre-check.
"""

import asyncio
import itertools
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from copy import deepcopy
from unittest.mock import Mock

import pytest
import pytest_asyncio

from config.batch_pipeline import projection_drain_claim_aware_enabled, projection_prefetch_depth
from config.policy.kill_switches import KILL_SWITCHES
from database import conversations as conversations_db
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from tests.unit.test_batch_pipeline_owner_chain_projection import BURST, ResultLog, chain, projector_for
from tests.unit.test_batch_pipeline_scheduler import MemoryStore
from tests.unit.test_sync_assignment_contention_retry import sdk_assignment  # noqa: F401 (fixture)
from tests.unit.test_sync_cross_job_assignment import chunk
from utils.batch_pipeline import projection, projection_drain, projection_followup, projection_prefetch
from utils.batch_pipeline.projection_index import ProjectionIndex
from utils.batch_pipeline.scheduler import owner_key
from utils.batch_pipeline.serving import Serving
from utils.sync.assignment import assign_in_transaction

SWITCHES = (
    'PROJECTION_DRAIN_LIVE_TARGET_BACKOFF',
    'PROJECTION_DRAIN_CLAIM_AWARE',
    'BATCH_PIPELINE_OWNER_DRAIN_ENABLED',
    'BATCH_PIPELINE_PROJECTION_PREFETCH',
    'BATCH_PIPELINE_PROJECTION_INDEX_DEFERRED_ENABLED',
    'BATCH_PIPELINE_SWEEP_OWNER_CHAIN_ENABLED',
    'BATCH_PIPELINE_PROJECTION_PENDING_PAGE_ENABLED',
    'BATCH_PIPELINE_OWNER_CHAIN_PROJECTION_ENABLED',
    'BATCH_PIPELINE_PROJECTION_PAGINATION_ENABLED',
)


class Claims:
    """Advisory owner claim: records concurrent holders; ``busy`` keys refuse."""

    def __init__(self):
        self.busy: set[str] = set()
        self.held: set[str] = set()
        self.entered: list[str] = []
        self.overlaps = 0

    @contextmanager
    def claim(self, namespace, key):
        if key in self.busy or key in self.held:
            if key in self.held:
                self.overlaps += 1
            yield False
            return
        self.held.add(key)
        self.entered.append(key)
        try:
            yield True
        finally:
            self.held.discard(key)


@pytest.fixture(autouse=True)
def claims(monkeypatch):
    state = Claims()
    monkeypatch.setattr(
        projection_drain, 'projection_claim_held', lambda namespace, key: key in state.busy or key in state.held
    )
    monkeypatch.setattr(projection, 'projection_claim', state.claim)
    monkeypatch.setattr(projection_followup, 'projection_claim', state.claim)
    for name in SWITCHES:
        monkeypatch.delenv(name, raising=False)
    return state


class CountingLog(ResultLog):
    """Counts read-only pre-check transactions apart from the persist fence."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.prechecks = 0

    def check(self, session, *, precheck=True):
        self.prechecks += int(precheck)
        return super().check(session)

    def session(self, sid, binding, now, **kwargs):
        session = super().session(sid, binding, now, **kwargs)
        log = self

        def persist_empty(**_):
            # The assignment transaction's own fence, not a pre-check.
            log.check(session, precheck=False)
            receipt = {'state': 'persisted'}
            log.results[sid].update(projection=receipt, projection_state='persisted')
            log.owners.setdefault(owner_key(binding.owner_id), {})['projection_watermark'] = sid
            log.persist_order.append(sid)
            return receipt

        session.persist_empty = persist_empty
        return session


async def settle(projector):
    """Wait until the process drain has nothing running or queued."""
    for _ in range(1000):
        drains = projector.drains
        if drains is None or (not drains.tasks and not drains.queue and not drains.backlog):
            return
        await asyncio.gather(*list(drains.tasks.values()), return_exceptions=True)
        await asyncio.sleep(0)
    raise AssertionError('owner drain did not settle')


def owner_rows(log, owner):
    key = owner_key(owner)
    return [sid for sid in log.persist_order if log.results[sid]['owner_key'] == key]


@pytest.fixture
def serial_owner_steps(monkeypatch):
    """Deterministic cross-owner persist order for the fairness assertions.

    Owner turns persist their steps through the 16-worker sync executor, so
    which of two concurrent turns' steps reaches ``persist_order`` first is
    thread timing, not scheduler order: on a loaded hosted runner a backlog
    continuation's step overtook the newly admitted owner's (SCA-2182,
    completion index 9 vs the asserted 7 — the scheduler had admitted the new
    owner first). Fairness tests below pin the order the scheduler actually
    controls by serializing steps (one FIFO executor worker) and skipping the
    executor claim hop only a first turn pays; claim-aware admission itself
    has its own tests below.
    """
    monkeypatch.setenv('PROJECTION_DRAIN_CLAIM_AWARE', 'off')
    with ThreadPoolExecutor(max_workers=1) as executor:
        monkeypatch.setattr(projection_drain, 'sync_executor', executor)
        yield


# --- fairness and scheduling -------------------------------------------------------


@pytest.mark.asyncio
async def test_heavy_owners_cannot_starve_a_light_owner(monkeypatch, claims, serial_owner_steps):
    """One slot, one two-row step per turn: owners take FIFO turns, in chain order."""
    monkeypatch.setattr(projection_drain, 'MAX_OWNER_DRAINS', 1)
    monkeypatch.setattr(projection_drain, 'FIRST_TURN_SECONDS', 0.0)  # The single FIFO queue.
    monkeypatch.setattr(projection, 'OWNER_DRAIN_STEP_ROWS', 2)
    # Each read jumps past any turn deadline, so every turn is exactly one step.
    ticks = itertools.count(0.0, 10_000.0)
    monkeypatch.setattr(projection_drain, 'time', Mock(monotonic=lambda: next(ticks)))
    log = ResultLog()
    heavy_1 = chain(log, 'heavy-1', 'h1', 12)
    heavy_2 = chain(log, 'heavy-2', 'h2', 12)
    light = chain(log, 'light', 'l', 3)
    projector = projector_for(log)
    projector.drain_requests = dict.fromkeys(['heavy-1', 'heavy-2', 'light'])
    projector.start_drains()
    await settle(projector)
    assert owner_rows(log, 'heavy-1') == heavy_1
    assert owner_rows(log, 'heavy-2') == heavy_2
    assert owner_rows(log, 'light') == light
    # Turns rotate (H1, H2, L, H1, H2, L): the light owner finishes in its
    # second turn, after 8 heavy rows instead of all 24.
    assert log.persist_order.index(light[-1]) == 10
    assert claims.overlaps == 0 and not projector.draining


@pytest.mark.asyncio
async def test_backlog_owners_do_not_hold_a_new_owner_behind_them(monkeypatch, claims, serial_owner_steps):
    """2026-11-13: a few hundred backlog owners held every slot for two minutes a turn and
    owners with a few fresh rows waited behind them. A new owner now goes before queued
    backlog owners; every chain still projects whole and in order."""
    monkeypatch.setattr(projection_drain, 'MAX_OWNER_DRAINS', 2)
    monkeypatch.setattr(projection, 'OWNER_DRAIN_STEP_ROWS', 2)
    ticks = itertools.count(0.0, 10_000.0)
    monkeypatch.setattr(projection_drain, 'time', Mock(monotonic=lambda: next(ticks)))
    log = ResultLog()
    heavy = {name: chain(log, name, name, 12) for name in ('h1', 'h2', 'h3')}
    light = chain(log, 'light', 'l', 2)
    projector = projector_for(log)
    projector.drain_requests = dict.fromkeys(['h1', 'h2', 'h3', 'light'])
    projector.start_drains()
    await settle(projector)
    for name, rows in heavy.items():
        assert owner_rows(log, name) == rows
    assert owner_rows(log, 'light') == light
    # The light owner is done after one first turn of each heavy owner ahead of it in the
    # queue (6 rows), before any heavy owner gets a second turn.
    assert log.persist_order.index(light[-1]) == 7
    assert claims.overlaps == 0 and not projector.draining


def test_new_owners_launch_first_and_the_backlog_still_advances(monkeypatch):
    monkeypatch.setattr(projection_drain, 'MAX_OWNER_DRAINS', 2)
    monkeypatch.setattr(projection_drain, 'BACKLOG_OWED_TURNS', 1)
    drains = projection_drain.OwnerDrains(projector_for(ResultLog()))
    drains.backlog.extend(['b1', 'b2'])
    drains.queue.extend(['n1', 'n2', 'n3'])
    assert [drains.next_owner(), drains.next_owner()] == ['n1', 'n2']
    # One round of new owners with no backlog owner running: the backlog is owed a turn.
    assert drains.next_owner() == 'b1' and drains.backlog_running == {'b1'}
    assert drains.next_owner() == 'n3'
    # No new owner waiting: backlog owners may use any free slot.
    assert drains.next_owner() == 'b2'
    assert drains.next_owner() is None


def test_a_backlog_turn_yields_only_for_a_new_owner_without_a_slot(monkeypatch):
    monkeypatch.setattr(projection_drain, 'MAX_OWNER_DRAINS', 3)
    drains = projection_drain.OwnerDrains(projector_for(ResultLog()))
    drains.tasks = dict.fromkeys(['b1', 'b2', 'b3'])
    drains.backlog_running = {'b1', 'b2', 'b3'}
    assert drains.should_yield('b1') is False  # Nobody is waiting.
    drains.queue.append('n1')
    assert drains.should_yield('b1') is True
    assert drains.should_yield('b2') is False  # One waiting owner takes one slot.
    drains.queue.append('n2')
    assert drains.should_yield('b2') is True
    drains.queue.append('n3')
    assert drains.should_yield('b3') is False  # Never the last backlog turn running.
    # A free slot serves the waiting owner without ending anyone's turn.
    drains.yielding.clear()
    drains.tasks.pop('b3')
    drains.backlog_running.discard('b3')
    drains.queue.clear()
    drains.queue.append('n1')
    assert drains.should_yield('b1') is False
    # A new owner's own first turn is never ended early.
    drains.queue.extend(['n2', 'n3'])
    assert drains.should_yield('n9') is False


def test_first_turn_zero_keeps_the_single_fifo_queue(monkeypatch):
    monkeypatch.setattr(projection_drain, 'FIRST_TURN_SECONDS', 0.0)
    drains = projection_drain.OwnerDrains(projector_for(ResultLog()))
    assert drains.classes() is False
    monkeypatch.setattr(projection_drain, 'FIRST_TURN_SECONDS', 15.0)
    assert drains.classes() is True


def test_first_turn_seconds_setting(monkeypatch):
    from config.batch_pipeline import owner_drain_first_turn_seconds

    monkeypatch.delenv('BATCH_PIPELINE_OWNER_DRAIN_FIRST_TURN_SECONDS', raising=False)
    assert owner_drain_first_turn_seconds() == 15
    for raw, want in (('0', 0), ('30', 30), ('999', 120), ('-5', 0), ('junk', 15)):
        monkeypatch.setenv('BATCH_PIPELINE_OWNER_DRAIN_FIRST_TURN_SECONDS', raw)
        assert owner_drain_first_turn_seconds() == want


@pytest.mark.asyncio
async def test_concurrent_drains_are_bounded_and_one_per_owner(monkeypatch, claims):
    monkeypatch.setattr(projection_drain, 'MAX_OWNER_DRAINS', 2)
    log = ResultLog()
    chains = {owner: chain(log, owner, owner, 5) for owner in ('o1', 'o2', 'o3', 'o4')}
    projector = projector_for(log)
    seen = []
    real = projector.drain_step

    def step(owner, budget, **kwargs):
        seen.append(len(projector.draining))
        return real(owner, budget, **kwargs)

    projector.drain_step = step
    projector.drain_requests = dict.fromkeys(chains)
    projector.start_drains()
    # Re-requesting a running or queued owner never starts a second walk.
    projector.drains.request(list(chains))
    await settle(projector)
    assert max(seen) <= 2
    for owner, ids in chains.items():
        assert owner_rows(log, owner) == ids
    assert claims.overlaps == 0


@pytest.mark.asyncio
async def test_sweep_discovers_owners_and_the_drain_walks_them(monkeypatch):
    log = ResultLog()
    ids = chain(log, BURST, 'a', 80)
    projector = projector_for(log)
    walk = Mock(wraps=projector._walk_owner)
    projector._walk_owner = walk
    service = Serving(MemoryStore(), projector=projector)
    await service.reconcile_async(periodic=True)
    await settle(projector)
    assert log.persist_order == ids
    # The sweep made no budgeted walk; it persisted the head and handed off.
    assert all(call.kwargs['budget_seconds'] == 0 for call in walk.call_args_list)
    # Every async row the drain persisted is owed a follow-up.
    assert set(ids[1:]) <= set(projector.chain_followups)
    assert projector.owes_followups and not projector.owes_drains


def test_sweep_leaves_page_rows_of_a_handed_off_owner_to_the_drain():
    log = ResultLog()
    ids = chain(log, BURST, 'a', 5)
    other = chain(log, 'other', 'o', 2)
    projector = projector_for(log)
    counts = projector.sweep()
    # Head rows only; the rest of each owner's page rows wait for its drain.
    assert log.persist_order == [ids[0], other[0]]
    assert list(projector.drain_requests) == [BURST, 'other']
    # Rows left to the drain still count as waiting, not vanish from the summary.
    assert counts == {'completed': 0, 'waiting': 7, 'blocked': 0, 'error': 0}


def test_an_owner_queued_from_an_earlier_pass_still_gets_page_progress():
    """Requests nobody consumed never stall an owner: each pass persists its head."""
    log = ResultLog()
    ids = chain(log, BURST, 'a', 3)
    projector = projector_for(log)
    for _ in ids:
        projector.sweep()
    assert log.persist_order == ids
    assert list(projector.drain_requests) == [BURST]


def test_handoffs_from_pool_threads_serialize_with_event_loop_swaps():
    import threading

    projector = projector_for(ResultLog())
    with projector.handoff:  # an event-loop swap in progress
        writers = [
            threading.Thread(target=projector.request_drain, args=('o1',)),
            threading.Thread(target=projector.owe_followups, args=(['s1'],)),
        ]
        for writer in writers:
            writer.start()
        assert not projector.drain_requests and not projector.chain_followups
    for writer in writers:
        writer.join(timeout=5)
    assert list(projector.drain_requests) == ['o1'] and projector.chain_followups == ['s1']


def test_kill_switch_restores_the_sweep_walk(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_OWNER_DRAIN_ENABLED', 'false')
    log = ResultLog()
    ids = chain(log, BURST, 'a', 10)
    projector = projector_for(log)
    projector.sweep()
    assert log.persist_order == ids
    assert not projector.drain_requests and projector.drains is None


def test_wake_that_stops_at_its_bound_hands_the_owner_to_the_drain():
    log = ResultLog()
    chain(log, BURST, 'a', 10)
    projector = projector_for(log)
    projector.project_owner(BURST, limit=3)
    assert log.persist_order == [f'a-{n}' for n in range(3)]
    assert list(projector.drain_requests) == [BURST]


# --- the drain step: claim, pre-checks, fences ----------------------------------------


def test_drain_step_holds_the_owner_claim_and_skips_only_the_pre_checks(claims):
    log = CountingLog()
    ids = chain(log, BURST, 'a', 6)
    projector = projector_for(log)
    walk = projector.drain_step(BURST, 30.0)
    assert walk.advanced == ids and log.persist_order == ids and not walk.more
    assert log.prechecks == 0
    # One claim for the whole step, not one per row.
    assert claims.entered == [owner_key(BURST)]


def test_drain_off_walk_keeps_every_pre_check(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_OWNER_DRAIN_ENABLED', 'false')
    log = CountingLog()
    ids = chain(log, BURST, 'a', 4)
    projector_for(log).project_owner(BURST)
    assert log.persist_order == ids and log.prechecks == len(ids)


def test_busy_owner_claim_stops_the_step_before_any_read(claims):
    log = ResultLog()
    chain(log, BURST, 'a', 3)
    claims.busy.add(owner_key(BURST))
    walk = projector_for(log).drain_step(BURST, 30.0)
    assert walk == projection.Walk([], [], False, 'claim_busy') and log.persist_order == []


def test_predecessor_fence_still_stops_a_drain_without_pre_checks():
    log = CountingLog()
    ids = chain(log, BURST, 'a', 5)
    projector = projector_for(log)
    real = log.projection_successor
    # A stale successor link (another replica's view) skips a row: the
    # transaction's predecessor fence refuses it, so nothing moves out of order.
    log.projection_successor = lambda key, previous: ids[2] if previous == ids[0] else real(key, previous)
    walk = projector.drain_step(BURST, 30.0)
    assert log.persist_order == ids[:1] and walk.advanced == ids[:1] and not walk.more
    assert log.blocked_checks == 1 and log.prechecks == 0


@pytest.mark.parametrize('fresh_read_saw_receipt', [True, False])
def test_a_row_persisted_elsewhere_is_a_replay_with_or_without_the_pre_check(fresh_read_saw_receipt):
    log = CountingLog()
    ids = chain(log, BURST, 'a', 2)
    projector = projector_for(log)
    job, entry, binding = log.read(ids[0])
    projector._persist_read(ids[0], job, dict(entry), binding)  # another walker won
    log.prechecks = 0
    seen = dict(entry, projection={'state': 'persisted'}) if fresh_read_saw_receipt else entry
    projector._assign(ids[0], job, seen, binding, finish=False, hint=projection.WalkHint(successor=True))
    assert log.persist_order == ids[:1]  # nothing persisted twice, nothing raised
    # A receipt the walk saw replays through the check; a raced one through the fence.
    assert log.prechecks == int(fresh_read_saw_receipt)


def test_step_bounded_by_rows_reports_more():
    log = ResultLog()
    chain(log, BURST, 'a', 5)
    walk = projector_for(log)._walk(BURST, recovered=None, limit=2, budget_seconds=30.0)
    assert len(walk.advanced) == 2 and walk.more


# --- equivalence with today's sweep walk ------------------------------------------------


def catch_up_log():
    log = ResultLog()
    log.commit(BURST, 'done', 'done', ['done'], state='ready')
    first = chain(log, BURST, 'a', 7)
    log.commit('other', 'x', 'x-0', ['x-0'])
    log.commit(BURST, 'gone', 'gone', ['gone'], erased=True)
    chain(log, BURST, 'b', 9)
    chain(log, 'other', 'y', 4)
    return log, first


def durable(log):
    return deepcopy(log.results), deepcopy(log.owners)


@pytest.mark.asyncio
async def test_drained_catch_up_final_state_equals_the_sweep_walk(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_OWNER_DRAIN_ENABLED', 'false')
    legacy, _ = catch_up_log()
    projector = projector_for(legacy)
    projector.clock = lambda: 1000.0
    for _ in range(10):
        projector.sweep()
    assert legacy.persisted(BURST) and legacy.persisted('other')

    monkeypatch.delenv('BATCH_PIPELINE_OWNER_DRAIN_ENABLED')
    drained, _ = catch_up_log()
    projector = projector_for(drained)
    projector.clock = lambda: 1000.0
    service = Serving(MemoryStore(), projector=projector)
    for _ in range(3):
        await service.reconcile_async(periodic=True)
        await settle(projector)
    assert durable(drained) == durable(legacy)
    for owner in (BURST, 'other'):
        assert owner_rows(drained, owner) == owner_rows(legacy, owner)


def test_projection_drain_sim_assignments_equal_the_sweep_walk():
    """Real assignment inputs (prefetch, parallel candidate, deferred index)."""
    from testing.pipeline_sim import projection_drain as sim

    legacy = sim.run('sweep_walk', rows=40)
    drained = sim.run('drain', rows=40)
    assert legacy['all_persisted'] and drained['all_persisted']
    assert legacy['chain_order'] and drained['chain_order']
    assert drained['assignments'] == legacy['assignments']
    assert drained['index'] == legacy['index']
    assert drained['check_transactions'] < legacy['check_transactions']


# --- read-ahead -------------------------------------------------------------------------


class InlineExecutor:
    def submit(self, fn, *args, **kwargs):
        from concurrent.futures import Future

        future = Future()
        try:
            future.set_result(fn(*args, **kwargs))
        except Exception as error:
            future.set_exception(error)
        return future


def test_prefetch_reads_immutable_inputs_once_and_successor_links_ahead(monkeypatch):
    log = ResultLog()
    ids = chain(log, BURST, 'a', 6)
    for sid in ids:
        log.results[sid]['result'] = {'outcome': 'no_recoverable_speech', 'result_uri': f'gs://synthetic/{sid}'}
    loads = []
    projector = projector_for(log)
    projector.load_result = lambda item, uri: loads.append(uri) or {}
    prefetch = projection_prefetch.ChainPrefetch(projector, owner_key(BURST), 3, executor=InlineExecutor())
    prefetch.advance(None)
    assert [prefetch.successor(previous) for previous in [None, *ids[:2]]] == ids[:3]
    taken = prefetch.take(ids[0])
    assert taken.binding == log.bindings[ids[0]] and taken.job['segment_id'] == ids[0]
    assert loads == [f'gs://synthetic/{sid}' for sid in ids[:3]]
    assert prefetch.take(ids[0]) is None  # taken once; a miss falls back inline
    prefetch.close()
    prefetch.advance(ids[0])
    assert prefetch.successor(ids[2]) is None


def test_prefetch_errors_fall_back_to_the_walks_own_reads(monkeypatch):
    log = ResultLog()
    ids = chain(log, BURST, 'a', 3)
    projector = projector_for(log)
    real = log.read

    def flaky(sid):
        if sid == ids[1]:
            raise RuntimeError('synthetic outage')
        return real(sid)

    log.read = flaky
    prefetch = projection_prefetch.ChainPrefetch(projector, owner_key(BURST), 4, executor=InlineExecutor())
    prefetch.advance(None)
    assert prefetch.take(ids[1]) is None
    log.read = real
    walk = projector.drain_step(BURST, 30.0, prefetch=prefetch)
    assert walk.advanced == ids


def test_a_still_loading_read_ahead_ends_the_step_instead_of_holding_the_slot(monkeypatch):
    log = ResultLog()
    ids = chain(log, BURST, 'a', 3)
    projector = projector_for(log)
    loading = Mock(successor=Mock(return_value=None), take=Mock(return_value=projection_prefetch.NOT_READY))
    walk = projector.drain_step(BURST, 15.0, prefetch=loading)
    assert walk == projection.Walk([], [], True, 'prefetch_wait') and log.persist_order == []
    # The wait is capped by what is left of the step, never the 30 s ceiling.
    assert 0 < loading.take.call_args.kwargs['timeout'] <= 15.0
    loading.take.return_value = None
    assert projector.drain_step(BURST, 15.0, prefetch=loading).advanced == ids


def test_a_slow_read_ahead_is_never_redone_inline_only_a_failed_one(monkeypatch):
    from concurrent.futures import Future

    log = ResultLog()
    ids = chain(log, BURST, 'a', 2)
    projector = projector_for(log)
    waits = []
    monkeypatch.setattr(projection_prefetch, 'wait', lambda futures, timeout: waits.append(timeout))
    prefetch = projection_prefetch.ChainPrefetch(projector, owner_key(BURST), 1, executor=InlineExecutor())
    slow = prefetch.rows[ids[0]] = Future()
    for _ in range(3):  # however long it has waited across steps
        assert prefetch.take(ids[0], timeout=60.0) is projection_prefetch.NOT_READY
    assert ids[0] in prefetch.rows and waits == [projection_prefetch.PREFETCH_WAIT_SECONDS] * 3
    slow.set_exception(RuntimeError('synthetic storage timeout'))
    assert prefetch.take(ids[0], timeout=15.0) is None and ids[0] not in prefetch.rows


def test_prefetch_depth_kill_switch_and_bounds(monkeypatch):
    for raw, expected in (('0', 0), ('8', 8), ('9', 4), ('-1', 4), ('x', 4)):
        monkeypatch.setenv('BATCH_PIPELINE_PROJECTION_PREFETCH', raw)
        assert projection_prefetch_depth() == expected
    monkeypatch.delenv('BATCH_PIPELINE_PROJECTION_PREFETCH')
    assert projection_prefetch_depth() == 4
    monkeypatch.setenv('BATCH_PIPELINE_PROJECTION_PREFETCH', '0')
    assert projector_for(ResultLog()).chain_prefetch(BURST) is None


def test_new_switches_are_registered_kill_switches():
    assert KILL_SWITCHES['BATCH_PIPELINE_OWNER_DRAIN_ENABLED'] is True
    assert KILL_SWITCHES['PROJECTION_DRAIN_CLAIM_AWARE'] is True
    assert KILL_SWITCHES['BATCH_PIPELINE_PROJECTION_INDEX_DEFERRED_ENABLED'] is True


def test_parallel_candidate_is_used_only_for_the_exact_span():
    pending = ((10, 20), InlineExecutor().submit(lambda: {'id': 'near'}))
    assert projection.Projector._parallel_candidate(pending, (10, 20)) == (True, {'id': 'near'})
    assert projection.Projector._parallel_candidate(pending, (10, 21)) == (False, None)
    assert projection.Projector._parallel_candidate(None, (10, 20)) == (False, None)
    # No match is looked up again inline: a conversation may have committed since.
    nothing_near = ((10, 20), InlineExecutor().submit(lambda: None))
    assert projection.Projector._parallel_candidate(nothing_near, (10, 20)) == (False, None)
    failed = ((10, 20), InlineExecutor().submit(lambda: 1 / 0))
    assert projection.Projector._parallel_candidate(failed, (10, 20)) == (False, None)


def test_parallel_candidate_wait_never_outlasts_the_step(monkeypatch):
    future = Mock()
    future.result.side_effect = TimeoutError
    monkeypatch.setattr(projection, 'time', Mock(monotonic=lambda: 100.0))
    assert projection.Projector._parallel_candidate(((1, 2), future), (1, 2), 103.0) == (False, None)
    assert future.result.call_args.kwargs['timeout'] == 3.0
    projection.Projector._parallel_candidate(((1, 2), future), (1, 2), 90.0)
    assert future.result.call_args.kwargs['timeout'] == 0.0


def test_a_row_stopped_between_parts_ends_the_step_with_more():
    log = ResultLog()
    chain(log, BURST, 'a', 2)
    projector = projector_for(log)
    projector._persist_read = Mock(side_effect=projection.StepDeadline)
    assert projector.drain_step(BURST, 15.0) == projection.Walk([], [], True, 'step_deadline')
    assert projector._persist_read.call_args.kwargs['hint'].deadline is not None


def test_step_deadline_stops_between_parts_and_the_next_step_resumes(monkeypatch):
    from utils.batch_pipeline import projection_parts
    from utils.batch_pipeline.contracts import Priority, ProjectionBinding, WorkItem

    item = WorkItem('segment', 'synthetic-owner', 0, 'gs://synthetic/audio', 2, Priority.DEEP)
    payload = {'words': [], 'audio_seconds': 2, 'speech_seconds': 1, 'diarization': {'turns': []}}
    projector = projection.Projector(Mock(), Mock(return_value=payload))
    projector.store = Mock()
    persisted = []
    projector.store.session.side_effect = lambda *a, part_index=None, **k: Mock(
        persist_empty=lambda **_: persisted.append(part_index) or {'state': 'persisted'}
    )
    monkeypatch.setattr(projection_parts, 'split_result', lambda item, payload: [(item, payload)] * 3)
    # The step's budget runs out while part 1 persists.
    monkeypatch.setattr(projection, 'time', Mock(monotonic=lambda: 50.0 if len(persisted) >= 2 else 0.0))
    binding = ProjectionBinding('synthetic-owner', 'job', 'content', ('segment',))
    hint = projection.WalkHint(successor=True, deadline=10.0)
    entry = {'result': {'result_uri': 'fixture'}}
    with pytest.raises(projection.StepDeadline):
        projector.assign_parts(item, entry, binding, finish=False, hint=hint)
    assert persisted == [0, 1]  # parts 0 and 1 persisted; part 2 waits for the next step


# --- deferred index: only new donors, eventual equivalence -------------------------------


def intake(store, incoming, absorbed):
    with store.lock:
        return assign_in_transaction(
            store.transaction(),
            store.collection('users').document('u'),
            incoming,
            decode=deepcopy,
            encode=deepcopy,
            invalidate=lambda payload: None,
            absorbed=absorbed,
        )


def test_assignment_reports_only_newly_absorbed_donors():
    store = StrictFirestore()
    absorbed: list[str] = []
    intake(store, chunk('a', 1000), absorbed)
    intake(store, chunk('b', 1240), absorbed)
    assert absorbed == []
    bridged, _, _ = intake(store, chunk('bridge', 1120), absorbed)
    assert absorbed == sorted(set(bridged['sync_merged_from']))
    assert absorbed
    later, _, _ = intake(store, chunk('later', 1250), absorbed)
    # The cumulative lineage still names the donor; nothing new was absorbed.
    assert later['sync_merged_from'] and absorbed == []


class FakeSearch:
    """Typesense stand-in converging from StrictFirestore's durable rows."""

    def __init__(self, store):
        self.store, self.docs, self.calls = store, {}, 0
        self.failing: set[str] = set()  # fail-open deletes that time out once

    def row(self, cid):
        return next((value for key, value in self.store.rows.items() if key[-1] == cid), None)

    def delete(self, uid, cid):
        self.calls += 1
        if cid in self.failing:
            self.failing.discard(cid)
            return
        self.docs.pop(cid, None)

    def sync(self, uid, cid):
        self.calls += 1
        row = self.row(cid)
        if row is None or row.get('deleted'):
            self.docs.pop(cid, None)
        else:
            self.docs[cid] = (row['started_at'], row['finished_at'], len(row['transcript_segments']))


def lineage(result, absorbed):
    """What assign_sync_conversation hands defer_index."""
    return sorted({*(result.get('sync_merged_from') or []), *absorbed})


def replay_index(monkeypatch, *, deferred, flush_every, failing=()):
    store = StrictFirestore()
    search = FakeSearch(store)
    search.failing.update(failing)
    monkeypatch.setattr(conversations_db, '_delete_conversation_search_index', search.delete)
    monkeypatch.setattr(conversations_db, '_sync_conversation_search_index', search.sync)
    monkeypatch.setattr(conversations_db, 'invalidate_people_stats_cache', lambda uid: None)
    index = ProjectionIndex()
    # 'bridge' folds b into a; 'c' appends to a; 'e' folds d into a too.
    rows = [('a', 1000), ('b', 1240), ('bridge', 1120), ('c', 1255), ('d', 1500), ('e', 1380), ('f', 1262)]
    for n, (key, at) in enumerate(rows, start=1):
        absorbed: list[str] = []
        result, _, _ = intake(store, chunk(key, at), absorbed)
        # Every written conversation is indexed at once, as the extension would.
        search.docs.setdefault(result['id'], 'seeded')
        if deferred:
            index.defer('u', result['id'], lineage(result, absorbed))
            if n % flush_every == 0:
                index.flush()
        else:
            conversations_db.index_sync_assignment('u', [result['id']], result.get('sync_merged_from') or [])
    index.flush()
    return search


def test_deferred_index_converges_to_the_inline_index(monkeypatch):
    inline = replay_index(monkeypatch, deferred=False, flush_every=1)
    deferred = replay_index(monkeypatch, deferred=True, flush_every=len('abcdefg'))
    assert deferred.docs == inline.docs
    assert set(deferred.docs) == {'a'}  # donors b and d are gone from search
    # One lineage delete per donor per flush, not one per appended row.
    assert deferred.calls < inline.calls


def test_a_failed_donor_delete_is_retried_by_a_later_flush(monkeypatch):
    """The lineage, not only new donors, is re-deleted, as the inline step did."""
    inline = replay_index(monkeypatch, deferred=False, flush_every=1, failing={'b'})
    deferred = replay_index(monkeypatch, deferred=True, flush_every=3, failing={'b'})
    assert 'b' not in inline.docs and 'b' not in deferred.docs
    assert deferred.docs == inline.docs


def test_index_flush_is_single_flight_and_keeps_late_deferrals(monkeypatch):
    calls = []
    monkeypatch.setattr(
        conversations_db, 'index_sync_assignment', lambda uid, ids, donors: calls.append((uid, ids, donors))
    )
    index = ProjectionIndex()
    index.defer('u', 'c1', [])
    index.defer('u', 'c2', ['c1'])
    index.defer('u', 'c2', [])
    index.flushing.acquire()
    assert index.flush() == 0 and index.owed  # another flusher owns it
    index.flushing.release()
    assert index.flush() == 1 and not index.owed
    assert calls == [('u', ['c1', 'c2'], ['c1'])]


def test_scoped_index_flush_leaves_other_owners_for_periodic_work(monkeypatch):
    calls = []
    monkeypatch.setattr(
        conversations_db, 'index_sync_assignment', lambda uid, ids, donors: calls.append((uid, ids, donors))
    )
    index = ProjectionIndex()
    index.defer('recovered-owner', 'recovered-conversation', [])
    index.defer('unrelated-owner', 'unrelated-conversation', [])

    assert index.flush('recovered-owner') == 1
    assert calls == [('recovered-owner', ['recovered-conversation'], [])]
    assert index.has_owed('unrelated-owner')
    assert index.flush() == 1
    assert calls[-1] == ('unrelated-owner', ['unrelated-conversation'], [])
    assert not index.owed


def test_index_sync_assignment_deletes_donors_and_converges_the_rest(monkeypatch):
    ops = []
    monkeypatch.setattr(conversations_db, '_delete_conversation_search_index', lambda uid, cid: ops.append(('d', cid)))
    monkeypatch.setattr(conversations_db, '_sync_conversation_search_index', lambda uid, cid: ops.append(('s', cid)))
    monkeypatch.setattr(conversations_db, 'invalidate_people_stats_cache', lambda uid: ops.append(('p', uid)))
    conversations_db.index_sync_assignment('u', ['c1', 'c2', 'c1'], ['c1'])
    assert ops == [('p', 'u'), ('d', 'c1'), ('s', 'c2')]


def test_assign_sync_conversation_defers_the_lineage_instead_of_indexing(sdk_assignment, monkeypatch):  # noqa: F811
    from utils.sync import assignment

    store, _ = sdk_assignment()

    def body(transaction, user_ref, incoming, **kwargs):
        store.doc_ref.get(transaction=transaction)
        merged = {**incoming, 'sync_merged_from': ['old', 'new']}
        transaction.set(store.doc_ref, merged)
        kwargs['absorbed'][:] = ['new']
        return merged, False, merged['transcript_segments']

    monkeypatch.setattr(assignment, 'assign_in_transaction', body)
    inline = Mock()
    monkeypatch.setattr(conversations_db, 'index_sync_assignment', inline)
    deferred = []
    conversations_db.assign_sync_conversation(
        'synthetic-unit',
        chunk('canonical', 1000),
        firestore_client=store,
        defer_index=lambda *args: deferred.append(args),
    )
    # The lineage (old + new) is re-deleted once per flush, never per row.
    assert deferred == [('synthetic-unit', 'canonical', ['new', 'old'])]
    inline.assert_not_called()
    conversations_db.assign_sync_conversation('synthetic-unit', chunk('canonical', 1000), firestore_client=store)
    inline.assert_called_once_with('synthetic-unit', ['canonical'], ['old', 'new'])


@pytest.mark.asyncio
async def test_serving_tick_flushes_deferred_index_off_the_chain(monkeypatch):
    log = ResultLog()
    projector = projector_for(log)
    projector.index.defer('u', 'c1', [])
    flushed = []
    monkeypatch.setattr(conversations_db, 'index_sync_assignment', lambda *args: flushed.append(args))
    await Serving(MemoryStore(), projector=projector).reconcile_async(periodic=True)
    for _ in range(50):
        if flushed:
            break
        await asyncio.sleep(0.01)
    assert flushed == [('u', ['c1'], [])]


# --- stop reasons (log-only; 2026-11-05 heavy-chain follow-up) ----------------------


def test_walk_names_why_it_stopped():
    log = ResultLog()
    chain(log, BURST, 'a', 5)
    projector = projector_for(log)
    assert projector._walk(BURST, recovered=None, limit=2, budget_seconds=30.0).stop == 'limit'
    assert projector._walk(BURST, recovered=None, limit=100, budget_seconds=30.0).stop == 'end'
    from utils.batch_pipeline.projection_walk_stop import WALK_STOPS

    assert {'end', 'limit', 'claim_busy', 'turn_deadline', 'error'} <= WALK_STOPS


def test_predecessor_fence_stop_is_a_closed_blocked_token():
    log = CountingLog()
    ids = chain(log, BURST, 'a', 5)
    projector = projector_for(log)
    real = log.projection_successor
    log.projection_successor = lambda key, previous: ids[2] if previous == ids[0] else real(key, previous)
    walk = projector.drain_step(BURST, 30.0)
    assert walk.stop.startswith('blocked_') and walk.stop != 'blocked_'


def test_block_stop_tokens_are_log_safe():
    from database.batch_pipeline_projection import ProjectionBlocked

    closed = ProjectionBlocked('anything at all 123')
    setattr(closed, 'block_reason', 'lineage_ambiguous')
    assert projection.walk_block_stop(closed, projection.projection_block_reason(closed)) == 'blocked_lineage_ambiguous'
    assert (
        projection.walk_block_stop(ProjectionBlocked('projection assignment claim busy'), 'other')
        == 'blocked_projection_assignment_claim_busy'
    )
    # Anything that is not a constant lowercase literal collapses to `other`.
    for message in ('missing-input repair held: x1', 'uid abc/123', 'A' * 10, 'x' * 80, ''):
        assert projection.walk_block_stop(ProjectionBlocked(message), 'other') == 'blocked_other'


@pytest.mark.asyncio
async def test_drain_turn_log_carries_the_last_step_stop(monkeypatch, claims, caplog):
    import logging

    log = ResultLog()
    chain(log, BURST, 'a', 3)
    projector = projector_for(log)
    with caplog.at_level(logging.INFO, logger=projection_drain.logger.name):
        more = await projection_drain.OwnerDrains(projector).run(BURST)
    assert more is False
    turns = [r.getMessage() for r in caplog.records if 'action=owner_drain outcome=turn' in r.getMessage()]
    assert turns and ' stop=end ' in turns[-1] and 'event=batch_projection ' in turns[-1]

    claims.busy.add(owner_key(BURST))
    caplog.clear()
    with caplog.at_level(logging.INFO, logger=projection_drain.logger.name):
        await projection_drain.OwnerDrains(projector).run(BURST)
    assert any(' advanced=0 ' in r.getMessage() and ' stop=claim_busy ' in r.getMessage() for r in caplog.records)


@pytest_asyncio.fixture
async def drain_timers(monkeypatch):
    """Advance only drain retry timers, without wall-clock sleeps."""
    timers = []

    def later(delay, callback):
        handle = Mock()
        timers.append((delay, callback, handle))
        return handle

    monkeypatch.setattr(asyncio.get_running_loop(), 'call_later', later)
    return timers


@pytest.mark.asyncio
async def test_claim_held_defers_admission_and_retries_after_release(monkeypatch, claims, drain_timers):
    log = ResultLog()
    ids = chain(log, BURST, 'a', 3)
    projector = projector_for(log)
    drains = projector.drains = projection_drain.OwnerDrains(projector)
    claims.busy.add(owner_key(BURST))
    prefetch = Mock(wraps=projector.chain_prefetch)
    projector.chain_prefetch = prefetch
    drains.request([BURST])
    await settle(projector)
    assert not drains.queue and not drains.tasks and BURST in drains.delayed
    assert not log.persist_order
    prefetch.assert_not_called()
    drains.request([BURST] * 20)  # discovery cannot bypass the delay
    assert len(drain_timers) == 1
    delay, retry, _ = drain_timers.pop()
    assert 5 <= delay <= 15
    claims.busy.clear()
    retry()
    await settle(projector)
    assert log.persist_order == ids and not drains.delayed


@pytest.mark.asyncio
async def test_claim_busy_again_request_backs_off_and_retries(monkeypatch, claims, drain_timers):
    # Admission saw a free key; another walker won SET NX before our step.
    monkeypatch.setattr(projection_drain, 'projection_claim_held', lambda *args: False)
    log = ResultLog()
    ids = chain(log, BURST, 'a', 3)
    projector = projector_for(log)
    drains = projector.drains = projection_drain.OwnerDrains(projector)
    claims.busy.add(owner_key(BURST))
    projector.chain_prefetch = Mock(wraps=projector.chain_prefetch)
    from utils.batch_pipeline.metrics import PROJECTION_DRAIN_CLAIM_BUSY_BACKOFFS

    before = PROJECTION_DRAIN_CLAIM_BUSY_BACKOFFS._value.get()
    drains.request([BURST])
    drains.request([BURST])  # a fresh request arrived during the active turn
    await settle(projector)
    assert BURST in drains.delayed and not log.persist_order
    projector.chain_prefetch.assert_called_once_with(BURST)  # lazy construction remains unchanged
    assert PROJECTION_DRAIN_CLAIM_BUSY_BACKOFFS._value.get() == before + 1
    delay, retry, _ = drain_timers.pop()
    assert 5 <= delay <= 15
    claims.busy.clear()
    retry()
    await settle(projector)
    assert log.persist_order == ids


@pytest.mark.asyncio
async def test_claim_aware_off_preserves_admission_prefetch_and_no_busy_retry(monkeypatch, claims, drain_timers):
    monkeypatch.setenv('PROJECTION_DRAIN_CLAIM_AWARE', 'off')
    peek = Mock(side_effect=AssertionError('off must not peek'))
    monkeypatch.setattr(projection_drain, 'projection_claim_held', peek)
    log = ResultLog()
    chain(log, BURST, 'a', 3)
    projector = projector_for(log)
    drains = projector.drains = projection_drain.OwnerDrains(projector)
    claims.busy.add(owner_key(BURST))
    projector.chain_prefetch = Mock(wraps=projector.chain_prefetch)
    drains.request([BURST])
    await settle(projector)
    peek.assert_not_called()
    projector.chain_prefetch.assert_called_once_with(BURST)
    assert not drains.delayed and not drain_timers and not drains.queue


@pytest.mark.asyncio
async def test_delayed_state_is_bounded_and_close_cancels_retries(monkeypatch, drain_timers):
    monkeypatch.setattr(projection_drain, 'MAX_DELAYED_OWNERS', 1)
    drains = projection_drain.OwnerDrains(projector_for(ResultLog()))
    drains.defer('first')
    drains.defer('second')
    assert list(drains.delayed) == ['first'] and not drains.queue
    assert list(drains.projector.drain_requests) == ['second']
    _, retry, handle = drain_timers[0]
    drains.close()
    handle.cancel.assert_called_once()
    retry()  # even a callback already dispatched at shutdown cannot resurrect work
    drains.request(['third'])
    assert not drains.delayed and not drains.queue and not drains.tasks


@pytest.mark.parametrize('mode', ['shadow', 'serve'])
@pytest.mark.parametrize('value', [None, '', 'true', 'false', '0', 'on', 'unknown', 'off', 'OFF', ' off '])
def test_claim_aware_is_disabled_only_by_off(monkeypatch, value, mode):
    monkeypatch.setenv('CAPTURE_COVERAGE_MODE', mode)
    if value is None:
        monkeypatch.delenv('PROJECTION_DRAIN_CLAIM_AWARE', raising=False)
    else:
        monkeypatch.setenv('PROJECTION_DRAIN_CLAIM_AWARE', value)
    assert projection_drain_claim_aware_enabled() is (value is None or value.strip().lower() != 'off')


@pytest.mark.asyncio
async def test_peek_outage_still_admits_and_drains_owner(monkeypatch):
    from database import batch_pipeline_projection_claim as claim_db

    monkeypatch.setattr(claim_db, '_redis_client', Mock(side_effect=RuntimeError('synthetic outage')))
    monkeypatch.setattr(projection_drain, 'projection_claim_held', claim_db.projection_claim_held)
    log = ResultLog()
    ids = chain(log, BURST, 'a', 3)
    projector = projector_for(log)
    projector.drains = projection_drain.OwnerDrains(projector)
    projector.drains.request([BURST])
    await settle(projector)
    assert log.persist_order == ids and not projector.drains.delayed


@pytest.mark.asyncio
async def test_claim_busy_without_again_keeps_existing_sweep_retry_behavior(monkeypatch, claims, drain_timers):
    monkeypatch.setattr(projection_drain, 'projection_claim_held', lambda *args: False)
    log = ResultLog()
    chain(log, BURST, 'a', 3)
    projector = projector_for(log)
    projector.drains = projection_drain.OwnerDrains(projector)
    claims.busy.add(owner_key(BURST))
    projector.drains.request([BURST])
    await settle(projector)
    assert not projector.drains.delayed and not drain_timers
    assert not log.persist_order  # durable rows are still discovered by the sweep


@pytest.mark.asyncio
async def test_productive_continuation_never_peeks_or_backs_off(monkeypatch, drain_timers):
    log = ResultLog()
    ids = chain(log, BURST, 'a', 5)
    projector = projector_for(log)
    drains = projector.drains = projection_drain.OwnerDrains(projector)
    monkeypatch.setattr(projection, 'OWNER_DRAIN_STEP_ROWS', 2)
    ticks = itertools.count(0.0, 10_000.0)
    monkeypatch.setattr(projection_drain, 'time', Mock(monotonic=lambda: next(ticks)))
    # Only initial admission may peek. Another peer could hold a claim between
    # turns, but productive continuations must still enter the ordinary FIFO.
    peek = Mock(side_effect=[False, AssertionError('continuation must not peek')])
    monkeypatch.setattr(projection_drain, 'projection_claim_held', peek)
    drains.request([BURST])
    await settle(projector)
    assert log.persist_order == ids
    peek.assert_called_once()
    assert not drain_timers and not drains.continuations


PRIVACY_STOPS = [
    ('blocked_privacy_disposition_requires_a_source_deletion_tombstone', 'tombstone'),
    ('blocked_privacy_refusal_no_longer_applies', 'refusal_no_longer_applies'),
    ('blocked_privacy_future_reason', 'other'),
    # BatchPrivacyBlocked from the assignment fence (e.g. after the #24747 refusal
    # fall-through). 2026-11-06 05:16Z: un-backed-off, it starved drain to 0.2 rows/s.
    ('privacy_blocked', 'other'),
]


@pytest.mark.asyncio
@pytest.mark.parametrize('stop,reason', PRIVACY_STOPS)
@pytest.mark.parametrize('again', [False, True])
async def test_zero_progress_privacy_turn_defers_and_retries(monkeypatch, drain_timers, stop, reason, again):
    from utils.batch_pipeline.metrics import PROJECTION_DRAIN_PRIVACY_STOPS, PROJECTION_DRAIN_PRIVACY_BACKOFFS
    from utils.batch_pipeline.metrics import PROJECTION_DRAIN_LIVE_TARGET_BACKOFFS

    monkeypatch.delenv('PROJECTION_DRAIN_PRIVACY_BACKOFF', raising=False)
    monkeypatch.setenv('PROJECTION_DRAIN_PRIVACY_BACKOFF_SECONDS', '180')
    log = ResultLog()
    ids = chain(log, BURST, 'a', 3)
    projector = projector_for(log)
    drains = projector.drains = projection_drain.OwnerDrains(projector)
    real = projector.drain_step
    blocked = True
    projector.drain_step = lambda *a, **kw: projection.Walk([], [], False, stop) if blocked else real(*a, **kw)
    before_stops = PROJECTION_DRAIN_PRIVACY_STOPS.labels(reason=reason)._value.get()
    before_backoffs = PROJECTION_DRAIN_PRIVACY_BACKOFFS._value.get()
    before_live = PROJECTION_DRAIN_LIVE_TARGET_BACKOFFS._value.get()
    drains.request([BURST])
    if again:
        drains.request([BURST])
    await settle(projector)
    assert BURST in drains.delayed and not drains.queue and not drains.again and not drains.stops
    assert PROJECTION_DRAIN_PRIVACY_STOPS.labels(reason=reason)._value.get() == before_stops + 1
    assert PROJECTION_DRAIN_PRIVACY_BACKOFFS._value.get() == before_backoffs + 1
    assert PROJECTION_DRAIN_LIVE_TARGET_BACKOFFS._value.get() == before_live
    assert not drains.live_target_attempts
    drains.request([BURST] * 10)
    assert len(drain_timers) == 1
    delay, retry, _ = drain_timers.pop()
    assert delay == 180
    blocked = False
    retry()
    await settle(projector)
    assert log.persist_order == ids and not drains.delayed


@pytest.mark.asyncio
@pytest.mark.parametrize('advanced,switch', [(1, 'on'), (0, 'off')])
async def test_productive_privacy_turn_or_switch_off_keeps_old_queue_behavior(
    monkeypatch, drain_timers, advanced, switch
):
    monkeypatch.setenv('PROJECTION_DRAIN_PRIVACY_BACKOFF', switch)
    projector = projector_for(ResultLog())
    drains = projector.drains = projection_drain.OwnerDrains(projector)
    step = Mock(
        side_effect=[
            projection.Walk([], ['synthetic'] * advanced, False, PRIVACY_STOPS[0][0]),
            projection.Walk([], [], False, 'end'),
        ]
    )
    projector.drain_step = step
    drains.request([BURST])
    drains.request([BURST])
    await settle(projector)
    assert step.call_count == 2
    assert not drains.delayed and not drain_timers and not drains.stops


@pytest.mark.asyncio
async def test_privacy_backoff_uses_existing_cap_and_close_cleanup(monkeypatch, drain_timers):
    monkeypatch.setattr(projection_drain, 'MAX_DELAYED_OWNERS', 1)
    monkeypatch.delenv('PROJECTION_DRAIN_PRIVACY_BACKOFF', raising=False)
    projector = projector_for(ResultLog())
    drains = projector.drains = projection_drain.OwnerDrains(projector)
    projector.drain_step = lambda *a, **kw: projection.Walk([], [], False, PRIVACY_STOPS[0][0])
    drains.defer('already-delayed')
    drains.request([BURST])
    await settle(projector)
    assert list(drains.delayed) == ['already-delayed']
    assert list(projector.drain_requests) == [BURST]
    drains.close()
    assert not drains.delayed and not drains.stops
    drain_timers[0][2].cancel.assert_called_once()


@pytest.mark.parametrize('name', ['PROJECTION_DRAIN_PRIVACY_BACKOFF'])
@pytest.mark.parametrize('mode', ['shadow', 'serve'])
@pytest.mark.parametrize('value', [None, '', 'false', '0', 'unknown', 'off', 'OFF', ' off '])
def test_privacy_switches_are_disabled_only_by_off(monkeypatch, name, mode, value):
    from config.policy import kill_switch

    monkeypatch.setenv('CAPTURE_COVERAGE_MODE', mode)
    if value is None:
        monkeypatch.delenv(name, raising=False)
    else:
        monkeypatch.setenv(name, value)
    assert kill_switch(name) is (value is None or value.strip().lower() != 'off')


@pytest.mark.parametrize(
    'value,expected', [(None, 180), ('bad', 180), ('0', 30), ('29', 30), ('30', 30), ('900', 900), ('901', 900)]
)
def test_privacy_backoff_ttl_is_clamped(monkeypatch, value, expected):
    from config.batch_pipeline import projection_drain_privacy_backoff_seconds

    if value is None:
        monkeypatch.delenv('PROJECTION_DRAIN_PRIVACY_BACKOFF_SECONDS', raising=False)
    else:
        monkeypatch.setenv('PROJECTION_DRAIN_PRIVACY_BACKOFF_SECONDS', value)
    assert projection_drain_privacy_backoff_seconds() == expected


@pytest.mark.asyncio
async def test_fence_privacy_stop_is_counted_as_other_and_backed_off(monkeypatch, drain_timers):
    from utils.batch_pipeline.metrics import PROJECTION_DRAIN_PRIVACY_STOPS

    projector = projector_for(ResultLog())
    drains = projector.drains = projection_drain.OwnerDrains(projector)
    projector.drain_step = lambda *a, **kw: projection.Walk([], [], False, 'privacy_blocked')
    counter = PROJECTION_DRAIN_PRIVACY_STOPS.labels(reason='other')
    before = counter._value.get()
    drains.request([BURST])
    await settle(projector)
    assert counter._value.get() == before + 1
    assert BURST in drains.delayed and len(drain_timers) == 1


def privacy_version_drain(monkeypatch):
    from types import SimpleNamespace

    projector = projector_for(ResultLog())
    projector.chain_prefetch = lambda owner: None
    first = iter([projection.Walk([], [], False, PRIVACY_STOPS[0][0], ('blocked-head', 1))])
    step = Mock(side_effect=lambda *a, **kw: next(first, projection.Walk([], ['blocked-head'], False, 'end')))
    projector.drain_step = step
    snapshot = SimpleNamespace(update_time=1, exists=True)
    read = Mock(return_value=snapshot)
    reference = Mock(get=read)
    ref = Mock(return_value=reference)
    monkeypatch.setattr(projector.store, 'ref', ref)
    drains = projector.drains = projection_drain.OwnerDrains(projector)
    return projector, drains, step, snapshot, read, ref


@pytest.mark.asyncio
async def test_unchanged_head_ttl_expiry_runs_a_drain_turn(monkeypatch, drain_timers):
    monkeypatch.delenv('PROJECTION_DRAIN_PRIVACY_BACKOFF', raising=False)
    monkeypatch.setenv('PROJECTION_DRAIN_PRIVACY_BACKOFF_SECONDS', '180')
    projector, drains, step, snapshot, read, ref = privacy_version_drain(monkeypatch)
    drains.request([BURST])
    await settle(projector)
    delay, retry, _ = drain_timers.pop(0)
    assert delay == 180
    retry()
    await settle(projector)
    assert step.call_count == 2
    read.assert_not_called()  # expiry retries external privacy state regardless of row version
    assert not drains.privacy_heads and not drains.stopped_heads and not drains.delayed


@pytest.mark.asyncio
async def test_ttl_turn_blocked_again_defers_for_one_new_ttl(monkeypatch, drain_timers):
    from utils.batch_pipeline.metrics import PROJECTION_DRAIN_PRIVACY_BACKOFFS

    monkeypatch.delenv('PROJECTION_DRAIN_PRIVACY_BACKOFF', raising=False)
    monkeypatch.setenv('PROJECTION_DRAIN_PRIVACY_BACKOFF_SECONDS', '180')
    projector, drains, step, snapshot, read, _ = privacy_version_drain(monkeypatch)
    step.side_effect = None
    step.return_value = projection.Walk([], [], False, PRIVACY_STOPS[0][0], ('blocked-head', 1))
    before = PROJECTION_DRAIN_PRIVACY_BACKOFFS._value.get()
    drains.request([BURST])
    await settle(projector)
    for turn in range(2, 5):
        delay, retry, _ = drain_timers.pop(0)
        assert delay == 180
        retry()
        await settle(projector)
        assert step.call_count == turn
        assert drains.privacy_heads[BURST] == ('blocked-head', 1)
        assert len(drains.delayed) == len(drain_timers) == 1
    assert PROJECTION_DRAIN_PRIVACY_BACKOFFS._value.get() == before + 4
    read.assert_not_called()
    drains.close()


@pytest.mark.asyncio
async def test_changed_head_rerequests_before_ttl(monkeypatch, drain_timers):
    from utils.batch_pipeline.metrics import PROJECTION_DRAIN_PRIVACY_ROW_CHANGED

    monkeypatch.delenv('PROJECTION_DRAIN_PRIVACY_BACKOFF', raising=False)
    projector, drains, step, snapshot, read, _ = privacy_version_drain(monkeypatch)
    before = PROJECTION_DRAIN_PRIVACY_ROW_CHANGED._value.get()
    drains.request([BURST])
    await settle(projector)
    snapshot.update_time = 2
    drains.request([BURST] * 20)  # coalesced while the single version read runs
    await settle(projector)
    assert read.call_count == 1
    assert step.call_count >= 2
    assert PROJECTION_DRAIN_PRIVACY_ROW_CHANGED._value.get() == before + 1
    assert not drains.privacy_heads and not drains.delayed
    assert any(handle.cancel.called for _, _, handle in drain_timers)


@pytest.mark.asyncio
@pytest.mark.parametrize('failure', ['read_error', 'missing_version', 'switch_off'])
async def test_privacy_version_check_fails_open_and_switch_off_restores_behavior(monkeypatch, drain_timers, failure):
    monkeypatch.delenv('PROJECTION_DRAIN_PRIVACY_BACKOFF', raising=False)
    projector, drains, step, snapshot, read, _ = privacy_version_drain(monkeypatch)
    drains.request([BURST])
    await settle(projector)
    if failure == 'read_error':
        read.side_effect = RuntimeError('synthetic read failure')
    elif failure == 'missing_version':
        snapshot.update_time = None
    else:
        monkeypatch.setenv('PROJECTION_DRAIN_PRIVACY_BACKOFF', 'off')
    drains.request([BURST])
    await settle(projector)
    assert step.call_count == 2
    assert read.call_count == int(failure != 'switch_off')
    assert not drains.privacy_heads and not drains.delayed


@pytest.mark.asyncio
async def test_unchanged_head_incoming_requests_keep_original_check_deadline(monkeypatch, drain_timers):
    monkeypatch.delenv('PROJECTION_DRAIN_PRIVACY_BACKOFF', raising=False)
    projector, drains, step, snapshot, read, _ = privacy_version_drain(monkeypatch)
    drains.request([BURST])
    await settle(projector)
    handle = drains.delayed[BURST]
    drains.request([BURST] * 100)
    await settle(projector)
    assert read.call_count == 1 and step.call_count == 1
    assert drains.delayed[BURST] is handle and len(drain_timers) == 1
    drains.close()


def test_walk_privacy_block_carries_the_observed_head_version(monkeypatch):
    from types import SimpleNamespace
    from database.batch_pipeline_projection_protocol import ProjectionBlocked

    log = ResultLog()
    ids = chain(log, BURST, 'head-version', 2)
    projector = projector_for(log)
    original = log.ref

    def ref(table, sid):
        wrapped = original(table, sid)
        return (
            SimpleNamespace(get=lambda: SimpleNamespace(to_dict=lambda: log.results[sid], update_time=123))
            if table == 'results'
            else wrapped
        )

    monkeypatch.setattr(log, 'ref', ref)
    monkeypatch.setattr(projector, 'chain_prefetch', lambda owner: None)
    monkeypatch.setattr(
        projector,
        '_persist_read',
        Mock(side_effect=ProjectionBlocked('privacy disposition requires a source deletion tombstone')),
    )
    walk = projector.drain_step(BURST, 30)
    assert walk.blocked_head == (ids[0], 123)
    assert not walk.advanced and walk.stop == PRIVACY_STOPS[0][0]


def test_walk_fence_privacy_block_carries_the_observed_head_version(monkeypatch):
    from types import SimpleNamespace
    from database.batch_pipeline_privacy import BatchPrivacyBlocked, BatchPrivacyReason

    log = ResultLog()
    ids = chain(log, BURST, 'fence-version', 2)
    projector = projector_for(log)
    original = log.ref

    def ref(table, sid):
        wrapped = original(table, sid)
        return (
            SimpleNamespace(get=lambda: SimpleNamespace(to_dict=lambda: log.results[sid], update_time=456))
            if table == 'results'
            else wrapped
        )

    monkeypatch.setattr(log, 'ref', ref)
    monkeypatch.setattr(projector, 'chain_prefetch', lambda owner: None)
    reason = next(iter(BatchPrivacyReason))
    monkeypatch.setattr(projector, '_persist_read', Mock(side_effect=BatchPrivacyBlocked(reason)))
    walk = projector.drain_step(BURST, 30)
    assert walk.stop == 'privacy_blocked' and not walk.advanced
    assert walk.blocked_head == (ids[0], 456)


@pytest.mark.asyncio
async def test_privacy_head_versions_share_the_delayed_owner_cap(monkeypatch, drain_timers):
    monkeypatch.setattr(projection_drain, 'MAX_DELAYED_OWNERS', 1)
    monkeypatch.delenv('PROJECTION_DRAIN_PRIVACY_BACKOFF', raising=False)
    projector, drains, step, snapshot, read, _ = privacy_version_drain(monkeypatch)
    projector.drain_step = lambda *a, **kw: projection.Walk([], [], False, PRIVACY_STOPS[0][0], ('blocked-head', 1))
    drains.request(['first', 'second'])
    await settle(projector)
    assert list(drains.privacy_heads) == list(drains.delayed) == ['first']
    assert list(projector.drain_requests) == ['second']
    drain_timers[0][1]()
    await settle(projector)
    assert list(drains.privacy_heads) == list(drains.delayed) == ['first']
    drains.close()
    assert not drains.privacy_heads and not drains.stopped_heads


@pytest.mark.asyncio
async def test_ttl_during_unchanged_early_check_cannot_lose_the_retry(monkeypatch, drain_timers):
    monkeypatch.delenv('PROJECTION_DRAIN_PRIVACY_BACKOFF', raising=False)
    projector, drains, step, snapshot, read, _ = privacy_version_drain(monkeypatch)
    drains.request([BURST])
    await settle(projector)
    checked, release = asyncio.Event(), asyncio.Event()
    real_run_blocking = projection_drain.run_blocking

    async def pause_check(executor, fn, *args, **kwargs):
        if fn == drains.privacy_head_unchanged:
            result = fn(*args, **kwargs)
            checked.set()
            await release.wait()
            return result
        return await real_run_blocking(executor, fn, *args, **kwargs)

    monkeypatch.setattr(projection_drain, 'run_blocking', pause_check)
    drains.request([BURST])
    await checked.wait()
    drain_timers[0][1]()
    release.set()
    await settle(projector)
    assert read.call_count == 1
    assert step.call_count == 2
    assert not drains.delayed and not drains.privacy_heads


# --- awaiting-live-target backoff ------------------------------------------------


@pytest.fixture(autouse=True)
def serving_sweep_runs(monkeypatch):
    # Default for this module: a serving runtime with its sweep is alive, so
    # live-target holds are passive. Tests that need otherwise override it.
    monkeypatch.setattr(projection_drain, '_recurring_sweep', 'serving')


def live_target_drain():
    projector = projector_for(ResultLog())
    projector.chain_prefetch = lambda owner: None
    projector.drain_step = Mock(return_value=projection.Walk([], [], False, 'head_awaiting_live_target'))
    drains = projector.drains = projection_drain.OwnerDrains(projector)
    return projector, drains


@pytest.mark.asyncio
async def test_live_target_backoff_grows_caps_and_blocks_sweep_requests(drain_timers):
    from utils.batch_pipeline.metrics import PROJECTION_DRAIN_LIVE_TARGET_BACKOFFS

    projector, drains = live_target_drain()
    before = PROJECTION_DRAIN_LIVE_TARGET_BACKOFFS._value.get()
    drains.request([BURST])
    drains.request([BURST])  # active-turn re-request must also respect backoff
    await settle(projector)
    for turn, expected in enumerate([30, 60, 120, 240, 300, 300, 300], 1):
        assert len(drain_timers) == 1
        delay, retry, _ = drain_timers.pop()
        assert delay == expected
        assert projector.drain_step.call_count == turn
        assert PROJECTION_DRAIN_LIVE_TARGET_BACKOFFS._value.get() == before + turn
        drains.request([BURST] * 20)
        await settle(projector)
        assert projector.drain_step.call_count == turn
        retry()  # expiry only re-admits; it never starts a turn on its own
        await settle(projector)
        assert projector.drain_step.call_count == turn and not drains.delayed
        drains.request([BURST] * 20)  # the next sweep request runs exactly one turn
        await settle(projector)
    drains.close()
    assert not drains.live_target_attempts and not drains.delayed


@pytest.mark.asyncio
async def test_live_target_retries_never_exceed_the_sweep_cadence(drain_timers):
    # 2026-11-09 readback: an expiry wake retried blocked owners every 30-300 s
    # and doubled owner-chain conflicts. Without sweep requests, expired holds
    # must start no turns at all; each sweep request starts at most one.
    projector, drains = live_target_drain()
    drains.request([BURST])
    await settle(projector)
    turns = 1
    for _sweep in range(10):
        assert projector.drain_step.call_count == turns
        _delay, retry, _handle = drain_timers.pop()
        retry()
        await settle(projector)
        # Expiry alone starts nothing and asks the serving loop for nothing.
        assert projector.drain_step.call_count == turns
        assert not drain_timers and not drains.delayed and not drains.queue
        assert not list(projector.drain_requests)
        drains.request([BURST])
        await settle(projector)
        turns += 1
    assert projector.drain_step.call_count == turns
    drains.close()


@pytest.mark.asyncio
@pytest.mark.parametrize('mode,sweep_switch', [(None, 'on'), ('serving', 'off')])
async def test_live_target_hold_keeps_its_wake_without_a_recurring_sweep(monkeypatch, drain_timers, mode, sweep_switch):
    # Luna B1 (both rounds): with no recurring sweep in this process (serving
    # runtime not running, e.g. a one-off reconcile request, or its sweep switch
    # off), nothing re-requests a held owner, so the hold keeps its wakes.
    monkeypatch.setattr(projection_drain, '_recurring_sweep', mode)
    monkeypatch.setattr(projection_drain, 'serving_projection_sweep_enabled', lambda: sweep_switch == 'on')
    monkeypatch.setattr(projection_drain, 'MAX_DELAYED_OWNERS', 1)
    projector, drains = live_target_drain()
    drains.request([BURST])
    await settle(projector)
    assert projector.drain_step.call_count == 1
    drains.request(['overflow'])
    await settle(projector)
    assert list(projector.drain_requests) == ['overflow']
    _delay, retry, _handle = drain_timers.pop(0)
    retry()
    await settle(projector)
    assert projector.drain_step.call_count == 3  # expiry woke BURST without a sweep request
    drains.close()


@pytest.mark.asyncio
@pytest.mark.parametrize('mode', ['serving', 'pump'])
async def test_live_target_hold_is_passive_while_a_recurring_sweep_runs(monkeypatch, drain_timers, mode):
    monkeypatch.setattr(projection_drain, '_recurring_sweep', mode)
    projector, drains = live_target_drain()
    drains.request([BURST])
    await settle(projector)
    drain_timers.pop()[1]()
    await settle(projector)
    assert projector.drain_step.call_count == 1 and not list(projector.drain_requests)
    drains.close()


def test_serving_runtime_marks_its_recurring_sweep_only_while_running():
    projection_drain.set_recurring_sweep(None)
    assert not projection_drain.recurring_sweep_active()
    projection_drain.set_recurring_sweep('pump')
    assert projection_drain.recurring_sweep_active()
    projection_drain.set_recurring_sweep(None)
    assert not projection_drain.recurring_sweep_active()


@pytest.mark.asyncio
@pytest.mark.parametrize('stop,advanced', [('head_awaiting_live_target', ['row']), ('head_error', []), ('end', [])])
async def test_live_target_attempts_reset_after_progress_or_other_stop(drain_timers, stop, advanced):
    projector, drains = live_target_drain()
    drains.request([BURST])
    await settle(projector)
    assert drains.live_target_attempts[BURST] == 1
    projector.drain_step.return_value = projection.Walk([], advanced, False, stop)
    drain_timers.pop()[1]()
    drains.request([BURST])
    await settle(projector)
    assert not drains.live_target_attempts and not drains.delayed
    projector.drain_step.return_value = projection.Walk([], [], False, 'head_awaiting_live_target')
    drains.request([BURST])
    await settle(projector)
    assert drain_timers.pop()[0] == 30
    drains.close()


@pytest.mark.asyncio
async def test_live_target_attempt_state_and_delays_are_bounded(monkeypatch, drain_timers):
    from utils.batch_pipeline.metrics import PROJECTION_DRAIN_LIVE_TARGET_BACKOFFS

    monkeypatch.setattr(projection_drain, 'MAX_DELAYED_OWNERS', 1)
    projector, drains = live_target_drain()
    drains.request(['first'])
    await settle(projector)
    before = PROJECTION_DRAIN_LIVE_TARGET_BACKOFFS._value.get()
    drains.request(['overflow'])
    await settle(projector)
    assert list(drains.delayed) == list(drains.live_target_attempts) == ['first']
    # A passive hold that cannot be taken keeps today's behavior: no extra wake.
    assert not list(projector.drain_requests)
    assert PROJECTION_DRAIN_LIVE_TARGET_BACKOFFS._value.get() == before
    # Expire a timer without running its owner yet, then admit another owner.
    monkeypatch.setattr(drains, 'launch', lambda: None)
    _, retry, _ = drain_timers.pop()
    retry()
    assert drains.defer_live_target('second')
    assert list(drains.live_target_attempts) == ['second']
    second_handle = drain_timers.pop()[2]
    drains.close()
    second_handle.cancel.assert_called_once()
    retry()
    assert not drains.live_target_attempts and not drains.delayed and not drains.queue
    assert drains.defer_live_target('closed') is False


@pytest.mark.asyncio
@pytest.mark.parametrize('stop,switch', [('head_error', 'on'), ('head_awaiting_live_target', 'off')])
async def test_other_head_errors_or_disabled_backoff_keep_existing_retry_behavior(
    monkeypatch, drain_timers, stop, switch
):
    from utils.batch_pipeline.metrics import PROJECTION_DRAIN_LIVE_TARGET_BACKOFFS

    monkeypatch.setenv('PROJECTION_DRAIN_LIVE_TARGET_BACKOFF', switch)
    projector, drains = live_target_drain()
    projector.drain_step.side_effect = [projection.Walk([], [], False, stop), projection.Walk([], [], False, 'end')]
    before = PROJECTION_DRAIN_LIVE_TARGET_BACKOFFS._value.get()
    drains.request([BURST])
    drains.request([BURST])
    await settle(projector)
    assert projector.drain_step.call_count == 2
    assert not drain_timers and not drains.delayed and not drains.live_target_attempts
    assert PROJECTION_DRAIN_LIVE_TARGET_BACKOFFS._value.get() == before


@pytest.mark.parametrize('value', [None, '', 'true', 'false', '0', 'unknown', 'off', 'OFF', ' off '])
@pytest.mark.parametrize('mode', ['shadow', 'serve'])
def test_live_target_switch_is_default_on_and_off_only(monkeypatch, value, mode):
    from config.batch_pipeline import projection_drain_live_target_backoff_enabled

    monkeypatch.setenv('CAPTURE_COVERAGE_MODE', mode)
    if value is None:
        monkeypatch.delenv('PROJECTION_DRAIN_LIVE_TARGET_BACKOFF', raising=False)
    else:
        monkeypatch.setenv('PROJECTION_DRAIN_LIVE_TARGET_BACKOFF', value)
    assert projection_drain_live_target_backoff_enabled() is (value is None or value.strip().lower() != 'off')


@pytest.mark.parametrize(
    'subtype,switch,expected',
    [
        ('live_target_not_persisted', 'on', 'head_awaiting_live_target'),
        ('live_target_not_persisted', 'off', 'head_error'),
        ('record_target_missing', 'on', 'head_error'),
        ('record_finalize_pending', 'on', 'head_error'),
        ('other', 'on', 'head_error'),
    ],
)
def test_walk_maps_only_waiting_live_target_conflict(monkeypatch, subtype, switch, expected):
    from utils.batch_pipeline.projection_walk_stop import WALK_STOPS
    from utils.sync.assignment_errors import SyncAssignmentConflict

    monkeypatch.setenv('PROJECTION_DRAIN_LIVE_TARGET_BACKOFF', switch)
    log = ResultLog()
    ids = chain(log, BURST, 'a', 2)
    projector = projector_for(log)
    projector.clock = lambda: 10.0
    projector._persist_read = Mock(side_effect=SyncAssignmentConflict('synthetic writer wait', subtype=subtype))
    walk = projector.drain_step(BURST, 30.0)
    assert walk.stop == expected and walk.stop in WALK_STOPS
    assert not walk.advanced and not walk.more
    assert log.results[ids[0]]['projection_blocked_since'] == 10.0
    assert log.projection_watermark(owner_key(BURST)) is None
    assert log.results[ids[0]]['projection_state'] == 'pending'


@pytest.mark.parametrize('switch', ['on', 'off'])
def test_live_target_backoff_does_not_change_24_hour_hold(monkeypatch, switch):
    from utils.sync.assignment_errors import SyncAssignmentConflict

    monkeypatch.setenv('PROJECTION_DRAIN_LIVE_TARGET_BACKOFF', switch)
    log = ResultLog()
    ids = chain(log, BURST, 'a', 2)
    # Unknown capture age still gets the existing durable 24-hour bound.
    for job in log.jobs.values():
        job.pop('capture_at')
    log.results[ids[0]]['projection_blocked_since'] = 1.0
    projector = projector_for(log)
    projector.clock = lambda: projection.PROJECTION_HEAD_RETRY_SECONDS + 2
    real = projector._persist_read

    def persist(sid, *a, **kw):
        if sid == ids[0]:
            raise SyncAssignmentConflict('synthetic writer wait', subtype='live_target_not_persisted')
        return real(sid, *a, **kw)

    projector._persist_read = persist
    walk = projector.drain_step(BURST, 30.0)
    assert walk.stop == 'end' and walk.advanced == ids
    assert log.results[ids[0]]['projection_state'] == 'quarantine_held'
    assert log.jobs[ids[0]]['recovery_state'] == 'held'
    assert log.projection_watermark(owner_key(BURST)) == ids[-1]


@pytest.mark.asyncio
async def test_live_target_attempts_belong_to_each_owner(drain_timers):
    projector, drains = live_target_drain()
    drains.request(['first'])
    await settle(projector)
    delay, retry, _ = drain_timers.pop()
    assert delay == 30
    retry()
    drains.request(['first'])
    await settle(projector)
    assert drain_timers.pop()[0] == 60
    drains.request(['second'])
    await settle(projector)
    assert drain_timers.pop()[0] == 30
    assert drains.live_target_attempts == {'first': 2, 'second': 1}
    drains.close()


@pytest.mark.asyncio
async def test_live_target_defer_refusal_preserves_active_rerequest(monkeypatch, drain_timers):
    monkeypatch.setattr(projection_drain, 'MAX_DELAYED_OWNERS', 1)
    projector, drains = live_target_drain()
    drains.defer('already-delayed')
    projector.drain_step.side_effect = [
        projection.Walk([], [], False, 'head_awaiting_live_target'),
        projection.Walk([], [], False, 'end'),
    ]
    drains.request([BURST])
    drains.request([BURST])
    await settle(projector)
    assert projector.drain_step.call_count == 2
    assert list(drains.delayed) == ['already-delayed']
    assert not drains.live_target_attempts and len(drain_timers) == 1
    # The refused passive hold adds no serving-loop wake; the active
    # re-request alone produced the second turn.
    assert not list(projector.drain_requests)
    drains.close()
