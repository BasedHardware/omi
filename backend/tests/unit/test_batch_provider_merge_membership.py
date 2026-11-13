"""Provider-route units as full members of the ordered merge (synthetic only).

2026-11-13: 1.68M transcribed provider units sat in ``result_ready``. Nothing woke their owner's
merge, they had no ``ready_at`` for the head wait, and no merge class for fresh-first.
"""

import asyncio
import logging
import time

import pytest

from database import batch_pipeline_intake
from routers import batch_provider_stt as route
from tests.unit.test_batch_provider_stt import (  # noqa: F401  # world is a fixture
    JA,
    OWNER,
    Artifacts,
    Outbox,
    StubStage,
    Vendor,
    _claim,
    admit,
    item,
    job,
    stage,
    world,
)
from utils.batch_pipeline import provider_stt, provider_stt_admission
from utils.batch_pipeline.contracts import ProjectionBinding
from utils.batch_pipeline.merge import OrderedMerge
from utils.batch_pipeline.provider_drain import HEAD_WAIT_MARGIN_SECONDS, OwnerDrainCoalescer
from utils.batch_pipeline.scheduler import owner_key
from utils.batch_pipeline.serving import Serving

SWITCH = 'BATCH_PIPELINE_PROVIDER_MERGE_MEMBERSHIP_ENABLED'
# admit() runs at 100.0 with 5 s units, so a capture at 10 is fresh.
FRESH_CAPTURE = 10


def settle(store, segment, now=200.0):
    outcome = stage(store, Artifacts(), Vendor(), now=now).run(segment)
    assert (outcome.outcome, outcome.reason) == ('done', 'processed')


def drain(merge, now):
    entries = []
    while entry := merge.commit_next(OWNER, now):
        entries.append(entry)
    return entries


# --- the two stamps -----------------------------------------------------------------------------


def test_provider_admission_stamps_the_merge_class(world, monkeypatch):
    _, store = world
    admit(monkeypatch, store, [item('fresh', FRESH_CAPTURE)], 'content-fresh', JA)
    # The same capture admitted two hours later is catch-up, as GPU admission classes it.
    late = item('old', FRESH_CAPTURE)
    binding = ProjectionBinding(OWNER, 'bp_content-old', 'content-old', ('old',), language='ja')
    enqueue = provider_stt_admission.provider_enqueue(JA, Outbox(), {})
    outcome = batch_pipeline_intake.admit(store, [late], binding, 7300.0, namespace=store.namespace, enqueue=enqueue)
    assert outcome['outcome'] == 'batch'
    assert job(store, 'fresh')['fresh_capture'] is True
    assert job(store, 'old')['fresh_capture'] is False


def test_provider_settle_stamps_ready_at(world, monkeypatch):
    _, store = world
    admit(monkeypatch, store, [item('p1', FRESH_CAPTURE)], 'content-p', JA)
    settle(store, 'p1', now=200.0)
    row = job(store, 'p1')
    assert row['state'] == 'result_ready' and row['ready_at'] == 200.0


def test_switch_off_writes_neither_stamp(world, monkeypatch):
    monkeypatch.setenv(SWITCH, 'false')
    _, store = world
    admit(monkeypatch, store, [item('p1', FRESH_CAPTURE)], 'content-p', JA)
    settle(store, 'p1')
    row = job(store, 'p1')
    assert row['state'] == 'result_ready' and 'ready_at' not in row and 'fresh_capture' not in row


def test_a_failed_unit_gets_no_ready_at(world, monkeypatch):
    _, store = world
    admit(monkeypatch, store, [item('p1', FRESH_CAPTURE)], 'content-p', JA)
    failing = stage(store, Artifacts(), Vendor(error=RuntimeError('synthetic vendor outage')))
    assert failing.run('p1').provider_reason == 'provider_failed'
    row = job(store, 'p1')
    assert row['state'] == 'quarantined' and row['merge_pending'] is False and 'ready_at' not in row


# --- the merge ----------------------------------------------------------------------------------


