"""Contract (b) ``Outbox`` conformance: the invariants every implementation must keep.

Backends: ``sim`` (reference model, ``testing/outbox_sim.py``), ``postgres`` (``database/jobstore/outbox_pg.py``)
and ``emulator`` (lane 9's Firestore outbox; skipped until ``database/outbox_firestore.py`` lands and
``testing/store_fixtures.build_outbox_backend`` constructs it). Invariant numbers refer to contracts.md (b).
A skip proves nothing: run with ``OMI_REQUIRE_STORE_BACKENDS=...`` when a result is claimed.

Invariant 4 lets ``enqueue`` without ``tx`` create its own wake (Firestore does; sim and Postgres leave it to
the caller), so assertions about ``ob.wakes`` look only at wakes made after the step under test.
"""

from __future__ import annotations

import dataclasses

import pytest

from database.outbox import Claim, Outcome
from testing.store_fixtures import outbox_backend  # noqa: F401

pytestmark = pytest.mark.integration

T0 = 1000.0
LEASE = 120.0


@pytest.fixture
def ob(outbox_backend):  # noqa: F811
    outbox_backend.store_harness.seed_user('o')
    return outbox_backend


def uid(ob):
    return ob.store_harness.uid('o')


def put(ob, key='k', *, at=T0, now=T0, **kw):
    """Enqueue ``key``. ``ob.key`` / ``ob.payload`` adapt generic labels to a backend's row shape (the
    Firestore enrichment outbox keys rows by (owner, conversation) and carries conversation_id + language)."""
    owner = kw.pop('owner', None) or uid(ob)
    extra = kw.pop('payload', None) or {}
    return ob.outbox.enqueue(ob.key(owner, key), owner, ob.payload(key, **extra), at, now=now, **kw)


def take(ob, key='k', *, at=T0, now=T0, lease=LEASE):
    """Enqueue then claim by the delivered wake token, as a Cloud Tasks push would."""
    queued = put(ob, key, at=at, now=now)
    claim = ob.outbox.claim_key(queued.row_id, queued.wake_token, lease, now=now)
    assert isinstance(claim, Claim)
    ob.wakes.clear()  # the enqueue's own wake; callers assert on the wakes that follow
    return queued, claim


# 1. Fencing ---------------------------------------------------------------------------------------
def test_foreign_or_unknown_lease_token_changes_nothing(ob):
    _, claim = take(ob)
    forged = dataclasses.replace(claim, lease_token='forged')
    assert not ob.outbox.heartbeat(forged, LEASE, now=T0 + 1)
    assert not ob.outbox.ack(forged, 'done', now=T0 + 1)
    assert ob.outbox.defer(forged, T0 + 50, 'later', now=T0 + 1) is None
    assert not ob.outbox.release(forged, 'retry', now=T0 + 1)
    assert ob.outbox.ack(claim, 'done', now=T0 + 2)  # the real holder is unaffected


def test_heartbeat_extends_a_live_lease_and_refuses_an_expired_one(ob):
    _, claim = take(ob)
    assert ob.outbox.heartbeat(claim, LEASE, now=T0 + 100)
    assert ob.outbox.claim(1, LEASE, now=T0 + 150) == []  # extended to T0+220: still held
    assert not ob.outbox.heartbeat(claim, LEASE, now=T0 + 300)  # expired


def test_a_claim_taken_after_expiry_fences_the_old_holder(ob):
    queued, old = take(ob)
    (new,) = ob.outbox.claim(1, LEASE, now=T0 + LEASE + 1)
    assert new.lease_token != old.lease_token and new.attempt == 2
    assert not ob.outbox.ack(old, 'done', now=T0 + LEASE + 2)
    assert not ob.outbox.heartbeat(old, LEASE, now=T0 + LEASE + 2)
    assert ob.outbox.ack(new, 'done', now=T0 + LEASE + 2)
    assert not ob.outbox.ack(new, 'done', now=T0 + LEASE + 3)  # already closed


