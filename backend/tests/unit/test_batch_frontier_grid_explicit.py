"""Explicit grids for the rejoin seed: every boundary, named and pinned.

Companion to the parametrized suites. Each test here is one named point of a
matrix: a priority, a credit shape, a window state or an entry-point/hint-mode
pair, asserted on the committed document or returned value — so a regression
names the exact broken cell.

Failure-Class: FC-rejoin-frontier-seed-read-joins-the-argmax-shard-abort-set
"""

import inspect
from copy import deepcopy
from pathlib import Path

import pytest
from config.batch_pipeline import scheduler_control_key
from tests.support.firestore_batch_pipeline_drivers import entries as driver_entries
from tests.support.firestore_query_driver_registry import BODY_DIGEST
from tests.unit.test_batch_frontier_hint_read import ControlClient, EMULATOR_HOST
from tests.unit.test_batch_pipeline_scheduler import MemoryStore, MemoryTransaction, item
from tests.unit.test_batch_rejoin_frontier_seed import SnapshotTx
from utils.batch_pipeline.contracts import Priority
from utils.batch_pipeline.scheduler import Scheduler, owner_key, rejoin_frontiers
from utils.batch_pipeline.intake import durable_status
from utils.batch_pipeline.control import activate, read_control

BACKEND = Path(__file__).resolve().parents[2]
PRIORITY = int(Priority.DEEP)
NOW = 100.0


@pytest.fixture(autouse=True)
def _emulator_env(monkeypatch):
    monkeypatch.setenv('FIRESTORE_EMULATOR_HOST', EMULATOR_HOST)
    monkeypatch.setenv('BATCH_PIPELINE_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_UID_ALLOWLIST', 'synthetic-owner')
    monkeypatch.setenv('BATCH_PIPELINE_PERCENT', '0')


def hint_over(rows, priority, namespace='batch_pipeline_test_unit'):
    client = ControlClient([doc for _, doc in rows])
    from database import batch_pipeline_store as storage

    return storage.FirestoreStore(namespace, firestore_client=client).service_frontier_hint(priority)


def memory_hint(rows, priority):
    store = MemoryStore()
    for key, doc in rows:
        store.rows[('control', key)] = dict(doc)
    return store.service_frontier_hint(priority)


def shard_of(owner):
    return scheduler_control_key(owner)


def full_doc(priority=None, service=None, active=None):
    doc = {'rings': {'0': [], '1': [], '2': []}}
    for value in (0, 1, 2):
        doc[f'p{value}_service'] = 0.0
        doc[f'p{value}_active'] = False
        doc[f'p{value}_batch_available_at'] = 0.0
        doc[f'p{value}_live_available_at'] = 0.0
    if priority is not None:
        doc[f'p{priority}_service'] = service if service is not None else 0.0
        if active is not None:
            doc[f'p{priority}_active'] = active
    return doc


# --------------------------------------------------------------------------
# S1. Hint value grid on the Firestore surface (priority x credit shape)
# --------------------------------------------------------------------------


def _rows(*values, field='p1_service'):
    return [(f'shard-{index}', {field: value}) for index, value in enumerate(values)]


def test_grid_p0_empty_collection_is_zero():
    assert hint_over([], 0) == 0.0


def test_grid_p1_empty_collection_is_zero():
    assert hint_over([], 1) == 0.0


def test_grid_p2_empty_collection_is_zero():
    assert hint_over([], 2) == 0.0


def test_grid_p0_single_credit():
    assert hint_over(_rows(3.0, field='p0_service'), 0) == 3.0


def test_grid_p1_single_credit():
    assert hint_over(_rows(3.0), 1) == 3.0


def test_grid_p2_single_credit():
    assert hint_over(_rows(3.0, field='p2_service'), 2) == 3.0


def test_grid_p0_max_of_two_left_larger():
    assert hint_over(_rows(8.0, 2.0, field='p0_service'), 0) == 8.0


def test_grid_p1_max_of_two_left_larger():
    assert hint_over(_rows(8.0, 2.0), 1) == 8.0