def test_ready_provider_row_commits_past_an_unready_head_after_the_head_wait(world, monkeypatch):
    _, store = world
    admit(monkeypatch, store, [item('p1', 10)], 'content-1', JA)
    admit(monkeypatch, store, [item('p2', 20)], 'content-2', JA)
    settle(store, 'p2', now=200.0)
    merge = OrderedMerge(store, head_wait_seconds=60, catch_up_depth=16)
    assert merge.commit_next(OWNER, 230.0) is None  # p1 still heads the owner; p2 has waited 30 s
    entry = merge.commit_next(OWNER, 261.0)
    assert entry['segment_id'] == 'p2' and entry['head_wait_bypass'] is True and entry['recovery_version'] == 1
    assert job(store, 'p1')['merge_pending'] is True
    # The bypassed head appends later, marked late.
    settle(store, 'p1', now=300.0)
    late = merge.commit_next(OWNER, 301.0)
    assert late['segment_id'] == 'p1' and late['late_capture'] is True


def test_switch_off_keeps_a_ready_provider_row_behind_its_unready_head(world, monkeypatch):
    monkeypatch.setenv(SWITCH, 'false')
    _, store = world
    admit(monkeypatch, store, [item('p1', 10)], 'content-1', JA)
    admit(monkeypatch, store, [item('p2', 20)], 'content-2', JA)
    settle(store, 'p2', now=200.0)
    merge = OrderedMerge(store, head_wait_seconds=60, catch_up_depth=16)
    assert merge.commit_next(OWNER, 10_000.0) is None


def _legacy_backlog(world, monkeypatch, count):
    """``count`` settled provider rows admitted and settled before the stamps existed."""
    _, store = world
    monkeypatch.setenv(SWITCH, 'false')
    names = [f'old{n}' for n in range(count)]
    for n, name in enumerate(names):
        admit(monkeypatch, store, [item(name, 10 + n)], f'content-{name}', JA)
        settle(store, name)
        row = job(store, name)
        assert 'fresh_capture' not in row and 'ready_at' not in row
    monkeypatch.delenv(SWITCH)
    return store, names


def _project_through(store, segment):
    key = owner_key(OWNER)
    store.run(lambda tx: tx.put('owners', key, {**tx.get('owners', key), 'projection_watermark': segment}))


def test_fresh_provider_row_passes_the_owners_unstamped_backlog(world, monkeypatch):
    store, names = _legacy_backlog(world, monkeypatch, 6)
    admit(monkeypatch, store, [item('new', 90)], 'content-new', JA)
    settle(store, 'new', now=200.0)
    merge = OrderedMerge(store, head_wait_seconds=60, catch_up_depth=4)
    entries = drain(merge, 201.0)
    # The backlog commits up to the depth cap, then holds; the fresh row lands right behind it.
    assert [e['segment_id'] for e in entries] == [*names[:4], 'new']
    assert entries[-1]['fresh_first'] is True and entries[-1]['late_capture'] is False
    assert [job(store, name)['state'] for name in names[4:]] == ['result_ready', 'result_ready']
    # The held backlog follows as projection advances, appended as late captures.
    _project_through(store, 'new')
    rest = drain(merge, 202.0)
    assert [e['segment_id'] for e in rest] == names[4:]
    assert all(e['late_capture'] is True for e in rest)


def test_switch_off_keeps_the_unstamped_backlog_in_plain_order(world, monkeypatch):
    store, names = _legacy_backlog(world, monkeypatch, 6)
    monkeypatch.setenv(SWITCH, 'false')
    admit(monkeypatch, store, [item('new', 90)], 'content-new', JA)
    settle(store, 'new', now=200.0)
    merge = OrderedMerge(store, head_wait_seconds=60, catch_up_depth=4)
    assert [e['segment_id'] for e in drain(merge, 201.0)] == [*names, 'new']


def test_unstamped_gpu_rows_keep_the_plain_order(world, monkeypatch):
    """Only provider rows are reclassified: a record-lane or older GPU row has no class either."""
    from utils.batch_pipeline.merge import _catch_up

    assert _catch_up({'stt_route': {'stt_route': 'provider'}}) is True
    assert _catch_up({'stt_route': {'stt_route': 'parakeet'}}) is False
    assert _catch_up({}) is False
    assert _catch_up({'fresh_capture': True, 'stt_route': {'stt_route': 'provider'}}) is False
    assert _catch_up({'fresh_capture': False}) is True


