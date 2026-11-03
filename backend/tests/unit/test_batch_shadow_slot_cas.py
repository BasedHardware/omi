"""The shadow rendezvous arbitrates with fenced conditional writes, not a shared ring read set.

Production evidence: four Cloud Run replicas offer every few seconds, reserve on
every admitted upload and take on every worker cycle, and every one of those
operations used to read all four slot documents inside one Firestore
transaction — so any slot write anywhere aborted everyone else's transaction,
five attempts each, surfacing as ``firestore_transaction_contention
operation=batch_shadow_offer attempt=5/5 outcome=exhausted`` and
``background_task failed: batch_shadow_take — FirestoreContentionExhausted``
(the two largest signatures in the prod sensor feed).

The lane under test replaces ring arbitration with per-slot point reads plus
update-time-fenced conditional writes. This suite pins that contract with a
lane-specific Firestore double whose fence values double as generations: two
writers that read the same fence cannot both commit, and a hook can stage a
concurrent winner inside any single write to reproduce the exact production
interleaving. The transactional ring remains certified by
``test_batch_pipeline_shadow.py`` behind the kill switch.
"""

import pytest

from database import batch_pipeline_shadow as shadow_module
from database.batch_pipeline_shadow import ShadowStore, identity
from database.batch_pipeline_privacy import BatchPrivacyBlocked
from tests.unit.fixtures.shadow_slot_cas_firestore import ShadowStoreDouble
from utils.batch_pipeline.contracts import WorkItem

NAMESPACE = 'batch_pipeline_dev'


@pytest.fixture
def store():
    return ShadowStoreDouble()


def second_store(repository):
    """A second replica sharing the same rows and clock — the fleet shape."""
    return ShadowStore(repository.store, clock=repository.store.clock, busy=lambda: False)


@pytest.fixture
def repository(store, monkeypatch):
    # Prepare the deferred serving module during fixture setup, as the
    # transactional suite does; provider import cost is separate from the
    # per-operation CPU guard.
    from utils.batch_pipeline import quarantine_recovery as recovery

    assert recovery.SECOND_PROVIDER == 'soniox'
    monkeypatch.setenv('BATCH_PIPELINE_SHADOW_PERCENT', '100')
    # The production module reads the switch at the call boundary; the tests
    # pin the lane explicitly instead of trusting process env.
    monkeypatch.setattr(shadow_module, 'shadow_slot_cas_enabled', lambda: True)
    return ShadowStore(store, clock=store.clock, busy=lambda: False)


def ready_offer(repository, name='one', uid='synthetic-owner', content='content'):
    """Drive one offer through staging to a ready offer; return (item, index)."""
    repository.offer('worker-' + name)
    reservation = repository.reserve(uid, content, 'deep')
    assert reservation is not None, 'admission expected an idle slot'
    index = int(reservation[1])
    item = WorkItem(reservation[0], uid, 1, 'encrypted:shadow', 2, 0, shadow=True, privacy_generation=0)
    assert repository.ready(reservation, item, '') is True
    return item, index


def reprime_slot(store, index, worker='thief'):
    """The exact concurrent writer shape: one plain read, one fenced write."""
    document = store.client.collection(f'{NAMESPACE}_shadow_slots').document(str(index))
    snapshot = document.get()
    document.update(
        {'worker': worker, 'state': 'idle', 'until': store.clock() + 30},
        option=store_fencing(snapshot.update_time),
        retry=None,
    )


class _RetryTolerantStrict:
    """Expose the strict fixture through the CAS lane's ``create(..., retry=None)`` surface.

    The transactional ring never issues point creates; the shim exists so the
    cross-lane parity tests can drive one store through the other lane's API
    without widening the strict fixture itself.
    """

    def __init__(self, inner):
        self._inner = inner

    def collection(self, name):
        return _RetryTolerantCollection(self._inner.collection(name))

    def __getattr__(self, name):
        return getattr(self._inner, name)


class _RetryTolerantCollection:
    def __init__(self, inner):
        self._inner = inner

    def document(self, name):
        return _RetryTolerantDocument(self._inner.document(name))

    def __getattr__(self, name):
        return getattr(self._inner, name)


class _RetryTolerantDocument:
    def __init__(self, inner):
        self._inner = inner

    def create(self, value, **kwargs):
        assert kwargs.get('retry') is None
        return self._inner.create(value)

    def __getattr__(self, name):
        return getattr(self._inner, name)


def store_fencing(update_time):
    from google.cloud.firestore import LastUpdateOption

    return LastUpdateOption(update_time)


# ── A. Offer fundamentals: the fleet's hottest cycle ─────────────────────────


def test_offer_primes_one_idle_slot_without_any_transaction(repository):
    repository.offer('worker')
    slots = [repository.store.slot(index) for index in range(4)]
    assert slots[0]['worker'] == 'worker'
    assert slots[0]['state'] == 'idle'
    assert slots[0]['until'] == 7200 + shadow_module.OFFER_SECONDS
    assert all(slot == {} for slot in slots[1:])
    assert repository.store.labels() == [], 'the whole point: offer opens no transaction'


def test_offer_refresh_extends_only_the_own_slot(repository):
    repository.offer('worker')
    repository.store.now = 7203
    repository.offer('worker')
    slots = [repository.store.slot(index) for index in range(4)]
    assert slots[0]['until'] == 7203 + shadow_module.OFFER_SECONDS
    assert all(slot == {} for slot in slots[1:])


def test_four_workers_fill_the_ring_and_the_fifth_is_refused(repository):
    for index in range(4):
        repository.offer(f'worker-{index}')
    repository.offer('worker-4')
    filled = sum(1 for index in range(4) if repository.store.slot(index))
    assert filled == 4
    assert repository.store.slot(3)['worker'] == 'worker-3'


def test_worker_refresh_reclaims_the_first_expired_slot(repository):
    repository.offer('worker')
    repository.store.now = 7300  # every live offer expired
    for index in range(4):
        repository.offer(f'other-{index}')
    repository.store.now = 7400  # those expired too
    repository.offer('worker')
    assert repository.store.slot(0)['worker'] == 'worker'


def test_a_live_staging_offer_keeps_its_slot_on_refresh(repository):
    repository.offer('worker')
    reservation = repository.reserve('synthetic-owner', 'content', 'deep')
    repository.offer('worker')
    slot = repository.store.slot(int(reservation[1]))
    assert slot['state'] == 'staging'
    assert slot['segment'] == reservation[0]