def test_grid_p2_max_of_two_left_larger():
    assert hint_over(_rows(8.0, 2.0, field='p2_service'), 2) == 8.0


def test_grid_p0_max_of_two_right_larger():
    assert hint_over(_rows(2.0, 8.0, field='p0_service'), 0) == 8.0


def test_grid_p1_max_of_two_right_larger():
    assert hint_over(_rows(2.0, 8.0), 1) == 8.0


def test_grid_p2_max_of_two_right_larger():
    assert hint_over(_rows(2.0, 8.0, field='p2_service'), 2) == 8.0


def test_grid_p0_tie_returns_the_value():
    assert hint_over(_rows(5.5, 5.5, field='p0_service'), 0) == 5.5


def test_grid_p1_tie_returns_the_value():
    assert hint_over(_rows(5.5, 5.5), 1) == 5.5


def test_grid_p2_tie_returns_the_value():
    assert hint_over(_rows(5.5, 5.5, field='p2_service'), 2) == 5.5


def test_grid_p1_skips_a_document_missing_the_field():
    rows = [('shard-x', {'other': 1.0}), ('shard-y', {'p1_service': 4.0})]
    assert hint_over(rows, 1) == 4.0


def test_grid_p1_all_documents_missing_the_field_is_zero():
    rows = [('shard-x', {'other': 1.0}), ('shard-y', {'rings': {}})]
    assert hint_over(rows, 1) == 0.0


def test_grid_p1_negative_maximum_is_faithful():
    assert hint_over(_rows(-9.0, -2.0), 1) == -2.0


def test_grid_p1_single_negative_is_faithful():
    assert hint_over(_rows(-6.0), 1) == -6.0


def test_grid_p1_fractional_is_faithful():
    assert hint_over(_rows(0.0625), 1) == 0.0625


def test_grid_p1_huge_is_faithful():
    assert hint_over(_rows(9.5e13), 1) == 9.5e13


def test_grid_p1_zero_is_a_valid_frontier():
    assert hint_over(_rows(0.0, -1.0), 1) == 0.0


def test_grid_p1_int_typed_credit_is_a_number():
    assert hint_over(_rows(7), 1) == 7


def test_grid_p1_three_way_max():
    assert hint_over(_rows(4.0, 44.0, 5.0), 1) == 44.0


# --------------------------------------------------------------------------
# S2. Cross-surface parity on the same named cells
# --------------------------------------------------------------------------


def test_parity_cell_empty():
    rows = []
    assert hint_over(rows, 1) == memory_hint(rows, 1) == 0.0


def test_parity_cell_single():
    rows = _rows(3.25)
    assert hint_over(rows, 1) == memory_hint(rows, 1) == 3.25


def test_parity_cell_two_sided_max():
    rows = _rows(2.0, 8.0)
    assert hint_over(rows, 1) == memory_hint(rows, 1) == 8.0


def test_parity_cell_tie():
    rows = _rows(5.0, 5.0)
    assert hint_over(rows, 1) == memory_hint(rows, 1) == 5.0


def test_parity_cell_negative():
    rows = _rows(-4.0)
    assert hint_over(rows, 1) == memory_hint(rows, 1) == -4.0


def test_parity_cell_fractional():
    rows = _rows(0.5)
    assert hint_over(rows, 1) == memory_hint(rows, 1) == 0.5


def test_parity_cell_p0():
    rows = _rows(6.0, field='p0_service')
    assert hint_over(rows, 0) == memory_hint(rows, 0) == 6.0


def test_parity_cell_p2():
    rows = _rows(9.0, field='p2_service')
    assert hint_over(rows, 2) == memory_hint(rows, 2) == 9.0


def test_parity_cell_mixed_priorities():
    rows = [('shard-a', {'p0_service': 1.0, 'p1_service': 2.0, 'p2_service': 3.0})]
    assert hint_over(rows, 0) == memory_hint(rows, 0) == 1.0
    assert hint_over(rows, 1) == memory_hint(rows, 1) == 2.0
    assert hint_over(rows, 2) == memory_hint(rows, 2) == 3.0


