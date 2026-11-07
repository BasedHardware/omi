"""Rejoin seeding semantics: ``control.activate`` consumes the advisory hint.

``activate`` used to read the frontier with a transactional query; it now
seeds ``max(own, frontier)`` from a value the entry point read outside the
transaction. Pinned here:

1. Seed semantics: the rejoining shard's service becomes ``max(own,
   frontier)`` for every priority, across own/frontier combinations including
   equal, negative and fractional values.
2. An already-active shard is never re-seeded — its accrued credit wins.
3. Activation still marks the shard active and widens both pools' availability
   windows to ``min(existing, now)``.
4. The activation reads nothing from the transaction: a rejoin body takes no
   transactional read at all, so no concurrent commit to the argmax shard can
   abort it.
5. ``migrate_legacy`` threads the per-priority seed map through every shard it
   activates, degrading to ``0.0`` for absent priorities and ``None`` maps.

Failure-Class: FC-rejoin-frontier-seed-read-joins-the-argmax-shard-abort-set
"""

from copy import deepcopy

from utils.batch_pipeline.control import activate, field, migrate_legacy, read_control


class SnapshotTx:
    """Rows-backed transaction view that records every read it is asked to do."""

    def __init__(self, rows=None):
        self.rows = dict(rows or {})
        self.reads = []
        self.puts = []

    def get(self, table, key):
        self.reads.append((table, key))
        return deepcopy(self.rows.get((table, key), {}))

    def put(self, table, key, value):
        self.puts.append((table, key))
        self.rows[(table, key)] = deepcopy(value)

    def patch(self, table, key, fields):
        row = self.rows.setdefault((table, key), {})
        row.update(deepcopy(fields))

    def check_privacy(self, uid, conversation_ids=(), expected_generation=None):
        return expected_generation or 0


def control_for(tx, key='shard-a'):
    return read_control(tx, key)


# --------------------------------------------------------------------------
# 1. Seed semantics on a rejoining (inactive) shard
# --------------------------------------------------------------------------


def test_rejoin_seeds_from_the_frontier_when_own_credit_is_zero():
    tx = SnapshotTx()
    control = control_for(tx, 'shard-a')
    activate(tx, control, 1, 100.0, 7.5)
    assert control[field(1, 'service')] == 7.5


def test_rejoin_keeps_own_credit_when_it_exceeds_the_frontier():
    tx = SnapshotTx()
    control = control_for(tx, 'shard-a')
    control[field(1, 'service')] = 12.0
    activate(tx, control, 1, 100.0, 7.5)
    assert control[field(1, 'service')] == 12.0


def test_rejoin_seed_equal_to_own_credit_stays_put():
    tx = SnapshotTx()
    control = control_for(tx, 'shard-a')
    control[field(1, 'service')] = 5.0
    activate(tx, control, 1, 100.0, 5.0)
    assert control[field(1, 'service')] == 5.0


def test_rejoin_seed_below_own_credit_never_lowers_service():
    tx = SnapshotTx()
    control = control_for(tx, 'shard-a')
    control[field(1, 'service')] = 9.0
    activate(tx, control, 1, 100.0, 1.0)
    assert control[field(1, 'service')] == 9.0


def test_rejoin_seed_zero_on_a_fresh_shard_is_the_empty_collection_seed():
    tx = SnapshotTx()
    control = control_for(tx, 'shard-a')
    activate(tx, control, 1, 100.0, 0.0)
    assert control[field(1, 'service')] == 0.0


def test_rejoin_seed_zero_does_not_reset_existing_credit():
    tx = SnapshotTx()
    control = control_for(tx, 'shard-a')
    control[field(1, 'service')] = 4.0
    activate(tx, control, 1, 100.0, 0.0)
    assert control[field(1, 'service')] == 4.0


def test_rejoin_seed_negative_frontier_never_lowers_own_credit():
    tx = SnapshotTx()
    control = control_for(tx, 'shard-a')
    control[field(1, 'service')] = 2.0
    activate(tx, control, 1, 100.0, -3.0)
    assert control[field(1, 'service')] == 2.0


