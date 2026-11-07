"""Rejoin-wave fairness: what the advisory seed does to scheduling order.

The seed is advisory, but it is not arbitrary: it decides where a rejoining
shard lands in the least-service-first scan. Pinned here, over the real
enqueue path and the real candidate scan:

1. Wave shape: a shard that drained keeps its document (service retained,
   active False); its next append reactivates it at ``max(own, hint)``.
2. Ordering: a shard rejoining at the frontier ties with the argmax shard and
   never leapfrogs it; a stale-low hint lands it first (compensating); a
   stale-high hint lands it last (bounded underserve).
3. The seed never compounds: repeated rejoins recompute ``max(own, hint)``
   from the same document, and the hint is never accumulated.
4. The seed never touches custody: with an extreme hint the job row, queue
   document and FIFO order are identical to a zero-hint enqueue.
5. Priority isolation: a p1 rejoin leaves p0/p2 fields and candidate scans
   untouched, and vice versa.
6. Candidates: an inactive shard is invisible to the scan; activation at the
   frontier makes it visible exactly at ``available_at <= now``.

Failure-Class: FC-rejoin-frontier-seed-read-joins-the-argmax-shard-abort-set
"""

from dataclasses import replace

import pytest
from config.batch_pipeline import scheduler_control_key
from tests.unit.test_batch_pipeline_scheduler import MemoryStore, item
from utils.batch_pipeline.contracts import Priority
from utils.batch_pipeline.scheduler import Scheduler, owner_key


class HintStore(MemoryStore):
    """MemoryStore with an explicit, controllable hint table."""

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


@pytest.fixture(autouse=True)
def cohort(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_UID_ALLOWLIST', 'synthetic-owner')
    monkeypatch.setenv('BATCH_PIPELINE_PERCENT', '0')


PRIORITY = int(Priority.DEEP)
NOW = 100.0


def full_shard_doc():
    """The default control document read_control produces, for all priorities."""
    doc = {'rings': {'0': [], '1': [], '2': []}}
    for priority in (0, 1, 2):
        doc[f'p{priority}_service'] = 0.0
        doc[f'p{priority}_active'] = False
        doc[f'p{priority}_batch_available_at'] = 0.0
        doc[f'p{priority}_live_available_at'] = 0.0
    return doc


def active_shard_doc(priority, service, pool='batch'):
    doc = full_shard_doc()
    doc[f'p{priority}_service'] = service
    doc[f'p{priority}_active'] = True
    return doc


def drained_shard_doc(priority, service):
    doc = active_shard_doc(priority, service)
    doc[f'p{priority}_active'] = False
    return doc


def _wave_store(prior, hint, priority=PRIORITY, other_service=10.0):
    store = HintStore(hints={priority: hint})
    alpha, beta = owner_key('alpha'), owner_key('beta')
    store.rows[('control', scheduler_control_key(alpha))] = active_shard_doc(priority, other_service)
    store.rows[('control', scheduler_control_key(beta))] = drained_shard_doc(priority, prior)
    Scheduler(store).enqueue(item('seg-b', owner='beta', priority=Priority(priority)), NOW)
    return store, alpha, beta


def _service(doc, priority=PRIORITY):
    return doc[f'p{priority}_service']


def _candidates(store, priority=PRIORITY, now=NOW):
    # A worker_id + fanout scans the whole eligible set; the bare scan is
    # capped at one candidate.
    return store.control_candidates(priority, 'batch', now, worker_id='worker-w', fanout=8)


# --------------------------------------------------------------------------
# 1. Wave shape: drained docs keep service; rejoin seeds max(own, hint)
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    'prior,hint,expected',
    [
        (0.0, 10.0, 10.0),
        (4.0, 10.0, 10.0),
        (12.0, 10.0, 12.0),
        (10.0, 10.0, 10.0),
        (4.0, 0.0, 4.0),
        (0.0, 0.0, 0.0),
        (2.5, 7.25, 7.25),
        (7.25, 2.5, 7.25),
    ],
)
def test_rejoin_seeds_max_of_own_and_hint(prior, hint, expected):
    store, alpha, beta = _wave_store(prior, hint)
    doc = store.rows[('control', scheduler_control_key(beta))]
    assert _service(doc) == expected
    assert doc[f'p{PRIORITY}_active'] is True


