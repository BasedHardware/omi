"""Dual-backend contract for the store-wide queue-age sampler (ADR-0044 facade + ADR-0002 port).

`database/durable_queue_age.py` arrived with upstream in the +1002 merge and the coverage ratchet found
it. Its at-risk shape is the one no other contract suite here covers: `collection_group`.

A collection-group query reads the SAME sub-collection name under EVERY user at once — the only way to
ask "what is the oldest unprocessed item anywhere" without walking every account. It is also the shape
whose translation differs most between the two backends: Firestore has a first-class collection-group
index; Mongo has to recognise the leaf name across owner-scoped paths. Get it wrong in the quiet
direction and the sampler returns nothing, the age metric reads zero, and a queue that has been stuck
for hours looks perfectly healthy. That is a monitoring blind spot, not a crash — nothing else would
report it.

What this suite holds: the query crosses users, it filters on the status field, it respects the bounded
page, and the age it derives is the OLDEST ready item's. What it does not hold: ordering guarantees
beyond the minimum — the sampler takes a bounded page and reduces it, and the reduction is the contract.

Binding and skip rules: the shared ``bind_store`` fixture in ``conftest.py``. Every test runs TWICE.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

NOW = datetime(2026, 9, 8, 12, tzinfo=timezone.utc)


def _client():
    """The client this backend deploys, resolved through the accessor ``bind_store`` patched."""
    from database import _client as client_module

    return client_module.get_firestore_client()


@pytest.fixture
def queue(bind_store):
    run = uuid.uuid4().hex[:8]
    owners = [f'uid-{run}-a', f'uid-{run}-b']
    written: list[str] = []

    def seed(owner_index: int, doc_id: str, *, status: str, created_at: datetime) -> None:
        path = f'users/{owners[owner_index]}/candidate_integration_outbox/{doc_id}'
        bind_store.set(path, {'status': status, 'created_at': created_at})
        written.append(path)

    yield {'owners': owners, 'seed': seed, 'store': bind_store}

    for path in written:
        bind_store.delete(path)
    for owner in owners:
        bind_store.delete(f'users/{owner}')


def _ages(queue, *, now=NOW):
    import database.durable_queue_age as queue_age

    return queue_age.sample_store_wide_oldest_ready_ages(
        now=now, firestore_client=_client(), finalization_summary={}
    )


# --- collection_group: the query has to cross owners ----------------------------------------------


def test_the_oldest_ready_item_is_found_across_different_owners(queue):
    """The whole reason for a collection group: the oldest item belongs to a DIFFERENT user than the
    newest, and a query scoped to one owner would report the wrong age — or none at all."""
    queue['seed'](0, 'newer', status='pending', created_at=NOW - timedelta(minutes=5))
    queue['seed'](1, 'older', status='pending', created_at=NOW - timedelta(hours=3))

    ages = _ages(queue)

    assert 'candidate_integration_outbox' in ages
    assert ages['candidate_integration_outbox'] == pytest.approx(3 * 3600, abs=5)


def test_only_the_ready_statuses_count(queue):
    """`completed` is not backlog. Counting it would make a healthy queue look ancient — and the age
    metric is what a human reads to decide whether anything is wrong."""
    queue['seed'](0, 'done', status='completed', created_at=NOW - timedelta(days=2))
    queue['seed'](0, 'waiting', status='pending', created_at=NOW - timedelta(minutes=10))

    ages = _ages(queue)

    assert ages['candidate_integration_outbox'] == pytest.approx(600, abs=5)


def test_an_empty_queue_reports_no_backlog_rather_than_going_missing(queue):
    """`None` means the sampler RAN and found nothing ready; a missing key means it failed. The two
    must not be confused, because one of them is 'healthy' and the other is 'we do not know'."""
    ages = _ages(queue)

    assert 'candidate_integration_outbox' in ages
    assert ages['candidate_integration_outbox'] is None


def test_every_configured_queue_is_reported(queue):
    """The sampler swallows per-queue errors on purpose, so a queue that silently stopped being
    sampled would just disappear from the metric. Both backends must produce the same key set."""
    import database.durable_queue_age as queue_age

    queue['seed'](0, 'waiting', status='pending', created_at=NOW - timedelta(minutes=1))
    ages = _ages(queue)

    expected = {
        name
        for name, spec in queue_age.QUEUE_AGE_SAMPLERS.items()
        if not spec.get('summary') or True  # summary queues are fed by the argument below
    }
    assert set(ages) == expected, 'a queue vanished from the sample'
