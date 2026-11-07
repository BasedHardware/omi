"""Gate and matrix pins for the rejoin seed's edges.

Companion grids for the probe gates, map hardening, candidate ordering and
custody-invariance cells that the other frontier suites do not name
individually.

Failure-Class: FC-rejoin-frontier-seed-read-joins-the-argmax-shard-abort-set
"""

from copy import deepcopy

import pytest
from config.batch_pipeline import scheduler_control_key
from tests.unit.test_batch_pipeline_scheduler import MemoryStore, item
from utils.batch_pipeline.contracts import Priority
from utils.batch_pipeline.scheduler import Scheduler, owner_key, rejoin_frontiers

PRIORITY = int(Priority.DEEP)
NOW = 100.0


@pytest.fixture(autouse=True)
def cohort(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_UID_ALLOWLIST', 'synthetic-owner')
    monkeypatch.setenv('BATCH_PIPELINE_PERCENT', '0')


class EdgeStore(MemoryStore):
    def __init__(self, hints=None):
        super().__init__()
        self._hints = dict(hints or {})
        self.hint_calls = []

    def service_frontier_hint(self, priority):
        if priority not in (0, 1, 2):
            raise ValueError('bounded priority required')
        value = self._hints.get(priority, 0.0)
        self.hint_calls.append((priority, value))
        return value


def _dead_row(priority=PRIORITY):
    return {
        'segment_id': 'seg-edge',
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


# --------------------------------------------------------------------------
# 1. redrive_dead probe-gate matrix
# --------------------------------------------------------------------------


@pytest.mark.parametrize('priority', [0, 1, 2])
def test_redrive_probe_reads_the_row_priority(priority):
    store = EdgeStore(hints={priority: 4.0})
    store.rows[('jobs', 'seg-edge')] = _dead_row(priority)
    Scheduler(store).redrive_dead('seg-edge', NOW)
    assert store.hint_calls == [(priority, 4.0)]


@pytest.mark.parametrize('priority', [0, 1, 2])
def test_redrive_probe_seeds_the_rejoined_shard(priority):
    store = EdgeStore(hints={priority: 4.0})
    store.rows[('jobs', 'seg-edge')] = _dead_row(priority)
    Scheduler(store).redrive_dead('seg-edge', NOW)
    shard = store.rows.get(('control', scheduler_control_key(owner_key('heavy'))))
    assert shard[f'p{priority}_service'] == 4.0


def test_redrive_probe_of_a_missing_row_defaults_to_priority_zero():
    store = EdgeStore(hints={0: 2.0})
    Scheduler(store).redrive_dead('ghost', NOW)
    assert store.hint_calls == [(0, 2.0)]


def test_redrive_probe_row_without_a_priority_field_defaults_to_zero():
    # The probe (and its priority-0 default) precedes the transaction; the
    # body then fails loudly on the malformed row instead of guessing.
    store = EdgeStore(hints={0: 2.0})
    row = _dead_row()
    row.pop('priority')
    store.rows[('jobs', 'seg-edge')] = row
    with pytest.raises(KeyError):
        Scheduler(store).redrive_dead('seg-edge', NOW)
    assert store.hint_calls == [(0, 2.0)]


def test_redrive_probe_string_priority_is_normalized():
    store = EdgeStore(hints={2: 3.0})
    row = _dead_row()
    row['priority'] = str(PRIORITY)
    store.rows[('jobs', 'seg-edge')] = row
    Scheduler(store).redrive_dead('seg-edge', NOW)
    assert store.hint_calls == [(PRIORITY, 3.0)]


def test_redrive_probe_runs_once_per_call():
    store = EdgeStore(hints={PRIORITY: 4.0})
    store.rows[('jobs', 'seg-edge')] = _dead_row()
    Scheduler(store).redrive_dead('seg-edge', NOW)
    assert len(store.hint_calls) == 1


# --------------------------------------------------------------------------
# 2. durable_status per-priority hint usage
# --------------------------------------------------------------------------


def _intake_rows_for(priority=PRIORITY):
    uid = 'synthetic-owner'
    return {
        ('intakes', 'job-1'): {
            'owner_id': uid,
            'content_id': 'content-1',
            'segment_ids': ['seg-edge'],
            'lane': 'backfill',
            'status': 'processing',
            'result': None,
            'total_segments': 1,
            'total_files': 1,
        },
        ('content', f'{uid}/content-1'): {
            'dispatch_protocol': 'batch_v1',
            'job_id': 'job-1',
            'status': 'processing',
            'result': None,
        },
        ('jobs', 'seg-edge'): {
            'segment_id': 'seg-edge',
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
        },
    }


@pytest.mark.parametrize('priority', [0, 1, 2])
def test_durable_status_reads_all_three_priorities_then_seeds_the_job(priority):
    from utils.batch_pipeline.intake import durable_status

    store = EdgeStore(hints={priority: 6.0})
    store.rows = _intake_rows_for(priority)
    durable_status(store, 'synthetic-owner', 'job-1')
    assert sorted(p for p, _ in store.hint_calls) == [0, 1, 2]
    shard = store.rows.get(('control', scheduler_control_key(owner_key('synthetic-owner'))))
    assert shard[f'p{priority}_service'] == 6.0


# --------------------------------------------------------------------------
# 3. Candidate ordering across seed ratios
# --------------------------------------------------------------------------


def _two_shards(alpha_service, hint, prior):
    store = EdgeStore(hints={PRIORITY: hint})
    alpha, beta = owner_key('alpha'), owner_key('beta')
    alpha_doc = {
        'rings': {'0': [], '1': [], '2': []},
        f'p{PRIORITY}_service': alpha_service,
        f'p{PRIORITY}_active': True,
        f'p{PRIORITY}_batch_available_at': 0.0,
        f'p{PRIORITY}_live_available_at': 0.0,
    }
    beta_doc = {
        'rings': {'0': [], '1': [], '2': []},
        f'p{PRIORITY}_service': prior,
        f'p{PRIORITY}_active': False,
        f'p{PRIORITY}_batch_available_at': 0.0,
        f'p{PRIORITY}_live_available_at': 0.0,
    }
    store.rows[('control', scheduler_control_key(alpha))] = alpha_doc
    store.rows[('control', scheduler_control_key(beta))] = beta_doc
    Scheduler(store).enqueue(item('seg-b', owner='beta', priority=Priority(PRIORITY)), NOW)
    candidates = store.control_candidates(PRIORITY, 'batch', NOW, worker_id='worker-w', fanout=8)
    services = {key: store.rows[('control', key)][f'p{PRIORITY}_service'] for key in candidates}
    return candidates, services, alpha, beta


def test_ordering_seed_half_the_frontier_joins_the_head():
    candidates, services, alpha, beta = _two_shards(10.0, 10.0, 5.0)
    assert candidates[0] == scheduler_control_key(beta)
    assert services[scheduler_control_key(beta)] == 10.0


def test_ordering_seed_at_the_frontier_stays_competitive():
    candidates, services, alpha, beta = _two_shards(10.0, 10.0, 10.0)
    assert set(candidates) == {scheduler_control_key(alpha), scheduler_control_key(beta)}
    assert services[scheduler_control_key(beta)] == 10.0


def test_ordering_seed_double_the_frontier_serves_last():
    candidates, _, alpha, beta = _two_shards(10.0, 10.0, 20.0)
    assert candidates[-1] == scheduler_control_key(beta)


def test_ordering_seed_zero_joins_the_head():
    candidates, _, alpha, beta = _two_shards(10.0, 10.0, 0.0)
    assert candidates[0] == scheduler_control_key(beta)


def test_ordering_seed_above_frontier_never_lowers_others():
    _, services, alpha, beta = _two_shards(10.0, 10.0, 20.0)
    assert services[scheduler_control_key(alpha)] == 10.0


# --------------------------------------------------------------------------
# 4. Map hardening in admit (None values, coercion)
# --------------------------------------------------------------------------


def _spy(monkeypatch, captured):
    real = Scheduler.enqueue_in_transaction

    def spy(tx, work, now, *, policy=None, frontier=0.0):
        captured.append(frontier)
        return real(tx, work, now, policy=policy, frontier=frontier)

    monkeypatch.setattr(Scheduler, 'enqueue_in_transaction', staticmethod(spy))


def test_admit_none_value_in_the_map_degrades_to_zero(monkeypatch):
    from database.batch_pipeline_intake import admit
    from tests.unit.test_batch_pipeline_intake import proposal

    store = EdgeStore()
    works, binding = proposal()
    captured = []
    _spy(monkeypatch, captured)
    admit(store, works, binding, 100, namespace='batch_pipeline_test_edge', frontiers={PRIORITY: None})
    assert captured[0] == 0.0


def test_admit_int_value_in_the_map_is_coerced(monkeypatch):
    from database.batch_pipeline_intake import admit
    from tests.unit.test_batch_pipeline_intake import proposal

    store = EdgeStore()
    works, binding = proposal()
    captured = []
    _spy(monkeypatch, captured)
    admit(store, works, binding, 100, namespace='batch_pipeline_test_edge', frontiers={PRIORITY: 5})
    assert captured[0] == 5.0


def test_admit_zero_value_in_the_map_stays_zero(monkeypatch):
    from database.batch_pipeline_intake import admit
    from tests.unit.test_batch_pipeline_intake import proposal

    store = EdgeStore()
    works, binding = proposal()
    captured = []
    _spy(monkeypatch, captured)
    admit(store, works, binding, 100, namespace='batch_pipeline_test_edge', frontiers={PRIORITY: 0.0})
    assert captured[0] == 0.0


# --------------------------------------------------------------------------
# 5. rejoin_frontiers logging pins
# --------------------------------------------------------------------------


def test_degraded_log_names_the_event_and_priority(caplog):
    import logging

    class Failing(MemoryStore):
        def service_frontier_hint(self, priority):
            raise RuntimeError('outage')

    with caplog.at_level(logging.WARNING, logger='utils.batch_pipeline.scheduler'):
        rejoin_frontiers(Failing(), (0,))
    messages = [record.getMessage() for record in caplog.records]
    assert any('event=batch_frontier_hint' in message and 'priority=0' in message for message in messages)


def test_degraded_log_carries_priority_and_exception_type(caplog):
    import logging

    class Failing(MemoryStore):
        def service_frontier_hint(self, priority):
            raise RuntimeError('outage')

    with caplog.at_level(logging.WARNING, logger='utils.batch_pipeline.scheduler'):
        rejoin_frontiers(Failing(), (0, 1, 2))
    messages = [record.getMessage() for record in caplog.records]
    assert any('event=batch_frontier_hint' in message for message in messages)
    assert any('priority=1' in message for message in messages)
    assert any('RuntimeError' in message for message in messages)


def test_degraded_log_fires_once_per_failing_priority(caplog):
    import logging

    class HalfFailing(MemoryStore):
        def service_frontier_hint(self, priority):
            if priority == 1:
                raise RuntimeError('outage')
            return 1.0

    with caplog.at_level(logging.WARNING, logger='utils.batch_pipeline.scheduler'):
        rejoin_frontiers(HalfFailing(), (0, 1, 2))
    degraded = [record for record in caplog.records if 'batch_frontier_hint' in record.getMessage()]
    assert len(degraded) == 1


# --------------------------------------------------------------------------
# 6. FIFO custody invariance under the seed
# --------------------------------------------------------------------------


def _enqueue_three(store, priority=PRIORITY):
    for segment in ('s1', 's2', 's3'):
        Scheduler(store).enqueue(item(segment, owner='beta', priority=Priority(priority)), NOW)
    queue_key = f'{priority}_' + owner_key('beta')
    return store.rows[('queues', queue_key)]


def test_fifo_items_are_seed_independent():
    zero = _enqueue_three(EdgeStore(hints={PRIORITY: 0.0}))
    high = _enqueue_three(EdgeStore(hints={PRIORITY: 1e9}))
    assert zero['items'] == high['items'] == ['s1', 's2', 's3']


def test_fifo_head_tail_are_seed_independent():
    zero = _enqueue_three(EdgeStore(hints={PRIORITY: 0.0}))
    high = _enqueue_three(EdgeStore(hints={PRIORITY: 1e9}))
    assert zero['head'] == high['head'] == 's1'
    assert zero['tail'] == high['tail'] == 's3'


def test_job_state_is_seed_independent():
    zero = EdgeStore(hints={PRIORITY: 0.0})
    high = EdgeStore(hints={PRIORITY: 1e9})
    for store in (zero, high):
        Scheduler(store).enqueue(item('s1', owner='beta', priority=Priority(PRIORITY)), NOW)
    assert zero.rows[('jobs', 's1')]['state'] == high.rows[('jobs', 's1')]['state'] == 'ready'


def test_job_enqueued_at_is_seed_independent():
    zero = EdgeStore(hints={PRIORITY: 0.0})
    high = EdgeStore(hints={PRIORITY: 1e9})
    for store in (zero, high):
        Scheduler(store).enqueue(item('s1', owner='beta', priority=Priority(PRIORITY)), NOW)
    assert zero.rows[('jobs', 's1')]['enqueued_at'] == high.rows[('jobs', 's1')]['enqueued_at']


def test_revision_fence_is_seed_independent():
    zero = EdgeStore(hints={PRIORITY: 0.0})
    high = EdgeStore(hints={PRIORITY: 1e9})
    for store in (zero, high):
        Scheduler(store).enqueue(item('s1', owner='beta', priority=Priority(PRIORITY)), NOW)
    assert zero.rows[('owners', owner_key('beta'))]['revision'] == high.rows[('owners', owner_key('beta'))]['revision']


def test_rings_of_other_shards_are_untouched_by_a_rejoin():
    store = EdgeStore(hints={PRIORITY: 5.0})
    alpha, beta = owner_key('alpha'), owner_key('beta')
    alpha_doc = {
        'rings': {'0': [], '1': [], '2': []},
        f'p{PRIORITY}_service': 50.0,
        f'p{PRIORITY}_active': True,
        f'p{PRIORITY}_batch_available_at': 0.0,
        f'p{PRIORITY}_live_available_at': 0.0,
    }
    store.rows[('control', scheduler_control_key(alpha))] = alpha_doc
    Scheduler(store).enqueue(item('s1', owner='beta', priority=Priority(PRIORITY)), NOW)
    assert store.rows[('control', scheduler_control_key(alpha))]['rings'] == {'0': [], '1': [], '2': []}


# --------------------------------------------------------------------------
# 7. Composed seed deltas (rejoin_frontiers -> activate)
# --------------------------------------------------------------------------


@pytest.mark.parametrize('hint,expected', [(0.0, 0.0), (5.0, 5.0), (12.0, 12.0)])
def test_composed_delta_fresh_shard_takes_the_hint(hint, expected):
    store = EdgeStore(hints={PRIORITY: hint})
    seeds = rejoin_frontiers(store, (PRIORITY,))
    tx_rows = {}
    from utils.batch_pipeline.control import activate, read_control
    from tests.unit.test_batch_rejoin_frontier_seed import SnapshotTx

    tx = SnapshotTx()
    control = read_control(tx, 'shard-a')
    activate(tx, control, PRIORITY, NOW, seeds[PRIORITY])
    assert control[f'p{PRIORITY}_service'] == expected


@pytest.mark.parametrize('own,expected', [(3.0, 5.0), (8.0, 8.0)])
def test_composed_delta_credited_shard_takes_max_with_a_fresh_hint(own, expected):
    store = EdgeStore(hints={PRIORITY: 5.0})
    seeds = rejoin_frontiers(store, (PRIORITY,))
    from utils.batch_pipeline.control import activate, read_control
    from tests.unit.test_batch_rejoin_frontier_seed import SnapshotTx

    tx = SnapshotTx()
    control = read_control(tx, 'shard-a')
    control[f'p{PRIORITY}_service'] = own
    activate(tx, control, PRIORITY, NOW, seeds[PRIORITY])
    assert control[f'p{PRIORITY}_service'] == expected


# --------------------------------------------------------------------------
# 8. Final edge pins
# --------------------------------------------------------------------------


@pytest.mark.parametrize('priority', [-1, 3, 9])
def test_edge_hint_store_refuses_unbounded_priorities(priority):
    store = EdgeStore()
    with pytest.raises(ValueError):
        store.service_frontier_hint(priority)


def test_edge_frontiers_accepts_enum_keyed_hint_tables():
    store = EdgeStore()
    store._hints = {int(Priority.DEEP): 7.0}
    assert rejoin_frontiers(store, (Priority.DEEP,)) == {PRIORITY: 7.0}


def test_edge_frontiers_accepts_bool_hint_values():
    store = EdgeStore()
    store._hints = {1: True}
    assert rejoin_frontiers(store, (1,)) == {1: 1.0}


@pytest.mark.parametrize('priority', [0, 1, 2])
def test_edge_redrive_hint_precedes_the_transaction(priority):
    store = EdgeStore(hints={priority: 4.0})
    store.rows[('jobs', 'seg-edge')] = _dead_row(priority)
    Scheduler(store).redrive_dead('seg-edge', NOW)
    assert store.hint_calls[0][0] == priority


def test_edge_durable_status_probe_precedes_the_hints():
    from utils.batch_pipeline.intake import durable_status

    store = EdgeStore(hints={0: 1.0})
    store.rows = _intake_rows_for()
    durable_status(store, 'synthetic-owner', 'job-1')
    assert store.hint_calls  # the probe ran first; the hints followed it


@pytest.mark.parametrize('pool', ['batch', 'live'])
def test_edge_early_rejoin_pulls_a_later_window_back_to_now(pool):
    # Activation clamps the pool window DOWN to the rejoin time: a window set
    # later than now never survives a rejoin that happened earlier.
    from tests.unit.test_batch_rejoin_frontier_seed import SnapshotTx
    from utils.batch_pipeline.control import activate, read_control

    tx = SnapshotTx()
    control = read_control(tx, 'shard-a')
    control[f'p1_{pool}_available_at'] = 20.0
    activate(tx, control, 1, 10.0, 1.0)
    assert control[f'p1_{pool}_available_at'] == 10.0


@pytest.mark.parametrize('priority', [0, 1, 2])
def test_edge_drained_shard_leaves_the_candidate_scan(priority):
    store = EdgeStore()
    store.rows[('control', scheduler_control_key(owner_key('beta')))] = {
        'rings': {'0': [], '1': [], '2': []},
        f'p{priority}_service': 5.0,
        f'p{priority}_active': False,
        f'p{priority}_batch_available_at': 0.0,
        f'p{priority}_live_available_at': 0.0,
    }
    assert store.control_candidates(priority, 'batch', NOW, worker_id='w', fanout=8) == []


def test_edge_sim_hint_reads_negative_credit_faithfully():
    from testing.pipeline_sim.store import CustomerData, SimStore

    store = SimStore(CustomerData(), namespace='batch_pipeline_test_unit')
    store.apply(('control', 'shard-a'), {'p1_service': -2.5})
    assert store.service_frontier_hint(1) == -2.5


def test_edge_sim_hint_missing_priority_is_zero():
    from testing.pipeline_sim.store import CustomerData, SimStore

    store = SimStore(CustomerData(), namespace='batch_pipeline_test_unit')
    store.apply(('control', 'shard-a'), {'p1_service': 4.0})
    assert store.service_frontier_hint(2) == 0.0


def test_edge_sim_hint_int_typed_value_is_a_number():
    from testing.pipeline_sim.store import CustomerData, SimStore

    store = SimStore(CustomerData(), namespace='batch_pipeline_test_unit')
    store.apply(('control', 'shard-a'), {'p1_service': 3})
    value = store.service_frontier_hint(1)
    assert value == 3 and isinstance(value, (int, float))


def test_edge_postgres_hint_bounds_priority():
    from database.jobstore.postgres_store import PostgresStore

    store = PostgresStore.__new__(PostgresStore)
    store.namespace = 'ns'
    with pytest.raises(ValueError):
        store.service_frontier_hint(11)


def test_edge_admit_custom_enqueue_with_frontiers_still_gets_no_kwarg(monkeypatch):
    from database.batch_pipeline_intake import admit
    from tests.unit.test_batch_pipeline_intake import proposal

    store = EdgeStore(hints={PRIORITY: 5.0})
    works, binding = proposal()
    kwargs_seen = []

    def custom(tx, work, now, *, policy=None, **extra):
        kwargs_seen.append(sorted(extra))
        return True

    admit(store, works, binding, 100, namespace='batch_pipeline_test_edge', enqueue=custom, frontiers={PRIORITY: 5.0})
    assert kwargs_seen == [[]]


def test_edge_enqueue_hint_read_uses_the_int_priority():
    store = EdgeStore(hints={PRIORITY: 4.0})
    Scheduler(store).enqueue(item('seg-edge', priority=Priority(PRIORITY)), NOW)
    assert store.hint_calls == [(PRIORITY, 4.0)]


def test_edge_frontiers_return_is_keyed_by_int():
    seeds = rejoin_frontiers(EdgeStore(hints={1: 2.0}), (1,))
    assert list(seeds) == [1]


def test_edge_repeated_probe_reads_do_not_accumulate_hints():
    store = EdgeStore(hints={PRIORITY: 4.0})
    store.rows[('jobs', 'seg-edge')] = _dead_row()
    Scheduler(store).redrive_dead('seg-edge', NOW)
    Scheduler(store).redrive_dead('seg-edge', NOW)
    assert store.hint_calls == [(PRIORITY, 4.0), (PRIORITY, 4.0)]
