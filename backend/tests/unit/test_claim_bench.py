"""Staging claim bench: seeds through the real enqueue, drains through the real pull/complete.

Hermetic: the batch scheduler runs on the pipeline-sim store and its privacy fence; no Firestore,
no network. The run mode's staging guard is checked without touching any client.
"""

from threading import Lock

import pytest

from scripts.staging import claim_bench
from testing.pipeline_sim.store import CustomerData, SimStore
from utils.batch_pipeline.contracts import Priority
from utils.batch_pipeline.scheduler import Scheduler, owner_key

RUN = 'cbtest1'


class LockedStore:
    """SimStore is single-threaded; the bench's lanes are threads."""

    def __init__(self, store: SimStore):
        self._store = store
        self._lock = Lock()

    def run(self, body):
        with self._lock:
            return self._store.run(body)

    def __getattr__(self, name):
        attribute = getattr(self._store, name)
        if not callable(attribute):
            return attribute

        def locked(*args, **kwargs):
            with self._lock:
                return attribute(*args, **kwargs)

        return locked


@pytest.fixture
def world(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_PERCENT', '100')
    customer = CustomerData()
    store = SimStore(customer)
    return customer, store


def test_owner_guard_accepts_only_this_runs_pseudo_owners():
    assert claim_bench.bench_owner('lg-cbtest1-o0007', RUN)
    assert not claim_bench.bench_owner('lg-cbtest1-o07', RUN)
    assert not claim_bench.bench_owner('lg-cbtest2-o0007', RUN)
    assert not claim_bench.bench_owner('lg-vl1-o0007', 'vl1')  # another harness's run shape
    assert not claim_bench.bench_owner('abcdefghijklmnopqrstuvwxyz12', RUN)  # a real uid shape
    with pytest.raises(ValueError):
        claim_bench.plan('CB-1', owners=1, units=1, duration=60.0, now=1_000_000.0)


def test_plan_is_fresh_unique_and_owner_ordered():
    items = claim_bench.plan(RUN, owners=3, units=4, duration=120.0, now=1_000_000.0)
    assert len(items) == 12
    assert len({item.segment_id for item in items}) == 12
    assert {item.owner_id for item in items} == {claim_bench.owner_id(RUN, i) for i in range(3)}
    assert all(item.priority == Priority.FRESH and item.duration_seconds == 120.0 for item in items)
    for i in range(3):
        mine = [item for item in items if item.owner_id == claim_bench.owner_id(RUN, i)]
        assert [item.capture_at for item in mine] == sorted(item.capture_at for item in mine)
        assert all(1_000_000.0 - item.capture_at < 900 for item in mine)


def test_seed_and_drive_drain_the_backlog_through_the_real_scheduler(world):
    customer, sim = world
    store = LockedStore(sim)
    items = claim_bench.plan(RUN, owners=5, units=6, duration=90.0, now=1_000_000.0)
    for uid in sorted({item.owner_id for item in items}):
        customer.add_user(uid)

    seeded = claim_bench.seed(Scheduler(store), items, now=lambda: 1_000_000.0, threads=3)
    assert seeded == 30

    stats = claim_bench.drive(
        lambda lane: Scheduler(store, worker_id=f'bench-{lane}'),
        lanes=4,
        total=len(items),
        batch=8,
        hold=0.0,
        deadline_s=60.0,
        now=lambda: 1_000_000.0,
    )
    assert stats['settled'] == stats['leased'] == 30
    assert stats['errors'] == {}
    assert stats['drain_leased_per_s'] > 0
    assert stats['pull_calls'] >= stats['nonempty_pulls'] >= 1
    assert 1 <= stats['leases_per_nonempty_pull'] <= 8
    for item in items:
        job = sim.rows[('jobs', item.segment_id)]
        # Never result_ready: serving's merge loop must have nothing of the bench's to commit or project.
        assert job['state'] == 'retry' and 'result' not in job
        assert job['available_at'] >= 1_000_000.0 + claim_bench.SETTLE_PARK_S  # not due again during the run
        assert job['attempt'] == 0  # refunded, so no quarantine-ceiling charge either
    assert not [key for key in sim.rows if key[0] == 'results']


def test_drive_stops_at_its_deadline_and_reports_partial_progress(world):
    customer, sim = world
    store = LockedStore(sim)
    items = claim_bench.plan(RUN, owners=1, units=3, duration=60.0, now=1_000_000.0)
    customer.add_user(items[0].owner_id)
    claim_bench.seed(Scheduler(store), items, now=lambda: 1_000_000.0, threads=1)

    # A total larger than the backlog never drains: the deadline must end the run.
    stats = claim_bench.drive(
        lambda lane: Scheduler(store, worker_id=f'bench-{lane}'),
        lanes=2,
        total=99,
        batch=8,
        hold=0.0,
        deadline_s=0.5,
        now=lambda: 1_000_000.0,
    )
    assert stats['settled'] == 3
    assert stats['timed_out'] is True


def test_a_foreign_unit_is_released_untouched_and_ends_the_run(world):
    customer, sim = world
    store = LockedStore(sim)
    foreign = claim_bench.plan('cbother', owners=1, units=1, duration=60.0, now=1_000_000.0)
    customer.add_user(foreign[0].owner_id)
    claim_bench.seed(Scheduler(store), foreign, now=lambda: 1_000_000.0, threads=1)

    stats = claim_bench.drive(
        lambda lane: Scheduler(store, worker_id=f'bench-{lane}'),
        lanes=1,
        total=5,
        batch=8,
        hold=0.0,
        deadline_s=30.0,
        now=lambda: 1_000_000.0,
        accept=lambda item: claim_bench.bench_owner(item.owner_id, RUN),
    )
    assert stats['foreign'] == 1
    assert stats['settled'] == 0
    job = sim.rows[('jobs', foreign[0].segment_id)]
    # Handed back the way a shutdown refund is: due again after defer's 1 s floor, no result written.
    assert job['state'] == 'retry' and job['available_at'] <= 1_000_001.0 and 'result' not in job
    assert job['attempt'] == 0  # the refund defer leaves no charged attempt behind


def test_merge_combines_processes_on_one_wall_clock_axis():
    part = {
        'leased': 10,
        'settled': 10,
        'rejected': 0,
        'nonempty_pulls': 2,
        'errors': {'Busy': 1},
        'wall_s': 12.0,
        'lanes': 2,
        'pull_calls': 20,
        'pull_wall_s': 4.0,
        'pull_p95_s': 0.4,
        'settle_p95_s': 0.1,
    }
    a = {**part, 'lease_times': [100.0 + i for i in range(10)]}
    b = {**part, 'lease_times': [100.5 + i for i in range(10)], 'errors': {'Busy': 2, 'Other': 1}}
    merged = claim_bench.merge([a, b], total=20)
    assert merged['leased'] == 20 and merged['lanes'] == 4 and merged['processes'] == 2
    assert merged['timed_out'] is False
    assert merged['errors'] == {'Busy': 3, 'Other': 1}
    assert merged['drain_s'] == 9.5
    assert merged['drain_leased_per_s'] == round(19 / 9.5, 3)
    assert merged['pull_wall_per_lease_s'] == 0.4


class RecordingClient:
    def __init__(self):
        self.deleted = []

    def collection(self, name):
        client = self

        class Collection:
            def document(self, key):
                class Document:
                    def delete(self):
                        client.deleted.append((name, key))

                return Document()

        return Collection()


def test_cleanup_deletes_only_documents_derived_from_this_run():
    client = RecordingClient()
    items = claim_bench.plan(RUN, owners=2, units=2, duration=60.0, now=1_000_000.0)
    counts = claim_bench.cleanup(client, 'batch_pipeline_prod', RUN, owners=2, units=2)
    owners = [claim_bench.owner_id(RUN, i) for i in range(2)]
    expected = (
        {('batch_pipeline_prod_jobs', item.segment_id) for item in items}
        | {('batch_pipeline_prod_results', item.segment_id) for item in items}
        | {('batch_pipeline_prod_queues', f'{int(Priority.FRESH)}_{owner_key(uid)}') for uid in owners}
        | {('batch_pipeline_prod_owners', owner_key(uid)) for uid in owners}
        | {('users', uid) for uid in owners}
    )
    assert set(client.deleted) == expected
    assert counts == {'jobs': 4, 'results': 4, 'queues': 2, 'owners': 2, 'users': 2}
    # Shared scheduler documents are never touched.
    assert not any(name.endswith(('_control', '_pull_claims')) for name, _ in client.deleted)


def test_run_has_no_mode_that_skips_cleanup():
    # A parked unit left behind comes due after a day and turns into live staging work.
    with pytest.raises(SystemExit):
        claim_bench.main(['run', '--run-id', RUN, '--owners', '1', '--units', '1', '--keep'])


def test_run_refuses_outside_the_staging_runtime(monkeypatch):
    monkeypatch.delenv('OMI_DEPLOYMENT', raising=False)
    monkeypatch.setenv('FIRESTORE_DATABASE_ID', 'staging')
    with pytest.raises(claim_bench.BenchRefused):
        claim_bench.require_staging()
    monkeypatch.setenv('OMI_DEPLOYMENT', 'staging')
    monkeypatch.setenv('FIRESTORE_DATABASE_ID', '(default)')
    with pytest.raises(claim_bench.BenchRefused):
        claim_bench.require_staging()
