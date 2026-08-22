"""Dual-backend contract for the memory review queue (ADR-0044 facade + ADR-0002 store port).

`database/review_queue.py` holds the conflicts a user is asked to adjudicate: "you told me two
different things, which is true?". The AST inventory finds exactly one at-risk shape in it, and the
module uses that shape in three different lanes:

    cursor   `list_review_conflicts` pages the ranked queue with `start_after(<last snapshot>)` over
             (impact DESC, created_at DESC, __name__ DESC), because a page can be entirely consumed by
             rows the authority projection redacts; it pages a SECOND, durable cursor — a document in
             `memory_state` — through the compatibility lane that drains rows predating the ranked
             fields; and `purge_stale_review_conflicts_for_memories` pages the cascade that tombstones
             conflicts whose source memory the user deleted.

             What each failure looks like to the user, since none of them raises:
             * ranked lane — the queue renders EMPTY while pending conflicts exist, because the first
               page was all stale rows and the scan kept re-reading it instead of moving past them;
             * durable lane — the oldest conflicts are never drained. The cursor is persisted, so a
               backend that ignored it would re-scan the same prefix on every request, for good; the
               rows behind it are unreachable from the product, permanently;
             * cascade lane — a conflict that quotes a memory the user deleted survives past the first
               page and keeps being shown, quoting content that is supposed to be gone.

             Distinctness, not page length, is what these tests assert: a backend that ignores the
             cursor returns full pages forever, which reads as progress.

Not covered: resolution (`resolve_review_conflict`, `append_resolution_commit`) reaches the memory
ledger, the canonical adapter and the non-active route store. Those are other modules' surfaces and
carry no document-store shape of their own here.

Binding and skip rules: the shared ``bind_store`` fixture in ``conftest.py``. Every test runs TWICE.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

BASE = datetime(2026, 6, 1, 9, 0, tzinfo=timezone.utc)

# `_advance_legacy_scan_cursor` only persists a cursor when the scan came back FULL, so the durable
# lane cannot be exercised with fewer rows than the module's own scan limit. Read from the module at
# import time would hide a change to it; the tests assert against the imported constant instead.
LEGACY_TAIL = 5


@pytest.fixture
def queue(bind_store):
    """An empty review queue for one user; every collection it touches is swept on teardown."""
    run = uuid.uuid4().hex[:8]
    uid = f'rq-{run}'

    yield {'uid': uid, 'run': run, 'store': bind_store}

    for collection in ('memory_review_queue', 'memory_state', 'memory_items'):
        for document in bind_store.query(f'users/{uid}/{collection}'):
            bind_store.delete(document.path)


def _seed(queue, review_id, **fields):
    payload = {'review_id': review_id, 'status': 'pending', 'conflict_with': []}
    payload.update(fields)
    queue['store'].set(f"users/{queue['uid']}/memory_review_queue/{review_id}", payload)
    return review_id


def _stored(queue, review_id):
    document = queue['store'].get(f"users/{queue['uid']}/memory_review_queue/{review_id}")
    return document.data if document is not None and document.exists else None


def _cursor_documents(queue):
    """The durable scan cursor, found by scanning its collection rather than recomputing its id.

    The document name embeds a digest of the status. Rebuilding that in the test would assert the test
    agrees with the module, not that the backend agrees with either.
    """
    return list(queue['store'].query(f"users/{queue['uid']}/memory_state"))


# --- cursor: the ranked queue lane -------------------------------------------------------------------


def test_a_page_of_stale_rows_does_not_hide_the_conflicts_behind_it(queue):
    """Four redacted rows rank above two real ones, and the caller asked for two.

    This is the ranked lane's whole reason for paging. A page whose rows are all dropped by the
    authority projection yields nothing, so the loop has to move PAST them with the cursor; the module
    budgets two extra pages for exactly this. A backend that ignored the cursor would re-read the same
    two stale rows three times and hand the user an EMPTY review queue while two conflicts sit waiting
    — no error, no log, just a screen that says there is nothing to review.

    The four stale rows are canonical reviews with no `fact_id`, which the projection tombstones
    without reading anything else, so this test differs from the passing case ONLY in the thing it
    claims to be testing.
    """
    import database.review_queue as review_db

    stale = [
        _seed(
            queue,
            f"stale{index}-{queue['run']}",
            authority='canonical_memory',
            impact=0.9 - index / 10,
            created_at=BASE + timedelta(minutes=index),
            candidate={'id': f'ghost-{index}'},
        )
        for index in range(4)
    ]
    live = [
        _seed(
            queue,
            f"live{index}-{queue['run']}",
            impact=0.5 - index / 10,
            created_at=BASE + timedelta(minutes=index),
            candidate={'id': f'fact-{index}'},
        )
        for index in range(2)
    ]

    items = review_db.list_review_conflicts(queue['uid'], 'pending', limit=2)

    assert [item['review_id'] for item in items] == live
    for review_id in stale:
        assert _stored(queue, review_id)['status'] == 'tombstoned', 'the scan must redact what it skipped'


def test_the_ranked_lane_reports_a_short_queue_without_looping(queue):
    """The other end: fewer rows than the limit must terminate on the short page, not keep asking."""
    import database.review_queue as review_db

    seeded = [
        _seed(
            queue,
            f"live{index}-{queue['run']}",
            impact=0.5 - index / 10,
            created_at=BASE + timedelta(minutes=index),
            candidate={'id': f'fact-{index}'},
        )
        for index in range(3)
    ]

    items = review_db.list_review_conflicts(queue['uid'], 'pending', limit=10)

    assert [item['review_id'] for item in items] == seeded


# --- cursor: the durable compatibility lane ----------------------------------------------------------


def _seed_legacy(queue, total):
    """`total` rows predating the ranked fields: no `impact`, no `created_at`.

    Firestore's order_by excludes a document missing an ordered field, so these are invisible to the
    ranked query until the compatibility lane backfills them — which is the lane the durable cursor
    paginates. Zero-padded ids so `__name__` order is the numeric order.
    """
    return [
        _seed(queue, f"lg{index:03d}-{queue['run']}", fact_id=f'fact-{index}', candidate={'id': f'fact-{index}'})
        for index in range(total)
    ]


def test_the_durable_scan_cursor_drains_the_tail_instead_of_re_reading_the_head(queue):
    """A cursor that OUTLIVES the request, and the only kind of paging bug that is permanent.

    The compatibility lane scans a bounded number of legacy rows per request and writes where it got
    to into `memory_state`. The next request resumes there. A backend that ignored that stored cursor
    would re-scan the same head every time — and because the head has just been backfilled, it now
    contributes nothing, so each request looks like a clean, complete answer while the rows behind the
    cursor are unreachable from the product forever.

    Two requests, and the assertion is on the SECOND: it has to surface the rows the first one did not.
    """
    import database.review_queue as review_db

    limit = review_db.REVIEW_LIST_LEGACY_SCAN_LIMIT
    seeded = _seed_legacy(queue, limit + LEGACY_TAIL)
    head, tail = set(seeded[LEGACY_TAIL:]), set(seeded[:LEGACY_TAIL])

    first = {item['review_id'] for item in review_db.list_review_conflicts(queue['uid'], 'pending', limit=500)}

    assert first == head, 'the first request scans one bounded page of the compatibility lane'
    assert len(_cursor_documents(queue)) == 1, 'a full scan must persist where it got to'

    second = {item['review_id'] for item in review_db.list_review_conflicts(queue['uid'], 'pending', limit=500)}

    assert tail <= second, 'the rows behind the durable cursor were never reached'
    assert second == head | tail
    assert len(second) == len(seeded), 'a resumed scan must not repeat what the first one returned'


def test_the_durable_cursor_is_dropped_at_the_tail_so_the_lane_wraps(queue):
    """Reaching the end deletes the cursor. Keeping it would pin the lane past the last row, and a
    conflict created afterwards with sparse fields would sit behind a cursor that never moves again."""
    import database.review_queue as review_db

    _seed_legacy(queue, review_db.REVIEW_LIST_LEGACY_SCAN_LIMIT + LEGACY_TAIL)

    review_db.list_review_conflicts(queue['uid'], 'pending', limit=500)
    assert len(_cursor_documents(queue)) == 1, 'precondition: the first scan parked a cursor'

    review_db.list_review_conflicts(queue['uid'], 'pending', limit=500)

    assert _cursor_documents(queue) == [], 'the lane must wrap once it has drained the tail'


def test_a_malformed_durable_cursor_is_discarded_rather_than_pinning_the_lane(queue):
    """An operational document is not trusted input.

    The cursor lives in the datastore, so a partial write or an older schema can leave one that no
    longer means what it says. Honouring it would park the compatibility lane past every row — this
    one names the LOWEST id, and the lane runs in descending order, so it would return nothing at all,
    for good. The module refuses it and deletes it.
    """
    import database.review_queue as review_db

    seeded = _seed_legacy(queue, 3)
    # The cursor's document name embeds a digest of the status. Ask the module where it keeps it
    # rather than rebuilding the digest here: a hand-computed name that drifted would put the seed
    # somewhere the module never looks, and the test would pass having proved nothing.
    queue['store'].set(
        review_db._legacy_scan_cursor_ref(queue['uid'], 'pending').path,
        {
            'schema_version': 'memory_review_legacy_scan_cursor.v0',
            'uid': queue['uid'],
            'status': 'pending',
            'last_review_id': seeded[0],
            'updated_at': BASE,
        },
    )

    items = review_db.list_review_conflicts(queue['uid'], 'pending', limit=500)

    assert {item['review_id'] for item in items} == set(seeded)


# --- cursor: the deleted-source cascade --------------------------------------------------------------


def test_the_cascade_purge_reaches_past_its_first_page(queue):
    """The user deleted a memory; every conflict quoting it must stop being shown.

    The cascade pages the conflicts that reference the removed memory. A scan that stopped at its first
    page would leave the rest visible in the review queue, still quoting content the user asked to have
    deleted — the exact failure the purge exists to prevent, and one nothing else would report.
    """
    import database.review_queue as review_db

    page_size = review_db.REVIEW_PURGE_PAGE_SIZE
    memory_id = f"mem-{queue['run']}"
    doomed = [
        _seed(
            queue,
            f"px{index:03d}-{queue['run']}",
            fact_id=memory_id,
            candidate={'id': memory_id, 'text': 'the user deleted this'},
        )
        for index in range(page_size + LEGACY_TAIL)
    ]
    unrelated = _seed(queue, f"keep-{queue['run']}", fact_id='other-memory', candidate={'id': 'other-memory'})

    purged = review_db.purge_stale_review_conflicts_for_memories(queue['uid'], [memory_id])

    assert purged == sorted(doomed), 'the cascade stopped before the tail of its own result set'
    for review_id in doomed:
        stored = _stored(queue, review_id)
        assert stored['status'] == 'tombstoned'
        assert stored['candidate'] == {'id': memory_id}, 'the quoted content must be redacted, not kept'
    assert _stored(queue, unrelated)['status'] == 'pending', 'the cascade must not touch other conflicts'


def test_a_repeated_cascade_purge_is_a_no_op(queue):
    """Deletion is retried. A second pass must not rewrite the tombstone: it would move `resolved_at`
    and the audit trail would then lie about when the conflict was closed.

    Two independent mechanisms produce that, and neither dies alone — measured, not assumed. The
    `already_redacted` short-circuit skips the write; the write itself, when it does run over an
    already-tombstoned row, preserves `reason`/`resolved_at`/`updated_at` from the stored document.
    Removing either one leaves this green; removing BOTH turns it red. So it holds the INVARIANT the
    user's audit trail depends on rather than any one guard, which is the honest thing for it to hold.
    """
    import database.review_queue as review_db

    memory_id = f"mem-{queue['run']}"
    review_id = _seed(queue, f"px-{queue['run']}", fact_id=memory_id, candidate={'id': memory_id, 'text': 'gone'})

    assert review_db.purge_stale_review_conflicts_for_memories(queue['uid'], [memory_id]) == [review_id]
    first = _stored(queue, review_id)

    assert review_db.purge_stale_review_conflicts_for_memories(queue['uid'], [memory_id]) == [review_id]

    assert _stored(queue, review_id) == first


def test_the_cascade_follows_the_conflict_side_as_well_as_the_fact_side(queue):
    """Two queries, one cursor loop each, unioned by document path. A conflict that only MENTIONS the
    deleted memory in `conflict_with` is quoting it just as much as one keyed on it."""
    import database.review_queue as review_db

    memory_id = f"mem-{queue['run']}"
    by_fact = _seed(queue, f"fact-{queue['run']}", fact_id=memory_id, candidate={'id': memory_id})
    by_conflict = _seed(
        queue, f"conf-{queue['run']}", fact_id='other', candidate={'id': 'other'}, conflict_with=[memory_id]
    )

    assert review_db.purge_stale_review_conflicts_for_memories(queue['uid'], [memory_id]) == sorted(
        [by_fact, by_conflict]
    )