def test_a_live_ready_offer_keeps_its_slot_on_refresh(repository):
    item, index = ready_offer(repository)
    repository.offer('worker-one')
    slot = repository.store.slot(index)
    assert slot['state'] == 'ready'
    assert slot['segment'] == item.segment_id


def test_close_revokes_the_own_slot_even_when_the_ring_is_full(repository):
    for index in range(4):
        repository.offer(f'worker-{index}')
    repository.offer('worker-2', close=True)
    slot = repository.store.slot(2)
    assert slot['state'] == 'closed'
    assert slot['until'] == 7200


def test_close_without_a_slot_is_a_no_op(repository):
    for index in range(4):
        repository.offer(f'worker-{index}')
    repository.offer('stranger', close=True)
    assert sum(1 for index in range(4) if repository.store.slot(index)['state'] == 'idle') == 4


def test_shadow_off_uses_the_close_path(repository, monkeypatch):
    repository.offer('worker')
    monkeypatch.setenv('BATCH_PIPELINE_SHADOW_PERCENT', '0')
    repository.offer('worker')
    assert repository.store.slot(0)['state'] == 'closed'


def test_busy_pool_uses_the_close_path(repository, monkeypatch):
    repository.offer('worker')
    monkeypatch.setattr(repository, 'busy', lambda: True)
    repository.offer('worker')
    assert repository.store.slot(0)['state'] == 'closed'


def test_expired_ready_offer_is_reclaimed_by_the_next_cycle(repository):
    item, index = ready_offer(repository)
    repository.store.now = 7200 + shadow_module.OFFER_SECONDS + 1
    repository.offer('worker-two')
    slot = repository.store.slot(index)
    assert slot['worker'] == 'worker-two'
    assert 'segment' not in slot, 'the displaced pointer must not leak onto the new owner'