@pytest.mark.parametrize('prior', [0.0, 4.0, 12.0])
def test_drained_shard_retains_its_service_document_before_the_rejoin(prior):
    store = HintStore()
    beta = owner_key('beta')
    store.rows[('control', scheduler_control_key(beta))] = drained_shard_doc(PRIORITY, prior)
    doc = store.rows[('control', scheduler_control_key(beta))]
    assert _service(doc) == prior
    assert doc[f'p{PRIORITY}_active'] is False


def test_rejoin_does_not_touch_the_argmax_shard():
    store, alpha, beta = _wave_store(4.0, 10.0)
    assert _service(store.rows[('control', scheduler_control_key(alpha))]) == 10.0
    assert store.rows[('control', scheduler_control_key(alpha))][f'p{PRIORITY}_active'] is True


def test_rejoin_marks_only_the_rejoining_shard_active():
    store, alpha, beta = _wave_store(4.0, 10.0)
    assert store.rows[('control', scheduler_control_key(beta))][f'p{PRIORITY}_active'] is True


# --------------------------------------------------------------------------
# 2. Ordering consequences, both bounded directions
# --------------------------------------------------------------------------


def test_rejoin_at_the_frontier_does_not_leapfrog_the_argmax():
    store, alpha, beta = _wave_store(10.0, 10.0)
    candidates = _candidates(store)
    assert scheduler_control_key(alpha) in candidates
    assert scheduler_control_key(beta) in candidates
    assert _service(store.rows[('control', scheduler_control_key(beta))]) == 10.0
    assert _service(store.rows[('control', scheduler_control_key(alpha))]) == 10.0


def test_rejoin_at_the_frontier_is_ordered_after_no_lower_service_shard():
    store, alpha, beta = _wave_store(10.0, 10.0)
    candidates = _candidates(store)
    services = [_service(store.rows[('control', key)]) for key in candidates]
    assert services == sorted(services)
    assert set(candidates) == {
        scheduler_control_key(alpha),
        scheduler_control_key(beta),
    }


def test_stale_low_hint_lands_the_rejoin_first():
    store, alpha, beta = _wave_store(2.0, 10.0)
    candidates = _candidates(store)
    assert candidates[0] == scheduler_control_key(beta)


def test_stale_high_hint_lands_the_rejoin_last():
    store, alpha, beta = _wave_store(20.0, 10.0)
    candidates = _candidates(store)
    assert candidates[-1] == scheduler_control_key(beta)


@pytest.mark.parametrize('delta', [-8.0, -5.0, -2.0, -0.5, 0.0, 0.5, 2.0, 5.0, 8.0])
def test_rejoin_ordering_matrix_is_service_sorted(delta):
    base = 10.0
    prior = base if delta == 0.0 else (base + delta if delta < 0 else base)
    store, alpha, beta = _wave_store(prior, base)
    candidates = _candidates(store)
    services = [_service(store.rows[('control', key)]) for key in candidates]
    assert services == sorted(services)


@pytest.mark.parametrize('delta', [-8.0, -2.0, 0.0, 2.0, 8.0])
def test_rejoin_service_matrix_equals_max_own_hint(delta):
    base = 10.0
    prior = base + delta
    store, alpha, beta = _wave_store(prior, base)
    assert _service(store.rows[('control', scheduler_control_key(beta))]) == max(prior, base)


def test_stale_low_by_each_step_is_monotonic_in_the_seed():
    services = []
    for hint in (4.0, 6.0, 8.0):
        store, _, beta = _wave_store(0.0, hint)
        services.append(_service(store.rows[('control', scheduler_control_key(beta))]))
    assert services == sorted(services)


def test_hint_above_frontier_never_pushes_service_below_own():
    store, _, beta = _wave_store(9.0, 1.0)
    assert _service(store.rows[('control', scheduler_control_key(beta))]) == 9.0


def test_hint_below_own_never_raises_service():
    store, _, beta = _wave_store(9.0, 1.0)
    doc = store.rows[('control', scheduler_control_key(beta))]
    assert _service(doc) == 9.0


# --------------------------------------------------------------------------
# 3. The seed never compounds
# --------------------------------------------------------------------------


def test_repeated_rejoins_do_not_accumulate_the_hint():
    store, alpha, beta = _wave_store(4.0, 10.0)
    beta_key = scheduler_control_key(beta)
    service = _service(store.rows[('control', beta_key)])
    doc = store.rows[('control', beta_key)]
    doc[f'p{PRIORITY}_active'] = False
    Scheduler(store).enqueue(item('seg-b2', owner='beta', priority=Priority(PRIORITY)), NOW + 1)
    assert _service(store.rows[('control', beta_key)]) == service


