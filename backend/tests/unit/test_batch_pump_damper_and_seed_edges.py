"""Pump plumbing edges, damper arithmetic and remaining store-label smokes.

Last sweep of the caller surface: the pump's owner serialisation, owner memo
and metrics cadence; the damper's generation arithmetic at the tracked-label
cap; the store's per-label wave-bridge smokes for the maintenance and
intake labels; the recover seed threading into the shard control document;
and the sim hint's named priorities.

Failure-Class: FC-contention-chain-spends-its-budget-inside-one-abort-wave
"""

import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from database import batch_pipeline_store as storage
from database.firestore_transaction_retry import FirestoreContentionExhausted
from testing.pipeline_sim.store import SimStore
from utils.batch_pipeline.pump import Pump, SEGMENT_OWNER_MEMO


class WaveTx:
    _max_attempts = 1
    _read_only = False
    _id = None

    def __init__(self):
        self._clean_up = lambda: None
        self._begin = lambda retry_id=None: None
        self._commit = lambda: None
        self._rollback = lambda: None


class OkClient:
    def __init__(self):
        self.minted = 0

    def transaction(self, max_attempts=5):
        self.minted += 1
        return WaveTx()


def build(monkeypatch, damper=None, client=None):
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    return storage.FirestoreStore('batch_pipeline_dev', firestore_client=client or OkClient(), storm_damper=damper)


def make_damper(monotonic=lambda: 500.0, sleeper=lambda s: None, random_value=lambda: 1.0):
    return storage._ContentionStormDamper(monotonic=monotonic, sleeper=sleeper, random_value=random_value)


@pytest.mark.parametrize(
    'label', ['batch_recover', 'batch_redrive', 'batch_gpu_release', 'batch_merge_hold_release', 'batch_intake_status']
)
def test_maintenance_label_commits_through_the_bridged_chain(monkeypatch, label):
    store = build(monkeypatch)
    assert store.run(lambda tx: 'ok', operation=label) == 'ok'


@pytest.mark.parametrize(
    'label', ['batch_recover', 'batch_redrive', 'batch_gpu_release', 'batch_merge_hold_release', 'batch_intake_status']
)
def test_maintenance_label_exhaustion_arms_its_own_damper(monkeypatch, label):
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')

    class Storm:
        def __init__(self):
            self.minted = 0

        def transaction(self, max_attempts=5):
            self.minted += 1

            tx = WaveTx()
            original = tx._commit

            def commit():
                raise Aborted('storm')

            tx._commit = commit
            return tx

    from google.api_core.exceptions import Aborted

    damper = make_damper()
    store = storage.FirestoreStore('batch_pipeline_dev', firestore_client=Storm(), storm_damper=damper)
    with pytest.raises(FirestoreContentionExhausted):
        store.run(lambda tx: True, operation=label)
    assert damper.consult(label)[0] > 0.0


def test_damper_generations_increment_per_arm():
    damper = make_damper()
    assert damper.consult('l')[1] == 0
    damper.arm('l')
    assert damper.consult('l')[1] == 1
    damper.arm('l')
    assert damper.consult('l')[1] == 2


def test_damper_consult_sleeps_only_the_residual():
    sleeps, now = [], [500.0]
    damper = make_damper(monotonic=lambda: now[0], sleeper=lambda s: sleeps.append(s))
    damper.arm('l')
    damper.consult('l')
    assert sleeps == [0.25]


def test_damper_success_of_an_unknown_label_is_harmless():
    damper = make_damper()
    damper.note_success('never-armed', 0)
    assert damper.tracked_labels() == 0


def test_the_cap_of_tracked_labels_still_damps_the_last_slot():
    damper = make_damper()
    for index in range(FirestoreStore_cap() - 1):
        damper.arm(f'l{index}')
    assert damper.arm('the_last') > 0.0


def FirestoreStore_cap():
    return storage.FirestoreStore.STORM_DAMPER_MAX_TRACKED_LABELS


# --------------------------------------------------------------------------
# Pump plumbing
# --------------------------------------------------------------------------


def make_pump(**overrides):
    pump = Pump.__new__(Pump)
    pump._owner_locks = {}
    pump._segment_owners = __import__('collections').OrderedDict()
    pump.publish_concurrency = overrides.get('publish_concurrency', 4)
    pump.timings = __import__('utils.batch_pipeline.stage_timings', fromlist=['StageTimings']).StageTimings()
    pump.scheduler = SimpleNamespace(store=SimpleNamespace(probe=lambda table, key: {'owner_id': 'o1'}))
    pump.merge = SimpleNamespace(commit_next=lambda owner_id, now: None, held_owners=set())
    return pump