def test_rejoin_seed_negative_frontier_on_fresh_shard_clamps_at_own_default():
    # A fresh shard's own default is 0.0, so a negative frontier can never
    # seed negative credit — max(own, frontier) keeps the floor.
    tx = SnapshotTx()
    control = control_for(tx, 'shard-a')
    activate(tx, control, 1, 100.0, -3.0)
    assert control[field(1, 'service')] == 0.0


def test_rejoin_seed_fractional_frontier_is_kept_exactly():
    tx = SnapshotTx()
    control = control_for(tx, 'shard-a')
    activate(tx, control, 1, 100.0, 0.125)
    assert control[field(1, 'service')] == 0.125


def test_rejoin_seed_huge_frontier_is_kept_exactly():
    tx = SnapshotTx()
    control = control_for(tx, 'shard-a')
    activate(tx, control, 1, 100.0, 1e12)
    assert control[field(1, 'service')] == 1e12


def test_rejoin_seed_priority_0_field():
    tx = SnapshotTx()
    control = control_for(tx, 'shard-a')
    activate(tx, control, 0, 100.0, 3.25)
    assert control[field(0, 'service')] == 3.25


def test_rejoin_seed_priority_2_field():
    tx = SnapshotTx()
    control = control_for(tx, 'shard-a')
    activate(tx, control, 2, 100.0, 3.25)
    assert control[field(2, 'service')] == 3.25


def test_rejoin_seed_only_touches_the_activated_priority():
    tx = SnapshotTx()
    control = control_for(tx, 'shard-a')
    control[field(0, 'service')] = 50.0
    control[field(2, 'service')] = 60.0
    activate(tx, control, 1, 100.0, 7.0)
    assert control[field(0, 'service')] == 50.0
    assert control[field(2, 'service')] == 60.0
    assert control[field(1, 'service')] == 7.0


def test_rejoin_seed_survives_a_deepcopy_of_the_control_view():
    tx = SnapshotTx()
    control = control_for(tx, 'shard-a')
    activate(tx, control, 1, 100.0, 6.5)
    copied = deepcopy(control)
    assert copied[field(1, 'service')] == 6.5


def test_rejoin_default_seed_is_the_empty_collection_zero():
    tx = SnapshotTx()
    control = control_for(tx, 'shard-a')
    activate(tx, control, 1, 100.0)
    assert control[field(1, 'service')] == 0.0


def test_rejoin_seed_ignores_retired_retired_service_fields():
    # Only the activated priority's service field participates; retired names
    # on the document are never consulted.
    tx = SnapshotTx()
    control = control_for(tx, 'shard-a')
    control['legacy_service'] = 99.0
    activate(tx, control, 1, 100.0, 2.0)
    assert control[field(1, 'service')] == 2.0


def test_rejoin_seed_is_idempotent_for_the_same_hint():
    tx = SnapshotTx()
    control = control_for(tx, 'shard-a')
    activate(tx, control, 1, 100.0, 5.0)
    first = control[field(1, 'service')]
    control[field(1, 'active')] = False
    activate(tx, control, 1, 100.0, 5.0)
    assert control[field(1, 'service')] == first


def test_rejoin_seed_second_activation_with_a_grown_frontier_takes_the_max():
    tx = SnapshotTx()
    control = control_for(tx, 'shard-a')
    activate(tx, control, 1, 100.0, 5.0)
    control[field(1, 'active')] = False
    activate(tx, control, 1, 100.0, 8.0)
    assert control[field(1, 'service')] == 8.0


def test_rejoin_seed_second_activation_with_a_shrunk_frontier_keeps_credit():
    tx = SnapshotTx()
    control = control_for(tx, 'shard-a')
    activate(tx, control, 1, 100.0, 8.0)
    control[field(1, 'active')] = False
    activate(tx, control, 1, 100.0, 3.0)
    assert control[field(1, 'service')] == 8.0