def test_a_live_lease_blocks_pull_claims(ob):
    take(ob)
    assert ob.outbox.claim(5, LEASE, now=T0 + 10) == []


# 2. Wake dedupe -------------------------------------------------------------------------------------
def test_wrong_wake_token_and_unknown_rows_are_stale(ob):
    queued = put(ob)
    assert ob.outbox.claim_key(queued.row_id, 'not-the-token', LEASE, now=T0) is Outcome.STALE
    assert ob.outbox.claim_key('999999', queued.wake_token, LEASE, now=T0) is Outcome.STALE
    assert ob.outbox.claim_key('not-a-number', queued.wake_token, LEASE, now=T0) is Outcome.STALE
    assert isinstance(ob.outbox.claim_key(queued.row_id, queued.wake_token, LEASE, now=T0), Claim)


def test_a_live_foreign_lease_is_busy_not_stale(ob):
    queued, _ = take(ob)
    assert ob.outbox.claim_key(queued.row_id, queued.wake_token, LEASE, now=T0 + 5) is Outcome.BUSY


def test_defer_mints_a_new_wake_token_and_old_deliveries_go_stale(ob):
    queued, claim = take(ob)
    new_token = ob.outbox.defer(claim, T0 + 500, 'not_due', now=T0 + 1)
    assert new_token and new_token != queued.wake_token
    assert ob.wakes[-1] == (queued.row_id, new_token, T0 + 500)  # the outbox owns wake creation on defer
    assert ob.outbox.claim_key(queued.row_id, queued.wake_token, LEASE, now=T0 + 2) is Outcome.STALE
    again = ob.outbox.claim_key(queued.row_id, new_token, LEASE, now=T0 + 500)
    assert isinstance(again, Claim) and again.attempt == 2
    assert ob.outbox.claim(1, LEASE, now=T0 + 400) == []  # deferred rows are not due before available_at


def test_release_keeps_the_wake_token_so_the_same_delivery_can_retry(ob):
    queued, claim = take(ob)
    assert ob.outbox.release(claim, 'transient', now=T0 + 1)
    again = ob.outbox.claim_key(queued.row_id, queued.wake_token, LEASE, now=T0 + 2)
    assert isinstance(again, Claim) and again.attempt == 2
    assert not ob.outbox.ack(claim, 'done', now=T0 + 3)  # the released lease no longer fences anything


def test_a_not_due_delivery_is_deferred_and_rearmed_by_the_outbox(ob):
    queued = put(ob, at=T0 + 300)
    assert ob.wakes == [(queued.row_id, queued.wake_token, T0 + 300)]  # the enqueue's own wake
    ob.wakes.clear()
    assert ob.outbox.claim_key(queued.row_id, queued.wake_token, LEASE, now=T0) is Outcome.DEFERRED
    ((row_id, fresh, at),) = ob.wakes
    assert (row_id, at) == (queued.row_id, T0 + 300) and fresh != queued.wake_token
    assert ob.outbox.claim_key(queued.row_id, queued.wake_token, LEASE, now=T0 + 1) is Outcome.STALE
    claim = ob.outbox.claim_key(queued.row_id, fresh, LEASE, now=T0 + 300)
    assert isinstance(claim, Claim) and claim.attempt == 1  # a deferral is not a processing attempt


def test_wake_is_idempotent_and_ignores_stale_tokens_and_closed_rows(ob):
    queued = put(ob)
    ob.outbox.wake(queued.row_id, queued.wake_token)
    ob.outbox.wake(queued.row_id, queued.wake_token)  # safe to repeat: task names make the create idempotent
    assert {w[:2] for w in ob.wakes} == {(queued.row_id, queued.wake_token)}
    ob.wakes.clear()
    ob.outbox.wake(queued.row_id, 'stale-token')
    ob.outbox.wake('999999', queued.wake_token)
    assert ob.wakes == []
    claim = ob.outbox.claim_key(queued.row_id, queued.wake_token, LEASE, now=T0)
    assert isinstance(claim, Claim) and ob.outbox.ack(claim, 'done', now=T0 + 1)
    ob.outbox.wake(queued.row_id, queued.wake_token)
    assert ob.wakes == []


