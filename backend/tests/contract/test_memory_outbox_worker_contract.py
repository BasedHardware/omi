"""Dual-backend contract for the canonical memory outbox worker (ADR-0044 facade + ADR-0002 port).

`database/memory_outbox_worker.py` is a leased work queue: a tick claims due events, performs the
side effect, then acknowledges. Everything that keeps two workers from doing the same work twice is
one shape.

    transaction   `_claim_event_transaction` re-reads the event INSIDE the transaction and refuses
                  unless it is still claimable; `_ack_event_transaction` re-reads and refuses unless
                  the caller still holds the lease at the same epoch. Without the read, two workers
                  lease the same event and both run its side effect — the memory is indexed twice, or
                  a stale worker's `delivered` ack retires an event the live worker is still working
                  on, and the delivery is silently lost.

The module carries its own compatibility branch worth pinning here: `_run_transaction` dispatches on
`transaction.__class__.__module__.startswith("google.cloud.firestore")`, taking the SDK's
`@transactional` decorator on one side and driving `_begin`/`_commit`/`_rollback` by hand on the
other. That branch is only ever exercised on ONE side per deployment, so a suite that ran on a single
backend would leave the other half unproven — which is the whole reason this file is parametrized.

Binding and skip rules: the shared ``bind_store`` fixture in ``conftest.py``. Every test runs TWICE.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

NOW = datetime(2026, 7, 1, 12, 0, tzinfo=timezone.utc)
PAST = NOW - timedelta(minutes=5)
FUTURE = NOW + timedelta(hours=1)


def _client():
    """The client this backend actually deploys, as the fixture bound it.

    Resolved through the accessor rather than imported at module load: `bind_store` patches
    `_client.get_firestore_client`, so a name bound at import time would keep pointing at the real
    one — the exact blind spot the conftest docstring records.
    """
    from database import _client as client_module

    return client_module.get_firestore_client()


def _event(event_id: str, *, status: str = 'pending', available_at=PAST, **overrides):
    data = {
        'event_id': event_id,
        'event_type': 'projection_sync',
        'status': status,
        'available_at': available_at,
        'commit_sequence': 1,
        'memory_id': f'mem-{event_id}',
        'attempt_count': 0,
        'updated_at': PAST,
    }
    data.update(overrides)
    return data


@pytest.fixture
def outbox(bind_store):
    run = uuid.uuid4().hex[:8]
    uid = f'outbox-{run}'
    paths: list[str] = []

    def seed(event_id: str, **overrides) -> str:
        path = f'users/{uid}/memory_outbox/{event_id}'
        bind_store.set(path, _event(event_id, **overrides))
        paths.append(path)
        return path

    yield {'uid': uid, 'run': run, 'store': bind_store, 'seed': seed, 'paths': paths}

    for path in paths:
        bind_store.delete(path)


def _raw(outbox, event_id):
    stored = outbox['store'].get(f"users/{outbox['uid']}/memory_outbox/{event_id}")
    return stored.data if stored is not None and stored.exists else None


def _lease(outbox, worker_id, **kwargs):
    import database.memory_outbox_worker as worker

    return worker.lease_canonical_memory_outbox_events(
        db_client=_client(), uid=outbox['uid'], worker_id=worker_id, now=NOW, **kwargs
    )


# --- transaction: the claim ---------------------------------------------------------------------


def test_a_due_event_is_leased_and_marked_processing(outbox):
    outbox['seed'](f"e1-{outbox['run']}")

    (leased,) = _lease(outbox, 'worker-a')

    assert leased.document_id == f"e1-{outbox['run']}"
    assert leased.lease_epoch == 1
    stored = _raw(outbox, f"e1-{outbox['run']}")
    assert stored['status'] == 'processing'
    assert stored['lease_owner'] == 'worker-a'


def test_a_second_worker_cannot_lease_an_event_that_is_already_leased(outbox):
    """The invariant the in-transaction read exists for. Without it the second worker overwrites the
    first owner and both run the side effect — the memory is indexed twice, and a `delivered` ack from
    whichever finishes second retires work the other never completed."""
    outbox['seed'](f"e1-{outbox['run']}")

    first = _lease(outbox, 'worker-a')
    second = _lease(outbox, 'worker-b')

    assert len(first) == 1
    assert second == [], 'a leased event must not be handed to a second worker'
    assert _raw(outbox, f"e1-{outbox['run']}")['lease_owner'] == 'worker-a', 'the incumbent keeps it'


def test_an_event_that_is_not_due_yet_is_left_alone(outbox):
    """`available_at` is the retry backoff. Leasing early turns a backoff into a hot loop."""
    outbox['seed'](f"later-{outbox['run']}", available_at=FUTURE)

    assert _lease(outbox, 'worker-a') == []


def test_an_expired_lease_is_reclaimed_with_a_higher_epoch(outbox):
    """A worker that died mid-event must not strand it. The epoch bump is what makes the dead
    worker's later ack refusable — see the fencing test below."""
    outbox['seed'](
        f"stale-{outbox['run']}",
        status='processing',
        lease_owner='worker-dead',
        lease_epoch=3,
        lease_expires_at=PAST,
    )

    (leased,) = _lease(outbox, 'worker-b')

    assert leased.lease_epoch == 4
    assert _raw(outbox, f"stale-{outbox['run']}")['lease_owner'] == 'worker-b'


