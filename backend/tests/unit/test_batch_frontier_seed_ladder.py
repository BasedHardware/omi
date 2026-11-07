"""Seed ladder: every entry point, priority and degrade mode, by the grid.

Companion to ``test_batch_admission_abort_set`` (ordering, gates, guards) and
``test_batch_rejoin_wave_fairness`` (scheduling consequences). This suite
walks the full grid:

1. ``rejoin_frontiers`` value semantics: partial tables, dedupe, float
   coercion, per-priority degradation, deterministic ascending call order.
2. The ring-enqueue hint grid: every bounded priority times every seed value,
   asserted on the committed shard document.
3. ``admit``'s ``frontiers`` map: exact, float-keyed, empty and absent maps;
   custom (provider-STT) enqueues stay off the kwarg.
4. The recover sweep threading one map through BOTH the legacy migration and
   the retry requeue.
5. The static requeue methods (restore / redrive) seeding every priority and
   both pool windows through their own transaction.
6. ``durable_status`` probe states that do and do not pay for hint reads.

Failure-Class: FC-rejoin-frontier-seed-read-joins-the-argmax-shard-abort-set
"""

import hashlib
from copy import deepcopy
from dataclasses import replace
from types import SimpleNamespace

import pytest
from config.batch_pipeline import scheduler_control_key
from database.batch_pipeline_intake import admit
from tests.unit.test_batch_pipeline_intake import proposal
from tests.unit.test_batch_pipeline_scheduler import MemoryStore, MemoryTransaction, item
from utils.batch_pipeline.contracts import Priority
from utils.batch_pipeline.scheduler import Scheduler, owner_key, rejoin_frontiers
from utils.batch_pipeline.intake import durable_status


class GridStore(MemoryStore):
    """Rows-backed store with a scripted hint table and failure switch."""

    def __init__(self, hints=None, failing=(), namespace='batch_pipeline_test_grid'):
        super().__init__()
        self._hints = dict(hints or {})
        self._failing = set(failing)
        self.hint_calls = []
        self.namespace = namespace

    def service_frontier_hint(self, priority):
        if priority not in (0, 1, 2):
            raise ValueError('bounded priority required')
        value = self._hints.get(priority, 0.0)
        self.hint_calls.append((priority, value))
        if priority in self._failing:
            raise RuntimeError('synthetic hint outage')
        return value