def test_repeated_rejoins_take_a_grown_frontier():
    store, alpha, beta = _wave_store(4.0, 10.0)
    beta_key = scheduler_control_key(beta)
    store.rows[('control', beta_key)][f'p{PRIORITY}_active'] = False
    store.rows[('control', scheduler_control_key(alpha))][f'p{PRIORITY}_service'] = 15.0
    store._hints[PRIORITY] = 15.0
    Scheduler(store).enqueue(item('seg-b2', owner='beta', priority=Priority(PRIORITY)), NOW + 1)
    assert _service(store.rows[('control', beta_key)]) == 15.0


def test_repeated_rejoins_keep_service_when_the_frontier_shrinks():
    store, alpha, beta = _wave_store(4.0, 10.0)
    beta_key = scheduler_control_key(beta)
    first = _service(store.rows[('control', beta_key)])
    store.rows[('control', beta_key)][f'p{PRIORITY}_active'] = False
    store._hints[PRIORITY] = 1.0
    Scheduler(store).enqueue(item('seg-b2', owner='beta', priority=Priority(PRIORITY)), NOW + 1)
    assert _service(store.rows[('control', beta_key)]) == first


@pytest.mark.parametrize('cycles', [2, 3, 5])
def test_wave_churn_over_many_cycles_keeps_the_seed_bounded(cycles):
    store, alpha, beta = _wave_store(4.0, 10.0)
    beta_key = scheduler_control_key(beta)
    for cycle in range(cycles):
        store.rows[('control', beta_key)][f'p{PRIORITY}_active'] = False
        Scheduler(store).enqueue(item(f'seg-{cycle}', owner='beta', priority=Priority(PRIORITY)), NOW + cycle)
        assert _service(store.rows[('control', beta_key)]) == 10.0


def test_hint_is_read_once_per_rejoin_not_accumulated():
    store, alpha, beta = _wave_store(4.0, 10.0)
    assert store.hint_calls == [(PRIORITY, 10.0)]


# --------------------------------------------------------------------------
# 4. The seed never touches custody
# --------------------------------------------------------------------------


@pytest.mark.parametrize('hint', [0.0, -100.0, 1e12])
def test_extreme_hints_produce_the_same_job_row(hint):
    zero = HintStore(hints={PRIORITY: 0.0})
    extreme = HintStore(hints={PRIORITY: hint})
    Scheduler(zero).enqueue(item('seg-x', owner='beta', priority=Priority(PRIORITY)), NOW)
    Scheduler(extreme).enqueue(item('seg-x', owner='beta', priority=Priority(PRIORITY)), NOW)
    zero_job = dict(zero.rows[('jobs', 'seg-x')])
    extreme_job = dict(extreme.rows[('jobs', 'seg-x')])
    zero_job.pop('token'), extreme_job.pop('token')
    assert zero_job == extreme_job


@pytest.mark.parametrize('hint', [-100.0, 1e12])
def test_extreme_hints_produce_the_same_queue_document(hint):
    zero = HintStore(hints={PRIORITY: 0.0})
    extreme = HintStore(hints={PRIORITY: hint})
    Scheduler(zero).enqueue(item('seg-x', owner='beta', priority=Priority(PRIORITY)), NOW)
    Scheduler(extreme).enqueue(item('seg-x', owner='beta', priority=Priority(PRIORITY)), NOW)
    zero_queue = dict(zero.rows[('queues', f'{PRIORITY}_' + owner_key('beta'))])
    extreme_queue = dict(extreme.rows[('queues', f'{PRIORITY}_' + owner_key('beta'))])
    assert zero_queue == extreme_queue


@pytest.mark.parametrize('hint', [-100.0, 1e12])
def test_fifo_order_within_an_owner_is_hint_independent(hint):
    zero = HintStore(hints={PRIORITY: 0.0})
    extreme = HintStore(hints={PRIORITY: hint})
    for store in (zero, extreme):
        Scheduler(store).enqueue(item('seg-1', owner='beta', priority=Priority(PRIORITY)), NOW)
        Scheduler(store).enqueue(item('seg-2', owner='beta', priority=Priority(PRIORITY)), NOW)
        Scheduler(store).enqueue(item('seg-3', owner='beta', priority=Priority(PRIORITY)), NOW)
    queue_key = f'{PRIORITY}_' + owner_key('beta')
    assert zero.rows[('queues', queue_key)]['items'] == ['seg-1', 'seg-2', 'seg-3']
    assert extreme.rows[('queues', queue_key)]['items'] == ['seg-1', 'seg-2', 'seg-3']