def test_rejoin_seed_on_a_shard_whose_document_was_wiped():
    # The reset-gaming guard: a recreated shard document (service lost) still
    # rejoins at the fleet frontier, never at ancient zero credit.
    tx = SnapshotTx({'shard': {'p1_service': 0.0}})
    control = control_for(tx, 'shard')
    activate(tx, control, 1, 100.0, 42.0)
    assert control[field(1, 'service')] == 42.0


# --------------------------------------------------------------------------
# 2. Active shards are never re-seeded
# --------------------------------------------------------------------------


def _active_control(tx, key='shard-a', priority=1, service=10.0):
    control = control_for(tx, key)
    control[field(priority, 'service')] = service
    control[field(priority, 'active')] = True
    return control


def test_active_shard_keeps_credit_when_frontier_is_higher():
    tx = SnapshotTx()
    control = _active_control(tx, service=10.0)
    activate(tx, control, 1, 100.0, 99.0)
    assert control[field(1, 'service')] == 10.0


def test_active_shard_keeps_credit_when_frontier_is_lower():
    tx = SnapshotTx()
    control = _active_control(tx, service=10.0)
    activate(tx, control, 1, 100.0, 1.0)
    assert control[field(1, 'service')] == 10.0


def test_active_shard_keeps_credit_when_frontier_is_zero():
    tx = SnapshotTx()
    control = _active_control(tx, service=10.0)
    activate(tx, control, 1, 100.0, 0.0)
    assert control[field(1, 'service')] == 10.0


def test_active_shard_keeps_negative_credit():
    tx = SnapshotTx()
    control = _active_control(tx, service=-1.5)
    activate(tx, control, 1, 100.0, 5.0)
    assert control[field(1, 'service')] == -1.5


def test_activation_marks_an_inactive_priority_active():
    tx = SnapshotTx()
    control = control_for(tx, 'shard-a')
    activate(tx, control, 1, 100.0, 3.0)
    assert control[field(1, 'active')] is True


def test_activation_keeps_an_active_priority_active():
    tx = SnapshotTx()
    control = _active_control(tx)
    activate(tx, control, 1, 100.0, 3.0)
    assert control[field(1, 'active')] is True


def test_activation_only_marks_the_one_priority_active():
    tx = SnapshotTx()
    control = control_for(tx, 'shard-a')
    activate(tx, control, 1, 100.0, 3.0)
    assert control[field(0, 'active')] is False
    assert control[field(2, 'active')] is False


def test_reactivation_after_drain_reseeds():
    # The production wave shape: a shard drains, the sweep deactivates the
    # priority, the next append rejoins — seeded from the frontier again.
    tx = SnapshotTx()
    control = control_for(tx, 'shard-a')
    control[field(1, 'service')] = 20.0
    control[field(1, 'active')] = False
    activate(tx, control, 1, 100.0, 25.0)
    assert control[field(1, 'service')] == 25.0
    assert control[field(1, 'active')] is True


# --------------------------------------------------------------------------
# 3. Availability windows
# --------------------------------------------------------------------------


def test_activation_opens_the_batch_window_on_a_fresh_shard():
    tx = SnapshotTx()
    control = control_for(tx, 'shard-a')
    control[field(1, 'batch_available_at')] = 200.0
    activate(tx, control, 1, 100.0, 1.0)
    assert control[field(1, 'batch_available_at')] == 100.0


def test_activation_opens_the_live_window_on_a_fresh_shard():
    tx = SnapshotTx()
    control = control_for(tx, 'shard-a')
    control[field(1, 'live_available_at')] = 200.0
    activate(tx, control, 1, 100.0, 1.0)
    assert control[field(1, 'live_available_at')] == 100.0


def test_activation_never_pushes_a_window_into_the_future():
    tx = SnapshotTx()
    control = control_for(tx, 'shard-a')
    control[field(1, 'batch_available_at')] = 50.0
    activate(tx, control, 1, 100.0, 1.0)
    assert control[field(1, 'batch_available_at')] == 50.0