def test_parity_cell_skips_missing_field():
    rows = [('shard-a', {'p0_service': 5.0})]
    assert hint_over(rows, 1) == memory_hint(rows, 1) == 0.0


def test_parity_cell_three_shards():
    rows = _rows(1.0, 30.0, 7.0)
    assert hint_over(rows, 1) == memory_hint(rows, 1) == 30.0


def test_parity_cell_shard_keyed_documents():
    rows = [(shard_of('a'), {'p1_service': 4.0}), (shard_of('b'), {'p1_service': 6.0})]
    assert hint_over(rows, 1) == memory_hint(rows, 1) == 6.0


# --------------------------------------------------------------------------
# S3. Seed max grid via activate (own x frontier x priority)
# --------------------------------------------------------------------------


def _activate_grid(own, frontier, priority):
    tx = SnapshotTx()
    control = read_control(tx, 'shard-a')
    if own is not None:
        control[f'p{priority}_service'] = own
    activate(tx, control, priority, NOW, frontier)
    return control[f'p{priority}_service'], control[f'p{priority}_active']


def test_seed_grid_p0_zero_over_zero():
    assert _activate_grid(0.0, 0.0, 0) == (0.0, True)


def test_seed_grid_p0_zero_over_hint():
    assert _activate_grid(0.0, 7.0, 0) == (7.0, True)


def test_seed_grid_p0_own_over_hint():
    assert _activate_grid(7.0, 0.0, 0) == (7.0, True)


def test_seed_grid_p1_zero_over_zero():
    assert _activate_grid(0.0, 0.0, 1) == (0.0, True)


def test_seed_grid_p1_zero_over_hint():
    assert _activate_grid(0.0, 7.0, 1) == (7.0, True)


def test_seed_grid_p1_own_over_hint():
    assert _activate_grid(7.0, 0.0, 1) == (7.0, True)


def test_seed_grid_p2_zero_over_zero():
    assert _activate_grid(0.0, 0.0, 2) == (0.0, True)


def test_seed_grid_p2_zero_over_hint():
    assert _activate_grid(0.0, 7.0, 2) == (7.0, True)


def test_seed_grid_p2_own_over_hint():
    assert _activate_grid(7.0, 0.0, 2) == (7.0, True)


def test_seed_grid_own_below_hint_takes_hint():
    assert _activate_grid(4.0, 9.0, 1)[0] == 9.0


def test_seed_grid_own_above_hint_keeps_own():
    assert _activate_grid(9.0, 4.0, 1)[0] == 9.0


def test_seed_grid_own_equal_hint_is_stable():
    assert _activate_grid(6.0, 6.0, 1)[0] == 6.0


def test_seed_grid_negative_hint_with_credit_keeps_credit():
    assert _activate_grid(2.0, -3.0, 1)[0] == 2.0


def test_seed_grid_negative_hint_without_credit_clamps_at_default():
    assert _activate_grid(None, -3.0, 1)[0] == 0.0


def test_seed_grid_fractional_pair_keeps_the_larger():
    assert _activate_grid(0.25, 0.75, 1)[0] == 0.75


def test_seed_grid_huge_pair_keeps_the_larger():
    assert _activate_grid(1e6, 1e9, 1)[0] == 1e9


def test_seed_grid_active_shard_ignores_a_higher_hint():
    tx = SnapshotTx()
    control = read_control(tx, 'shard-a')
    control[f'p1_service'] = 3.0
    control[f'p1_active'] = True
    activate(tx, control, 1, NOW, 99.0)
    assert control[f'p1_service'] == 3.0


def test_seed_grid_default_frontier_is_zero():
    tx = SnapshotTx()
    control = read_control(tx, 'shard-a')
    activate(tx, control, 1, NOW)
    assert control[f'p1_service'] == 0.0


def test_seed_grid_second_activation_with_equal_frontier_is_idempotent():
    tx = SnapshotTx()
    control = read_control(tx, 'shard-a')
    activate(tx, control, 1, NOW, 5.0)
    control[f'p1_active'] = False
    activate(tx, control, 1, NOW, 5.0)
    assert control[f'p1_service'] == 5.0


