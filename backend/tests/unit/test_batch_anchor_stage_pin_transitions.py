"""Anchor stage pins inside the real scheduler transitions.

The pump publishes one owner's leases concurrently (`_publish_flight`), so
every sibling transition that historically wrote the shared anchor row raced
every other one. These tests drive the real `Scheduler` state machine over the
simulated store and prove the contention surface: the anchor row only ever
appears in a dedicated single-document pin transaction, never inside a
sibling's fail/pull/defer/complete write set.
"""

import pytest

from config.policy import telemetry
from database.batch_pipeline_policy import AnchorStagePin
from dataclasses import asdict
from testing.pipeline_sim.store import CustomerData, SimStore
from utils.batch_pipeline.contracts import Priority, ProjectionBinding, WorkItem, WorkResult
from utils.batch_pipeline.scheduler import Scheduler

BINDING = asdict(ProjectionBinding('owner', 'job', 'content', ('head', 'tail')))


class PinSpy:
    """Counts every dedicated pin transaction; optionally breaks them."""

    def __init__(self, inner):
        self.inner = inner
        self.pin_runs = 0
        self.broken = False
        self.operations = []

    def run(self, body, *, operation=None):
        self.operations.append(operation)
        if self.broken and operation == 'batch_anchor_stage_pin':
            self.pin_runs += 1
            raise RuntimeError('simulated contention exhaustion')
        if operation == 'batch_anchor_stage_pin':
            self.pin_runs += 1
        return self.inner.run(body, operation=operation)

    def __getattr__(self, name):
        return getattr(self.inner, name)


def make_scheduler(*, break_pins=False):
    customer = CustomerData()
    customer.add_user('owner')
    store = SimStore(customer)
    spy = PinSpy(store)
    queue = Scheduler(spy)
    queue.enqueue(WorkItem('tail', 'owner', 1, 'sim://audio', 1, Priority.FRESH), 1)
    store.rows[('jobs', 'head')] = {'segment_id': 'head', 'owner_id': 'owner'}
    for sid in ('head', 'tail'):
        store.rows[('jobs', sid)]['projection_binding'] = dict(BINDING)
    spy.broken = break_pins
    return store, spy, queue


def strip_parts(store):
    for sid in ('head', 'tail', 'mid', 'lone'):
        row = store.rows.get(('jobs', sid))
        if row is None:
            continue
        row.pop('policy', None)
        row.pop('policy_source', None)
        row.pop('policy_parts', None)
        row.pop('policy_part_sources', None)


def observed_writes(store):
    """Address sets per transaction index, recorded by the SimStore observers."""
    seen = {}

    def observe(address, before, after):
        seen.setdefault(store.transactions, set()).add(address)

    store.observers.append(observe)
    return seen


def test_pull_stages_the_head_job_and_pins_the_anchor_afterwards():
    store, spy, queue = make_scheduler()
    writes = observed_writes(store)
    lease = queue.pull(2)[0]
    assert lease is not None
    assert store.get('jobs', 'tail')['policy_parts']['scheduler']
    assert store.get('jobs', 'head')['policy_parts']['scheduler']
    anchor_txns = [index for index, addresses in writes.items() if ('jobs', 'head') in addresses]
    assert all(index > min(writes) for index in anchor_txns), 'the anchor write never shares the pull transaction'
    assert spy.pin_runs == 1


def test_pull_write_set_excludes_the_anchor_row():
    store, _, queue = make_scheduler()
    writes = observed_writes(store)
    queue.pull(2)
    pull_txn = min(writes)
    assert ('jobs', 'head') not in writes[pull_txn]
    assert ('jobs', 'tail') in writes[pull_txn]


def test_second_pull_copies_the_pinned_part_without_another_pin():
    store, spy, queue = make_scheduler()
    queue.pull(2)
    first_pins = spy.pin_runs
    queue.enqueue(WorkItem('mid', 'owner', 1, 'sim://audio', 1, Priority.FRESH), 2)
    store.rows[('jobs', 'mid')]['projection_binding'] = dict(BINDING)
    writes = observed_writes(store)
    queue.pull(3)
    assert spy.pin_runs == first_pins, 'the pinned anchor is copied, never repinned'
    anchor_txns = [index for index, addresses in writes.items() if ('jobs', 'head') in addresses]
    assert anchor_txns == [], 'a pinned owner keeps the anchor out of every later pull'