def test_activation_widens_both_pools_at_once():
    tx = SnapshotTx()
    control = control_for(tx, 'shard-a')
    control[field(1, 'batch_available_at')] = 300.0
    control[field(1, 'live_available_at')] = 400.0
    activate(tx, control, 1, 100.0, 1.0)
    assert control[field(1, 'batch_available_at')] == 100.0
    assert control[field(1, 'live_available_at')] == 100.0


def test_activation_windows_are_per_priority():
    tx = SnapshotTx()
    control = control_for(tx, 'shard-a')
    control[field(0, 'batch_available_at')] = 300.0
    activate(tx, control, 1, 100.0, 1.0)
    assert control[field(0, 'batch_available_at')] == 300.0


def test_activation_window_still_applies_to_active_shards():
    tx = SnapshotTx()
    control = _active_control(tx)
    control[field(1, 'batch_available_at')] = 500.0
    activate(tx, control, 1, 100.0, 1.0)
    assert control[field(1, 'batch_available_at')] == 100.0


# --------------------------------------------------------------------------
# 4. Purity: an activation takes no transactional read
# --------------------------------------------------------------------------


class ExplodingTx:
    """Any transactional read or frontier query inside a rejoin body fails."""

    def __init__(self):
        self.reads = 0

    def get(self, table, key):
        self.reads += 1
        return {}

    def put(self, table, key, value):
        raise AssertionError('activate must not write')

    def service_frontier(self, priority):
        raise AssertionError('the transactional frontier read is retired')

    def check_privacy(self, uid, conversation_ids=(), expected_generation=None):
        raise AssertionError('activate must not read privacy')


def test_activate_takes_no_transactional_read():
    tx = ExplodingTx()
    control = read_control(tx, 'shard-a')
    tx.reads = 0
    activate(tx, control, 1, 100.0, 5.0)
    assert tx.reads == 0


def test_activate_never_queries_the_retired_transactional_frontier():
    tx = ExplodingTx()
    control = read_control(tx, 'shard-a')
    activate(tx, control, 1, 100.0, 5.0)
    assert True  # reaching here proves service_frontier was never touched


def test_activate_with_a_high_seed_takes_no_transactional_read():
    tx = ExplodingTx()
    control = read_control(tx, 'shard-a')
    tx.reads = 0
    activate(tx, control, 1, 100.0, 99999.0)
    assert tx.reads == 0


def test_activate_of_an_active_shard_takes_no_transactional_read():
    tx = ExplodingTx()
    control = read_control(tx, 'shard-a')
    control[field(1, 'active')] = True
    tx.reads = 0
    activate(tx, control, 1, 100.0, 99999.0)
    assert tx.reads == 0


def test_rejoin_body_of_snapshot_tx_records_no_reads_for_activation():
    tx = SnapshotTx()
    control = control_for(tx, 'shard-a')
    tx.reads = []
    activate(tx, control, 1, 100.0, 5.0)
    assert tx.reads == []


# --------------------------------------------------------------------------
# 5. read_control defaults
# --------------------------------------------------------------------------


def test_read_control_defaults_rings_for_every_priority():
    tx = SnapshotTx()
    control = control_for(tx, 'shard-a')
    assert control['rings'] == {'0': [], '1': [], '2': []}


def test_read_control_preserves_existing_rings():
    tx = SnapshotTx({('control', 'shard-a'): {'rings': {'1': ['q1']}}})
    control = control_for(tx, 'shard-a')
    assert control['rings'] == {'1': ['q1']}


def test_read_control_defaults_service_to_zero():
    tx = SnapshotTx()
    control = control_for(tx, 'shard-a')
    assert control[field(1, 'service')] == 0.0


def test_read_control_defaults_active_to_false():
    tx = SnapshotTx()
    control = control_for(tx, 'shard-a')
    assert control[field(1, 'active')] is False


def test_read_control_defaults_both_pool_windows():
    tx = SnapshotTx()
    control = control_for(tx, 'shard-a')
    assert control[field(1, 'batch_available_at')] == 0.0
    assert control[field(1, 'live_available_at')] == 0.0


def test_read_control_defaults_for_all_three_priorities():
    tx = SnapshotTx()
    control = control_for(tx, 'shard-a')
    for priority in (0, 1, 2):
        assert control[field(priority, 'service')] == 0.0
        assert control[field(priority, 'active')] is False