def test_admission_outcome_is_hint_independent():
    for hint in (0.0, -50.0, 500.0):
        store = HintStore(hints={PRIORITY: hint})
        assert Scheduler(store).enqueue(item('seg-ok', owner='beta', priority=Priority(PRIORITY)), NOW) is True


def test_privacy_fence_fields_are_hint_independent():
    zero = HintStore(hints={PRIORITY: 0.0})
    extreme = HintStore(hints={PRIORITY: 1e12})
    for store in (zero, extreme):
        Scheduler(store).enqueue(item('seg-p', owner='beta', priority=Priority(PRIORITY)), NOW)
    assert zero.rows[('jobs', 'seg-p')]['privacy_generation'] == extreme.rows[('jobs', 'seg-p')]['privacy_generation']


# --------------------------------------------------------------------------
# 5. Priority isolation
# --------------------------------------------------------------------------


@pytest.mark.parametrize('priority', [0, 1, 2])
def test_rejoin_only_seeds_its_own_priority(priority):
    store = HintStore(hints={priority: 6.0})
    beta = owner_key('beta')
    store.rows[('control', scheduler_control_key(beta))] = drained_shard_doc(priority, 1.0)
    Scheduler(store).enqueue(item('seg-b', owner='beta', priority=Priority(priority)), NOW)
    doc = store.rows[('control', scheduler_control_key(beta))]
    assert _service(doc, priority) == 6.0
    for other in (0, 1, 2):
        if other != priority:
            assert doc[f'p{other}_service'] == 0.0


def test_p1_rejoin_leaves_the_p0_candidate_scan_untouched():
    store, alpha, beta = _wave_store(4.0, 10.0)
    assert _candidates(store, priority=0) == []


def test_p1_rejoin_leaves_p0_documents_untouched():
    store, alpha, beta = _wave_store(4.0, 10.0)
    alpha_doc = store.rows[('control', scheduler_control_key(alpha))]
    assert alpha_doc['p0_service'] == 0.0
    assert alpha_doc['p0_active'] is False


def test_p0_scan_still_sees_the_active_argmax_shard():
    store = HintStore(hints={0: 8.0})
    alpha = owner_key('alpha')
    store.rows[('control', scheduler_control_key(alpha))] = active_shard_doc(0, 8.0)
    assert _candidates(store, priority=0) == [scheduler_control_key(alpha)]


# --------------------------------------------------------------------------
# 6. Candidate visibility across activation
# --------------------------------------------------------------------------


def test_drained_shard_is_invisible_to_the_scan_before_the_rejoin():
    store = HintStore()
    beta = owner_key('beta')
    store.rows[('control', scheduler_control_key(beta))] = drained_shard_doc(PRIORITY, 4.0)
    assert _candidates(store) == []


def test_rejoin_makes_the_shard_visible_to_the_scan():
    store, alpha, beta = _wave_store(4.0, 10.0)
    assert scheduler_control_key(beta) in _candidates(store)


def test_rejoined_shard_visible_from_its_window():
    store, alpha, beta = _wave_store(4.0, 10.0)
    assert scheduler_control_key(beta) in _candidates(store, now=NOW)
    assert scheduler_control_key(beta) in _candidates(store, now=NOW + 30)


def test_candidate_scan_before_the_window_excludes_a_paused_rejoin():
    # Activation clamps each pool window DOWN to now: a shard paused until the
    # future rejoins eligible exactly at now, never before.
    store = HintStore(hints={PRIORITY: 10.0})
    beta = owner_key('beta')
    doc = drained_shard_doc(PRIORITY, 4.0)
    doc[f'p{PRIORITY}_batch_available_at'] = NOW + 50.0
    store.rows[('control', scheduler_control_key(beta))] = doc
    Scheduler(store).enqueue(item('seg-b', owner='beta', priority=Priority(PRIORITY)), NOW)
    shard = store.rows[('control', scheduler_control_key(beta))]
    assert shard[f'p{PRIORITY}_batch_available_at'] == NOW
    assert scheduler_control_key(beta) in _candidates(store, now=NOW)
    assert _candidates(store, now=NOW - 1) == []


def test_scan_excludes_dispositioned_neighbours_not_the_rejoin():
    store, alpha, beta = _wave_store(4.0, 10.0)
    gamma = owner_key('gamma')
    dead = active_shard_doc(PRIORITY, 50.0)
    dead[f'p{PRIORITY}_active'] = False
    store.rows[('control', scheduler_control_key(gamma))] = dead
    candidates = _candidates(store)
    assert scheduler_control_key(gamma) not in candidates
    assert scheduler_control_key(beta) in candidates


