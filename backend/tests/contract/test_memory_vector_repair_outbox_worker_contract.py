"""Dual-backend contract for the vector-repair purge worker (ADR-0044 facade + ADR-0002 port).

`database/memory_vector_repair_outbox_worker.py` drains purge/repair records that undo a memory's
presence in the vector index. It shares one collection — `users/{uid}/memory_outbox` — with the
canonical outbox worker, and the two do NOT agree on how a timestamp is written:

    canonical worker  (`memory_outbox_worker.py`)  writes `available_at` / `lease_expires_at` as
                      **datetimes** and queries them against a datetime
    this worker                                     writes them as **ISO strings** and queries them
                      against a string, and its claimability check additionally requires
                      `isinstance(available_at, str)`

Two conventions in one collection is a fact about the tree, not a preference, and it is only safe
because a range query brackets by value type on both backends. That is a storage-layer promise, so it
is pinned here — on both backends — rather than assumed. If one backend ever compared across types,
one worker would lease the other's records and run the wrong side effect against them: a purge worker
would delete vectors for a memory that was merely waiting to be indexed.

    transaction   `_claim_vector_repair_purge_outbox_snapshot` re-reads the record inside a
                  transaction and claims it only if it is still pending (or its lease has expired).
                  It dispatches on `transaction.__class__.__module__.startswith("google.cloud.
                  firestore")`, so each deployment only ever exercises one of the two arms — the
                  reason this file is parametrized rather than run once.
                  Without the re-read, two workers lease the same purge and both delete: the second
                  delete finds nothing and is indistinguishable from success, so a purge that never
                  happened is recorded as done.

Binding and skip rules: the shared ``bind_store`` fixture in ``conftest.py``. Every test runs TWICE.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

NOW = datetime(2026, 7, 1, 12, 0, tzinfo=timezone.utc)
PAST_ISO = (NOW - timedelta(minutes=5)).isoformat()
FUTURE_ISO = (NOW + timedelta(hours=1)).isoformat()


def _client():
    """The client this backend deploys, resolved through the accessor `bind_store` patched."""
    from database import _client as client_module

    return client_module.get_firestore_client()


def _record(record_id: str, *, status: str = 'pending', available_at: str = PAST_ISO, **overrides):
    data = {
        'record_id': record_id,
        'event_type': 'vector_repair_purge',
        'status': status,
        'available_at': available_at,
        'memory_id': f'mem-{record_id}',
        'attempt_count': 0,
        'updated_at': PAST_ISO,
    }
    data.update(overrides)
    return data


@pytest.fixture
def purges(bind_store):
    run = uuid.uuid4().hex[:8]
    uid = f'vrepair-{run}'
    paths: list[str] = []

    def seed(record_id: str, payload=None, **overrides) -> str:
        path = f'users/{uid}/memory_outbox/{record_id}'
        bind_store.set(path, payload if payload is not None else _record(record_id, **overrides))
        paths.append(path)
        return path

    yield {'uid': uid, 'run': run, 'store': bind_store, 'seed': seed}

    for path in paths:
        bind_store.delete(path)


def _raw(purges, record_id):
    stored = purges['store'].get(f"users/{purges['uid']}/memory_outbox/{record_id}")
    return stored.data if stored is not None and stored.exists else None


def _lease(purges, worker_id, **kwargs):
    import database.memory_vector_repair_outbox_worker as vr

    return vr.lease_vector_repair_purge_outbox_records(
        db_client=_client(), uid=purges['uid'], worker_id=worker_id, now=NOW, **kwargs
    )


# --- transaction: the claim ----------------------------------------------------------------------


def test_a_due_purge_is_leased_and_marked_in_progress(purges):
    record_id = f"p1-{purges['run']}"
    purges['seed'](record_id)

    (leased,) = _lease(purges, 'worker-a')

    assert leased['record_id'] == record_id
    assert leased['outbox_path'].endswith(record_id)
    assert leased['status'] == 'pending', 'the returned record keeps the pre-claim status by design'
    stored = _raw(purges, record_id)
    assert stored['status'] == 'in_progress'
    assert stored['lease_owner'] == 'worker-a'


def test_a_second_worker_does_not_get_a_purge_that_is_already_leased(purges):
    """Two workers leasing the same purge both delete the vectors; the second delete finds nothing and
    looks exactly like success, so a purge that never ran is recorded as done."""
    record_id = f"p1-{purges['run']}"
    purges['seed'](record_id)

    assert len(_lease(purges, 'worker-a')) == 1
    assert _lease(purges, 'worker-b') == []
    assert _raw(purges, record_id)['lease_owner'] == 'worker-a'


def test_a_purge_that_is_not_due_yet_is_left_alone(purges):
    purges['seed'](f"later-{purges['run']}", available_at=FUTURE_ISO)

    assert _lease(purges, 'worker-a') == []


def test_an_expired_lease_is_reclaimed(purges):
    """A worker that died mid-purge must not strand the record — a memory's vectors would survive a
    deletion the user asked for."""
    record_id = f"stale-{purges['run']}"
    purges['seed'](record_id, status='in_progress', lease_owner='worker-dead', lease_expires_at=PAST_ISO)

    (leased,) = _lease(purges, 'worker-b')

    assert leased['record_id'] == record_id
    assert _raw(purges, record_id)['lease_owner'] == 'worker-b'


def test_a_completed_purge_is_never_re_leased(purges):
    purges['seed'](f"done-{purges['run']}", status='completed')

    assert _lease(purges, 'worker-a') == []


def test_a_record_claimed_between_the_scan_and_the_transaction_is_not_stolen(purges):
    """The TOCTOU the in-transaction re-read is FOR: the candidate query has already run by the time
    the claim executes, so only the re-read can see a competing claim. Simulated deterministically by
    wrapping the claim seam rather than with threads — a threaded version of this test would pass with
    the guard removed, because nothing forces the interleaving."""
    import database.memory_vector_repair_outbox_worker as vr

    record_id = f"race-{purges['run']}"
    path = purges['seed'](record_id)
    original = vr._claim_vector_repair_purge_outbox_snapshot
    fired = []

    def claim_first_then_run(**kwargs):
        if not fired:
            fired.append(True)
            purges['store'].set(
                path,
                {
                    **_raw(purges, record_id),
                    'status': 'in_progress',
                    'lease_owner': 'worker-b',
                    'lease_expires_at': FUTURE_ISO,
                },
            )
        return original(**kwargs)

    vr._claim_vector_repair_purge_outbox_snapshot = claim_first_then_run
    try:
        leased = _lease(purges, 'worker-a')
    finally:
        vr._claim_vector_repair_purge_outbox_snapshot = original

    assert fired, 'the wrapper never ran — the test proves nothing'
    assert leased == [], 'the record was claimed after the scan; the transaction must refuse it'
    assert _raw(purges, record_id)['lease_owner'] == 'worker-b'


# --- the shared collection: two timestamp conventions, one range query ----------------------------


def test_the_range_query_brackets_by_value_type_and_never_scans_the_other_convention(purges):
    """The isolation both workers depend on, proven on the backend we deploy — and proven at the
    QUERY, which is the only place it can be.

    A first version of this test seeded a canonical `projection_sync` event and asserted it was not
    leased. That passed for the wrong reason: the two workers are already separated by their
    `event_type` filter, so the range comparison was never put to the test, and the mutation that
    deletes the availability bound survived. The record below therefore carries **this worker's own
    event_type and status** and differs only in the TYPE of `available_at` — a datetime where this
    worker writes a string. Nothing but value-type bracketing can keep it out.

    Observed through the module's own control flow rather than by re-running the query in the test: the
    claim seam is wrapped to record which paths the scan actually handed it. Re-building the query here
    would assert that our test agrees with production source, not that the backend agrees with either.

    If a backend ever compared across types, this worker would scan and refuse (the isinstance guard in
    the next test), but the canonical worker's records would be walked on every tick — and the guard is
    the last line, not the design.
    """
    import database.memory_vector_repair_outbox_worker as vr

    datetime_keyed = f"dtkeyed-{purges['run']}"
    purges['seed'](datetime_keyed, payload=_record(datetime_keyed) | {'available_at': NOW - timedelta(minutes=5)})
    string_keyed = f"strkeyed-{purges['run']}"
    purges['seed'](string_keyed)

    scanned: list[str] = []
    original = vr._claim_vector_repair_purge_outbox_snapshot

    def record_then_run(**kwargs):
        scanned.append(kwargs['path'].rsplit('/', 1)[-1])
        return original(**kwargs)

    vr._claim_vector_repair_purge_outbox_snapshot = record_then_run
    try:
        leased = _lease(purges, 'worker-a')
    finally:
        vr._claim_vector_repair_purge_outbox_snapshot = original

    assert scanned == [string_keyed], f'the datetime-keyed record was scanned: {scanned}'
    assert [row['record_id'] for row in leased] == [string_keyed]
    assert _raw(purges, datetime_keyed)['status'] == 'pending', 'and untouched'


def test_the_canonical_worker_does_not_lease_this_workers_records(purges):
    """The other direction. Here the separation is done in Python — `_collect_supported_snapshots`
    drops any event whose `event_type` is not one of the canonical two — so this holds the filter, not
    the bracketing. Worth pinning anyway: both workers run against the same collection on every tick,
    and a canonical worker that leased a purge record would run a projection sync against it."""
    import database.memory_outbox_worker as canonical

    purges['seed'](f"mine-{purges['run']}")

    claimed = canonical.lease_canonical_memory_outbox_events(
        db_client=_client(), uid=purges['uid'], worker_id='canonical-worker', now=NOW
    )

    assert claimed == []
    assert _raw(purges, f"mine-{purges['run']}")['status'] == 'pending'


def test_a_datetime_available_at_is_refused_even_if_a_query_surfaced_it(purges):
    """Defense in depth, and the reason it is not redundant: the claimability check requires
    `isinstance(available_at, str)`, so the wrong convention is refused at the transaction even if a
    future backend's range query stopped bracketing by type. Driven at the claim seam directly, which
    is the only way to get past the query."""
    import database.memory_vector_repair_outbox_worker as vr

    record_id = f"wrongtype-{purges['run']}"
    path = purges['seed'](record_id, payload=_record(record_id) | {'available_at': NOW - timedelta(minutes=5)})

    claimed = vr._claim_vector_repair_purge_outbox_snapshot(
        db_client=_client(),
        path=path,
        worker_id='worker-a',
        now_iso=NOW.isoformat(),
        lease_expires_at=FUTURE_ISO,
    )

    assert claimed is None
    assert _raw(purges, record_id)['status'] == 'pending', 'nothing was written'


# --- the ack -------------------------------------------------------------------------------------


def test_acknowledging_a_leased_purge_writes_the_patch_and_stamps_it(purges):
    import database.memory_vector_repair_outbox_worker as vr

    record_id = f"ack-{purges['run']}"
    purges['seed'](record_id)
    (leased,) = _lease(purges, 'worker-a')

    applied = vr.ack_vector_repair_purge_outbox_record(
        db_client=_client(), record=leased, patch={'status': 'completed', 'action': 'deleted'}, now=NOW
    )

    assert applied['updated_at'] == NOW.isoformat()
    stored = _raw(purges, record_id)
    assert stored['status'] == 'completed'
    assert stored['action'] == 'deleted'


def test_an_ack_for_a_record_that_no_longer_exists_propagates(purges):
    """Deliberate, and documented in the module: write failures propagate so the caller can account
    for an ambiguous ack instead of dropping it. A swallowed failure here is a purge whose outcome
    nobody records — it stays `in_progress` forever and is re-leased on every tick."""
    import database.memory_vector_repair_outbox_worker as vr

    record_id = f"gone-{purges['run']}"
    purges['seed'](record_id)
    (leased,) = _lease(purges, 'worker-a')
    purges['store'].delete(f"users/{purges['uid']}/memory_outbox/{record_id}")

    with pytest.raises(Exception):
        vr.ack_vector_repair_purge_outbox_record(db_client=_client(), record=leased, patch={'status': 'completed'})
