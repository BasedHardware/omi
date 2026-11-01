"""Per-owner projection drain, read-ahead and deferred indexing (Phase 1).

The drain runs the real ``Projector`` walk, ``OwnerDrains`` scheduler and
``Serving.reconcile_async`` on the ``ResultLog`` contract model. Ordering stays
with the predecessor fence: ``ResultLog``'s ``persist_empty`` reruns it, as the
assignment transaction does, even when a walk skips the pre-check.
"""

import asyncio
import itertools
from contextlib import contextmanager
from copy import deepcopy
from unittest.mock import Mock

import pytest

from config.batch_pipeline import projection_prefetch_depth
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
        if drains is None or (not drains.tasks and not drains.queue):
            return
        await asyncio.gather(*list(drains.tasks.values()), return_exceptions=True)
        await asyncio.sleep(0)
    raise AssertionError('owner drain did not settle')


def owner_rows(log, owner):
    key = owner_key(owner)
    return [sid for sid in log.persist_order if log.results[sid]['owner_key'] == key]


# --- fairness and scheduling -------------------------------------------------------


@pytest.mark.asyncio
async def test_heavy_owners_cannot_starve_a_light_owner(monkeypatch, claims):
    """One slot, one two-row step per turn: owners take FIFO turns, in chain order."""
    monkeypatch.setattr(projection_drain, 'MAX_OWNER_DRAINS', 1)
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
    assert walk == projection.Walk([], [], False) and log.persist_order == []


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
    for _ in range(10):
        projector.sweep()
    assert legacy.persisted(BURST) and legacy.persisted('other')

    monkeypatch.delenv('BATCH_PIPELINE_OWNER_DRAIN_ENABLED')
    drained, _ = catch_up_log()
    projector = projector_for(drained)
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
    assert walk == projection.Walk([], [], True) and log.persist_order == []
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
    assert projector.drain_step(BURST, 15.0) == projection.Walk([], [], True)
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
