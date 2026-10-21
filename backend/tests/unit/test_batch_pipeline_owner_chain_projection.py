"""Owner-chain projection wake after recovery; ordering fences stay authoritative.

``ResultLog`` models only the projection contract the real ``Projector`` relies
on: a per-owner singly linked result log (``previous_segment_id``), the owner
projection watermark, and a predecessor check that blocks any row whose
predecessor (through erased receipts) is not the watermark. The real sweep,
discovery cursors, follow-up scheduler and ``Serving.reconcile`` run on it.
"""

import asyncio
import itertools
import threading
from contextlib import contextmanager
from dataclasses import asdict
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from config.policy import ProjectionPolicy
from database.batch_pipeline_projection import ProjectionBlocked, ProjectionReplay
from database.batch_pipeline_projection_protocol import ProjectionPredecessorPending
from database.batch_pipeline_store import projection_successor
from utils.batch_pipeline import projection, projection_followup
from utils.batch_pipeline.contracts import Priority, ProjectionBinding, WorkItem
from utils.batch_pipeline.scheduler import owner_key
from utils.batch_pipeline.serving import Serving
from tests.unit.test_batch_pipeline_scheduler import MemoryStore

BURST = 'burst-owner'


class Doc(SimpleNamespace):
    def get(self, **_):
        return SimpleNamespace(to_dict=lambda: dict(self.row()) if self.row() is not None else None)


class ResultLog:
    """Durable rows; ``ProjectionStore`` and ``FirestoreStore`` facades over them."""

    namespace = 'batch_pipeline_test_chain'

    def __init__(self, *, async_projection=True):
        self.results: dict[str, dict] = {}
        self.jobs: dict[str, dict] = {}
        self.bindings: dict[str, ProjectionBinding] = {}
        self.owners: dict[str, dict] = {}
        self.tails: dict[str, str | None] = {}
        self.clock = 0.0
        self.policy = ProjectionPolicy(async_projection=async_projection).to_dict()
        self.blocked_checks = 0
        self.persist_order: list[str] = []
        self.store = self  # Projector.store.store is the FirestoreStore facade.

    # --- writers ---------------------------------------------------------
    def commit(self, owner, content, segment, siblings, *, state='pending', erased=False):
        """OrderedMerge.commit_next: append at this owner's log tail."""
        key = owner_key(owner)
        self.clock += 1
        self.results[segment] = {
            'owner_key': key,
            'segment_id': segment,
            'previous_segment_id': self.tails.get(key),
            'committed_at': self.clock,
            'projection_state': 'erased' if erased else state,
            'result': {'outcome': 'silence'},
        }
        if state != 'pending' and not erased:
            self.results[segment]['projection'] = {'state': state}
            self.owners.setdefault(key, {})['projection_watermark'] = segment
        self.tails[key] = segment
        binding = ProjectionBinding(owner, f'job-{content}', content, tuple(siblings))
        self.bindings[segment] = binding
        self.jobs[segment] = {
            **asdict(WorkItem(segment, owner, self.clock, 'gs://synthetic/audio', 1, Priority.DEEP)),
            'policy_parts': {'projection': self.policy},
        }

    # --- FirestoreStore facade --------------------------------------------
    def projection_page(self, limit=100, *, after=None, states=('pending', 'persisted', 'ready')):
        rows = sorted(
            (row['committed_at'], sid) for sid, row in self.results.items() if row['projection_state'] in states
        )
        if after is not None:
            rows = [row for row in rows if row > after]
        page = rows[:limit]
        return [sid for _, sid in page], (page[-1] if len(page) == limit else None)

    def projection_pending(self, limit=100):
        return self.projection_page(limit)[0]

    def projection_successor(self, key, previous):
        matches = [
            sid
            for sid, row in self.results.items()
            if row['owner_key'] == key and row['previous_segment_id'] == previous
        ]
        return matches[0] if len(matches) == 1 else None

    # --- ProjectionStore facade -------------------------------------------
    def ref(self, table, sid):
        assert table == 'results'
        return Doc(row=lambda: self.results.get(sid))

    def read(self, sid):
        if sid not in self.results:
            raise ProjectionBlocked('committed result and durable intake binding required')
        return dict(self.jobs[sid]), dict(self.results[sid]), self.bindings[sid]

    def projection_watermark(self, key):
        return self.owners.get(key, {}).get('projection_watermark')

    def session(self, sid, binding, now, **_):
        log = self

        class Session:
            def persist_empty(self, **_):
                log.check(self)
                receipt = {'state': 'persisted'}
                log.results[sid].update(projection=receipt, projection_state='persisted')
                log.owners.setdefault(owner_key(binding.owner_id), {})['projection_watermark'] = sid
                log.persist_order.append(sid)
                return receipt

        session = Session()
        session.segment_id, session.binding = sid, binding
        return session

    def check(self, session):
        row = self.results[session.segment_id]
        if row.get('projection'):
            raise ProjectionReplay(row['projection'])
        predecessor, watermark = row['previous_segment_id'], self.projection_watermark(row['owner_key'])
        while predecessor != watermark:
            earlier = self.results.get(predecessor or '')
            if not earlier or earlier['projection_state'] != 'erased':
                self.blocked_checks += 1
                raise ProjectionPredecessorPending('earlier committed projection must persist first')
            predecessor = earlier['previous_segment_id']

    def persisted(self, owner):
        key = owner_key(owner)
        return all(
            row.get('projection') or row['projection_state'] == 'erased'
            for row in self.results.values()
            if row['owner_key'] == key
        )