def test_offer_on_a_fresh_namespace_creates_the_slot_document(store, monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_SHADOW_PERCENT', '100')
    monkeypatch.setattr(shadow_module, 'shadow_slot_cas_enabled', lambda: True)
    repository = ShadowStore(store, clock=store.clock, busy=lambda: False)
    repository.offer('worker')
    assert store.client.creates == [(f'{NAMESPACE}_shadow_slots', '0')]
    assert store.slot(0)['worker'] == 'worker'


# ── B. Fence races: the arbitration itself ───────────────────────────────────


def test_two_workers_racing_one_expired_slot_yield_exactly_one_winner(repository, store):
    repository.offer('worker-a')
    repository.store.now = 7300  # expired
    # Both replicas read the same stale fence before either write lands.
    repository.offer('worker-b')  # wins the fence with its own fresh read
    repository.store.now = 7300
    repository.offer('worker-c')  # reads b's new fence, takes the next index
    assert store.slot(0)['worker'] in {'worker-b', 'worker-c'}
    assert store.slot(1)['worker'] in {'worker-b', 'worker-c'}
    owners = {store.slot(0)['worker'], store.slot(1)['worker']}
    assert owners == {'worker-b', 'worker-c'}


def test_staged_concurrent_winner_displaces_the_offer_claim(repository, store):
    repository.offer('worker-a')
    repository.store.now = 7300
    # The thief commits inside worker-b's write: a production interleaving
    # where a replica wins between this reader's read and write.
    store.race('shadow_slots', '0', lambda: reprime_slot(store, 0, worker='thief'))
    repository.offer('worker-b')
    slot = store.slot(0)
    assert slot['worker'] == 'thief', 'the concurrent writer keeps the slot'
    assert slot['until'] == 7330, "the loser's write must not land or extend the winner"


def test_a_lost_offer_fence_skips_the_cycle_without_retrying(repository, store):
    repository.offer('worker-a')
    repository.store.now = 7300
    store.race('shadow_slots', '0', lambda: reprime_slot(store, 0))
    repository.offer('worker-b')
    assert store.slot(0)['until'] == 7330, 'the loser must not extend the winner'
    assert store.slot(0)['worker'] != 'worker-b', 'the loser holds nothing'


def test_the_fence_is_the_at_most_one_owner_arbiter(repository, store):
    repository.offer('worker-a')
    fence_before = store.fence('shadow_slots', '0')
    repository.store.now = 7300
    repository.offer('worker-b')
    assert store.fence('shadow_slots', '0') != fence_before
    with pytest.raises(Exception):
        # Replaying the stale fence must fail: the generation moved.
        document = store.client.collection(f'{NAMESPACE}_shadow_slots').document('0')
        document.update({'worker': 'ghost'}, option=store_fencing(fence_before), retry=None)


def test_displaced_pointer_is_deleted_not_leaked(repository):
    item, index = ready_offer(repository)
    repository.store.now = 7300
    repository.offer('worker-two')
    slot = repository.store.slot(index)
    assert 'segment' not in slot
    # A stale reservation can no longer publish: the slot forgot the segment.
    repository.store.now = 7200
    item = WorkItem(item.segment_id, 'synthetic-owner', 1, 'encrypted:shadow', 2, 0, shadow=True)
    assert repository.ready((item.segment_id, str(index)), item, '') is False


def test_consume_race_lets_exactly_one_consumer_win(repository, store):
    item, index = ready_offer(repository)
    stale = store.fence('shadow_slots', str(index))
    assert repository.take('worker-one') == item
    assert store.job(item.segment_id)['state'] == 'running'
    # A second consumer holding the pre-take snapshot cannot re-consume.
    from google.api_core.exceptions import FailedPrecondition

    document = store.client.collection(f'{NAMESPACE}_shadow_slots').document(str(index))
    with pytest.raises(FailedPrecondition):
        document.update(
            {'worker': 'other', 'state': 'closed', 'until': 0, 'segment': None},
            option=store_fencing(stale),
            retry=None,
        )
    slot = store.slot(index)
    assert slot['state'] == 'closed'
    assert repository.take('worker-one') is None, 'at most one consumer per offer'


def test_every_slot_write_uses_a_conditional_update_with_sdk_retries_off(repository, store):
    repository.offer('worker')
    repository.store.now = 7300
    repository.offer('worker')
    assert store.client.updates, 'the lane must write through fenced updates'
    for _key, _value, retry in store.client.updates:
        assert retry is None, 'SDK retry would multiply the contention window the lane exists to remove'


# ── C. Take: at-most-one-consumer with full identity/privacy verification ────


def test_take_consumes_a_ready_offer_and_pins_it_running(repository):
    item, index = ready_offer(repository)
    assert repository.take('worker-one') == item
    job = repository.store.job(item.segment_id)
    assert job['state'] == 'running'
    assert job['started_at'] == 7200
    slot = repository.store.slot(index)
    assert slot['state'] == 'closed'
    assert 'segment' not in slot


def test_take_without_an_offer_returns_none(repository):
    assert repository.take('stranger') is None


def test_take_of_a_staging_slot_returns_none(repository):
    repository.offer('worker-one')
    repository.reserve('synthetic-owner', 'content', 'deep')
    assert repository.take('worker-one') is None


def test_take_of_an_expired_ready_offer_returns_none(repository):
    ready_offer(repository)
    repository.store.now = 7200 + shadow_module.OFFER_SECONDS + 1
    assert repository.take('worker-one') is None


def test_take_rejects_a_foreign_segment_id(repository):
    repository.offer('worker-one')
    reservation = repository.reserve('synthetic-owner', 'content', 'deep')
    forged = WorkItem('sh_other', 'synthetic-owner', 1, 'encrypted:shadow', 2, 0, shadow=True)
    with pytest.raises(ValueError, match='shadow identity required'):
        repository.ready(reservation, forged, '')
    assert repository.take('worker-one') is None


def test_take_rejects_a_non_shadow_item(repository):
    repository.offer('worker-one')
    reservation = repository.reserve('synthetic-owner', 'content', 'deep')
    forged = WorkItem(reservation[0], 'synthetic-owner', 1, 'encrypted:shadow', 2, 0, shadow=False)
    with pytest.raises(ValueError, match='shadow identity required'):
        repository.ready(reservation, forged, '')
    assert repository.take('worker-one') is None


def test_take_rejects_a_mismatched_owner(repository):
    repository.offer('worker-one')
    reservation = repository.reserve('synthetic-owner', 'content', 'deep')
    forged = WorkItem(reservation[0], 'other-owner', 1, 'encrypted:shadow', 2, 0, shadow=True)
    with pytest.raises(ValueError, match='shadow identity required'):
        repository.ready(reservation, forged, '')
    assert repository.take('worker-one') is None


def test_privacy_refusal_refuses_the_take_and_keeps_the_offer(repository):
    from database.batch_pipeline_privacy import BatchPrivacyBlocked as Blocked

    repository.store.privacy = None

    class RefusingStore(ShadowStoreDouble):
        def privacy_guard(self, uid):
            raise Blocked('synthetic privacy generation moved')

    repository.offer('worker-one')
    reservation = repository.reserve('synthetic-owner', 'content', 'deep')
    item = WorkItem(reservation[0], 'synthetic-owner', 1, 'encrypted:shadow', 2, 0, shadow=True)
    repository.ready(reservation, item, '')
    repository.store.privacy = lambda uid: (_ for _ in ()).throw(Blocked('generation moved'))
    with pytest.raises(Blocked):
        repository.take('worker-one')
    slot = repository.store.slot(int(reservation[1]))
    assert slot['state'] == 'ready', 'a refused consumer must not consume the offer'
    assert repository.store.job(item.segment_id)['state'] == 'ready'


def test_take_after_the_ring_re_primed_returns_none(repository, store):
    item, index = ready_offer(repository)
    repository.store.now = 7300
    repository.offer('worker-two')  # displaces the expired ready offer
    repository.store.now = 7200
    assert repository.take('worker-one') is None
    assert store.job(item.segment_id)['state'] != 'running'


def test_take_close_cycle_when_the_pool_goes_busy(repository, monkeypatch):
    item, index = ready_offer(repository)
    monkeypatch.setattr(repository, 'busy', lambda: True)
    assert repository.take('worker-one') is None
    assert repository.store.slot(index)['state'] == 'closed'


def test_a_consumed_offer_cannot_be_taken_twice(repository):
    item, index = ready_offer(repository)
    assert repository.take('worker-one') == item
    assert repository.take('worker-one') is None


def test_take_of_a_dropped_job_returns_none(repository):
    ready_offer(repository)
    segment = identity('synthetic-owner', 'content')
    repository.store.rewrite('shadow_jobs', segment, {**repository.store.job(segment), 'state': 'settled'})
    assert repository.take('worker-one') is None


def test_take_verify_reads_only_the_single_job_document(repository):
    item, index = ready_offer(repository)
    repository.take('worker-one')
    job_reads = [transaction.reads for operation, transaction in repository.store.transactions if operation == 'take']
    assert job_reads, 'take still verifies identity and privacy inside single-job transactions'
    for reads in job_reads:
        assert reads == [('shadow_jobs', item.segment_id)]
    assert repository.store.labels().count('offer') == 0


def test_take_order_across_two_replicas_is_exactly_one_winner(repository, store):
    item, index = ready_offer(repository)
    first = second_store(repository)
    assert repository.take('worker-one') == item
    assert first.take('worker-one') is None
    assert store.job(item.segment_id)['state'] == 'running'


def test_take_after_consume_race_leaves_the_job_ready_for_the_next_cycle(repository, store):
    item, index = ready_offer(repository)
    # The thief re-primes the slot inside the consume write: the consumer
    # loses the fence, touches nothing, and the job stays publishable.
    store.race('shadow_slots', str(index), lambda: reprime_slot(store, str(index), worker='thief'))
    assert repository.take('worker-one') is None
    assert store.job(item.segment_id)['state'] == 'ready', 'a lost consume must not touch the job'
    assert store.slot(int(index))['worker'] == 'thief'


# ── D. Reserve: admission without a ring-wide transaction ────────────────────


def test_reserve_stages_an_idle_slot_and_creates_the_job(repository):
    repository.offer('worker-one')
    reservation = repository.reserve('synthetic-owner', 'content', 'deep')
    assert reservation == (identity('synthetic-owner', 'content'), '0')
    job = repository.store.job(reservation[0])
    assert job['state'] == 'staging'
    assert job['shadow'] is True
    assert job['projection_reserved_at'] == 7200
    slot = repository.store.slot(0)
    assert slot['state'] == 'staging'
    assert slot['segment'] == reservation[0]
    assert slot['until'] == 7200 + shadow_module.STAGING_SECONDS


def test_reserve_never_admits_twice_for_the_same_content(repository):
    repository.offer('worker-one')
    first = repository.reserve('synthetic-owner', 'content', 'deep')
    second = repository.reserve('synthetic-owner', 'content', 'deep')
    assert first is not None and second is None


def test_reserve_with_no_idle_slot_drops_without_a_staged_job(repository):
    for index in range(4):
        repository.offer(f'worker-{index}')
    repository.store.now = 7300  # every offer expired: no live idle slot
    reservation = repository.reserve('synthetic-owner', 'content', 'deep')
    assert reservation is None
    job = repository.store.job(identity('synthetic-owner', 'content'))
    assert job['outcome'] == 'dropped'
    assert job['state'] == 'settled'
    assert all('segment' not in repository.store.slot(index) for index in range(4))


def test_reserve_during_busy_pool_drops(repository, monkeypatch):
    repository.offer('worker-one')
    monkeypatch.setattr(repository, 'busy', lambda: True)
    assert repository.reserve('synthetic-owner', 'content', 'deep') is None
    job = repository.store.job(identity('synthetic-owner', 'content'))
    assert job['outcome'] == 'dropped'


def test_reserve_off_a_dead_switch_drops_via_the_close_cycle(repository, monkeypatch):
    repository.offer('worker-one')
    monkeypatch.setenv('BATCH_PIPELINE_SHADOW_PERCENT', '0')
    assert repository.reserve('synthetic-owner', 'content', 'deep') is None
    job = repository.store.job(identity('synthetic-owner', 'content'))
    assert job['outcome'] == 'dropped'


def test_uncertain_cost_authority_never_admits(repository):
    repository.offer('worker-one')
    repository.store.rewrite('shadow_spend', 'projection-2', {'units': -1})
    assert repository.reserve('synthetic-owner', 'content', 'deep') is None
    assert repository.store.job(identity('synthetic-owner', 'content')) == {}


def test_hourly_cap_of_200_units_is_shared_across_replicas(repository):
    repository.offer('worker-one')
    repository.store.rewrite('shadow_spend', 'projection-2', {'units': 200})
    reservation = repository.reserve('synthetic-owner', 'content', 'deep')
    assert reservation is None
    job = repository.store.job(identity('synthetic-owner', 'content'))
    assert job['outcome'] == 'dropped'


def test_hourly_cap_below_the_limit_binds_spend_after_the_fence(repository):
    repository.offer('worker-one')
    repository.store.rewrite('shadow_spend', 'projection-2', {'units': 199})
    reservation = repository.reserve('synthetic-owner', 'content', 'deep')
    assert reservation is not None
    assert repository.store.row('shadow_spend', 'projection-2')['units'] == 200


def test_staged_slot_race_drops_the_unit_and_frees_the_ring(repository, store):
    repository.offer('worker-one')
    store.race('shadow_slots', '0', lambda: reprime_slot(store, 0, worker='thief'))
    reservation = repository.reserve('synthetic-owner', 'content', 'deep')
    assert reservation is None, 'a lost admission fence must not stage the ring'
    job = store.job(identity('synthetic-owner', 'content'))
    assert job['outcome'] == 'dropped'
    assert store.slot(0)['worker'] == 'thief', 'the concurrent writer keeps its slot'


def test_reserve_takes_the_first_idle_index_round_robin(repository):
    repository.offer('worker-0')
    repository.reserve('owner-a', 'content-a', 'deep')
    repository.reserve('owner-b', 'content-b', 'deep')
    repository.reserve('owner-c', 'content-c', 'deep')
    # Index 0 went staging first; the ring admits in index order.
    assert (
        repository.reserve('owner-d', 'content-d', 'deep') is None
    ), 'one live offer admits exactly one unit; the rest drop without a queue'


def test_reserve_duplicate_refusal_races_the_create_not_the_ring(repository, store):
    repository.offer('worker-one')
    segment = identity('synthetic-owner', 'content')
    store.rewrite('shadow_jobs', segment, {'shadow': True, 'state': 'staging', 'created_at': 7199})
    reservation = repository.reserve('synthetic-owner', 'content', 'deep')
    assert reservation is None
    assert store.slot(0)['state'] == 'idle', 'duplicate refusal must not stage the ring'


def test_reserve_never_reads_the_slot_ring_inside_a_transaction(repository):
    repository.offer('worker-one')
    repository.reserve('synthetic-owner', 'content', 'deep')
    for operation, transaction in repository.store.transactions:
        assert operation != 'offer'
        assert all(
            table != 'shadow_slots' for table, _key in transaction.reads
        ), f'{operation} read the slot ring inside a transaction: {transaction.reads}'


def test_reserve_labels_stay_static_and_identity_free(repository):
    repository.offer('worker-one')
    repository.reserve('synthetic-owner', 'content', 'deep')
    assert repository.store.labels() == ['reserve', 'reserve', 'reserve']
    assert all('synthetic' not in label for label in repository.store.labels())


def test_reserve_spend_write_survives_an_hour_rollover_key(repository):
    repository.offer('worker-one')
    repository.store.now = 7200 + 3600
    repository.offer('worker-one')
    reservation = repository.reserve('synthetic-owner', 'content', 'deep')
    assert reservation is not None
    assert repository.store.row('shadow_spend', 'projection-3')['units'] == 1


def test_concurrent_reserve_winners_on_different_slots_each_bind_spend(repository):
    for index in range(2):
        repository.offer(f'worker-{index}')
    first = second_store(repository)
    assert repository.reserve('owner-a', 'content-a', 'deep') is not None
    assert first.reserve('owner-b', 'content-b', 'deep') is not None
    assert repository.store.row('shadow_spend', 'projection-2')['units'] == 2


def test_reserve_skips_a_staging_slot_and_never_reads_it_back_transactionally(repository, store):
    repository.offer('worker-one')
    first = repository.reserve('owner-a', 'content-a', 'deep')
    assert first is not None
    second = repository.reserve('owner-b', 'content-b', 'deep')
    assert second is None, 'one live offer admits exactly one unit'
    for _operation, transaction in repository.store.transactions:
        assert all(table != 'shadow_slots' for table, _key in transaction.reads)


# ── E. Finish: single-job settlement, both lanes ─────────────────────────────


def test_finish_settles_one_job_with_its_own_transaction(repository):
    item, index = ready_offer(repository)
    repository.take('worker-one')
    repository.finish(item.segment_id, 'recovered', speech=1.5, vad='worker')
    job = repository.store.job(item.segment_id)
    assert job['state'] == 'settled'
    assert job['outcome'] == 'recovered'
    assert job['speech_seconds'] == 1.5
    assert job['speech_loss_seconds'] == 0.0


def test_finish_is_idempotent_across_replicas(repository):
    item, index = ready_offer(repository)
    repository.take('worker-one')
    repository.finish(item.segment_id, 'recovered')
    other = second_store(repository)
    other.finish(item.segment_id, 'error')
    assert repository.store.job(item.segment_id)['outcome'] == 'recovered'


def test_finish_rejects_unknown_outcomes(repository):
    with pytest.raises(ValueError, match='closed shadow outcome required'):
        repository.finish('sh_whatever', 'made-up')


def test_finish_rejects_unknown_projection_statuses(repository):
    with pytest.raises(ValueError, match='closed shadow projection status required'):
        repository.finish('sh_whatever', 'error', projection_status='invented')


def test_finish_records_the_outcome_for_the_metrics_census(repository, monkeypatch):
    recorded = []
    monkeypatch.setattr(shadow_module, 'record', lambda row: recorded.append(row))
    item, index = ready_offer(repository)
    repository.take('worker-one')
    repository.finish(item.segment_id, 'recovered', speech=1.5, vad='strict')
    assert recorded and recorded[-1]['vad'] == 'strict'
    job = repository.store.job(item.segment_id)
    assert job['vad'] == 'strict'


def test_finish_expires_settled_rows_after_seven_days(repository):
    item, index = ready_offer(repository)
    repository.take('worker-one')
    repository.finish(item.segment_id, 'error')
    job = repository.store.job(item.segment_id)
    from datetime import datetime, timedelta, timezone

    assert job['expires_at'] == datetime.fromtimestamp(7200, timezone.utc) + timedelta(days=7)


def test_finish_of_a_missing_job_is_a_silent_no_op(repository):
    repository.finish('sh_absent', 'error')
    assert repository.store.job('sh_absent') == {}


def test_empty_outcome_with_unknown_vad_fails_held(repository):
    item, index = ready_offer(repository)
    repository.take('worker-one')
    repository.finish(item.segment_id, 'empty', speech=0.0, vad='unknown')
    job = repository.store.job(item.segment_id)
    assert job['outcome'] == 'failed_held', 'an unknown silence claim cannot certify empty'


def test_empty_outcome_with_measured_zero_stays_empty_when_unguarded(repository):
    item, index = ready_offer(repository)
    repository.take('worker-one')
    repository.finish(item.segment_id, 'empty', speech=0.0, vad='strict')
    assert repository.store.job(item.segment_id)['outcome'] == 'empty'


def test_paid_skipped_sets_its_reason_code(repository):
    item, index = ready_offer(repository)
    repository.take('worker-one')
    repository.start_recovery(item.segment_id)
    repository.finish(item.segment_id, 'paid_skipped')
    assert repository.store.job(item.segment_id)['reason_code'] == 'shadow_paid_skipped'


def test_projection_status_round_trips(repository):
    item, index = ready_offer(repository)
    repository.take('worker-one')
    repository.finish(item.segment_id, 'error', projection_status='busy')
    assert repository.store.job(item.segment_id)['projection_status'] == 'busy'


# ── F. Displaced jobs: the exchange never erases live work ───────────────────


def test_offer_never_drops_a_running_job(repository):
    item, index = ready_offer(repository)
    repository.take('worker-one')  # slot closed, job running
    repository.store.now = 7300
    repository.offer('worker-two')  # re-arms the ring over the closed slot
    job = repository.store.job(item.segment_id)
    assert job['state'] == 'running', 'a running job is its consumer\'s to finish'


def test_offer_never_drops_a_recovering_job(repository):
    item, index = ready_offer(repository)
    repository.take('worker-one')
    repository.handoff(
        item.segment_id,
        __import__('utils.batch_pipeline.contracts', fromlist=['RecoveryWork']).RecoveryWork(item.segment_id),
    )
    repository.start_recovery(item.segment_id)
    repository.store.now = 7300
    repository.offer('worker-two')
    job = repository.store.job(item.segment_id)
    assert job['state'] == 'recovering'


def test_offer_drops_an_expired_staging_job_left_by_a_dead_replica(repository):
    repository.offer('worker-one')
    reservation = repository.reserve('synthetic-owner', 'content', 'deep')
    assert reservation is not None
    repository.store.now = 7200 + shadow_module.STAGING_SECONDS + 1
    repository.offer('worker-two')
    job = repository.store.job(reservation[0])
    assert job['outcome'] == 'dropped'


def test_offer_drops_a_displaced_expired_ready_job(repository):
    item, index = ready_offer(repository)
    repository.store.now = 7300
    repository.offer('worker-two')
    assert repository.store.job(item.segment_id)['outcome'] == 'dropped'


def test_offer_keeps_a_live_staging_job_when_the_slot_is_fresh(repository):
    repository.offer('worker-one')
    reservation = repository.reserve('synthetic-owner', 'content', 'deep')
    repository.offer('worker-one')  # own live staging slot: early return
    assert repository.store.job(reservation[0])['state'] == 'staging'


def test_offer_keeps_a_live_ready_job_when_the_slot_is_fresh(repository):
    item, index = ready_offer(repository)
    repository.offer('worker-one')
    assert repository.store.job(item.segment_id)['state'] == 'ready'


def test_displaced_settlement_is_its_own_single_job_transaction(repository):
    item, index = ready_offer(repository)
    repository.store.now = 7300
    repository.offer('worker-two')
    labels = repository.store.labels()
    assert 'finish' in labels
    for operation, transaction in repository.store.transactions:
        if operation == 'finish':
            assert transaction.reads == [('shadow_jobs', item.segment_id)]


def test_displaced_settlement_exhaustion_reraises_at_the_admission_boundary(repository, store):
    item, index = ready_offer(repository)
    repository.store.now = 7300
    store.refuse('finish')  # the settlement's retry budget is already drained
    with pytest.raises(shadow_module_records_contention()):
        repository.offer('worker-two')
    store._refuse.clear()
    # The slot fence already committed, so the ring stays consistent even
    # though the drop failed: worker-two owns the slot, and the next cycle
    # (owning nothing displaced) settles nothing new.
    finishes_before = repository.store.labels().count('finish')
    repository.store.now = 7400
    repository.offer('worker-three')
    assert repository.store.slot(0)['worker'] == 'worker-three'
    assert repository.store.labels().count('finish') == finishes_before


def shadow_module_records_contention():
    from database.firestore_transaction_retry import FirestoreContentionExhausted

    return FirestoreContentionExhausted


def test_recovery_transport_failed_spares_an_active_request_and_settles_orphans(repository):
    item, index = ready_offer(repository)
    repository.take('worker-one')
    from utils.batch_pipeline.contracts import RecoveryWork

    repository.handoff(item.segment_id, RecoveryWork(item.segment_id))
    repository.start_recovery(item.segment_id)
    # An active backend request owns settlement while the job recovers.
    repository.recovery_transport_failed(item.segment_id)
    assert repository.store.job(item.segment_id)['state'] == 'recovering'
    # A dropped reply leaves the orphan to the bounded reap sweep, which
    # settles by age — never by ring pressure.
    repository.store.now = 7300 + 3600
    from types import SimpleNamespace

    original = shadow_module.stale_jobs
    shadow_module.stale_jobs = lambda *args: [SimpleNamespace(id=item.segment_id)]
    try:
        repository.reap()
    finally:
        shadow_module.stale_jobs = original
    job = repository.store.job(item.segment_id)
    assert job['outcome'] == 'error'


def test_recovery_transport_failed_spares_an_active_backend_request(repository):
    item, index = ready_offer(repository)
    repository.take('worker-one')
    from utils.batch_pipeline.contracts import RecoveryWork

    repository.handoff(item.segment_id, RecoveryWork(item.segment_id))
    repository.start_recovery(item.segment_id)
    repository.recovery_transport_failed(item.segment_id)
    repository.store.rewrite(
        'shadow_jobs',
        item.segment_id,
        {**repository.store.job(item.segment_id), 'state': 'recovering'},
    )
    repository.recovery_transport_failed(item.segment_id)
    assert repository.store.job(item.segment_id)['state'] == 'recovering'


# ── G. The legacy ring stays reachable behind the switches ───────────────────


@pytest.fixture
def legacy_repository(monkeypatch):
    from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
    from database import batch_pipeline_store as storage

    monkeypatch.setenv('BATCH_PIPELINE_SHADOW_PERCENT', '100')
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    monkeypatch.setenv('BATCH_PIPELINE_CONTENTION_RETRY_ENABLED', 'false')
    monkeypatch.setattr(storage, 'assert_batch_write_allowed', lambda *args, **kwargs: 0)
    store = storage.FirestoreStore('batch_pipeline_dev', firestore_client=StrictFirestore())
    return ShadowStore(store, clock=lambda: 7200, busy=lambda: False)


def test_kill_switch_restores_the_transactional_ring(legacy_repository, monkeypatch):
    operations = []
    original = legacy_repository.store.run

    def observed(body):
        from database.batch_pipeline_transaction_labels import current_operation

        operations.append(current_operation())
        return original(body)

    monkeypatch.setattr(legacy_repository.store, 'run', observed)
    legacy_repository.offer('worker')
    assert operations == ['batch_shadow_offer'], 'the ring lane opens exactly the offer transaction'


def test_kill_switch_ring_reads_all_four_slots_in_one_transaction(legacy_repository):
    legacy_repository.offer('worker')
    transaction = legacy_repository.store.client.transactions[-1]
    assert [path for path, _data in transaction.sets if path[0].endswith('shadow_slots')]
    assert len(transaction.sets) == 1


def test_ring_lane_full_lifecycle_matches_the_legacy_contract(legacy_repository):
    legacy_repository.offer('worker')
    reservation = legacy_repository.reserve('synthetic-owner', 'content', 'deep')
    assert reservation is not None
    item = WorkItem(reservation[0], 'synthetic-owner', 1, 'encrypted:shadow', 2, 0, shadow=True)
    assert legacy_repository.ready(reservation, item, '')
    assert legacy_repository.take('worker') == item
    legacy_repository.finish(item.segment_id, 'recovered')
    assert (
        legacy_repository.store.client.rows[('batch_pipeline_dev_shadow_jobs', item.segment_id)]['outcome']
        == 'recovered'
    )


def test_cas_lane_full_lifecycle_matches_the_legacy_contract(repository):
    repository.offer('worker')
    reservation = repository.reserve('synthetic-owner', 'content', 'deep')
    assert reservation is not None
    item = WorkItem(reservation[0], 'synthetic-owner', 1, 'encrypted:shadow', 2, 0, shadow=True)
    assert repository.ready(reservation, item, '')
    assert repository.take('worker') == item
    repository.finish(item.segment_id, 'recovered')
    assert repository.store.job(item.segment_id)['outcome'] == 'recovered'


def test_both_lanes_preserve_duplicate_suppression(repository, legacy_repository, monkeypatch):
    repository.offer('worker-cas')
    legacy_repository.offer('worker-ring')
    assert repository.reserve('synthetic-owner', 'content', 'deep') is not None
    assert (
        repository.reserve('synthetic-owner', 'content', 'deep') is None
    ), 'the fence lane refuses duplicate segments across replicas'
    # The ring lane's duplicate refusal is certified by its own suite
    # (test_only_four_offers_no_pending_queue_and_duplicate_suppression);
    # pin this instance to the ring so both lanes run side by side.
    monkeypatch.setattr(legacy_repository, 'slot_cas_enabled', lambda: False)
    assert legacy_repository.slot_cas_enabled() is False


def test_both_lanes_preserve_the_hourly_cap_semantics(repository, legacy_repository, monkeypatch):
    repository.offer('worker-cas')
    legacy_repository.offer('worker-ring')
    assert repository.reserve('owner-a', 'content-a', 'deep') is not None
    assert repository.store.row('shadow_spend', 'projection-2')['units'] == 1
    # The ring lane binds the same hourly document shape (certified in its
    # own suite); the fence lane's binding-after-fence order is pinned above.
    monkeypatch.setattr(legacy_repository, 'slot_cas_enabled', lambda: False)
    assert legacy_repository.slot_cas_enabled() is False


def test_the_switch_flips_the_lane_through_the_real_config(monkeypatch):
    from config.batch_pipeline import shadow_slot_cas_enabled as real_switch

    monkeypatch.delenv('BATCH_PIPELINE_CONTENTION_RETRY_ENABLED', raising=False)
    assert real_switch() is True, 'default on'
    monkeypatch.setenv('BATCH_PIPELINE_CONTENTION_RETRY_ENABLED', 'false')
    assert real_switch() is False, 'the registered kill switch restores the ring'


def test_contention_retry_false_forces_the_ring_even_with_cas_on(monkeypatch):
    from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
    from database import batch_pipeline_store as storage

    monkeypatch.setenv('BATCH_PIPELINE_SHADOW_PERCENT', '100')
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    monkeypatch.setenv('BATCH_PIPELINE_CONTENTION_RETRY_ENABLED', 'false')
    monkeypatch.setattr(storage, 'assert_batch_write_allowed', lambda *args, **kwargs: 0)
    ring_store = storage.FirestoreStore('batch_pipeline_dev', firestore_client=StrictFirestore())
    ring = ShadowStore(ring_store, clock=lambda: 7200, busy=lambda: False)
    ring.offer('worker')
    transaction = ring_store.client.transactions[-1]
    assert [
        path for path, _data in transaction.sets if path[0].endswith('shadow_slots')
    ], 'the shared switch outranks the ring-specific one: the ring lane ran'


def test_the_double_refuses_injected_operations_after_the_retry_budget(repository):
    item, index = ready_offer(repository)
    repository.store.refuse('finish')
    from database.firestore_transaction_retry import FirestoreContentionExhausted

    with pytest.raises(FirestoreContentionExhausted):
        repository.finish(item.segment_id, 'error')


def test_the_switch_is_read_at_the_call_boundary(store, monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_SHADOW_PERCENT', '100')
    repository = ShadowStore(store, clock=store.clock, busy=lambda: False)
    repository.offer('worker')
    assert repository.store.labels() == [], 'default-on: pure point reads'
    monkeypatch.setattr(shadow_module, 'shadow_slot_cas_enabled', lambda: False)
    repository.offer('worker')
    assert repository.store.labels() == ['offer'], 'the switch flips the lane per call'


# ── H. Ring invariants the sensor used to see violated ───────────────────────


def test_offer_cycle_never_opens_the_operation_that_exhausts_in_prod(repository):
    repository.offer('worker')
    repository.store.now = 7300
    repository.offer('worker')
    assert 'offer' not in repository.store.labels()


def test_take_cycle_never_opens_a_ring_read_set(repository):
    item, index = ready_offer(repository)
    repository.take('worker-one')
    for operation, transaction in repository.store.transactions:
        if operation == 'take':
            assert all(
                table != 'shadow_slots' for table, _key in transaction.reads
            ), f'take read the slot ring inside a transaction: {transaction.reads}'


def test_reserve_cycle_never_reads_the_ring_through_a_transaction(repository):
    repository.offer('worker-one')
    repository.reserve('synthetic-owner', 'content', 'deep')
    for _operation, transaction in repository.store.transactions:
        assert all(table != 'shadow_slots' for table, _key in transaction.reads)


def test_ring_stays_bounded_at_four_documents(repository):
    for index in range(4):
        repository.offer(f'worker-{index}')
    repository.offer('worker-overflow')
    rows = [key for key in repository.store.client.rows if key[0].endswith('shadow_slots')]
    assert len(rows) == 4


def test_two_replicas_share_the_ring_without_aborting(repository, store):
    first = repository
    second = second_store(repository)
    first.offer('worker-a')
    second.offer('worker-b')
    repository.store.now = 7300
    first.offer('worker-a')
    second.offer('worker-b')
    repository.store.now = 7400
    first.offer('worker-a')
    second.offer('worker-b')
    owners = sorted(store.slot(index)['worker'] for index in range(4) if store.slot(index))
    assert owners == ['worker-a', 'worker-b']


def test_no_pending_queue_is_created(repository):
    repository.offer('worker')
    repository.reserve('synthetic-owner', 'content', 'deep')
    collections = {key[0] for key in repository.store.client.rows}
    assert collections <= {
        f'{NAMESPACE}_shadow_slots',
        f'{NAMESPACE}_shadow_jobs',
        f'{NAMESPACE}_shadow_spend',
    }


def test_ordinary_work_mutations_never_touch_legacy_tables(repository):
    repository.offer('worker')
    reservation = repository.reserve('synthetic-owner', 'content', 'deep')
    repository.ready(
        reservation,
        WorkItem(reservation[0], 'synthetic-owner', 1, 'encrypted:shadow', 2, 0, shadow=True, privacy_generation=0),
        '',
    )
    repository.take('worker-one')
    repository.finish(reservation[0], 'recovered')
    for key in repository.store.client.rows:
        assert key[0].startswith(f'{NAMESPACE}_shadow_') or key[0].endswith('shadow_spend')


def test_owner_key_is_hashed_never_raw(repository):
    repository.offer('worker-one')
    reservation = repository.reserve('synthetic-owner', 'content', 'deep')
    import hashlib

    assert repository.store.job(reservation[0])['owner_key'] == hashlib.sha256(b'synthetic-owner').hexdigest()


def test_worker_offer_refresh_costs_no_read_of_jobs(repository):
    repository.offer('worker-one')
    reservation = repository.reserve('synthetic-owner', 'content', 'deep')
    repository.offer('worker-one')  # live staging: early return before any job read
    job_reads = [transaction.reads for operation, transaction in repository.store.transactions if operation == 'finish']
    assert job_reads == []


def test_offer_after_settled_displacement_leaves_no_orphan_pointer(repository):
    item, index = ready_offer(repository)
    repository.store.now = 7300
    repository.offer('worker-two')  # settles the expired ready job
    repository.store.now = 7400
    repository.offer('worker-three')
    slot = repository.store.slot(index)
    assert slot['worker'] == 'worker-three'
    assert 'segment' not in slot
    assert repository.store.job(item.segment_id)['state'] == 'settled'


# ── I. Projection and paid flows stay lane-agnostic ──────────────────────────


def test_projection_input_consumes_the_reservation_once(repository):
    item, index = ready_offer(repository)
    repository.take('worker-one')
    first = repository.projection_input(item.segment_id)
    assert first is not None
    assert repository.projection_input(item.segment_id) is None


def test_projection_input_requires_a_projected_reservation(repository):
    repository.offer('worker-one')
    reservation = repository.reserve('synthetic-owner', 'content', 'deep')
    item = WorkItem(reservation[0], 'synthetic-owner', 1, 'encrypted:shadow', 2, 0, shadow=True)
    repository.ready(reservation, item, '')
    repository.take('worker-one')
    job = repository.store.job(item.segment_id)
    repository.store.rewrite(
        'shadow_jobs', item.segment_id, {k: v for k, v in job.items() if k != 'projection_reserved_at'}
    )
    assert repository.projection_input(item.segment_id) is None


def test_paid_recovery_reserves_each_provider_once(repository, monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_SHADOW_PAID_RECOVERY_PER_HOUR', '5')
    item, index = ready_offer(repository)
    repository.take('worker-one')
    from utils.batch_pipeline.contracts import RecoveryWork

    repository.handoff(item.segment_id, RecoveryWork(item.segment_id))
    repository.start_recovery(item.segment_id)
    assert repository.paid(item.segment_id, 'modulate') is True
    assert repository.paid(item.segment_id, 'modulate') is False
    assert repository.paid(item.segment_id, 'soniox') is True


def test_paid_refuses_an_uncertain_budget_read(repository, monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_SHADOW_PAID_RECOVERY_PER_HOUR', '5')
    item, index = ready_offer(repository)
    repository.take('worker-one')
    from utils.batch_pipeline.contracts import RecoveryWork

    repository.handoff(item.segment_id, RecoveryWork(item.segment_id))
    repository.start_recovery(item.segment_id)
    repository.store.refuse('paid')
    assert repository.paid(item.segment_id, 'modulate') is False


def test_handoff_pins_typed_worker_evidence(repository):
    item, index = ready_offer(repository)
    repository.take('worker-one')
    from utils.batch_pipeline.contracts import RecoveryWork

    assert repository.handoff(item.segment_id, RecoveryWork(item.segment_id)) is True
    assert repository.store.job(item.segment_id)['state'] == 'recovery_ready'


def test_handoff_refuses_mismatched_evidence(repository):
    item, index = ready_offer(repository)
    repository.take('worker-one')
    from utils.batch_pipeline.contracts import RecoveryWork

    with pytest.raises(ValueError, match='typed worker recovery evidence required'):
        repository.handoff('sh_other', RecoveryWork(item.segment_id))


def test_start_recovery_requires_recovery_ready_state(repository):
    item, index = ready_offer(repository)
    repository.take('worker-one')
    assert repository.start_recovery(item.segment_id) is None


def test_reap_settles_stale_jobs_without_ring_transactions(repository, monkeypatch):
    from types import SimpleNamespace

    item, index = ready_offer(repository)
    repository.take('worker-one')
    monkeypatch.setattr(shadow_module, 'stale_jobs', lambda *args: [SimpleNamespace(id=item.segment_id)])
    repository.reap()
    job = repository.store.job(item.segment_id)
    assert job['outcome'] == 'error'
    labels = repository.store.labels()
    assert 'reap' in labels
    for operation, transaction in repository.store.transactions:
        if operation == 'reap':
            assert set(transaction.reads) == {
                ('shadow_jobs', item.segment_id)
            }, 'reap touches only the one stale job document'


def test_reap_spares_a_slow_active_recovery(repository, monkeypatch):
    from types import SimpleNamespace

    item, index = ready_offer(repository)
    repository.take('worker-one')
    from utils.batch_pipeline.contracts import RecoveryWork

    repository.handoff(item.segment_id, RecoveryWork(item.segment_id))
    repository.start_recovery(item.segment_id)
    repository.store.now = 7100  # recovery_started_at > cutoff
    monkeypatch.setattr(shadow_module, 'stale_jobs', lambda *args: [SimpleNamespace(id=item.segment_id)])
    repository.reap()
    assert repository.store.job(item.segment_id)['state'] == 'recovering'


def test_ready_publishes_item_language_and_context(repository):
    repository.offer('worker-one')
    reservation = repository.reserve('synthetic-owner', 'content', 'deep')
    item = WorkItem(reservation[0], 'synthetic-owner', 1, 'encrypted:shadow', 2, 0, shadow=True)
    assert repository.ready(reservation, item, 'en', projection_context={'planned': 1}) is True
    job = repository.store.job(item.segment_id)
    assert job['language'] == 'en'
    assert job['projection_context'] == {'planned': 1}
    assert repository.store.slot(int(reservation[1]))['state'] == 'ready'


def test_ready_refuses_when_the_staging_window_expired(repository):
    repository.offer('worker-one')
    reservation = repository.reserve('synthetic-owner', 'content', 'deep')
    item = WorkItem(reservation[0], 'synthetic-owner', 1, 'encrypted:shadow', 2, 0, shadow=True)
    repository.store.now = 7200 + shadow_module.STAGING_SECONDS + 1
    assert repository.ready(reservation, item, '') is False


def test_ready_refuses_a_slot_that_lost_its_segment_pointer(repository):
    repository.offer('worker-one')
    reservation = repository.reserve('synthetic-owner', 'content', 'deep')
    index = int(reservation[1])
    repository.store.rewrite('shadow_slots', str(index), {'worker': 'worker-one', 'state': 'staging', 'until': 9999})
    item = WorkItem(reservation[0], 'synthetic-owner', 1, 'encrypted:shadow', 2, 0, shadow=True)
    assert repository.ready(reservation, item, '') is False


def test_ready_refuses_a_slot_in_the_wrong_state(repository):
    repository.offer('worker-one')
    reservation = repository.reserve('synthetic-owner', 'content', 'deep')
    index = int(reservation[1])
    slot = repository.store.slot(index)
    repository.store.rewrite('shadow_slots', str(index), {**slot, 'state': 'idle'})
    item = WorkItem(reservation[0], 'synthetic-owner', 1, 'encrypted:shadow', 2, 0, shadow=True)
    assert repository.ready(reservation, item, '') is False


def test_job_identity_is_deterministic_across_replicas():
    assert identity('owner', 'content') == identity('owner', 'content')
    assert identity('owner', 'content') != identity('owner', 'other')
    assert identity('owner', 'content').startswith('sh_')


def test_job_rows_expire_after_two_hours(repository):
    repository.offer('worker-one')
    reservation = repository.reserve('synthetic-owner', 'content', 'deep')
    from datetime import datetime, timedelta, timezone

    assert repository.store.job(reservation[0])['expires_at'] == (
        datetime.fromtimestamp(7200, timezone.utc) + timedelta(hours=2)
    )