def test_read_control_keeps_stored_service_values():
    tx = SnapshotTx({('control', 'shard-a'): {'p1_service': 12.5}})
    control = control_for(tx, 'shard-a')
    assert control[field(1, 'service')] == 12.5


def test_read_control_keeps_stored_active_values():
    tx = SnapshotTx({('control', 'shard-a'): {'p1_active': True}})
    control = control_for(tx, 'shard-a')
    assert control[field(1, 'active')] is True


def test_read_control_does_not_write():
    tx = SnapshotTx()
    control_for(tx, 'shard-a')
    assert tx.puts == []


def test_read_control_reads_exactly_once():
    tx = SnapshotTx()
    control_for(tx, 'shard-a')
    assert tx.reads == [('control', 'shard-a')]


def test_read_control_over_a_missing_document_is_the_default_view():
    tx = SnapshotTx()
    control = control_for(tx, 'missing-shard')
    assert control['rings'] == {'0': [], '1': [], '2': []}
    assert control[field(1, 'service')] == 0.0


# --------------------------------------------------------------------------
# 6. migrate_legacy threads the seed map through every activation
# --------------------------------------------------------------------------
def _legacy_rows(rings, queues):
    rows = {('control', 'scheduler'): {'rings': rings}}
    for key, head in queues.items():
        rows[('queues', key)] = {'head': head}
    return rows


def shard_of(owner):
    from config.batch_pipeline import scheduler_control_key

    return scheduler_control_key(owner)


OWNER_A = 'cafe0001'
OWNER_B = 'deadbeef'
OWNER_C = 'feedface'
OWNER_D = 'ba5eba11'


def test_migrate_activates_a_transferred_shard_with_its_seed():
    tx = SnapshotTx(_legacy_rows({'1': [f'1_{OWNER_A}']}, {f'1_{OWNER_A}': 'seg-1'}))
    migrate_legacy(tx, 100.0, {1: 9.0})
    shard = tx.rows[('control', shard_of(OWNER_A))]
    assert shard[field(1, 'service')] == 9.0


def test_migrate_seed_defaults_to_zero_for_absent_priorities():
    tx = SnapshotTx(_legacy_rows({'1': [f'1_{OWNER_A}']}, {f'1_{OWNER_A}': 'seg-1'}))
    migrate_legacy(tx, 100.0, {0: 5.0, 2: 7.0})
    shard = tx.rows[('control', shard_of(OWNER_A))]
    assert shard[field(1, 'service')] == 0.0


def test_migrate_with_no_seed_map_degrades_to_zero():
    tx = SnapshotTx(_legacy_rows({'1': [f'1_{OWNER_A}']}, {f'1_{OWNER_A}': 'seg-1'}))
    migrate_legacy(tx, 100.0, None)
    shard = tx.rows[('control', shard_of(OWNER_A))]
    assert shard[field(1, 'service')] == 0.0


def test_migrate_transfers_the_queue_into_the_shard_ring():
    tx = SnapshotTx(_legacy_rows({'1': [f'1_{OWNER_A}']}, {f'1_{OWNER_A}': 'seg-1'}))
    migrate_legacy(tx, 100.0, {1: 9.0})
    assert tx.rows[('control', shard_of(OWNER_A))]['rings']['1'] == [f'1_{OWNER_A}']


def test_migrate_marks_the_shard_active():
    tx = SnapshotTx(_legacy_rows({'1': [f'1_{OWNER_A}']}, {f'1_{OWNER_A}': 'seg-1'}))
    migrate_legacy(tx, 100.0, {1: 9.0})
    assert tx.rows[('control', shard_of(OWNER_A))][field(1, 'active')] is True