# 3. Idempotent enqueue ---------------------------------------------------------------------------------
def test_same_key_coalesces_into_one_row_and_never_a_second(ob):
    first = put(ob, at=T0 + 10)
    second = put(ob, at=T0 + 10)
    assert not first.coalesced and second.coalesced and second.row_id == first.row_id
    assert second.wake_token is None  # nothing moved: the existing wake is still right
    assert len(ob.outbox.claim(10, LEASE, now=T0 + 20)) == 1


def test_max_coalescing_settles_later_and_min_coalescing_pulls_earlier(ob):
    a = put(ob, 'settle', at=T0 + 10, coalesce='max')
    b = put(ob, 'settle', at=T0 + 60, coalesce='max')
    assert b.coalesced and b.row_id == a.row_id and b.wake_token != a.wake_token
    # A later settle may keep the old wake (reprocess.mark rules): delivered early, it never claims.
    assert ob.outbox.claim_key(a.row_id, a.wake_token, LEASE, now=T0 + 30) in (Outcome.STALE, Outcome.DEFERRED)
    assert ob.outbox.claim(10, LEASE, now=T0 + 30) == []  # not due at the old time
    c = put(ob, 'deadline', at=T0 + 600, coalesce='min')
    d = put(ob, 'deadline', at=T0 + 120, coalesce='min')
    e = put(ob, 'deadline', at=T0 + 900, coalesce='min')  # a later settle never extends a first-summary deadline
    assert d.wake_token and e.wake_token is None and c.row_id == d.row_id == e.row_id
    assert [x.row_id for x in ob.outbox.claim(10, LEASE, now=T0 + 119)] == [b.row_id]  # 'settle' is due at +60
    assert [x.row_id for x in ob.outbox.claim(10, LEASE, now=T0 + 120)] == [c.row_id]  # the deadline, not +900


def test_enqueue_after_the_row_closed_starts_a_fresh_row(ob):
    _, claim = take(ob)
    assert ob.outbox.ack(claim, 'done', now=T0 + 1)
    again = put(ob, now=T0 + 2, at=T0 + 2)
    assert not again.coalesced
    assert [c.row_id for c in ob.outbox.claim(5, LEASE, now=T0 + 3)] == [again.row_id]


def test_claim_carries_owner_payload_policy_and_attempt(ob):
    queued = put(ob, 'c1', policy_id='pol-1')
    (claim,) = ob.outbox.claim(1, LEASE, now=T0)
    assert (claim.row_id, claim.owner_id, claim.policy_id, claim.attempt) == (queued.row_id, uid(ob), 'pol-1', 1)
    assert claim.payload['conversation_id'] == 'c1' and claim.wake_token == ''
    assert claim.lease_until == T0 + LEASE and claim.kind == ob.outbox.kind


def test_pull_claims_are_ordered_by_due_time_limited_and_skip_future_rows(ob):
    ids = [put(ob, f'k{i}', at=T0 + 10 - i).row_id for i in range(4)]  # k3 is due first
    put(ob, 'future', at=T0 + 5000)
    claimed = ob.outbox.claim(3, LEASE, now=T0 + 100)
    assert [c.row_id for c in claimed] == [ids[3], ids[2], ids[1]]
    assert [c.row_id for c in ob.outbox.claim(10, LEASE, now=T0 + 100)] == [ids[0]]


def test_payload_must_be_small_and_content_free(ob):
    with pytest.raises(ValueError):
        put(ob, payload={'blob': 'x' * 5000})  # a content-free payload never carries blobs


# 4/5. Durable before wake; transactional enqueue ------------------------------------------------------------
def test_tx_enqueue_commits_with_the_store_transaction(ob):
    results = ob.run_tx(lambda tx: put(ob, 'tx-ok', tx=tx))
    assert not results.coalesced
    assert [c.row_id for c in ob.outbox.claim(5, LEASE, now=T0)] == [results.row_id]