def test_seed_grid_activation_writes_nothing_through_tx():
    tx = SnapshotTx()
    control = read_control(tx, 'shard-a')
    activate(tx, control, 1, NOW, 5.0)
    assert tx.puts == []


# --------------------------------------------------------------------------
# S4. Availability window clamp grid
# --------------------------------------------------------------------------


@pytest.mark.parametrize('pool', ['batch', 'live'])
def test_window_grid_past_window_stays_past(pool):
    tx = SnapshotTx()
    control = read_control(tx, 'shard-a')
    control[f'p1_{pool}_available_at'] = 50.0
    activate(tx, control, 1, NOW, 1.0)
    assert control[f'p1_{pool}_available_at'] == 50.0


@pytest.mark.parametrize('pool', ['batch', 'live'])
def test_window_grid_future_window_clamps_to_now(pool):
    tx = SnapshotTx()
    control = read_control(tx, 'shard-a')
    control[f'p1_{pool}_available_at'] = 500.0
    activate(tx, control, 1, NOW, 1.0)
    assert control[f'p1_{pool}_available_at'] == NOW


@pytest.mark.parametrize('pool', ['batch', 'live'])
def test_window_grid_default_window_stays_zero(pool):
    tx = SnapshotTx()
    control = read_control(tx, 'shard-a')
    activate(tx, control, 1, NOW, 1.0)
    assert control[f'p1_{pool}_available_at'] == 0.0


@pytest.mark.parametrize('pool', ['batch', 'live'])
def test_window_grid_equal_window_stays_now(pool):
    tx = SnapshotTx()
    control = read_control(tx, 'shard-a')
    control[f'p1_{pool}_available_at'] = NOW
    activate(tx, control, 1, NOW, 1.0)
    assert control[f'p1_{pool}_available_at'] == NOW


# --------------------------------------------------------------------------
# S5. Entry-point x hint-mode grid
# --------------------------------------------------------------------------


class ModeStore(MemoryStore):
    def __init__(self, hints=None, failing=False):
        super().__init__()
        self._hints = dict(hints or {})
        self._failing = failing
        self.hint_calls = []

    def service_frontier_hint(self, priority):
        if priority not in (0, 1, 2):
            raise ValueError('bounded priority required')
        value = self._hints.get(priority, 0.0)
        self.hint_calls.append((priority, value))
        if self._failing:
            raise RuntimeError('synthetic hint outage')
        return value


def _enqueue_on(store, priority=PRIORITY):
    return Scheduler(store).enqueue(item('seg-mode', priority=Priority(priority)), NOW)


def _recover_on(store, priority=PRIORITY):
    store.rows[('jobs', 'seg-mode')] = {
        'segment_id': 'seg-mode',
        'state': 'retry',
        'available_at': 50.0,
        'attempt': 2,
        'owner_id': 'heavy',
        'owner_key': owner_key('heavy'),
        'priority': priority,
        'enqueued_at': 40.0,
        'capture_at': 40.0,
        'merge_pending': True,
        'next': '',
        'policy': {},
        'privacy_generation': None,
    }
    Scheduler(store, metrics=None).recover(NOW)
    return store.rows[('jobs', 'seg-mode')]['state'] == 'ready'


def _redrive_on(store, priority=PRIORITY):
    store.rows[('jobs', 'seg-mode')] = {
        'segment_id': 'seg-mode',
        'state': 'dead',
        'merge_pending': True,
        'owner_id': 'heavy',
        'owner_key': owner_key('heavy'),
        'priority': priority,
        'enqueued_at': 40.0,
        'capture_at': 40.0,
        'next': '',
        'policy': {},
        'privacy_generation': None,
    }
    return Scheduler(store).redrive_dead('seg-mode', NOW)