def test_fail_quarantines_the_sibling_and_pins_the_anchor():
    store, spy, queue = make_scheduler()
    lease = queue.pull(2)[0]
    baseline = spy.pin_runs
    strip_parts(store)
    writes = observed_writes(store)
    assert queue.fail('tail', lease.token, 3, quarantine=True) is True
    job = store.get('jobs', 'tail')
    assert job['state'] == 'quarantined'
    assert job['policy_parts']['scheduler']
    assert store.get('jobs', 'head')['policy_parts']['scheduler']
    fail_txn = min(writes)
    assert ('jobs', 'head') not in writes[fail_txn], 'the fail transaction stays single-row'
    assert spy.pin_runs == baseline + 1


def test_fail_write_set_is_exactly_the_transition_row():
    store, _, queue = make_scheduler()
    lease = queue.pull(2)[0]
    strip_parts(store)
    writes = observed_writes(store)
    queue.fail('tail', lease.token, 3, quarantine=True)
    fail_txn = min(writes)
    assert ('jobs', 'head') not in writes[fail_txn]
    assert ('jobs', 'tail') in writes[fail_txn]


def test_fail_with_a_broken_pin_store_still_quarantines(caplog):
    store, spy, queue = make_scheduler(break_pins=True)
    lease = queue.pull(2)[0]
    strip_parts(store)
    with caplog.at_level('WARNING', logger='database.batch_pipeline_policy'):
        assert queue.fail('tail', lease.token, 3, quarantine=True) is True
    job = store.get('jobs', 'tail')
    assert job['state'] == 'quarantined' and job['policy_parts']['scheduler']
    assert store.get('jobs', 'head').get('policy_parts') is None
    assert any('outcome=deferred' in record.getMessage() for record in caplog.records)


def test_broken_pin_converges_on_the_next_staging_touch():
    store, spy, queue = make_scheduler(break_pins=True)
    lease = queue.pull(2)[0]
    strip_parts(store)
    queue.fail('tail', lease.token, 3, quarantine=True)
    assert store.get('jobs', 'head').get('policy_parts') is None
    spy.broken = False
    from database.batch_pipeline_policy import load_stage_policy

    _, policy = load_stage_policy(store, 'head', 'scheduler')
    assert store.get('jobs', 'head')['policy_parts']['scheduler'] == policy.to_dict()


def test_defer_opens_no_pin_transaction():
    store, spy, queue = make_scheduler()
    lease = queue.pull(2)[0]
    before = spy.pin_runs
    assert queue.defer('tail', lease.token, 3, retry_after=30, held_reason='held') is True
    assert spy.pin_runs == before, 'deferring consults policy but never stages a new part'


def test_complete_opens_no_pin_transaction():
    store, spy, queue = make_scheduler()
    lease = queue.pull(2)[0]
    before = spy.pin_runs
    assert queue.complete(WorkResult('tail', 'sim://result'), lease.token, 3) is True
    assert spy.pin_runs == before


def test_single_unit_owner_keeps_the_self_stage_path():
    customer = CustomerData()
    customer.add_user('owner')
    store = SimStore(customer)
    spy = PinSpy(store)
    queue = Scheduler(spy)
    queue.enqueue(WorkItem('lone', 'owner', 1, 'sim://audio', 1, Priority.FRESH), 1)
    store.rows[('jobs', 'lone')]['projection_binding'] = dict(
        asdict(ProjectionBinding('owner', 'job', 'content', ('lone',)))
    )
    lease = queue.pull(2)[0]
    strip_parts(store)
    assert queue.fail('lone', lease.token, 3, quarantine=True) is True
    assert spy.pin_runs == 0, 'the anchor is the job itself: no pin transactions exist'
    assert store.get('jobs', 'lone')['policy_parts']['scheduler']


def test_enqueue_opens_no_pin_transaction():
    store, spy, _ = make_scheduler()
    assert spy.pin_runs == 0
    assert 'batch_anchor_stage_pin' not in spy.operations


def test_pinned_anchor_survives_sibling_completion():
    store, spy, queue = make_scheduler()
    lease = queue.pull(2)[0]
    assert store.get('jobs', 'head')['policy_parts']['scheduler']
    assert queue.complete(WorkResult('tail', 'sim://result'), lease.token, 3) is True
    assert store.get('jobs', 'head')['policy_parts']['scheduler'], 'completion never rewrites the anchor'


def test_planted_owner_mismatch_is_refused_without_staging():
    store, _, queue = make_scheduler()
    lease = queue.pull(2)[0]
    strip_parts(store)
    store.rows[('jobs', 'head')]['owner_id'] = 'someone-else'
    with pytest.raises(ValueError, match='policy sibling owner mismatch'):
        queue.fail('tail', lease.token, 3, quarantine=True)
    assert store.get('jobs', 'tail').get('policy_parts') is None
    assert store.get('jobs', 'tail').get('state') != 'quarantined'