def test_tx_enqueue_rolls_back_with_the_store_transaction(ob):
    def body(tx):
        tx.put('owners', 'x', {'v': 1})
        put(ob, 'tx-gone', tx=tx)
        raise KeyError('boom')

    with pytest.raises(KeyError):
        ob.run_tx(body)
    assert ob.outbox.claim(5, LEASE, now=T0) == []
    assert ob.store_harness.store.run(lambda tx: tx.get('owners', 'x')) == {}


def test_enqueue_without_tx_commits_then_creates_its_own_wake(ob):
    # M1 L12-3, invariant 4: the caller follows the protocol and never calls wake() after a non-tx enqueue.
    queued = put(ob, at=T0 + 10)
    assert ob.wakes == [(queued.row_id, queued.wake_token, T0 + 10)]
    assert ob.outbox.sweep(now=T0 + 1).rewoken == 0  # nothing left pending for the sweep
    moved = put(ob, at=T0 + 20)  # 'max' coalescing moves the row: a new token, woken by the outbox again
    assert moved.coalesced and ob.wakes[-1] == (queued.row_id, moved.wake_token, T0 + 20)
    still = put(ob, at=T0 + 15)  # does not move: no token, no wake
    assert still.wake_token is None and len(ob.wakes) == 2


def test_wake_holds_no_pooled_connection_across_the_task_create(ob):
    # M1 L12-5: the pool (<= 4) is shared with PostgresStore; four slow task creates must not pin it.
    if ob.name != 'postgres':
        pytest.skip('connection-pool behaviour of the Postgres outbox')
    slots = ob.outbox.store.pool._slots
    free_during_create = []
    inner = ob.outbox.create_wake
    ob.outbox.create_wake = lambda *args: (free_during_create.append(slots._value), inner(*args))
    put(ob)
    assert free_during_create == [slots._initial_value] and len(ob.wakes) == 1


def test_a_failed_caller_wake_after_a_tx_enqueue_is_retried_by_sweep(ob):
    queued = ob.run_tx(lambda tx: put(ob, tx=tx))  # durable first; the caller's wake() after commit then fails
    assert ob.wakes == []  # with tx the caller owns the wake
    ob.fail_wakes[0] = True
    with pytest.raises(RuntimeError):
        ob.outbox.wake(queued.row_id, queued.wake_token)
    assert ob.outbox.sweep(now=T0 + 1).errors == 1
    ob.fail_wakes[0] = False
    assert ob.outbox.sweep(now=T0 + 2).rewoken == 1
    assert ob.wakes == [(queued.row_id, queued.wake_token, T0)]


def test_a_failed_wake_leaves_the_row_pending_and_sweep_retries_it(ob):
    ob.fail_wakes[0] = True
    queued = put(ob)  # durable first; the outbox's own wake after commit fails and is not raised
    assert ob.wakes == []
    with pytest.raises(RuntimeError):
        ob.outbox.wake(queued.row_id, queued.wake_token)
    counts = ob.outbox.sweep(now=T0 + 1)
    assert (counts.errors, counts.rewoken) == (1, 0) and ob.wakes == []
    ob.fail_wakes[0] = False
    counts = ob.outbox.sweep(now=T0 + 2)
    assert (counts.errors, counts.rewoken) == (0, 1)
    assert ob.wakes == [(queued.row_id, queued.wake_token, T0)]  # same token: the task name stays stable
    assert ob.outbox.sweep(now=T0 + 3).rewoken == 0  # delivered: nothing pending any more
    assert isinstance(ob.outbox.claim_key(queued.row_id, queued.wake_token, LEASE, now=T0 + 4), Claim)