def _durable_on(store, priority=PRIORITY):

    uid = 'synthetic-owner'
    store.rows[('intakes', 'job-1')] = {
        'owner_id': uid,
        'content_id': 'content-1',
        'segment_ids': ['seg-mode'],
        'lane': 'backfill',
        'status': 'processing',
        'result': None,
        'total_segments': 1,
        'total_files': 1,
    }
    store.rows[('content', f'{uid}/content-1')] = {
        'dispatch_protocol': 'batch_v1',
        'job_id': 'job-1',
        'status': 'processing',
        'result': None,
    }
    store.rows[('jobs', 'seg-mode')] = {
        'segment_id': 'seg-mode',
        'state': 'dead',
        'merge_pending': True,
        'owner_id': uid,
        'owner_key': owner_key(uid),
        'priority': priority,
        'enqueued_at': 40.0,
        'capture_at': 40.0,
        'next': '',
        'policy': {},
        'privacy_generation': None,
    }
    durable_status(store, uid, 'job-1')
    return store.rows[('jobs', 'seg-mode')]['state'] == 'ready'


ENTRY_POINTS = {
    'enqueue': _enqueue_on,
    'recover': _recover_on,
    'redrive_dead': _redrive_on,
    'durable_status': _durable_on,
}


def test_grid_enqueue_hint_present():
    store = ModeStore(hints={PRIORITY: 5.0})
    assert ENTRY_POINTS['enqueue'](store) is True


def test_grid_enqueue_hint_absent():
    store = ModeStore()
    assert ENTRY_POINTS['enqueue'](store) is True


def test_grid_enqueue_hint_failing():
    store = ModeStore(failing=True)
    assert ENTRY_POINTS['enqueue'](store) is True


def test_grid_recover_hint_present():
    store = ModeStore(hints={PRIORITY: 5.0})
    assert ENTRY_POINTS['recover'](store) is True


def test_grid_recover_hint_absent():
    store = ModeStore()
    assert ENTRY_POINTS['recover'](store) is True


def test_grid_recover_hint_failing():
    store = ModeStore(failing=True)
    assert ENTRY_POINTS['recover'](store) is True


def test_grid_redrive_hint_present():
    store = ModeStore(hints={PRIORITY: 5.0})
    assert ENTRY_POINTS['redrive_dead'](store) is True


def test_grid_redrive_hint_absent():
    store = ModeStore()
    assert ENTRY_POINTS['redrive_dead'](store) is True


def test_grid_redrive_hint_failing():
    store = ModeStore(failing=True)
    assert ENTRY_POINTS['redrive_dead'](store) is True


def test_grid_durable_status_hint_present():
    store = ModeStore(hints={PRIORITY: 5.0})
    assert ENTRY_POINTS['durable_status'](store) is True


def test_grid_durable_status_hint_absent():
    store = ModeStore()
    assert ENTRY_POINTS['durable_status'](store) is True


def test_grid_durable_status_hint_failing():
    store = ModeStore(failing=True)
    assert ENTRY_POINTS['durable_status'](store) is True


# --------------------------------------------------------------------------
# S6. Static requeue seed-relation grid
# --------------------------------------------------------------------------


def _tx_with_credited_shard(priority, own):
    owner = owner_key('heavy')
    rows = {('control', shard_of(owner)): full_doc(priority, own)}
    return MemoryTransaction(deepcopy(rows)), owner


def _restorable(priority):
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


def _dead(priority):
    return {
        'segment_id': 'seg-dead',
        'state': 'dead',
        'merge_pending': True,
        'owner_id': 'heavy',
        'owner_key': owner_key('heavy'),
        'priority': priority,
    }


@pytest.mark.parametrize('priority', [0, 1, 2])
def test_static_restore_grid_hint_above_own(priority):
    tx, owner = _tx_with_credited_shard(priority, 2.0)
    Scheduler.restore_audio_in_transaction(tx, _restorable(priority), NOW, frontier=8.0)
    assert tx.rows[('control', shard_of(owner))][f'p{priority}_service'] == 8.0