def test_a_live_lease_held_by_someone_else_is_not_stolen(outbox):
    outbox['seed'](
        f"live-{outbox['run']}",
        status='processing',
        lease_owner='worker-a',
        lease_epoch=1,
        lease_expires_at=FUTURE,
    )

    assert _lease(outbox, 'worker-b') == []


def test_an_unsupported_event_type_is_never_leased(outbox):
    """The same collection carries the vector-repair worker's records. Leasing one here would run the
    wrong side effect against it — see test_memory_vector_repair_outbox_worker_contract.py."""
    outbox['seed'](f"foreign-{outbox['run']}", event_type='vector_repair_purge')

    assert _lease(outbox, 'worker-a') == []


def test_the_claim_stops_at_the_limit(outbox):
    for index in range(4):
        outbox['seed'](f'e{index}-{outbox["run"]}', available_at=PAST + timedelta(seconds=index))

    leased = _lease(outbox, 'worker-a', limit=2)

    assert len(leased) == 2
    still_pending = [e for e in (_raw(outbox, f'e{i}-{outbox["run"]}') for i in range(4)) if e['status'] == 'pending']
    assert len(still_pending) == 2, 'the other two must stay claimable'


# --- transaction: the ack -----------------------------------------------------------------------


def test_the_lease_holder_can_acknowledge(outbox):
    """`_ack_leased_event` is private, but it is the only caller of the second transaction and the tick
    that wraps it performs real side effects (vector indexing, search projection) that have no place in
    a storage contract. Driving the seam directly is deliberate."""
    import database.memory_outbox_worker as worker

    outbox['seed'](f"ack-{outbox['run']}")
    (leased,) = _lease(outbox, 'worker-a')

    assert worker._ack_leased_event(db_client=_client(), lease=leased, patch={'status': 'delivered'}) is True
    assert _raw(outbox, f"ack-{outbox['run']}")['status'] == 'delivered'


def test_an_ack_from_a_worker_that_lost_the_lease_is_refused(outbox):
    """Fencing. A worker whose lease expired, whose event was reclaimed, and which then finishes its
    side effect must NOT be able to write `delivered` — that would retire an event the new owner is
    still processing, and the delivery disappears with no error anywhere."""
    import database.memory_outbox_worker as worker

    outbox['seed'](f"fence-{outbox['run']}", lease_expires_at=PAST)
    (stale_lease,) = _lease(outbox, 'worker-a')

    # The lease expires and worker-b reclaims it, bumping the epoch.
    outbox['store'].set(
        f"users/{outbox['uid']}/memory_outbox/fence-{outbox['run']}",
        {**_raw(outbox, f"fence-{outbox['run']}"), 'lease_expires_at': PAST},
    )
    (new_lease,) = _lease(outbox, 'worker-b')
    assert new_lease.lease_epoch > stale_lease.lease_epoch

    assert worker._ack_leased_event(db_client=_client(), lease=stale_lease, patch={'status': 'delivered'}) is False
    stored = _raw(outbox, f"fence-{outbox['run']}")
    assert stored['status'] == 'processing', 'the stale worker must not retire the new owner\'s event'
    assert stored['lease_owner'] == 'worker-b'


def test_an_ack_for_an_event_that_no_longer_exists_is_refused_rather_than_raising(outbox):
    """Acks run after a side effect that may have taken minutes; the event may have been purged with
    the account. The worker must record the ambiguity, not crash the tick."""
    import database.memory_outbox_worker as worker

    outbox['seed'](f"gone-{outbox['run']}")
    (leased,) = _lease(outbox, 'worker-a')
    outbox['store'].delete(f"users/{outbox['uid']}/memory_outbox/gone-{outbox['run']}")

    assert worker._ack_leased_event(db_client=_client(), lease=leased, patch={'status': 'delivered'}) is False


