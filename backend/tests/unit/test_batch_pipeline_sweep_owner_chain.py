"""The sweep continues an owner's chain and pages only assignable rows.

Runs the real ``Projector.sweep``, discovery cursors, follow-up scheduler and
``Serving.reconcile_async`` on the ``ResultLog`` contract model. Ordering
fences (predecessor check, owner claim, watermark) stay authoritative. This is
the owner-drain kill-switch path (``BATCH_PIPELINE_OWNER_DRAIN_ENABLED=false``);
``test_batch_pipeline_owner_drain.py`` covers the drain.
"""

import asyncio
import itertools
from contextlib import contextmanager
from unittest.mock import Mock

import pytest

from database.batch_pipeline_store import (
    PROJECTION_DISCOVERY_STATES,
    projection_page,
)
from utils.batch_pipeline import projection, projection_followup
from utils.batch_pipeline.scheduler import owner_key
from utils.batch_pipeline.serving import Serving
from tests.unit.test_batch_pipeline_owner_chain_projection import BURST, ResultLog, chain, projector_for
from tests.unit.test_batch_pipeline_scheduler import MemoryStore

SWITCHES = ('BATCH_PIPELINE_SWEEP_OWNER_CHAIN_ENABLED', 'BATCH_PIPELINE_PROJECTION_PENDING_PAGE_ENABLED')