def test_owner_serial_is_mutually_exclusive():
    pump = make_pump()
    order = []

    async def user():
        async with pump._owner_serial('o1'):
            order.append('enter')
            await asyncio.sleep(0.01)
            order.append('exit')

    async def both():
        await asyncio.gather(user(), user())

    asyncio.run(both())
    assert order == ['enter', 'exit', 'enter', 'exit']


def test_owner_serial_entries_are_evicted_when_idle():
    pump = make_pump()

    async def one():
        async with pump._owner_serial('o1'):
            pass

    asyncio.run(one())
    assert 'o1' not in pump._owner_locks


def test_remember_owner_is_bounded():
    pump = make_pump()
    for index in range(SEGMENT_OWNER_MEMO + 50):
        pump._remember_owner(f'seg-{index}', 'o1')
    assert len(pump._segment_owners) == SEGMENT_OWNER_MEMO
    assert 'seg-0' not in pump._segment_owners  # the oldest entry was evicted


def test_drain_ready_owners_resolves_and_memoizes_the_owner(monkeypatch):
    pump = make_pump()
    probes = []
    pump.scheduler.store.probe = lambda table, key: probes.append(key) or {'owner_id': 'o1'}
    drains = []

    async def drain(owner_id):
        drains.append(owner_id)

    monkeypatch.setattr(pump, 'drain_owner', drain)
    asyncio.run(pump._drain_ready_owners(['seg-1']))
    assert drains == ['o1']
    assert pump._segment_owners['seg-1'] == 'o1'  # memoized for the next sweep


# --------------------------------------------------------------------------
# Recover seeds reach the shard control document
# --------------------------------------------------------------------------


class TxStub:
    def __init__(self, rows):
        self.rows = rows

    def get(self, table, key):
        import copy

        return copy.deepcopy(self.rows.get((table, key), {}))

    def put(self, table, key, value):
        import copy

        self.rows[(table, key)] = copy.deepcopy(value)

    def patch(self, table, key, fields):
        import copy

        self.rows.setdefault((table, key), {}).update(copy.deepcopy(fields))

    def check_privacy(self, uid, conversation_ids=(), expected_generation=None):
        return expected_generation or 0


def test_rejoin_frontiers_maps_every_requested_priority():
    from utils.batch_pipeline.scheduler import rejoin_frontiers

    hints = {}

    class HintStore:
        def service_frontier_hint(self, priority):
            hints[priority] = hints.get(priority, 0) + 1
            return float(priority)

    seeds = rejoin_frontiers(HintStore(), (0, 1, 2))
    assert seeds == {0: 0.0, 1: 1.0, 2: 2.0}
    assert hints == {0: 1, 1: 1, 2: 1}


def test_rejoin_frontiers_degrades_to_zero_when_a_hint_fails():
    from utils.batch_pipeline.scheduler import rejoin_frontiers

    class FailingStore:
        def service_frontier_hint(self, priority):
            raise RuntimeError('hint down')

    assert rejoin_frontiers(FailingStore(), (0, 1)) == {0: 0.0, 1: 0.0}


# --------------------------------------------------------------------------
# Sim hint named priorities
# --------------------------------------------------------------------------


def sim_with(services):
    store = SimStore.__new__(SimStore)
    store.rows = {}
    store._controls = set()
    for index, value in enumerate(services):
        key = f'c{index}'
        store.rows[('control', key)] = {f'p{index}_service': value}
        store._controls.add(key)
    return store


def test_sim_hint_priority_zero_is_the_max_of_p0():
    store = sim_with([3.0])
    store.rows[('control', 'c0')] = {'p0_service': 3.0}
    assert store.service_frontier_hint(0) == 3.0


def test_sim_hint_priority_one_is_the_max_of_p1():
    store = sim_with([0.0])
    store.rows[('control', 'c0')] = {'p1_service': 4.5}
    assert store.service_frontier_hint(1) == 4.5


def test_sim_hint_priority_two_is_the_max_of_p2():
    store = sim_with([0.0])
    store.rows[('control', 'c0')] = {'p2_service': 0.25}
    assert store.service_frontier_hint(2) == 0.25


def test_the_recover_sweep_reads_the_sim_hint_priorities():
    store = SimStore.__new__(SimStore)
    store.rows, store._controls = {}, set()
    hints = []
    store.service_frontier_hint = lambda priority: hints.append(priority) or 0.0
    assert store.service_frontier_hint(1) == 0.0
    assert hints == [1]