# --- the coalesced owner drain ------------------------------------------------------------------


class Drains:
    def __init__(self, on_call=None, error=None):
        self.calls: list[str] = []
        self.on_call, self.error = on_call, error

    async def __call__(self, owner_id):
        self.calls.append(owner_id)
        if self.on_call is not None:
            self.on_call(len(self.calls))
        if self.error is not None:
            raise self.error


def coalescer(drains, *, head_wait=60.0, slept=None, **kwargs):
    async def sleep(seconds):
        if slept is not None:
            slept.append(seconds)
        await asyncio.sleep(0)

    return OwnerDrainCoalescer(drains, head_wait=lambda: head_wait, sleep=sleep, **kwargs)


async def _idle(drainer):
    for _ in range(10_000):
        if not drainer.pending():
            return
        await asyncio.sleep(0)
    raise AssertionError('owner drains did not finish')


@pytest.mark.asyncio
async def test_a_burst_for_one_owner_costs_one_round_of_two_drains():
    drains, slept = Drains(), []
    drainer = coalescer(drains, slept=slept)
    assert all(drainer.request('owner-a') for _ in range(50))
    assert drainer.pending() == 1
    await _idle(drainer)
    # One drain after the delay, one after the head wait: 50 settles, 2 drains.
    assert drains.calls == ['owner-a', 'owner-a']
    assert slept == [2.0, 60.0 + HEAD_WAIT_MARGIN_SECONDS]


@pytest.mark.asyncio
async def test_a_request_during_a_round_buys_exactly_one_more_round():
    drainer = None

    def during(call):
        if call == 1:
            for _ in range(10):
                drainer.request('owner-a')

    drains = Drains(on_call=during)
    drainer = coalescer(drains)
    drainer.request('owner-a')
    await _idle(drainer)
    assert drains.calls == ['owner-a'] * 4


@pytest.mark.asyncio
async def test_head_wait_off_drains_once_and_owners_are_independent():
    drains = Drains()
    drainer = coalescer(drains, head_wait=0.0)
    drainer.request('owner-a')
    drainer.request('owner-b')
    assert drainer.pending() == 2
    await _idle(drainer)
    assert sorted(drains.calls) == ['owner-a', 'owner-b']


@pytest.mark.asyncio
async def test_owner_bound_drops_the_request_and_a_later_one_is_accepted(caplog):
    drains = Drains()
    drainer = coalescer(drains, head_wait=0.0, max_owners=1)
    assert drainer.request('owner-a') is True
    with caplog.at_level(logging.WARNING):
        assert drainer.request('owner-b') is False
    assert 'event=batch_provider_drain outcome=dropped reason=owner_bound' in caplog.text
    await _idle(drainer)
    assert drainer.request('owner-b') is True
    await _idle(drainer)
    assert drains.calls == ['owner-a', 'owner-b']


@pytest.mark.asyncio
async def test_a_failing_drain_is_logged_by_type_and_frees_the_owner(caplog):
    drains = Drains(error=RuntimeError('synthetic private detail'))
    drainer = coalescer(drains)
    with caplog.at_level(logging.WARNING):
        drainer.request('owner-a')
        await _idle(drainer)
    assert drains.calls == ['owner-a', 'owner-a'] and drainer.pending() == 0
    assert 'event=batch_provider_drain outcome=retry exception_type=RuntimeError' in caplog.text
    assert 'synthetic private detail' not in caplog.text and 'owner-a' not in caplog.text


@pytest.mark.asyncio
async def test_drains_run_at_most_the_configured_number_at_once():
    running, peak = 0, 0

    async def drain(owner_id):
        nonlocal running, peak
        running += 1
        peak = max(peak, running)
        await asyncio.sleep(0)
        running -= 1

    drainer = coalescer(drain, head_wait=0.0, concurrency=2)
    for n in range(8):
        drainer.request(f'owner-{n}')
    await _idle(drainer)
    assert peak == 2


# --- the wake from a delivery -------------------------------------------------------------------