def test_fail_telemetry_reports_the_fallback_once():
    store, _, queue = make_scheduler()
    lease = queue.pull(2)[0]
    strip_parts(store)
    events = []
    original = telemetry.record_policy_source
    telemetry.record_policy_source = lambda source, *_, **__: events.append(source)
    try:
        queue.fail('tail', lease.token, 3, quarantine=True)
    finally:
        telemetry.record_policy_source = original
    assert events == ['fallback']


def test_privacy_parked_pull_stages_and_pins_nothing():
    store, spy, queue = make_scheduler()
    store.customer.block_privacy('owner')
    assert queue.pull(2) == []
    assert spy.pin_runs == 0
    assert store.get('jobs', 'tail').get('policy_parts') is None


def test_two_owners_pin_their_own_anchors():
    customer = CustomerData()
    customer.add_user('owner-a')
    customer.add_user('owner-b')
    store = SimStore(customer)
    spy = PinSpy(store)
    queue = Scheduler(spy)
    for owner in ('owner-a', 'owner-b'):
        queue.enqueue(WorkItem(f'{owner}-tail', owner, 1, 'sim://audio', 1, Priority.FRESH), 1)
        store.rows[('jobs', f'{owner}-head')] = {'segment_id': f'{owner}-head', 'owner_id': owner}
        binding = asdict(ProjectionBinding(owner, 'job', 'content', (f'{owner}-head', f'{owner}-tail')))
        store.rows[('jobs', f'{owner}-head')]['projection_binding'] = dict(binding)
        store.rows[('jobs', f'{owner}-tail')]['projection_binding'] = dict(binding)
    queue.pull(2)
    assert store.get('jobs', 'owner-a-head')['policy_parts']['scheduler']
    queue.pull(2)
    assert store.get('jobs', 'owner-b-head')['policy_parts']['scheduler']
    assert spy.pin_runs == 2, 'each owner converges on its own canonical row'


# ---------------------------------------------------------------------------
# Storm nails: the write-amplification model, old behavior vs new.
# ---------------------------------------------------------------------------


def test_legacy_mode_three_siblings_write_the_anchor_three_times():
    from database import batch_pipeline_policy as policies
    from tests.unit.test_batch_anchor_stage_pin_parity import make_store, stage_buffered

    unit = make_store()
    for sid in ('head', 'mid', 'tail'):
        writes, _, _, _ = stage_buffered(unit, sid, 'scheduler', pins=None)
        assert ('jobs', 'head') in writes, 'the legacy write set carries the shared anchor row'


def test_pin_mode_three_siblings_write_the_anchor_never():
    from database import batch_pipeline_policy as policies
    from tests.unit.test_batch_anchor_stage_pin_parity import make_store, stage_buffered

    unit = make_store()
    pins = []
    for sid in ('mid', 'tail'):
        writes, _, _, _ = stage_buffered(unit, sid, 'scheduler', pins=pins)
        assert ('jobs', 'head') not in writes, 'a sibling transition never carries the anchor row'
    assert len(pins) == 2
    assert policies.flush_anchor_stage_pins(unit, pins) == 1


def test_descriptor_flush_order_decides_the_canonical_winner():
    from dataclasses import replace
    from config.policy.stages import STAGE_TYPES
    from database import batch_pipeline_policy as policies
    from tests.unit.test_batch_anchor_stage_pin_parity import make_store

    unit = make_store()
    first = replace(STAGE_TYPES['scheduler'](), max_attempts=2)
    second = replace(STAGE_TYPES['scheduler'](), max_attempts=9)
    descriptors = [
        AnchorStagePin('head', 'scheduler', first.to_dict(), 'fallback'),
        AnchorStagePin('head', 'scheduler', second.to_dict(), 'fallback'),
    ]
    assert policies.flush_anchor_stage_pins(unit, descriptors) == 1
    assert unit.get('jobs', 'head')['policy_parts']['scheduler']['max_attempts'] == 2


def test_every_stage_transition_write_set_is_single_row():
    from tests.unit.test_batch_anchor_stage_pin_parity import STAGES, make_store, stage_buffered

    for stage in STAGES:
        unit = make_store()
        writes, _, _, _ = stage_buffered(unit, 'tail', stage)
        assert set(writes) == {('jobs', 'tail')}, f'{stage} must not write the anchor row'


def test_pin_transaction_writes_exactly_one_document():
    from tests.unit.test_batch_anchor_stage_pin_parity import make_store, stage_buffered

    unit = make_store()
    writes = observed_writes(unit)
    _, _, pins, _ = stage_buffered(unit, 'tail', 'scheduler')
    from database.batch_pipeline_policy import flush_anchor_stage_pins

    flush_anchor_stage_pins(unit, pins)
    pin_txn = max(writes)
    assert writes[pin_txn] == {('jobs', 'head')}, 'the pin is a single-document transaction'