@pytest.mark.parametrize('priority', [0, 1, 2])
def test_static_restore_grid_hint_below_own(priority):
    tx, owner = _tx_with_credited_shard(priority, 8.0)
    Scheduler.restore_audio_in_transaction(tx, _restorable(priority), NOW, frontier=2.0)
    assert tx.rows[('control', shard_of(owner))][f'p{priority}_service'] == 8.0


@pytest.mark.parametrize('priority', [0, 1, 2])
def test_static_restore_grid_hint_equal_own(priority):
    tx, owner = _tx_with_credited_shard(priority, 5.0)
    Scheduler.restore_audio_in_transaction(tx, _restorable(priority), NOW, frontier=5.0)
    assert tx.rows[('control', shard_of(owner))][f'p{priority}_service'] == 5.0


@pytest.mark.parametrize('priority', [0, 1, 2])
def test_static_redrive_grid_hint_above_own(priority):
    tx, owner = _tx_with_credited_shard(priority, 2.0)
    assert Scheduler.redrive_in_transaction(tx, _dead(priority), NOW, frontier=8.0) is True
    assert tx.rows[('control', shard_of(owner))][f'p{priority}_service'] == 8.0


@pytest.mark.parametrize('priority', [0, 1, 2])
def test_static_redrive_grid_hint_below_own(priority):
    tx, owner = _tx_with_credited_shard(priority, 8.0)
    assert Scheduler.redrive_in_transaction(tx, _dead(priority), NOW, frontier=2.0) is True
    assert tx.rows[('control', shard_of(owner))][f'p{priority}_service'] == 8.0


@pytest.mark.parametrize('priority', [0, 1, 2])
def test_static_redrive_grid_hint_equal_own(priority):
    tx, owner = _tx_with_credited_shard(priority, 5.0)
    assert Scheduler.redrive_in_transaction(tx, _dead(priority), NOW, frontier=5.0) is True
    assert tx.rows[('control', shard_of(owner))][f'p{priority}_service'] == 5.0


# --------------------------------------------------------------------------
# S7. Wiring source pins per production file
# --------------------------------------------------------------------------


def test_wiring_pin_store_module_renames_the_hint():
    text = (BACKEND / 'database' / 'batch_pipeline_store.py').read_text()
    assert 'def service_frontier_hint(' in text
    assert 'def service_frontier(' not in text


def test_wiring_pin_store_module_drops_the_transaction_binding():
    text = (BACKEND / 'database' / 'batch_pipeline_store.py').read_text()
    assert '.stream(transaction=transaction)' not in text.split('def service_frontier_hint')[1][:600]


def test_wiring_pin_control_module_has_no_transactional_frontier_call():
    text = (BACKEND / 'utils' / 'batch_pipeline' / 'control.py').read_text()
    assert 'tx.service_frontier(' not in text


def test_wiring_pin_scheduler_module_reads_frontiers_before_run():
    text = (BACKEND / 'utils' / 'batch_pipeline' / 'scheduler.py').read_text()
    assert 'def rejoin_frontiers(' in text
    assert text.count('rejoin_frontiers(') >= 4  # def + enqueue + recover + redrive_dead


def test_wiring_pin_intake_module_threads_frontiers_into_admit():
    text = (BACKEND / 'utils' / 'batch_pipeline' / 'intake.py').read_text()
    assert 'frontiers=rejoin_frontiers' in text or (
        'rejoin_frontiers(store, (item.priority for item in items))' in text and 'frontiers=frontiers' in text
    )


def test_wiring_pin_durable_status_probe_gates_the_seeds():
    text = (BACKEND / 'utils' / 'batch_pipeline' / 'intake.py').read_text()
    assert "store.probe('intakes', job_id)" in text


def test_wiring_pin_artifact_restore_reads_seeds_before_run():
    text = (BACKEND / 'database' / 'batch_pipeline_artifact_missing.py').read_text()
    assert 'seeds = rejoin_frontiers(' in text
    assert text.index('seeds = rejoin_frontiers(') < text.index("operation='batch_artifact_missing_restore'")


def test_wiring_pin_intake_db_admit_accepts_frontiers():
    text = (BACKEND / 'database' / 'batch_pipeline_intake.py').read_text()
    assert 'frontiers: dict | None = None' in text