class AsyncStubStage(StubStage):
    async def run_async(self, segment_id, run_sync):
        return self.run(segment_id)


async def _inline(fn, *args, **kwargs):
    return fn(*args, **kwargs)


@pytest.mark.parametrize(
    'unit,woken',
    [
        (provider_stt.UnitOutcome('done', 'processed'), True),
        # A terminal unit leaves the owner's merge order, which can unblock the rows behind it.
        (provider_stt.UnitOutcome('done', 'processed', provider_reason='provider_failed'), True),
        (provider_stt.UnitOutcome('done', 'superseded'), False),
        (provider_stt.UnitOutcome('deferred', 'not_due', 260.0), False),
        (provider_stt.UnitOutcome('discarded', 'privacy_blocked'), False),
        (provider_stt.UnitOutcome('retry', 'dependency_warming'), False),
    ],
)
@pytest.mark.asyncio
async def test_only_a_processed_delivery_wakes_the_owner_merge(unit, woken):
    seen = []
    consumer = provider_stt.ProviderSttConsumer(lambda: AsyncStubStage(unit), clock=lambda: 100.0, settled=seen.append)
    await consumer.process_async(_claim(), lambda: True, _inline)
    assert seen == ([OWNER] if woken else [])


@pytest.mark.asyncio
async def test_a_failing_wake_never_changes_the_delivery_result(caplog):
    def broken(owner_id):
        raise RuntimeError('synthetic private detail')

    unit = provider_stt.UnitOutcome('done', 'processed')
    consumer = provider_stt.ProviderSttConsumer(lambda: AsyncStubStage(unit), clock=lambda: 100.0, settled=broken)
    with caplog.at_level(logging.WARNING):
        result = await consumer.process_async(_claim(), lambda: True, _inline)
    assert (result.outcome.value, result.reason.value) == ('done', 'processed')
    assert 'action=merge_wake outcome=failed exception_type=RuntimeError' in caplog.text
    assert 'synthetic private detail' not in caplog.text


def test_the_sync_consumer_and_default_construction_have_no_wake():
    unit = provider_stt.UnitOutcome('done', 'processed')
    consumer = provider_stt.ProviderSttConsumer(lambda: StubStage(unit), clock=lambda: 100.0)
    assert consumer.settled is None
    assert consumer.process(_claim(), lambda: True).outcome.value == 'done'


class Requests:
    def __init__(self):
        self.owners = []

    def request(self, owner_id):
        self.owners.append(owner_id)
        return True


def test_route_wake_requests_a_drain_and_the_switch_turns_it_off(monkeypatch):
    requests = Requests()
    monkeypatch.setattr(route, '_owner_drains', requests)
    route.wake_owner_merge(OWNER)
    assert requests.owners == [OWNER]
    monkeypatch.setenv(SWITCH, 'false')
    route.wake_owner_merge(OWNER)
    assert requests.owners == [OWNER]


@pytest.mark.asyncio
async def test_the_serving_route_builds_its_consumer_with_the_wake(monkeypatch):
    built = []

    async def run_push_async(consumer, outbox, row_id, wake_token, *, now, run_sync):
        built.append(consumer)
        return None

    monkeypatch.setattr(route, 'run_push_async', run_push_async)
    await route.run_delivery_async('p1', 'wake', outbox=object())
    assert built[0].settled is route.wake_owner_merge


# --- the drain itself ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_settled_owner_drain_commits_in_capture_order_and_never_skips_the_head_wait(world, monkeypatch):
    _, store = world
    admit(monkeypatch, store, [item('p1', 10)], 'content-1', JA)
    admit(monkeypatch, store, [item('p2', 20)], 'content-2', JA)
    admit(monkeypatch, store, [item('p3', 30)], 'content-3', JA)
    # The drain reads the wall clock, so the rows become ready "now".
    settle(store, 'p1', now=time.time())
    settle(store, 'p3', now=time.time())
    await Serving(store).drain_settled_async(OWNER)
    # p1 commits; p3 is ready behind the unsettled p2 and has not waited out the head wait.
    assert job(store, 'p1')['state'] == 'committed'
    assert job(store, 'p3')['state'] == 'result_ready' and job(store, 'p2')['merge_pending'] is True