def test_a_failed_wake_on_defer_does_not_lose_the_deferral(ob):
    _, claim = take(ob)
    ob.wakes.clear()
    ob.fail_wakes[0] = True
    token = ob.outbox.defer(claim, T0 + 50, 'later', now=T0 + 1)
    assert token and ob.wakes == []
    ob.fail_wakes[0] = False
    assert ob.outbox.sweep(now=T0 + 50).rewoken == 1  # by the deferred time at the latest
    assert ob.wakes == [(claim.row_id, token, T0 + 50)]


# Sweep: expired leases are re-woken under a new token -----------------------------------------------------------
def test_sweep_rewakes_an_expired_lease_under_a_new_token(ob):
    queued, claim = take(ob)
    ob.wakes.clear()
    assert ob.outbox.sweep(now=T0 + 10).expired_leases == 0  # a live lease is left alone
    assert ob.wakes == []
    counts = ob.outbox.sweep(now=T0 + LEASE + 1)
    assert (counts.expired_leases, counts.rewoken, counts.errors) == (1, 1, 0)
    ((row_id, token, _),) = ob.wakes
    assert row_id == queued.row_id and token != queued.wake_token
    assert ob.outbox.claim_key(queued.row_id, queued.wake_token, LEASE, now=T0 + LEASE + 2) is Outcome.STALE
    new = ob.outbox.claim_key(row_id, token, LEASE, now=T0 + LEASE + 2)
    assert isinstance(new, Claim) and not ob.outbox.ack(claim, 'done', now=T0 + LEASE + 3)


def test_sweep_pages_only_actionable_rows(ob):
    # M1 L12-2: earlier-due, already-woken rows (the normal push backlog) must not fill the page and hide a
    # failed wake or an expired lease.
    if ob.name == 'emulator':
        pytest.skip('the Firestore sweep pages through utils.enrichment.outbox.sweep, not this predicate')
    for i in range(4):
        put(ob, f'healthy-{i}', at=T0 - 100 + i)
    ob.fail_wakes[0] = True
    pending = put(ob, 'pending', at=T0)
    ob.fail_wakes[0] = False
    _, leased = take(ob, 'leased', at=T0)
    counts = ob.outbox.sweep(now=T0 + LEASE + 1, limit=2)
    assert (counts.rewoken, counts.expired_leases, counts.discarded, counts.errors) == (2, 1, 0, 0)
    assert {w[0] for w in ob.wakes} == {pending.row_id, leased.row_id}


# 6. Privacy ------------------------------------------------------------------------------------------------------------
def test_blocked_owner_rows_are_discarded_by_claim(ob):
    put(ob)
    ob.store_harness.customer.block_privacy(uid(ob))
    assert ob.outbox.claim(5, LEASE, now=T0) == []
    ob.store_harness.customer.add_user(uid(ob))  # even if the fence were lifted, the row is closed
    assert ob.outbox.claim(5, LEASE, now=T0 + 1) == []


def test_blocked_owner_is_discarded_on_delivery_and_by_sweep(ob):
    queued = put(ob, 'by-key')
    ob.fail_wakes[0] = True  # the sweep acts on rows whose wake is still pending
    other = put(ob, 'by-sweep', at=T0 + 1)
    ob.fail_wakes[0] = False
    ob.store_harness.customer.block_privacy(uid(ob))
    assert ob.outbox.claim_key(queued.row_id, queued.wake_token, LEASE, now=T0) is Outcome.DISCARDED
    assert ob.outbox.sweep(now=T0 + 5).discarded == 1
    assert ob.outbox.claim_key(other.row_id, other.wake_token, LEASE, now=T0 + 6) is Outcome.STALE


def test_deleted_conversation_in_the_payload_discards_the_row(ob):
    ob.store_harness.customer.add_conversation(uid(ob), 'gone')
    ob.store_harness.customer.delete_conversation(uid(ob), 'gone')
    ob.store_harness.customer.add_conversation(uid(ob), 'live')
    put(ob, 'gone')
    put(ob, 'live')
    assert [c.payload['conversation_id'] for c in ob.outbox.claim(5, LEASE, now=T0)] == ['live']