@pytest.fixture(autouse=True)
def claims(monkeypatch):
    """Advisory owner claim that records nesting; a busy set refuses entry."""
    state = SimpleClaims()

    @contextmanager
    def claim(namespace, key):
        if key in state.busy or key in state.held:
            yield False
            return
        state.held.add(key)
        state.max_depth = max(state.max_depth, len(state.held))
        state.entered.append(key)
        try:
            yield True
        finally:
            state.held.discard(key)

    monkeypatch.setattr(projection, 'projection_claim', claim)
    monkeypatch.setattr(projection_followup, 'projection_claim', claim)
    for name in (
        *SWITCHES,
        'BATCH_PIPELINE_OWNER_CHAIN_PROJECTION_ENABLED',
        'BATCH_PIPELINE_PROJECTION_PAGINATION_ENABLED',
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv('BATCH_PIPELINE_OWNER_DRAIN_ENABLED', 'false')
    return state


class SimpleClaims:
    def __init__(self):
        self.busy: set[str] = set()
        self.held: set[str] = set()
        self.entered: list[str] = []
        self.max_depth = 0


def switches(monkeypatch, *, chain_on: bool, pending_on: bool):
    monkeypatch.setenv(SWITCHES[0], str(chain_on).lower())
    monkeypatch.setenv(SWITCHES[1], str(pending_on).lower())


class Recording:
    """Wraps the store facade and records every call the projector makes."""

    def __init__(self, log):
        self.log, self.calls = log, []

    def __getattr__(self, name):
        attribute = getattr(self.log, name)
        if not callable(attribute):
            return attribute

        def call(*args, **kwargs):
            self.calls.append((name, args, tuple(sorted(kwargs.items()))))
            return attribute(*args, **kwargs)

        return call


# --- owner chain inside the sweep ------------------------------------------------


def test_blocked_successor_rebuilds_missing_predecessor_in_same_pass():
    log = ResultLog()
    ids = chain(log, BURST, 'a', 5)
    projector = projector_for(log)
    # The cursor already paged past the head. Only a successor is discovered.
    projector.assignment_discovery.after = (log.results[ids[2]]['committed_at'], ids[2])
    counts = projector.sweep(limit=1)
    assert counts['blocked'] == 1
    assert log.persist_order == ids
    assert set(projector.chain_followups) == set(ids)
    assert projector.has_async_followups


def test_blocked_successor_requests_owner_drain(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_OWNER_DRAIN_ENABLED', 'true')
    log = ResultLog()
    ids = chain(log, BURST, 'a', 5)
    projector = projector_for(log)
    projector.assignment_discovery.after = (log.results[ids[2]]['committed_at'], ids[2])
    projector.sweep(limit=1)
    assert projector.owes_drains
    assert log.persist_order == []
    walk = projector.drain_step(BURST, budget_seconds=30)
    assert walk.advanced == ids


def test_predecessor_error_before_binding_read_never_reuses_previous_owner(monkeypatch):
    from database.batch_pipeline_projection_protocol import ProjectionPredecessorPending

    monkeypatch.setenv('BATCH_PIPELINE_OWNER_DRAIN_ENABLED', 'true')
    log = ResultLog()
    log.commit('done-owner', 'done', 'done', ['done'], state='ready')
    log.commit(BURST, 'a', 'head', ['head'])
    real = log.read

    def read(sid):
        if sid == 'head':
            raise ProjectionPredecessorPending('synthetic read failure')
        return real(sid)

    log.read = read
    projector = projector_for(log)
    counts = projector.sweep()
    assert counts['blocked'] == 1
    assert not projector.owes_drains


def test_blocked_successor_replay_kill_switch_restores_previous_behavior(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_PROJECTION_PREDECESSOR_REPLAY_ENABLED', 'off')
    log = ResultLog()
    ids = chain(log, BURST, 'a', 5)
    projector = projector_for(log)
    projector.assignment_discovery.after = (log.results[ids[2]]['committed_at'], ids[2])
    assert projector.sweep(limit=1)['blocked'] == 1
    assert log.persist_order == []
    assert not projector.owes_drains


def test_missing_predecessor_replay_does_not_bypass_head_binding_fence():
    from database.batch_pipeline_projection import ProjectionBlocked

    log = ResultLog()
    ids = chain(log, BURST, 'a', 5)
    real = log.session

    def fenced(sid, *args, **kwargs):
        if sid == ids[0]:
            raise ProjectionBlocked('immutable result binding mismatch')
        return real(sid, *args, **kwargs)

    log.session = fenced
    projector = projector_for(log)
    projector.assignment_discovery.after = (log.results[ids[2]]['committed_at'], ids[2])
    projector.sweep(limit=1)
    assert log.persist_order == []
    assert not projector.chain_followups


def test_missing_predecessor_replay_respects_row_budget(monkeypatch):
    monkeypatch.setattr(projection, 'OWNER_CHAIN_LIMIT', 2)
    log = ResultLog()
    ids = chain(log, BURST, 'a', 5)
    projector = projector_for(log)
    projector.assignment_discovery.after = (log.results[ids[2]]['committed_at'], ids[2])
    projector.sweep(limit=1)
    assert log.persist_order == ids[:2]
    assert set(projector.chain_followups) == set(ids[:2])


def test_owner_backlog_drains_in_one_sweep_pass_up_to_the_chain_limit(monkeypatch, claims):
    log = ResultLog()
    ids = chain(log, BURST, 'a', 100)
    projector = projector_for(log)
    counts = projector.sweep(limit=5)
    # The page reached the head; the continuation walked 64 more rows in order.
    assert log.persist_order == ids[: 1 + projection.OWNER_CHAIN_LIMIT]
    assert log.blocked_checks == 0
    # Page rows the walk persisted are not re-read, re-attempted or counted.
    assert counts == {'completed': 0, 'waiting': 1, 'blocked': 0, 'error': 0}
    assert claims.max_depth == 1


def test_legacy_sweep_advances_only_rows_inside_its_page(monkeypatch):
    switches(monkeypatch, chain_on=False, pending_on=False)
    log = ResultLog()
    ids = chain(log, BURST, 'a', 100)
    projector_for(log).sweep(limit=5)
    assert log.persist_order == ids[:5]


def test_continuation_budget_is_shared_across_owners_in_one_sweep(monkeypatch):
    log = ResultLog()
    first = chain(log, 'owner-1', 'a', 10)
    second = chain(log, 'owner-2', 'b', 10)
    # Ordered by commit: owner-1's rows then owner-2's. owner-1's walk spends
    # the whole sweep budget after two rows. Without budget, every remaining
    # page row is still attempted in order, exactly as the legacy page did.
    ticks = itertools.chain([0.0, 0.0, 0.0, 0.0, 0.0], itertools.repeat(projection.OWNER_CHAIN_SECONDS + 1))
    monkeypatch.setattr(projection.time, 'monotonic', lambda: next(ticks))
    projector = projector_for(log)
    walk = Mock(wraps=projector._walk_owner)
    projector._walk_owner = walk
    projector.sweep(limit=100)
    assert log.persist_order == first + second
    walks = [call for call in walk.call_args_list if call.kwargs['budget_seconds'] > 0]
    assert [call.args[0] for call in walks] == ['owner-1']


def test_continuation_stops_at_predecessor_fence_and_privacy_block(monkeypatch):
    from database.batch_pipeline_privacy import BatchPrivacyBlocked

    log = ResultLog()
    ids = chain(log, BURST, 'a', 6)
    real = log.session

    def fenced(sid, *args, **kwargs):
        if sid == ids[3]:
            raise BatchPrivacyBlocked('synthetic deletion')
        return real(sid, *args, **kwargs)

    log.session = fenced
    projector = projector_for(log)
    projector.sweep()
    # Rows after the fenced one are never projected around it.
    assert log.persist_order == ids[:3]
    assert all(log.results[sid]['projection_state'] == 'pending' for sid in ids[3:])
    log.session = real
    projector.sweep()
    assert log.persist_order == ids


def test_walk_stopped_by_its_row_limit_leaves_later_page_rows_to_the_page(monkeypatch):
    monkeypatch.setattr(projection, 'OWNER_CHAIN_LIMIT', 2)
    log = ResultLog()
    ids = chain(log, BURST, 'a', 6)
    projector = projector_for(log)
    walk = Mock(wraps=projector._walk_owner)
    projector._walk_owner = walk
    counts = projector.sweep()
    # Head by the page, two by the walk, the rest in page order; one walk only,
    # then seed-only hand-offs for the rows the page persisted itself.
    assert log.persist_order == ids
    assert [call.kwargs['budget_seconds'] > 0 for call in walk.call_args_list] == [True, False, False, False]
    assert set(projector.chain_followups) == set(ids)
    assert counts['waiting'] == 4 and log.blocked_checks == 0


def test_walk_budget_starts_at_the_first_walk_not_the_page(monkeypatch):
    log = ResultLog(async_projection=False)
    ids = chain(log, BURST, 'a', 4)
    now = [0.0]
    monkeypatch.setattr(projection.time, 'monotonic', lambda: now[0])
    projector = projector_for(log)
    finished = []

    def slow_finish(segment_id, *_):
        finished.append(segment_id)
        if len(finished) == 1:
            now[0] += projection.OWNER_CHAIN_SECONDS + 10  # the head itself is slow

    projector._finish = Mock(side_effect=slow_finish)
    projector.sweep()
    assert log.persist_order == ids
    # Each row finishes once: the finish page skips rows this sweep finished.
    assert finished == ids


def test_walked_async_tail_behind_a_sync_head_keeps_followups_scheduled(monkeypatch):
    log = ResultLog(async_projection=False)
    log.commit(BURST, 'h', 'head', ['head'])
    async_policy = projection.ProjectionPolicy(async_projection=True).to_dict()
    tails = chain(log, BURST, 'a', 3)
    for sid in tails:
        log.jobs[sid]['policy_parts'] = {'projection': async_policy}
    projector = projector_for(log)
    projector._finish = Mock(return_value=None)
    # The finish cursor already sits past the tails the walk will persist.
    projector.finish_discovery.after = (log.clock + 1, 'zz')
    projector.sweep(limit=1)
    assert log.persist_order == ['head', *tails]
    assert projector.has_async_followups


@pytest.mark.asyncio
async def test_walked_async_tails_behind_parked_cursors_still_start_followups(monkeypatch):
    """Both cursors are parked past the tails; the walk's owed rows still run."""
    log = ResultLog(async_projection=False)
    log.commit(BURST, 'h', 'head', ['head'])
    async_policy = projection.ProjectionPolicy(async_projection=True).to_dict()
    tails = chain(log, BURST, 'a', 3)
    for sid in tails:
        log.jobs[sid]['policy_parts'] = {'projection': async_policy}
    sync_receipts = []
    for n in range(120):
        sid = f'sync-{n}'
        log.commit(f'owner-{n}', f's{n}', sid, [sid], state='persisted')
        sync_receipts.append(sid)
    projector = projector_for(log)
    projector._finish = Mock(return_value=None)
    parked = (log.results['sync-0']['committed_at'], 'sync-0')
    projector.finish_discovery.after = parked
    projector.followups = projection_followup.ProjectionFollowups(projector)
    projector.followups.discovery.after = parked
    service = Serving(MemoryStore(), projector=projector)
    started = []

    async def run(self, segment):
        started.append(segment)

    monkeypatch.setattr(projection_followup.ProjectionFollowups, 'run', run)
    for _ in range(2):
        await service.reconcile_async(periodic=True)
        await asyncio.sleep(0)
    assert log.persist_order[: 1 + len(tails)] == ['head', *tails]
    assert set(tails) <= set(started)
    # Out-of-order owed rows do not move the follow-up discovery rotation.
    assert projector.followups.after not in tails


@pytest.mark.asyncio
async def test_owed_tails_start_even_when_the_queue_was_busy_at_handoff(monkeypatch):
    """The queue is busy when the walk hands off; the next pass sees no async row."""
    monkeypatch.setattr(projection_followup, 'MAX_FOLLOWUPS', 1)
    log = ResultLog(async_projection=False)
    log.commit(BURST, 'h', 'head', ['head'])
    async_policy = projection.ProjectionPolicy(async_projection=True).to_dict()
    tails = chain(log, BURST, 'a', 3)
    for sid in tails:
        log.jobs[sid]['policy_parts'] = {'projection': async_policy}
    # Enough synchronous receipts that the finish page cannot wrap back to
    # the tails within this test's passes.
    for n in range(800):
        sid = f'sync-{n}'
        log.commit(f'owner-{n}', f's{n}', sid, [sid], state='persisted')
    projector = projector_for(log)
    projector._finish = Mock(return_value=None)
    parked = (log.results['sync-0']['committed_at'], 'sync-0')
    projector.finish_discovery.after = parked
    projector.followups = projection_followup.ProjectionFollowups(projector)
    projector.followups.discovery.after = parked
    projector.followups.pending.extend(['busy-0', 'busy-1'])
    service = Serving(MemoryStore(), projector=projector)
    release, started = asyncio.Event(), []

    async def run(self, segment):
        if segment.startswith('busy'):
            await release.wait()
        started.append(segment)

    monkeypatch.setattr(projection_followup.ProjectionFollowups, 'run', run)
    await service.reconcile_async(periodic=True)
    assert set(tails) <= set(projector.followups.owed)
    release.set()
    for _ in range(4):
        await asyncio.sleep(0)
        while projector.followups.tasks:
            await asyncio.gather(*list(projector.followups.tasks.values()))
        await service.reconcile_async(periodic=True)
    while projector.followups.tasks:
        await asyncio.gather(*list(projector.followups.tasks.values()))
    assert set(tails) <= set(started)


def test_walk_read_failure_after_a_persisted_async_row_still_hands_it_off():
    log = ResultLog()
    ids = chain(log, BURST, 'a', 3)
    real = log.projection_successor

    def flaky(key, previous):
        if previous == ids[1]:
            raise RuntimeError('synthetic index outage')
        return real(key, previous)

    log.projection_successor = flaky
    projector = projector_for(log)
    projector.sweep(limit=1)
    assert log.persist_order == ids[:2]
    # The walked row plus its content's persisted, not-ready sibling.
    assert projector.chain_followups == ids[:2]
    assert projector.owes_followups


@pytest.mark.asyncio
async def test_owed_rows_fall_through_to_discovery_once_the_queue_launches():
    runner = projection_followup.ProjectionFollowups(Mock())
    runner.candidates = lambda: ['page-a']
    snapshots = []

    def launch():
        snapshots.append(list(runner.pending))
        runner.pending.clear()  # free slots took every queued row

    runner.launch = launch
    runner.pending.append('queued')
    await runner.schedule(tail=['owed-1'])
    # Same call: the queue launched, then discovery ran with the owed row behind it.
    assert snapshots == [['queued'], ['page-a', 'owed-1']]
    assert not runner.owed


@pytest.mark.asyncio
async def test_owed_overflow_restarts_followup_discovery_at_the_head():
    runner = projection_followup.ProjectionFollowups(Mock())
    runner.discovery.after = (5.0, 'parked')
    runner.launch = lambda: None
    runner.pending.append('queued')
    await runner.schedule(tail=[f't-{n}' for n in range(projection_followup.MAX_OWED + 10)])
    assert len(runner.owed) == projection_followup.MAX_OWED
    assert runner.discovery.after is None


@pytest.mark.asyncio
async def test_owed_rows_join_behind_the_discovered_page_and_never_block_discovery():
    projector = Mock()
    runner = projection_followup.ProjectionFollowups(projector)
    runner.candidates = lambda: ['page-a', 'page-b']
    launched = []
    runner.launch = lambda: launched.append(list(runner.pending))
    runner.pending.append('queued')
    await runner.schedule(tail=['owed-1', 'page-a'])
    # A non-empty queue launches first; owed rows wait for the next discovery.
    assert list(runner.pending) == ['queued'] and list(runner.owed) == ['owed-1', 'page-a']
    runner.pending.clear()
    await runner.schedule(tail=['owed-2'])
    assert list(runner.pending) == ['page-a', 'page-b', 'owed-1', 'owed-2']
    assert not runner.owed and {'owed-1', 'owed-2'} <= runner.prioritized


def test_walk_keeps_a_persisted_async_row_when_its_sibling_read_fails():
    log = ResultLog()
    ids = chain(log, BURST, 'a', 2)
    real = log.ref
    calls = []

    def flaky(table, sid):
        calls.append(sid)
        if len(calls) > 1 and log.results[ids[0]].get('projection'):
            raise RuntimeError('synthetic read outage')
        return real(table, sid)

    log.ref = flaky
    followups, advanced = projector_for(log)._walk_owner(BURST, recovered=None, limit=64, budget_seconds=30)
    assert advanced == [ids[0]] and followups == [ids[0]]


def test_finish_page_contention_on_async_receipts_still_logs_the_summary(monkeypatch, caplog):
    log = ResultLog()
    log.policy = projection.ProjectionPolicy(async_projection=True, projection_contention=True).to_dict()
    log.commit('other', 'o', 'o-0', ['o-0'], state='persisted')
    with caplog.at_level('INFO', logger=projection.logger.name):
        projector_for(log).sweep()
    assert any('action=sweep outcome=summary' in record.getMessage() for record in caplog.records)


def test_single_segment_contents_hand_off_the_page_row_too():
    """The row the page persisted is owed, not only the rows the walk persisted."""
    log = ResultLog()
    ids = ['a', 'b', 'c']
    for sid in ids:
        log.commit(BURST, sid, sid, [sid])  # each content is one segment
    projector = projector_for(log)
    projector.sweep(limit=1)
    assert log.persist_order == ids
    assert projector.chain_followups == ids


def test_watermark_read_failure_after_a_persist_still_hands_the_row_off():
    log = ResultLog()
    ids = ['a', 'b']
    for sid in ids:
        log.commit(BURST, sid, sid, [sid])
    real = log.projection_watermark
    reads = []

    def flaky(key):
        reads.append(key)
        if log.results['b'].get('projection'):
            raise RuntimeError('synthetic watermark outage')
        return real(key)

    log.projection_watermark = flaky
    projector = projector_for(log)
    projector.sweep(limit=1)
    assert log.persist_order == ids
    assert projector.chain_followups == ids


def test_opening_watermark_read_failure_still_hands_the_page_row_off():
    log = ResultLog()
    log.commit(BURST, 'a', 'a', ['a'])
    log.commit(BURST, 'b', 'b', ['b'])

    projector = projector_for(log)
    real = log.projection_watermark
    failed = []

    def first_fails(key):
        # Fail the first read made after the page persisted 'a': the walk's
        # opening read of the watermark.
        if log.results['a'].get('projection') and not failed:
            failed.append(key)
            raise RuntimeError('synthetic watermark outage')
        return real(key)

    log.projection_watermark = first_fails
    projector.sweep(limit=1)
    # The page persisted 'a'; the walk's opening read failed, so it walked no
    # further but still owed the page row.
    assert log.persist_order == ['a']
    assert projector.chain_followups == ['a']


def test_seed_only_hand_off_reads_one_watermark_and_no_siblings(monkeypatch):
    log = ResultLog()
    siblings = [f'a-{n}' for n in range(128)]
    for sid in siblings[:2]:
        log.commit(BURST, 'a', sid, siblings)
    projector = projector_for(log)
    reads = []
    real = log.ref
    log.ref = lambda table, sid: reads.append(sid) or real(table, sid)
    projector._persist_read('a-0', *log.read('a-0'))
    followups, advanced = projector._walk_owner(
        BURST, recovered=None, limit=64, budget_seconds=0.0, seed=('a-0', log.read('a-0')[2])
    )
    assert followups == ['a-0'] and advanced == []
    assert reads == []  # no sibling scan and no successor read


def test_partial_page_persist_that_did_not_advance_is_not_handed_off():
    log = ResultLog()
    log.commit(BURST, 'a', 'a', ['a'])
    projector = projector_for(log)
    projector._persist_read = Mock()  # partial multipart: no receipt, no advance
    projector.sweep()
    assert projector.chain_followups == []


def test_busy_owner_claim_blocks_the_row_and_starts_no_walk(monkeypatch, claims):
    log = ResultLog()
    ids = chain(log, BURST, 'a', 3)
    claims.busy.add(owner_key(BURST))
    projector = projector_for(log)
    walk = Mock(wraps=projector._walk_owner)
    projector._walk_owner = walk
    counts = projector.sweep()
    assert log.persist_order == []
    assert counts['blocked'] == len(ids)
    walk.assert_not_called()


def test_replayed_rows_do_not_start_a_walk(monkeypatch):
    switches(monkeypatch, chain_on=True, pending_on=False)
    log = ResultLog()
    log.commit(BURST, 'a', 'done', ['done'], state='persisted')
    projector = projector_for(log)
    projector._walk_owner = Mock()
    projector.sweep()
    projector._walk_owner.assert_not_called()


# --- pending-only assignment page ---------------------------------------------------


def test_pending_page_skips_receipts_and_follow_ups_still_run(monkeypatch):
    """No pending row at all: the finish page alone keeps follow-ups scheduled."""
    log = ResultLog()
    persisted = []
    for n in range(150):
        sid = f'done-{n}'
        log.commit(f'owner-{n}', f'c{n}', sid, [sid], state='persisted')
        persisted.append(sid)
    recorder = Recording(log)
    projector = projector_for(log)
    projector.store = recorder
    projector.discovery.store = projector.assignment_discovery.store = recorder
    projector.finish_discovery.store = recorder
    projector.sweep()
    assert projector.has_async_followups
    pages = [call for call in recorder.calls if call[0] == 'projection_page']
    assert [dict(call[2]).get('states') for call in pages] == [('pending',), ('persisted', 'ready')]
    # Async receipts are not replayed through the assignment claim/check.
    assert [call for call in recorder.calls if call[0] in {'session', 'check'}] == []


@pytest.mark.asyncio
async def test_no_follow_up_is_starved_behind_a_pending_backlog(monkeypatch):
    log = ResultLog()
    # A blocked backlog: every pending row waits on an unpersisted head that is
    # absent from the log (another replica's busy chain), filling every page.
    for n in range(250):
        log.commit('blocked', 'z', f'z-{n}', ['z'])
    log.owners[owner_key('blocked')] = {'projection_watermark': 'never'}
    persisted = []
    for n in range(30):
        sid = f'done-{n}'
        log.commit(f'owner-{n}', f'c{n}', sid, [sid], state='persisted')
        persisted.append(sid)
    projector = projector_for(log)
    service = Serving(MemoryStore(), projector=projector)
    started = []

    async def run(self, segment):
        started.append(segment)

    monkeypatch.setattr(projection_followup.ProjectionFollowups, 'run', run)
    for _ in range(40):
        await service.reconcile_async(periodic=True)
        await asyncio.sleep(0)
        if set(persisted) <= set(started):
            break
    assert set(persisted) <= set(started)


def test_synchronous_policy_receipts_still_finish_from_the_finish_page(monkeypatch):
    log = ResultLog(async_projection=False)
    log.commit(BURST, 'a', 'a-0', ['a-0', 'a-1'], state='persisted')
    log.commit(BURST, 'a', 'a-1', ['a-0', 'a-1'], state='ready')
    projector = projector_for(log)
    projector._finish = Mock(return_value=None)
    counts = projector.sweep()
    assert [call.args[0] for call in projector._finish.call_args_list] == ['a-0', 'a-1']
    assert counts == {'completed': 0, 'waiting': 2, 'blocked': 0, 'error': 0}
    assert not projector.has_async_followups


# --- kill switches ------------------------------------------------------------------


def mixed_log():
    log = ResultLog()
    log.commit('other', 'o', 'o-0', ['o-0'], state='persisted')
    chain(log, BURST, 'a', 4)
    log.commit('third', 't', 't-0', ['t-0'], state='ready')
    chain(log, 'late', 'l', 2)
    return log


def legacy_trace(log):
    """The pre-change sweep's store calls, derived from its loop, by hand.

    One mixed page; for each row a read, then the claim/predecessor check (and
    persist for assignable rows). No successor walk and no second page.
    """
    return [
        ('projection_page', (), (('after', None), ('limit', 100))),
        *[('read', (sid,), ()) for sid in log_order(log)],
    ]


def log_order(log):
    return [sid for _, sid in sorted((row['committed_at'], sid) for sid, row in log.results.items())]


def test_both_switches_off_is_the_legacy_sweep(monkeypatch):
    switches(monkeypatch, chain_on=False, pending_on=False)
    log = mixed_log()
    recorder = Recording(log)
    projector = projector_for(log)
    projector.store = recorder
    projector.discovery.store = recorder
    counts = projector.sweep()
    reads = [call for call in recorder.calls if call[0] in {'projection_page', 'projection_pending', 'read'}]
    assert reads == legacy_trace(log)
    assert not [call for call in recorder.calls if call[0] in {'projection_successor', 'projection_watermark'}]
    assert counts == {'completed': 0, 'waiting': 8, 'blocked': 0, 'error': 0}
    assert log.persist_order == ['a-0', 'a-1', 'a-2', 'a-3', 'l-0', 'l-1']


def test_each_switch_is_independent(monkeypatch):
    switches(monkeypatch, chain_on=False, pending_on=True)
    log = mixed_log()
    projector = projector_for(log)
    projector._walk_owner = Mock()
    projector.sweep()
    projector._walk_owner.assert_not_called()
    assert log.persist_order == ['a-0', 'a-1', 'a-2', 'a-3', 'l-0', 'l-1']
    switches(monkeypatch, chain_on=True, pending_on=False)
    log = mixed_log()
    recorder = Recording(log)
    projector = projector_for(log)
    projector.discovery.store = recorder
    projector.sweep()
    assert [dict(call[2]).get('states') for call in recorder.calls if call[0] == 'projection_page'] == [None]
    assert log.persist_order == ['a-0', 'a-1', 'a-2', 'a-3', 'l-0', 'l-1']


# --- store query --------------------------------------------------------------------


def query_client():
    query = Mock()
    query.where.return_value = query
    query.order_by.return_value = query
    query.start_after.return_value = query
    query.limit.return_value = query
    query.stream.return_value = []
    client = Mock()
    client.collection.return_value = query
    return client, query


def test_projection_page_states_narrow_the_same_filter():
    client, query = query_client()
    projection_page(client, 'batch_pipeline_dev', 100)
    assert query.where.call_args.args == ('projection_state', 'in', list(PROJECTION_DISCOVERY_STATES))
    projection_page(client, 'batch_pipeline_dev', 100, states=('pending',))
    assert query.where.call_args.args == ('projection_state', 'in', ['pending'])
    assert [call.args for call in query.order_by.call_args_list[-2:]] == [('committed_at',), ('__name__',)]
    for states in ((), ('completed',), ('pending', 'erased')):
        with pytest.raises(ValueError):
            projection_page(client, 'batch_pipeline_dev', 100, states=states)