@pytest.fixture(autouse=True)
def cohort(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_UID_ALLOWLIST', 'synthetic-owner')
    monkeypatch.setenv('BATCH_PIPELINE_PERCENT', '0')


# --------------------------------------------------------------------------
# 1. rejoin_frontiers value semantics
# --------------------------------------------------------------------------


def test_frontiers_full_table_is_returned():
    seeds = rejoin_frontiers(GridStore(hints={0: 1.0, 1: 2.0, 2: 3.0}), (0, 1, 2))
    assert seeds == {0: 1.0, 1: 2.0, 2: 3.0}


def test_frontiers_missing_priorities_default_to_zero():
    seeds = rejoin_frontiers(GridStore(hints={2: 5.0}), (0, 1, 2))
    assert seeds == {0: 0.0, 1: 0.0, 2: 5.0}


def test_frontiers_empty_table_is_all_zero():
    seeds = rejoin_frontiers(GridStore(), (0, 1, 2))
    assert seeds == {0: 0.0, 1: 0.0, 2: 0.0}


def test_frontiers_single_priority():
    assert rejoin_frontiers(GridStore(hints={1: 4.0}), (1,)) == {1: 4.0}


def test_frontiers_dedupe_priorities():
    store = GridStore(hints={1: 4.0})
    seeds = rejoin_frontiers(store, (1, 1, 1))
    assert seeds == {1: 4.0}
    assert len(store.hint_calls) == 1


def test_frontiers_calls_priorities_in_ascending_order():
    store = GridStore(hints={0: 1.0, 1: 2.0, 2: 3.0})
    rejoin_frontiers(store, (2, 0, 1))
    assert [priority for priority, _ in store.hint_calls] == [0, 1, 2]


def test_frontiers_integer_enum_values_are_accepted():
    seeds = rejoin_frontiers(GridStore(hints={2: 7.0}), (int(Priority.DEEP),))
    assert seeds == {int(Priority.DEEP): 7.0}


def test_frontiers_coerces_int_hint_values_to_float():
    store = GridStore()
    store._hints[1] = 4
    assert rejoin_frontiers(store, (1,)) == {1: 4.0}
    assert type(rejoin_frontiers(store, (1,))[1]) is float


def test_frontiers_coerce_failure_degrades_that_priority_only():
    store = GridStore()
    store._hints[1] = 'not-a-number'
    seeds = rejoin_frontiers(store, (0, 1, 2))
    assert seeds == {0: 0.0, 1: 0.0, 2: 0.0}
    assert len(store.hint_calls) == 3


def test_frontiers_negative_values_pass_through():
    assert rejoin_frontiers(GridStore(hints={1: -2.5}), (1,)) == {1: -2.5}


def test_frontiers_huge_values_pass_through():
    assert rejoin_frontiers(GridStore(hints={1: 1e15}), (1,)) == {1: 1e15}


def test_frontiers_degrades_out_of_band_priorities_instead_of_raising():
    # The helper is fail-open by contract: an out-of-band priority degrades to
    # a 0.0 seed (and its degraded log) rather than failing the caller.
    seeds = rejoin_frontiers(GridStore(), (5,))
    assert seeds == {5: 0.0}


# --------------------------------------------------------------------------
# 2. Ring-enqueue hint grid
# --------------------------------------------------------------------------


@pytest.mark.parametrize('enum', [Priority.FRESH, Priority(1), Priority.DEEP])
@pytest.mark.parametrize('hint', [0.0, 5.5, 99.0])
def test_enqueue_grid_seeds_the_committed_shard(enum, hint):
    store = GridStore(hints={int(enum): hint})
    assert Scheduler(store).enqueue(item('seg-grid', priority=enum), 100.0) is True
    shard = store.rows.get(('control', scheduler_control_key(owner_key('heavy'))))
    assert shard[f'p{int(enum)}_service'] == hint
    assert shard[f'p{int(enum)}_active'] is True


@pytest.mark.parametrize('enum', [Priority.FRESH, Priority(1), Priority.DEEP])
def test_enqueue_grid_without_a_hint_seeds_zero(enum):
    store = GridStore()
    Scheduler(store).enqueue(item('seg-grid', priority=enum), 100.0)
    shard = store.rows.get(('control', scheduler_control_key(owner_key('heavy'))))
    assert shard[f'p{int(enum)}_service'] == 0.0


@pytest.mark.parametrize('enum', [Priority.FRESH, Priority(1), Priority.DEEP])
def test_enqueue_grid_failure_degrades_to_zero_and_admits(enum):
    store = GridStore(failing={int(enum)})
    assert Scheduler(store).enqueue(item('seg-grid', priority=enum), 100.0) is True
    shard = store.rows.get(('control', scheduler_control_key(owner_key('heavy'))))
    assert shard[f'p{int(enum)}_service'] == 0.0


def test_enqueue_grid_keeps_priorities_isolated():
    store = GridStore(hints={0: 1.0, 1: 2.0, 2: 3.0})
    for enum in (Priority.FRESH, Priority(1), Priority.DEEP):
        Scheduler(store).enqueue(item(f'seg-{int(enum)}', priority=enum), 100.0)
    shard = store.rows.get(('control', scheduler_control_key(owner_key('heavy'))))
    assert shard['p0_service'] == 1.0
    assert shard['p1_service'] == 2.0
    assert shard['p2_service'] == 3.0


# --------------------------------------------------------------------------
# 3. admit's frontiers map grid
# --------------------------------------------------------------------------


def _spy(monkeypatch, captured):
    real = Scheduler.enqueue_in_transaction

    def spy(tx, work, now, *, policy=None, frontier=0.0):
        captured.append((int(work.priority), frontier))
        return real(tx, work, now, policy=policy, frontier=frontier)

    monkeypatch.setattr(Scheduler, 'enqueue_in_transaction', staticmethod(spy))


def test_admit_exact_map_reaches_the_ring(monkeypatch):
    store = GridStore()
    works, binding = proposal()
    captured = []
    _spy(monkeypatch, captured)
    admit(store, works, binding, 100, namespace='batch_pipeline_test_grid', frontiers={int(Priority.DEEP): 9.0})
    assert captured[0] == (int(Priority.DEEP), 9.0)


def test_admit_float_keyed_map_reaches_the_ring(monkeypatch):
    store = GridStore()
    works, binding = proposal()
    captured = []
    _spy(monkeypatch, captured)
    admit(store, works, binding, 100, namespace='batch_pipeline_test_grid', frontiers={float(int(Priority.DEEP)): 9.0})
    assert captured[0] == (int(Priority.DEEP), 9.0)


def test_admit_empty_map_degrades_to_zero(monkeypatch):
    store = GridStore()
    works, binding = proposal()
    captured = []
    _spy(monkeypatch, captured)
    admit(store, works, binding, 100, namespace='batch_pipeline_test_grid', frontiers={})
    assert captured[0] == (int(Priority.DEEP), 0.0)


def test_admit_absent_map_degrades_to_zero(monkeypatch):
    store = GridStore()
    works, binding = proposal()
    captured = []
    _spy(monkeypatch, captured)
    admit(store, works, binding, 100, namespace='batch_pipeline_test_grid')
    assert captured[0] == (int(Priority.DEEP), 0.0)


def test_admit_map_never_reaches_a_custom_enqueue(monkeypatch):
    store = GridStore()
    works, binding = proposal()
    seen = []

    def custom(tx, work, now, *, policy=None):
        seen.append(work.segment_id)
        return True

    admit(
        store,
        works,
        binding,
        100,
        namespace='batch_pipeline_test_grid',
        enqueue=custom,
        frontiers={int(Priority.DEEP): 9.0},
    )
    assert seen == [works[0].segment_id]


def test_admit_siblings_share_their_priority_seed(monkeypatch):
    store = GridStore()
    works, binding = proposal()
    works = [
        works[0],
        replace(works[0], segment_id='segment-2', capture_at=2.0),
    ]
    from utils.batch_pipeline.contracts import ProjectionBinding

    binding = ProjectionBinding(
        binding.owner_id, binding.job_id, binding.content_id, tuple(w.segment_id for w in works)
    )
    captured = []
    _spy(monkeypatch, captured)
    admit(store, works, binding, 100, namespace='batch_pipeline_test_grid', frontiers={int(Priority.DEEP): 6.0})
    assert captured == [(int(Priority.DEEP), 6.0), (int(Priority.DEEP), 6.0)]


# --------------------------------------------------------------------------
# 4. The recover sweep threads one map through migration and requeue
# --------------------------------------------------------------------------


def _recover_store(hints=None):
    from config.batch_pipeline import scheduler_control_key as sck

    store = GridStore(hints=hints)
    owner = owner_key('heavy')
    store.rows[('jobs', 'seg-1')] = {
        'segment_id': 'seg-1',
        'state': 'retry',
        'available_at': 50.0,
        'attempt': 2,
        'owner_id': 'heavy',
        'owner_key': owner,
        'priority': int(Priority.DEEP),
        'enqueued_at': 40.0,
        'capture_at': 40.0,
        'merge_pending': True,
        'next': '',
        'policy': {},
        'privacy_generation': None,
    }
    legacy_owner = 'cafe0001'
    store.rows[('control', 'scheduler')] = {
        'rings': {str(int(Priority.DEEP)): [f'{int(Priority.DEEP)}_{legacy_owner}']}
    }
    store.rows[('queues', f'{int(Priority.DEEP)}_{legacy_owner}')] = {'head': 'seg-legacy'}
    return store, legacy_owner


def test_recover_seeds_both_the_migration_and_the_requeue():
    store, legacy_owner = _recover_store(hints={int(Priority.DEEP): 7.0})
    Scheduler(store, metrics=None).recover(100.0)
    legacy_shard = store.rows.get(('control', scheduler_control_key(legacy_owner)))
    assert legacy_shard[f'p{int(Priority.DEEP)}_service'] == 7.0
    retried_shard = store.rows.get(('control', scheduler_control_key(owner_key('heavy'))))
    assert retried_shard[f'p{int(Priority.DEEP)}_service'] == 7.0


def test_recover_requeues_and_migrates_in_one_sweep():
    store, legacy_owner = _recover_store(hints={int(Priority.DEEP): 7.0})
    Scheduler(store, metrics=None).recover(100.0)
    assert store.rows[('jobs', 'seg-1')]['state'] == 'ready'
    assert ('control', scheduler_control_key(legacy_owner)) in store.rows


def test_recover_migrate_seed_defaults_to_zero_for_unhinted_priorities():
    store, legacy_owner = _recover_store(hints={0: 5.0})
    Scheduler(store, metrics=None).recover(100.0)
    legacy_shard = store.rows.get(('control', scheduler_control_key(legacy_owner)))
    assert legacy_shard[f'p{int(Priority.DEEP)}_service'] == 0.0


def test_recover_degraded_hints_still_complete_the_sweep():
    store, legacy_owner = _recover_store(hints={int(Priority.DEEP): 7.0})
    store._failing = {0, 1, 2}
    Scheduler(store, metrics=None).recover(100.0)
    assert store.rows[('jobs', 'seg-1')]['state'] == 'ready'
    legacy_shard = store.rows.get(('control', scheduler_control_key(legacy_owner)))
    assert legacy_shard[f'p{int(Priority.DEEP)}_service'] == 0.0


# --------------------------------------------------------------------------
# 5. Static requeue methods: seed grid through their own transaction
# --------------------------------------------------------------------------


def _tx_with_owner(priority=int(Priority.DEEP)):
    owner = owner_key('heavy')
    rows = {
        ('control', scheduler_control_key(owner)): {
            f'p{priority}_active': False,
            f'p{priority}_service': 1.0,
            f'p{priority}_batch_available_at': 500.0,
            f'p{priority}_live_available_at': 500.0,
            'rings': {'0': [], '1': [], '2': []},
        }
    }
    return MemoryTransaction(deepcopy(rows)), rows, owner


def _restorable_job(priority=int(Priority.DEEP)):
    return {
        'segment_id': 'seg-restore',
        'state': 'quarantined',
        'recovery_state': 'failed_held',
        'artifact_disposition': {'state': 'restored'},
        'merge_pending': False,
        'token': '',
        'lease_until': 0.0,
        'owner_id': 'heavy',
        'owner_key': owner_key('heavy'),
        'priority': priority,
    }


def _dead_job(priority=int(Priority.DEEP)):
    return {
        'segment_id': 'seg-dead',
        'state': 'dead',
        'merge_pending': True,
        'owner_id': 'heavy',
        'owner_key': owner_key('heavy'),
        'priority': priority,
    }


@pytest.mark.parametrize('priority', [0, 1, 2])
@pytest.mark.parametrize('hint', [0.0, 12.5])
def test_restore_static_seeds_every_priority(priority, hint):
    tx, rows, owner = _tx_with_owner(priority)
    job = _restorable_job(priority)
    Scheduler.restore_audio_in_transaction(tx, deepcopy(job), 100.0, frontier=hint)
    shard = tx.rows[('control', scheduler_control_key(owner))]
    assert shard[f'p{priority}_service'] == max(1.0, hint)
    assert shard[f'p{priority}_active'] is True


@pytest.mark.parametrize('priority', [0, 1, 2])
@pytest.mark.parametrize('hint', [0.0, 12.5])
def test_redrive_static_seeds_every_priority(priority, hint):
    tx, rows, owner = _tx_with_owner(priority)
    job = _dead_job(priority)
    assert Scheduler.redrive_in_transaction(tx, deepcopy(job), 100.0, frontier=hint) is True
    shard = tx.rows[('control', scheduler_control_key(owner))]
    assert shard[f'p{priority}_service'] == max(1.0, hint)
    assert shard[f'p{priority}_active'] is True


@pytest.mark.parametrize('pool', ['batch', 'live'])
@pytest.mark.parametrize('method', ['restore', 'redrive'])
def test_static_requeues_clamp_both_pool_windows(method, pool):
    tx, rows, owner = _tx_with_owner()
    job = _restorable_job() if method == 'restore' else _dead_job()
    if method == 'restore':
        Scheduler.restore_audio_in_transaction(tx, job, 100.0, frontier=3.0)
    else:
        Scheduler.redrive_in_transaction(tx, job, 100.0, frontier=3.0)
    shard = tx.rows[('control', scheduler_control_key(owner))]
    assert shard[f'p{int(Priority.DEEP)}_{pool}_available_at'] == 100.0


def test_restore_static_without_a_seed_uses_zero():
    tx, rows, owner = _tx_with_owner()
    Scheduler.restore_audio_in_transaction(tx, _restorable_job(), 100.0)
    assert tx.rows[('control', scheduler_control_key(owner))][f'p{int(Priority.DEEP)}_service'] == 1.0


def test_redrive_static_without_a_seed_uses_zero():
    tx, rows, owner = _tx_with_owner()
    Scheduler.redrive_in_transaction(tx, _dead_job(), 100.0)
    assert tx.rows[('control', scheduler_control_key(owner))][f'p{int(Priority.DEEP)}_service'] == 1.0


def test_redrive_static_refuses_non_dead_rows():
    tx, rows, owner = _tx_with_owner()
    job = _dead_job()
    job['state'] = 'ready'
    assert Scheduler.redrive_in_transaction(tx, job, 100.0, frontier=9.0) is False


def test_restore_static_refuses_unrestorable_rows():
    tx, rows, owner = _tx_with_owner()
    job = _restorable_job()
    job['artifact_disposition'] = {'state': 'missing'}
    with pytest.raises(ValueError):
        Scheduler.restore_audio_in_transaction(tx, job, 100.0, frontier=9.0)


# --------------------------------------------------------------------------
# 6. durable_status probe states
# --------------------------------------------------------------------------


def _intake_rows(status='processing', result=None):
    uid = 'synthetic-owner'
    owner = owner_key(uid)
    return {
        ('intakes', 'job-1'): {
            'owner_id': uid,
            'content_id': 'content-1',
            'segment_ids': ['seg-1'],
            'lane': 'backfill',
            'status': status,
            'result': result,
            'total_segments': 1,
            'total_files': 1,
        },
        ('content', f'{uid}/content-1'): {
            'dispatch_protocol': 'batch_v1',
            'job_id': 'job-1',
            'status': status,
            'result': result,
        },
        ('jobs', 'seg-1'): {
            'segment_id': 'seg-1',
            'state': 'dead',
            'merge_pending': True,
            'owner_id': uid,
            'owner_key': owner,
            'priority': int(Priority.DEEP),
            'enqueued_at': 40.0,
            'capture_at': 40.0,
            'next': '',
            'policy': {},
            'privacy_generation': None,
        },
    }


def test_durable_status_failed_status_reads_hints():

    store = GridStore()
    store.rows = _intake_rows(status='failed')
    durable_status(store, 'synthetic-owner', 'job-1')
    assert sorted(priority for priority, _ in store.hint_calls) == [0, 1, 2]


def test_durable_status_partial_status_reads_hints():

    store = GridStore()
    store.rows = _intake_rows(status='partial', result={'held_segments': 1, 'total_segments': 1})
    durable_status(store, 'synthetic-owner', 'job-1')
    assert store.hint_calls


def test_durable_status_invalid_completed_result_still_reads_hints(monkeypatch):
    from utils.batch_pipeline import intake as intake_module

    monkeypatch.setattr(intake_module, 'is_valid_completed_sync_content_result', lambda result: False)
    store = GridStore()
    store.rows = _intake_rows(status='completed', result={'bogus': True})
    durable_status(store, 'synthetic-owner', 'job-1')
    assert store.hint_calls


def test_durable_status_missing_intake_never_pays(monkeypatch):

    store = GridStore()
    durable_status(store, 'synthetic-owner', 'missing-job')
    assert store.hint_calls == []


def test_durable_status_redrive_seed_lands_on_the_shard():

    store = GridStore(hints={int(Priority.DEEP): 21.0})
    store.rows = _intake_rows()
    durable_status(store, 'synthetic-owner', 'job-1')
    shard = store.rows.get(('control', scheduler_control_key(owner_key('synthetic-owner'))))
    assert shard[f'p{int(Priority.DEEP)}_service'] == 21.0
    assert store.rows[('jobs', 'seg-1')]['state'] == 'ready'