def test_wiring_pin_jobstore_postgres_hint_is_store_level():
    text = (BACKEND / 'database' / 'jobstore' / 'postgres_store.py').read_text()
    assert 'def service_frontier_hint(' in text
    assert 'def service_frontier(' not in text


def test_wiring_pin_sim_stores_expose_the_hint():
    text = (BACKEND / 'testing' / 'pipeline_sim' / 'store.py').read_text()
    assert 'def service_frontier_hint(' in text
    assert 'def service_frontier(' not in text


# --------------------------------------------------------------------------
# S8. Registry pins
# --------------------------------------------------------------------------


def test_registry_pin_hint_present_in_digest_map():

    assert 'database.batch_pipeline_store.FirestoreStore.service_frontier_hint' in BODY_DIGEST


def test_registry_pin_retired_adapter_absent():

    assert 'database.batch_pipeline_store.FirestoreTransaction.service_frontier' not in BODY_DIGEST


def test_registry_pin_retired_module_absent():

    assert 'database.batch_pipeline_store.service_frontier:' not in str(BODY_DIGEST.keys())


def test_drivers_pin_hint_entry_present():

    assert any(entry.function == 'database.batch_pipeline_store.service_frontier_hint' for entry in driver_entries())


def test_drivers_pin_retired_tx_entry_absent():

    assert not any(
        entry.function == 'database.batch_pipeline_store.FirestoreTransaction.service_frontier'
        for entry in driver_entries()
    )


def test_drivers_pin_retired_module_entry_absent():

    assert not any(entry.function == 'database.batch_pipeline_store.service_frontier' for entry in driver_entries())


# --------------------------------------------------------------------------
# S9. Docs pins
# --------------------------------------------------------------------------


def test_docs_pin_design_section_names_the_hot_document_property():
    text = (BACKEND / 'docs' / 'batch-rejoin-frontier-hint.md').read_text()
    assert 'hottest' in text


def test_docs_pin_safety_section_names_both_stale_directions():
    text = (BACKEND / 'docs' / 'batch-rejoin-frontier-hint.md').read_text()
    assert 'too **low**' in text and 'too **high**' in text


def test_docs_pin_rollout_states_no_flag():
    text = (BACKEND / 'docs' / 'batch-rejoin-frontier-hint.md').read_text()
    assert 'No flag' in text


def test_docs_pin_migration_names_every_production_file():
    text = (BACKEND / 'docs' / 'batch-rejoin-frontier-hint.md').read_text()
    for name in (
        'batch_pipeline_store.py',
        'postgres_store.py',
        'control.py',
        'scheduler.py',
        'batch_pipeline_intake.py',
        'batch_pipeline_artifact_missing.py',
    ):
        assert name in text


# --------------------------------------------------------------------------
# S10. Margin cells: composed entry-point behaviors, named
# --------------------------------------------------------------------------


def test_margin_enqueue_after_a_drained_shard_seeds_from_hint():
    from tests.unit.test_batch_frontier_gate_matrix import EdgeStore

    store = EdgeStore(hints={PRIORITY: 5.0})
    store.rows[('control', shard_of(owner_key('beta')))] = full_doc(PRIORITY, 3.0, active=False)
    assert Scheduler(store).enqueue(item('seg-m', owner='beta', priority=Priority(PRIORITY)), NOW) is True
    shard = store.rows[('control', shard_of(owner_key('beta')))]
    assert shard[f'p{PRIORITY}_service'] == 5.0


def test_margin_enqueue_after_a_credited_drain_keeps_own():
    from tests.unit.test_batch_frontier_gate_matrix import EdgeStore

    store = EdgeStore(hints={PRIORITY: 1.0})
    store.rows[('control', shard_of(owner_key('beta')))] = full_doc(PRIORITY, 9.0, active=False)
    Scheduler(store).enqueue(item('seg-m', owner='beta', priority=Priority(PRIORITY)), NOW)
    shard = store.rows[('control', shard_of(owner_key('beta')))]
    assert shard[f'p{PRIORITY}_service'] == 9.0