@pytest.fixture(autouse=True)
def advisory_claim(monkeypatch):
    @contextmanager
    def claim(*_):
        yield True

    monkeypatch.setattr(projection, 'projection_claim', claim)
    monkeypatch.setattr(projection_followup, 'projection_claim', claim)
    monkeypatch.delenv('BATCH_PIPELINE_OWNER_CHAIN_PROJECTION_ENABLED', raising=False)
    monkeypatch.delenv('BATCH_PIPELINE_PROJECTION_PAGINATION_ENABLED', raising=False)
    monkeypatch.delenv('BATCH_PIPELINE_SWEEP_OWNER_CHAIN_ENABLED', raising=False)
    monkeypatch.delenv('BATCH_PIPELINE_PROJECTION_PENDING_PAGE_ENABLED', raising=False)


def projector_for(log):
    projector = projection.Projector(log, Mock())
    projector.store = log
    return projector


def chain(log, owner, content, count, *, prefix=None):
    ids = [f'{prefix or content}-{n}' for n in range(count)]
    for sid in ids:
        log.commit(owner, content, sid, ids)
    return ids


# --- chain walk ---------------------------------------------------------------


def test_walk_assigns_owner_rows_in_chain_order_and_skips_other_owners():
    log = ResultLog()
    first = chain(log, BURST, 'a', 3)
    log.commit('other', 'x', 'other-0', ['other-0'])
    second = chain(log, BURST, 'b', 2)
    followups = projector_for(log).project_owner(BURST)
    assert log.persist_order == first + second
    assert log.blocked_checks == 0
    assert log.results['other-0']['projection_state'] == 'pending'
    assert followups == first + second


def test_walk_follows_erased_receipts_and_resumes_after_watermark():
    log = ResultLog()
    log.commit(BURST, 'a', 'done', ['done'], state='ready')
    log.commit(BURST, 'gone', 'gone', ['gone'], erased=True)
    later = chain(log, BURST, 'b', 2)
    assert projector_for(log).project_owner(BURST) == later
    assert log.persist_order == later


def test_walk_is_bounded_by_rows_and_time(monkeypatch):
    log = ResultLog()
    ids = chain(log, BURST, 'a', 5)
    projector = projector_for(log)
    projector.project_owner(BURST, limit=2)
    assert log.persist_order == ids[:2]
    ticks = itertools.chain([0.0, 0.0], itertools.repeat(2.0))
    monkeypatch.setattr(projection.time, 'monotonic', lambda: next(ticks))
    projector.project_owner(BURST, budget_seconds=1.0)
    assert log.persist_order == ids[:3]
    projector.project_owner(BURST, limit=projection.OWNER_CHAIN_LIMIT, budget_seconds=60)
    assert log.persist_order == ids


def test_walk_stops_at_first_fenced_row_and_never_skips_it():
    from database.batch_pipeline_privacy import BatchPrivacyBlocked

    log = ResultLog()
    ids = chain(log, BURST, 'a', 4)
    projector = projector_for(log)
    real = log.session

    def fenced(sid, *args, **kwargs):
        if sid == ids[1]:
            raise BatchPrivacyBlocked('synthetic deletion')
        return real(sid, *args, **kwargs)

    log.session = fenced
    assert projector.project_owner(BURST) == [ids[0]]
    assert log.persist_order == [ids[0]]
    log.session = Mock(side_effect=RuntimeError('synthetic outage'))
    assert projector.project_owner(BURST) == []
    log.session = real
    # The touched content's earlier persisted sibling is still owed a follow-up.
    assert projector.project_owner(BURST) == ids