def test_migrate_opens_the_windows_at_now():
    rows = _legacy_rows({'1': [f'1_{OWNER_A}']}, {f'1_{OWNER_A}': 'seg-1'})
    shard_key = ('control', shard_of(OWNER_A))
    rows[shard_key] = {field(1, 'batch_available_at'): 200.0, field(1, 'live_available_at'): 300.0}
    tx = SnapshotTx(rows)
    migrate_legacy(tx, 100.0, {1: 9.0})
    shard = tx.rows[shard_key]
    assert shard[field(1, 'batch_available_at')] == 100.0
    assert shard[field(1, 'live_available_at')] == 100.0


def test_migrate_skips_headless_queues_but_counts_them():
    owners = [OWNER_A, OWNER_B]
    tx = SnapshotTx(
        _legacy_rows(
            {'1': [f'1_{owner}' for owner in owners]},
            {f'1_{OWNER_A}': 'seg-1'},  # OWNER_B's queue has no head
        )
    )
    migrate_legacy(tx, 100.0, {1: 9.0})
    assert ('control', shard_of(OWNER_B)) not in tx.rows
    assert tx.rows[('control', shard_of(OWNER_A))][field(1, 'service')] == 9.0
    assert ('control', 'scheduler') in tx.puts


def test_migrate_transfers_every_priority_with_its_own_seed():
    rows = _legacy_rows(
        {'0': [f'0_{OWNER_A}'], '1': [f'1_{OWNER_B}'], '2': [f'2_{OWNER_C}']},
        {f'0_{OWNER_A}': 'seg-a', f'1_{OWNER_B}': 'seg-b', f'2_{OWNER_C}': 'seg-c'},
    )
    tx = SnapshotTx(rows)
    migrate_legacy(tx, 100.0, {0: 1.0, 1: 2.0, 2: 3.0})
    assert tx.rows[('control', shard_of(OWNER_A))][field(0, 'service')] == 1.0
    assert tx.rows[('control', shard_of(OWNER_B))][field(1, 'service')] == 2.0
    assert tx.rows[('control', shard_of(OWNER_C))][field(2, 'service')] == 3.0


def test_migrate_never_exceeds_the_bounded_walk():
    owners = [f'{index:08x}' for index in range(150)]
    rings = {'1': [f'1_{owner}' for owner in owners]}
    queues = {f'1_{owner}': f'seg-{owner}' for owner in owners}
    tx = SnapshotTx(_legacy_rows(rings, queues))
    migrate_legacy(tx, 100.0, {1: 4.0})
    transfers = [(table, key) for (table, key) in tx.puts if table == 'control' and key != 'scheduler']
    assert len(transfers) == 100


def test_migrate_persists_the_drained_legacy_document():
    tx = SnapshotTx(_legacy_rows({'1': [f'1_{OWNER_A}']}, {f'1_{OWNER_A}': 'seg-1'}))
    migrate_legacy(tx, 100.0, {1: 9.0})
    assert tx.rows[('control', 'scheduler')]['rings']['1'] == []


def test_migrate_without_moves_writes_nothing():
    tx = SnapshotTx(_legacy_rows({}, {}))
    migrate_legacy(tx, 100.0, {1: 9.0})
    assert tx.puts == []


def test_migrate_without_a_legacy_document_writes_nothing():
    tx = SnapshotTx()
    migrate_legacy(tx, 100.0, {1: 9.0})
    assert tx.puts == []


def test_migrate_uses_int_seeds_for_string_ring_priorities():
    tx = SnapshotTx(_legacy_rows({'2': [f'2_{OWNER_D}']}, {f'2_{OWNER_D}': 'seg-d'}))
    migrate_legacy(tx, 100.0, {2: 6.0})
    assert tx.rows[('control', shard_of(OWNER_D))][field(2, 'service')] == 6.0


def test_migrate_seed_only_seeds_when_the_shard_was_inactive():
    rows = _legacy_rows({'1': [f'1_{OWNER_A}']}, {f'1_{OWNER_A}': 'seg-1'})
    rows[('control', shard_of(OWNER_A))] = {field(1, 'active'): True, field(1, 'service'): 15.0}
    tx = SnapshotTx(rows)
    migrate_legacy(tx, 100.0, {1: 9.0})
    assert tx.rows[('control', shard_of(OWNER_A))][field(1, 'service')] == 15.0