def test_margin_recover_requeue_seeds_only_the_job_priority():
    from tests.unit.test_batch_frontier_gate_matrix import EdgeStore

    store = EdgeStore(hints={0: 1.0, 1: 2.0, 2: 3.0})
    store.rows[('jobs', 'seg-m')] = {
        'segment_id': 'seg-m',
        'state': 'retry',
        'available_at': 50.0,
        'attempt': 2,
        'owner_id': 'heavy',
        'owner_key': owner_key('heavy'),
        'priority': 1,
        'enqueued_at': 40.0,
        'capture_at': 40.0,
        'merge_pending': True,
        'next': '',
        'policy': {},
        'privacy_generation': None,
    }
    Scheduler(store, metrics=None).recover(NOW)
    shard = store.rows.get(('control', shard_of(owner_key('heavy'))))
    assert shard['p1_service'] == 2.0
    assert shard['p0_service'] == 0.0
    assert shard['p2_service'] == 0.0


def test_margin_redrive_dead_of_a_second_shard_uses_its_own_hint():
    from tests.unit.test_batch_frontier_gate_matrix import EdgeStore

    store = EdgeStore(hints={0: 10.0, 1: 20.0, 2: 30.0})
    store.rows[('jobs', 'seg-m')] = {
        'segment_id': 'seg-m',
        'state': 'dead',
        'merge_pending': True,
        'owner_id': 'heavy',
        'owner_key': owner_key('heavy'),
        'priority': 1,
        'enqueued_at': 40.0,
        'capture_at': 40.0,
        'next': '',
        'policy': {},
        'privacy_generation': None,
    }
    Scheduler(store).redrive_dead('seg-m', NOW)
    shard = store.rows[('control', shard_of(owner_key('heavy')))]
    assert shard['p1_service'] == 20.0


def test_margin_redrive_logs_degraded_and_still_requeues(caplog):
    import logging

    from tests.unit.test_batch_frontier_gate_matrix import EdgeStore

    class Dead(MemoryStore):
        def service_frontier_hint(self, priority):
            raise RuntimeError('outage')

        def probe(self, table, key):
            return {'priority': 1}

    store = Dead()
    store.rows[('jobs', 'seg-m')] = {
        'segment_id': 'seg-m',
        'state': 'dead',
        'merge_pending': True,
        'owner_id': 'heavy',
        'owner_key': owner_key('heavy'),
        'priority': 1,
        'enqueued_at': 40.0,
        'capture_at': 40.0,
        'next': '',
        'policy': {},
        'privacy_generation': None,
    }
    with caplog.at_level(logging.WARNING, logger='utils.batch_pipeline.scheduler'):
        assert Scheduler(store).redrive_dead('seg-m', NOW) is True
    assert any('batch_frontier_hint' in record.getMessage() for record in caplog.records)
    assert store.rows[('jobs', 'seg-m')]['state'] == 'ready'


def test_margin_enqueue_degraded_seed_is_visible_on_the_shard(caplog):
    import logging

    from tests.unit.test_batch_frontier_gate_matrix import EdgeStore

    class Dead(MemoryStore):
        def service_frontier_hint(self, priority):
            raise RuntimeError('outage')

    store = Dead()
    Scheduler(store).enqueue(item('seg-m'), NOW)
    shard = store.rows[('control', shard_of(owner_key('heavy')))]
    assert shard[f'p{PRIORITY}_service'] == 0.0
    assert any('batch_frontier_hint' in record.getMessage() for record in caplog.records)


def test_margin_hint_failure_never_consumes_the_transaction():
    from tests.unit.test_batch_frontier_gate_matrix import EdgeStore

    store = EdgeStore()
    runs = []
    original = MemoryStore.run

    def counting(self, body, *, operation=None):
        runs.append(operation)
        return original(self, body, operation=operation)

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(MemoryStore, 'run', counting)
        Scheduler(store).enqueue(item('seg-m'), NOW)
    assert len(runs) == 1