def test_walk_stops_when_watermark_does_not_advance():
    log = ResultLog()
    ids = chain(log, BURST, 'a', 3)
    projector = projector_for(log)
    projector._persist_read = Mock()  # Busy claim / partial multipart: no receipt.
    assert projector.project_owner(BURST) == []
    projector._persist_read.assert_called_once()
    assert log.projection_watermark(owner_key(BURST)) is None
    assert log.results[ids[1]]['projection_state'] == 'pending'


def test_walk_returns_unready_siblings_of_touched_content_once():
    log = ResultLog()
    siblings = ['a-0', 'a-1', 'a-2']
    log.commit(BURST, 'a', 'a-0', siblings, state='persisted')
    log.commit(BURST, 'a', 'a-1', siblings, state='ready')
    log.commit(BURST, 'a', 'a-2', siblings)
    assert projector_for(log).project_owner(BURST) == ['a-0', 'a-2']


def test_recovered_content_followups_lead_the_backlog():
    log = ResultLog()
    backlog = chain(log, BURST, 'b', 2)
    log.commit(BURST, 'r', 'r-early', ['r-early', 'r'], state='persisted')
    log.commit(BURST, 'r', 'r', ['r-early', 'r'])
    # r-early persisted after b-*, so the walk starts at the tail's predecessor.
    log.owners[owner_key(BURST)]['projection_watermark'] = None
    log.results['r-early'].pop('projection')
    log.results['r-early']['projection_state'] = 'pending'
    assert projector_for(log).project_owner(BURST, recovered='r') == ['r-early', 'r', *backlog]
    assert log.persist_order == [*backlog, 'r-early', 'r']


def test_synchronous_policy_projects_and_finishes_without_followups():
    log = ResultLog(async_projection=False)
    ids = chain(log, BURST, 'a', 2)
    projector = projector_for(log)
    projector._finish = Mock(return_value=None)
    assert projector.project_owner(BURST) == []
    assert log.persist_order == ids
    assert [call.args[0] for call in projector._finish.call_args_list] == ids


def test_successor_query_fails_closed_on_ambiguous_link():
    rows = [SimpleNamespace(id='one'), SimpleNamespace(id='two')]
    query = Mock()
    query.where.return_value = query
    query.order_by.return_value = query
    query.limit.return_value = query
    query.stream.return_value = rows
    client = Mock()
    client.collection.return_value = query
    assert projection_successor(client, 'batch_pipeline_dev', 'owner', 'head') is None
    query.stream.return_value = rows[:1]
    assert projection_successor(client, 'batch_pipeline_dev', 'owner', 'head') == 'one'
    client.collection.assert_called_with('batch_pipeline_dev_results')
    assert [call.args for call in query.where.call_args_list[:2]] == [
        ('owner_key', '==', 'owner'),
        ('previous_segment_id', '==', 'head'),
    ]


# --- serving wiring -------------------------------------------------------------


def test_reconcile_drains_then_walks_owner_before_generic_sweep(monkeypatch):
    calls = []
    projector = Mock(has_async_followups=False)
    projector.project_owner.side_effect = lambda owner, recovered: calls.append(('chain', owner, recovered)) or ['seg']
    projector.sweep.side_effect = lambda: calls.append(('sweep',))
    service = Serving(MemoryStore(), projector=projector)
    monkeypatch.setattr(service, 'drain_owner', lambda owner, recovered=None: calls.append(('drain', owner, recovered)))
    assert service.reconcile(owner_id=BURST, recovered='r') == ['seg']
    assert calls == [('drain', BURST, 'r'), ('chain', BURST, 'r'), ('sweep',)]
    calls.clear()
    assert service.reconcile() == []
    assert calls == [('sweep',)]


def test_failed_chain_wake_still_runs_generic_sweep():
    projector = Mock(has_async_followups=False)
    projector.project_owner.side_effect = RuntimeError('synthetic index unavailable')
    service = Serving(MemoryStore(), projector=projector)
    assert service.reconcile(owner_id=BURST) == []
    projector.sweep.assert_called_once()