# --- transaction: the races the sequential tests above cannot reach -------------------------------
#
# The three tests below exist because mutation testing said the ones above were not enough. Removing
# the in-transaction claimability check, the epoch fence, or the owner fence all SURVIVED the first
# version of this suite — not because the guards do nothing, but because in a sequential test the
# candidate query already filters the event out, and in a cross-worker ack the owner and epoch checks
# each catch the case alone. Each guard needs the scenario that only it can catch.


def test_a_candidate_claimed_between_the_scan_and_the_transaction_is_not_stolen(outbox):
    """The TOCTOU the in-transaction read is FOR.

    `lease_canonical_memory_outbox_events` streams candidates first and claims them one at a time, so
    a candidate can be claimed by another worker in between. The query cannot protect against that —
    it already ran. Only the re-read inside the transaction can.

    Simulated deterministically rather than with threads: `_run_transaction` is wrapped so the
    competing claim lands after the scan and before the transaction, which is exactly the interleaving
    a race produces and the only one that matters. (A ThreadPoolExecutor version of a test like this
    passed with the guard removed — it never actually raced.)
    """
    import database.memory_outbox_worker as worker

    event_id = f"race-{outbox['run']}"
    path = outbox['seed'](event_id)
    original = worker._run_transaction
    fired = []

    def claim_first_then_run(db_client, callback, *args):
        if not fired:
            fired.append(True)
            outbox['store'].set(
                path,
                {
                    **_raw(outbox, event_id),
                    'status': 'processing',
                    'lease_owner': 'worker-b',
                    'lease_epoch': 1,
                    'lease_expires_at': FUTURE,
                },
            )
        return original(db_client, callback, *args)

    worker._run_transaction = claim_first_then_run
    try:
        leased = _lease(outbox, 'worker-a')
    finally:
        worker._run_transaction = original

    assert fired, 'the wrapper never ran — the test proves nothing'
    assert leased == [], 'the event was claimed after the scan; the transaction must refuse it'
    assert _raw(outbox, event_id)['lease_owner'] == 'worker-b'


def test_the_same_worker_cannot_acknowledge_with_a_lease_it_has_already_superseded(outbox):
    """What the EPOCH fence catches and the owner fence cannot: one worker, two generations.

    A worker whose lease expired and which then reclaims the same event — after a restart, or from a
    second thread — matches on `lease_owner`. Only the epoch tells the two generations apart. Without
    it the older generation's ack retires an event the newer one is still processing.
    """
    import database.memory_outbox_worker as worker

    event_id = f"gen-{outbox['run']}"
    outbox['seed'](event_id, lease_expires_at=PAST)
    (first_generation,) = _lease(outbox, 'worker-a')

    outbox['store'].set(
        f"users/{outbox['uid']}/memory_outbox/{event_id}",
        {**_raw(outbox, event_id), 'lease_expires_at': PAST},
    )
    (second_generation,) = _lease(outbox, 'worker-a')

    assert second_generation.worker_id == first_generation.worker_id
    assert second_generation.lease_epoch > first_generation.lease_epoch

    assert worker._ack_leased_event(db_client=_client(), lease=first_generation, patch={'status': 'delivered'}) is False
    assert _raw(outbox, event_id)['status'] == 'processing'
    assert worker._ack_leased_event(db_client=_client(), lease=second_generation, patch={'status': 'delivered'}) is True


def test_an_ack_carrying_the_right_epoch_but_the_wrong_owner_is_refused(outbox):
    """What the OWNER fence catches and the epoch fence cannot.

    The lease object is a plain dataclass the caller constructs; the fence must not assume the caller
    is honest about who it is. Here the epoch is the current one and only the name is wrong — a shape
    a restarted or misconfigured worker produces, and the only ack the epoch check waves through.
    """
    import database.memory_outbox_worker as worker

    event_id = f"impostor-{outbox['run']}"
    outbox['seed'](event_id)
    (held,) = _lease(outbox, 'worker-b')

    impostor = worker.LeasedMemoryOutboxEvent(
        path=held.path,
        document_id=held.document_id,
        raw_event=held.raw_event,
        worker_id='worker-a',
        lease_epoch=held.lease_epoch,
    )

    assert worker._ack_leased_event(db_client=_client(), lease=impostor, patch={'status': 'delivered'}) is False
    assert _raw(outbox, event_id)['status'] == 'processing'
    assert _raw(outbox, event_id)['lease_owner'] == 'worker-b'
