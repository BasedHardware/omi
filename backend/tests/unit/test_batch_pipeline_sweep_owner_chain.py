"""The sweep continues an owner's chain and pages only assignable rows.

Runs the real ``Projector.sweep``, discovery cursors, follow-up scheduler and
``Serving.reconcile_async`` on the ``ResultLog`` contract model. Ordering
fences (predecessor check, owner claim, watermark) stay authoritative.
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


def test_owner_backlog_drains_in_one_sweep_pass_up_to_the_chain_limit(monkeypatch, claims):
    log = ResultLog()
    ids = chain(log, BURST, 'a', 100)
    projector = projector_for(log)
    counts = projector.sweep(limit=5)
    # The page reached the head; the continuation walked 64 more rows in order.
    assert log.persist_order == ids[: 1 + projection.OWNER_CHAIN_LIMIT]
    assert log.blocked_checks == 0
    # Page rows the walk persisted are not re-read or re-attempted.
    assert counts == {'completed': 0, 'waiting': 5, 'blocked': 0, 'error': 0}
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
    assert [call.args[0] for call in walk.call_args_list] == ['owner-1']


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
    # Head by the page, two by the walk, the rest in page order; one walk only.
    assert log.persist_order == ids
    assert walk.call_count == 1
    assert counts['waiting'] == 6 and log.blocked_checks == 0


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