def test_kill_switch_restores_generic_reconcile(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_OWNER_CHAIN_PROJECTION_ENABLED', 'false')
    projector = Mock(has_async_followups=False)
    service = Serving(MemoryStore(), projector=projector)
    assert service.reconcile(owner_id=BURST) == []
    projector.project_owner.assert_not_called()
    projector.sweep.assert_called_once()


@pytest.mark.asyncio
async def test_reconcile_async_hands_priority_to_followups():
    projector = Mock(has_async_followups=False)
    projector.project_owner.return_value = ['a-2', 'a-0']
    projector.start_followups = AsyncMock()
    await Serving(MemoryStore(), projector=projector).reconcile_async(owner_id=BURST)
    projector.start_followups.assert_awaited_once_with(['a-2', 'a-0'])


@pytest.mark.asyncio
async def test_priority_followups_jump_discovered_queue_within_slot_bound(monkeypatch):
    monkeypatch.setattr(projection_followup, 'MAX_FOLLOWUPS', 1)
    release = asyncio.Event()
    runner = projection_followup.ProjectionFollowups(Mock())
    started = []

    async def run(segment):
        started.append(segment)
        await release.wait()

    runner.run = run
    runner.pending.extend(['busy', 'queued', 'shared'])
    runner.launch()
    await runner.schedule(['shared', 'busy', 'urgent', 'shared'])
    # 'busy' is running and not requeued; priority keeps its order, then the rest.
    assert list(runner.pending) == ['shared', 'urgent', 'queued']
    assert list(runner.tasks) == ['busy']
    release.set()
    while runner.tasks:
        await asyncio.gather(*list(runner.tasks.values()))
    assert started == ['busy', 'shared', 'urgent', 'queued']


@pytest.mark.asyncio
async def test_suspended_discovery_read_keeps_wake_rows_queued_behind_full_slots(monkeypatch):
    """A discovery read in flight must not replace rows a wake queued meanwhile."""
    monkeypatch.setattr(projection_followup, 'MAX_FOLLOWUPS', 4)
    release, reading, resume = asyncio.Event(), threading.Event(), threading.Event()
    runner = projection_followup.ProjectionFollowups(Mock())

    def candidates():
        reading.set()
        assert resume.wait(5)
        return ['busy-0', 'page-a', 'page-b']

    runner.candidates = candidates

    async def run(segment):
        await release.wait()

    runner.run = run
    runner.pending.extend(f'busy-{n}' for n in range(4))
    runner.launch()
    runner.after = 'busy-3'
    assert len(runner.tasks) == 4 and not runner.pending
    discovery = asyncio.create_task(runner.schedule())
    assert await asyncio.to_thread(reading.wait, 2)
    await runner.schedule(['recovered'])
    assert list(runner.pending) == ['recovered']
    resume.set()
    await discovery
    assert list(runner.pending) == ['recovered', 'page-a', 'page-b']
    release.set()
    while runner.tasks:
        await asyncio.gather(*list(runner.tasks.values()))
    # The wake row launched out of order without moving the discovery rotation.
    assert runner.after == 'page-b'
    assert not runner.prioritized


# --- characterization: recovered predecessor committed late -----------------------


def backlog_log():
    """Run 6 shape: one owner's backlog behind a busy page of other owners.

    The burst owner's chain head X0 was attempted last pass while another
    replica held the owner claim, so this instance's assignment cursor already
    sits past it. Its successors (and the recovered unit R, which settles last
    and commits at the log tail) are blocked behind X0 until the cursor wraps.
    The follow-up page is full of other owners' persisted receipts.
    """
    log = ResultLog()
    siblings = ['r-held', 'r']
    log.commit(BURST, 'r', 'r-held', siblings, state='ready')  # persisted before its sibling quarantined
    log.results['r-held']['projection_state'] = 'quarantine_held'
    backlog = ['x-0']
    log.commit(BURST, 'x', 'x-0', backlog)
    for n in range(60):
        log.commit(f'noise-{n}', f'n{n}', f'noise-{n}', [f'noise-{n}'], state='persisted')
    for content in 'bcdef':
        ids = [f'{content}-{n}' for n in range(4)]
        for sid in ids:
            log.commit(BURST, content, sid, ids)
            log.commit(f'noise-{sid}', f'n{sid}', f'noise-{sid}', [f'noise-{sid}'], state='persisted')
        backlog.extend(ids)
    for n in range(60, 120):
        log.commit(f'noise-{n}', f'n{n}', f'noise-{n}', [f'noise-{n}'], state='persisted')
    log.commit(BURST, 'r', 'r', siblings)  # recovered unit, committed at the tail
    return log, backlog + ['r']


async def passes_until_recovered_followup(monkeypatch, *, owner_chain, sweep_chain=False):
    """Count serving passes until R is persisted and its follow-up has started.

    Each pass is one ``reconcile_async``; the first is the recover-quarantine
    handler's own pass. Follow-ups take longer than a pass to finish, and a
    pass releases the previous pass's follow-ups first. ``sweep_chain`` drives
    the sweep's own owner-chain continuation and pending-only assignment page.
    """
    monkeypatch.setenv('BATCH_PIPELINE_OWNER_CHAIN_PROJECTION_ENABLED', str(owner_chain).lower())
    monkeypatch.setenv('BATCH_PIPELINE_SWEEP_OWNER_CHAIN_ENABLED', str(sweep_chain).lower())
    monkeypatch.setenv('BATCH_PIPELINE_PROJECTION_PENDING_PAGE_ENABLED', str(sweep_chain).lower())
    log, burst = backlog_log()
    projector = projector_for(log)
    cursor = (log.results['x-0']['committed_at'], 'x-0')
    projector.discovery.after = projector.assignment_discovery.after = cursor
    service = Serving(MemoryStore(), projector=projector)
    started, gates, stopping = [], [], []

    async def run(self, segment):
        if stopping:
            return
        started.append(segment)
        gate = asyncio.Event()
        gates.append(gate)
        await gate.wait()

    monkeypatch.setattr(projection_followup.ProjectionFollowups, 'run', run)
    try:
        for completed in range(1, 100):
            for gate in gates:
                gate.set()
            await asyncio.sleep(0)
            if completed == 1:  # the recover-quarantine handler's pass
                await service.reconcile_async(owner_id=BURST, recovered='r')
            else:
                await service.reconcile_async(periodic=True)
            await asyncio.sleep(0)
            if log.persisted(BURST) and 'r' in started:
                assert log.persist_order == burst  # chain order, never skipped
                return completed, log.blocked_checks
        raise AssertionError('recovered unit never reached a follow-up')
    finally:
        stopping.append(True)
        for gate in gates:
            gate.set()
        followups = projector.followups
        while followups and followups.tasks:
            await asyncio.gather(*list(followups.tasks.values()))


@pytest.mark.asyncio
async def test_recovered_tail_unit_projects_in_the_recovery_pass(monkeypatch):
    with_chain, blocked_with = await passes_until_recovered_followup(monkeypatch, owner_chain=True)
    without_chain, blocked_without = await passes_until_recovered_followup(monkeypatch, owner_chain=False)
    assert with_chain == 1
    assert blocked_with == 0
    # Without the wake: cursor wrap for assignment, then a follow-up page full
    # of other owners' receipts, four slots at a time, ahead of R.
    assert without_chain >= 30  # 36 for this deterministic shape
    assert blocked_without > 0


@pytest.mark.parametrize('sweep_chain', [True, False])
def test_sweep_chain_persists_backlog_in_the_pass_that_reaches_its_head(monkeypatch, sweep_chain):
    """Without the recovery wake, the sweep itself walks the owner's chain.

    The assignment cursor sits past the head. With predecessor replay, the
    first blocked successor wakes the head and persists the chain immediately.
    """
    monkeypatch.setenv('BATCH_PIPELINE_SWEEP_OWNER_CHAIN_ENABLED', str(sweep_chain).lower())
    monkeypatch.setenv('BATCH_PIPELINE_PROJECTION_PENDING_PAGE_ENABLED', str(sweep_chain).lower())
    # The sweep's own walk; test_batch_pipeline_owner_drain.py covers the drain.
    monkeypatch.setenv('BATCH_PIPELINE_OWNER_DRAIN_ENABLED', 'false')
    log, burst = backlog_log()
    projector = projector_for(log)
    cursor = (log.results['x-0']['committed_at'], 'x-0')
    projector.discovery.after = projector.assignment_discovery.after = cursor
    passes = 0
    while not log.persisted(BURST):
        passes += 1
        assert passes < 200
        projector.sweep()
    assert log.persist_order == burst
    assert (passes, log.blocked_checks) == ((1, 1) if sweep_chain else (4, 21))