def test_tied_frontier_candidates_are_deterministic():
    orders = []
    for _ in range(2):
        store, alpha, beta = _wave_store(10.0, 10.0)
        orders.append(_candidates(store))
    assert orders[0] == orders[1]


def test_equal_service_candidates_are_deterministically_ordered():
    # Ties are broken by worker affinity (sha256 of worker:shard), which is
    # deterministic for a fixed worker id and shard pair.
    store, alpha, beta = _wave_store(10.0, 10.0)
    a_key, b_key = scheduler_control_key(alpha), scheduler_control_key(beta)
    candidates = _candidates(store)
    assert set(candidates) == {a_key, b_key}
    assert candidates == _candidates(store)


def test_worker_affinity_only_reorders_equal_service():
    store, alpha, beta = _wave_store(10.0, 10.0)
    a_key, b_key = scheduler_control_key(alpha), scheduler_control_key(beta)
    flat = store.control_candidates(PRIORITY, 'batch', NOW, worker_id='worker-7', fanout=8)
    assert set(flat) == {a_key, b_key}


def test_fanout_bounds_the_candidate_list():
    store, alpha, beta = _wave_store(4.0, 10.0)
    assert len(store.control_candidates(PRIORITY, 'batch', NOW, worker_id='worker-7', fanout=1)) == 1


# --------------------------------------------------------------------------
# 7. Live pool symmetry
# --------------------------------------------------------------------------


def test_activation_opens_both_pools_for_the_scan():
    store, alpha, beta = _wave_store(4.0, 10.0)
    beta_key = scheduler_control_key(beta)
    assert beta_key in store.control_candidates(PRIORITY, 'batch', NOW)
    assert beta_key in store.control_candidates(PRIORITY, 'live', NOW)


@pytest.mark.parametrize('pool', ['batch', 'live'])
def test_pool_window_tracks_the_rejoin_now(pool):
    store, alpha, beta = _wave_store(4.0, 10.0)
    beta_doc = store.rows[('control', scheduler_control_key(beta))]
    assert beta_doc[f'p{PRIORITY}_{pool}_available_at'] <= NOW


# --------------------------------------------------------------------------
# 8. Composed semantics: rejoin_frontiers + activate
# --------------------------------------------------------------------------


def test_composed_seed_is_the_hint_the_store_reported():
    store, alpha, beta = _wave_store(4.0, 10.0)
    doc = store.rows[('control', scheduler_control_key(beta))]
    assert _service(doc) == store._hints[PRIORITY]


def test_composed_seed_with_a_zero_frontier_keeps_a_credited_shard():
    store, alpha, beta = _wave_store(6.0, 0.0)
    assert _service(store.rows[('control', scheduler_control_key(beta))]) == 6.0


def test_composed_seed_equal_to_own_is_stable_under_repeat():
    store, alpha, beta = _wave_store(10.0, 10.0)
    beta_key = scheduler_control_key(beta)
    first = _service(store.rows[('control', beta_key)])
    store.rows[('control', beta_key)][f'p{PRIORITY}_active'] = False
    Scheduler(store).enqueue(item('seg-again', owner='beta', priority=Priority(PRIORITY)), NOW + 1)
    assert _service(store.rows[('control', beta_key)]) == first


def test_wave_over_three_shards_isolates_each_seed():
    store = HintStore(hints={PRIORITY: 12.0})
    owners = [owner_key(name) for name in ('alpha', 'beta', 'gamma')]
    for index, owner in enumerate(owners):
        store.rows[('control', scheduler_control_key(owner))] = active_shard_doc(PRIORITY, 10.0 + index)
    joiner = owner_key('delta')
    store.rows[('control', scheduler_control_key(joiner))] = drained_shard_doc(PRIORITY, 2.0)
    Scheduler(store).enqueue(item('seg-d', owner='delta', priority=Priority(PRIORITY)), NOW)
    assert _service(store.rows[('control', scheduler_control_key(joiner))]) == 12.0
    for index, owner in enumerate(owners):
        assert _service(store.rows[('control', scheduler_control_key(owner))]) == 10.0 + index


def test_wave_does_not_change_the_owner_count_of_the_argmax_ring():
    store, alpha, beta = _wave_store(4.0, 10.0)
    alpha_doc = store.rows[('control', scheduler_control_key(alpha))]
    assert alpha_doc['rings'] == {'0': [], '1': [], '2': []}
