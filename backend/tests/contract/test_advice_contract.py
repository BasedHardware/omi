"""Dual-backend contract for advice (ADR-0044 facade + ADR-0002 store port).

`database/advice.py` stores the proactive coaching items a user sees in their advice feed, each with an
unread flag that drives a badge. One shape:

    batch   `mark_all_advice_read` is the "clear my badge" action. It pages the unread set with a bounded
            `is_read == False` query and commits each page as one `db.batch()` of `batch.update` writes,
            relying on the mutation itself to advance the pages: every committed page drops out of the
            next query, so the same bounded query self-drains without a cursor.

            Three ways the translation can go wrong, all visible to the user. If the batch's `update`
            were applied as a document REPLACE, every advice item would come back blank — the content,
            category and timestamps live in the same document as the flag, and clearing a badge would
            erase the feed. If a page's commit did not land before the next query ran, the loop would
            re-read the same unread page forever and the request would hang holding a worker (the module
            caps it at 1000 pages precisely because termination depends on the mutation, not on a
            cursor). And if the commit silently dropped writes past some size, the badge would come back
            after a refresh with a count nobody can explain.

            What this suite holds is the DRAINING and the FIELD-WISE update, exercised across a real
            multi-page rollover by lowering `BATCH_LIMIT` on the module. It does NOT hold Firestore's
            500-writes-per-commit ceiling: neither the emulator nor Mongo enforces it, so a build that
            never rolled over passes here too (the folders and staged-tasks suites record the same
            limitation). That belongs to the unit suite; this holds what a user would see.

The read path is covered alongside it because the batch is steered by it: `mark_all_advice_read` pages
on the same `is_read == False` predicate the feed filters on, so an equality filter the backend renders
differently would either drain nothing or drain items the user never marked.

Binding and skip rules: the shared ``bind_store`` fixture in ``conftest.py``. Every test runs TWICE.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

BASE = datetime(2026, 5, 4, 7, 0, tzinfo=timezone.utc)


@pytest.fixture
def advice(bind_store):
    """One user with five advice items: four unread, one already read, one of them dismissed."""
    run = uuid.uuid4().hex[:8]
    uid = f'adv-{run}'
    ids = [f'a{index}-{run}' for index in range(5)]

    for index, advice_id in enumerate(ids):
        bind_store.set(
            f'users/{uid}/advice/{advice_id}',
            {
                'id': advice_id,
                'content': f'advice {index}',
                'category': 'health' if index % 2 == 0 else 'work',
                'confidence': 0.5,
                'created_at': BASE + timedelta(minutes=index),
                'updated_at': BASE + timedelta(minutes=index),
                'is_read': index == 4,
                'is_dismissed': index == 3,
            },
        )

    yield {'uid': uid, 'run': run, 'ids': ids, 'store': bind_store}

    for document in bind_store.query(f'users/{uid}/advice'):
        bind_store.delete(document.path)


def _doc(advice, advice_id):
    stored = advice['store'].get(f"users/{advice['uid']}/advice/{advice_id}")
    return stored.data if stored is not None and stored.exists else None


def _unread(advice) -> set[str]:
    return {
        document.id
        for document in advice['store'].query(f"users/{advice['uid']}/advice")
        if not (document.data or {}).get('is_read')
    }


# --- batch ------------------------------------------------------------------------------------------


def test_clearing_the_badge_marks_every_unread_item(advice):
    """The user-facing promise of 'mark all read': nothing unread is left behind, and the return value is
    the count the caller reports back."""
    import database.advice as advice_db

    assert advice_db.mark_all_advice_read(advice['uid']) == 4
    assert _unread(advice) == set()


def test_a_second_clear_finds_nothing_left_to_do(advice):
    """The loop terminates on an empty first page. A batch whose writes did not take would return 4 again
    here — and would have spun 1000 pages the first time."""
    import database.advice as advice_db

    advice_db.mark_all_advice_read(advice['uid'])

    assert advice_db.mark_all_advice_read(advice['uid']) == 0


def test_the_batch_updates_the_flag_without_erasing_the_advice(advice):
    """`batch.update`, not `batch.set`. The content and the category are in the same document as the
    flag, so a replacing write would hand the user an advice feed of empty rows the moment they cleared
    the badge — and `created_at` would go with it, destroying the ordering."""
    import database.advice as advice_db

    advice_db.mark_all_advice_read(advice['uid'])

    stored = _doc(advice, advice['ids'][0])
    assert stored['is_read'] is True
    assert stored['content'] == 'advice 0'
    assert stored['category'] == 'health'
    assert stored['confidence'] == 0.5
    assert stored['created_at'] is not None


def test_clearing_the_badge_does_not_undismiss_anything(advice):
    """A dismissed item is unread too, so the batch touches it — but `is_dismissed` must survive, or
    items the user swiped away reappear in the feed."""
    import database.advice as advice_db

    advice_db.mark_all_advice_read(advice['uid'])

    assert _doc(advice, advice['ids'][3])['is_dismissed'] is True
    assert _doc(advice, advice['ids'][3])['is_read'] is True


def test_the_batch_moves_the_freshness_stamp(advice):
    """Each queued update carries a fresh `updated_at`; clients sync on it, so a batch that wrote only
    the flag would leave the change invisible to an incremental sync."""
    import database.advice as advice_db

    advice_db.mark_all_advice_read(advice['uid'])

    assert _doc(advice, advice['ids'][0])['updated_at'] > BASE


def test_an_already_read_item_is_not_recounted(advice):
    """The page query filters on `is_read == False`. A backend that rendered that equality loosely would
    re-write the whole collection and report a count larger than the badge ever showed."""
    import database.advice as advice_db

    before = _doc(advice, advice['ids'][4])['updated_at']

    assert advice_db.mark_all_advice_read(advice['uid']) == 4
    assert _doc(advice, advice['ids'][4])['updated_at'] == before, 'the read item was rewritten'


def test_a_backlog_larger_than_one_commit_is_fully_drained(advice, monkeypatch):
    """The rollover, exercised for real by lowering the page size rather than by seeding 500 rows: four
    unread items over a page size of two means three round trips (two full pages, then an empty one).

    This is the case the module's own comment is about — the loop advances only because each committed
    page stops matching the query. If the commit were not visible to the next read, this hangs at the
    page cap; if the loop stopped after one page, the badge would keep two items the user cleared.
    """
    import database.advice as advice_db

    monkeypatch.setattr(advice_db, 'BATCH_LIMIT', 2)

    assert advice_db.mark_all_advice_read(advice['uid']) == 4
    assert _unread(advice) == set()


def test_an_exact_multiple_of_the_page_size_still_stops(advice, monkeypatch):
    """The awkward boundary the module documents: every page came back full, so the loop cannot tell from
    the last page alone that it is done. It must probe rather than warn — and must not loop again."""
    import database.advice as advice_db

    advice['store'].set(f"users/{advice['uid']}/advice/{advice['ids'][4]}", {'is_read': True}, merge=True)
    monkeypatch.setattr(advice_db, 'BATCH_LIMIT', 4)

    assert advice_db.mark_all_advice_read(advice['uid']) == 4
    assert _unread(advice) == set()


def test_the_page_budget_stops_the_loop_rather_than_the_request(advice, monkeypatch):
    """The hard bound. With one page of two allowed, the call must commit that page and RETURN, leaving
    the rest unread — a partially-cleared badge is recoverable, a request that never returns is not."""
    import database.advice as advice_db

    monkeypatch.setattr(advice_db, 'BATCH_LIMIT', 2)
    monkeypatch.setattr(advice_db, '_MAX_MARK_READ_PAGES', 1)

    assert advice_db.mark_all_advice_read(advice['uid']) == 2
    assert len(_unread(advice)) == 2


def test_clearing_an_empty_feed_is_a_no_op(advice):
    """A user with no advice at all: no commit, no error, zero."""
    import database.advice as advice_db

    assert advice_db.mark_all_advice_read(f"nobody-{advice['run']}") == 0


# --- the query the batch pages on -------------------------------------------------------------------


def test_the_feed_is_newest_first_and_hides_dismissed_items(advice):
    """`order_by(created_at DESC)` plus `is_dismissed == False`. Wrong order and the user's newest
    coaching item is buried; a dropped filter and everything they swiped away comes back."""
    import database.advice as advice_db

    items = advice_db.get_advice(advice['uid'])

    assert [item['id'] for item in items] == [advice['ids'][4], advice['ids'][2], advice['ids'][1], advice['ids'][0]]


def test_asking_for_dismissed_items_returns_them_too(advice):
    import database.advice as advice_db

    assert len(advice_db.get_advice(advice['uid'], include_dismissed=True)) == 5


def test_the_category_filter_narrows_the_feed(advice):
    """Two equality filters at once — the category and the not-dismissed guard."""
    import database.advice as advice_db

    items = advice_db.get_advice(advice['uid'], category='health')

    assert [item['id'] for item in items] == [advice['ids'][4], advice['ids'][2], advice['ids'][0]]


def test_the_feed_pages_with_limit_and_offset(advice):
    """`offset` on top of the ordering. A backend that applied the offset before the sort would hand the
    user page 2 with rows they already scrolled past."""
    import database.advice as advice_db

    first = advice_db.get_advice(advice['uid'], limit=2)
    second = advice_db.get_advice(advice['uid'], limit=2, offset=2)

    assert [item['id'] for item in first] == [advice['ids'][4], advice['ids'][2]]
    assert [item['id'] for item in second] == [advice['ids'][1], advice['ids'][0]]
    assert not {item['id'] for item in first} & {item['id'] for item in second}


# --- the single-item writes the feed is edited through ----------------------------------------------


def test_a_created_item_lands_unread_and_shows_up_in_the_feed(advice):
    """`create_advice` is the producer side of everything above; its document has to be the same shape the
    feed query and the batch both assume."""
    import database.advice as advice_db

    created = advice_db.create_advice(advice['uid'], 'drink water', category='health', confidence=0.9)

    stored = _doc(advice, created['id'])
    assert stored['content'] == 'drink water'
    assert stored['is_read'] is False and stored['is_dismissed'] is False
    assert created['id'] in {item['id'] for item in advice_db.get_advice(advice['uid'])}


def test_updating_one_item_leaves_the_rest_of_it_alone(advice):
    """The single-document counterpart of the batch's field-wise update."""
    import database.advice as advice_db

    updated = advice_db.update_advice(advice['uid'], advice['ids'][0], is_read=True)

    assert updated['is_read'] is True
    assert updated['content'] == 'advice 0'
    assert updated['id'] == advice['ids'][0]


def test_updating_an_item_that_never_existed_reports_nothing(advice):
    """The existence probe: `snap.exists` has to read False identically on both backends. This is the
    cheap half — the interesting one is the race below."""
    import database.advice as advice_db

    assert advice_db.update_advice(advice['uid'], f"ghost-{advice['run']}", is_read=True) is None


def test_an_item_deleted_mid_edit_reports_gone_instead_of_raising(advice, monkeypatch):
    """The race the module's own `except NotFound` exists for, driven deterministically.

    `update_advice` checks existence, then reads the clock, then updates — so a clock that deletes the
    document is the real window, not a simulated one. What must then happen is identical on both
    backends: Firestore raises `google.api_core.exceptions.NotFound`, Mongo matches nothing and raises
    the neutral `errors.NotFound` which the facade re-raises as the SAME google type. Miss that mapping
    and editing an advice item another device just deleted is a 500 rather than a quiet "it's gone".
    """
    import database.advice as advice_db

    advice_id = advice['ids'][0]

    class _ClockThatDeletes:
        @staticmethod
        def now(tz=None):
            advice['store'].delete(f"users/{advice['uid']}/advice/{advice_id}")
            return datetime.now(tz)

    monkeypatch.setattr(advice_db, 'datetime', _ClockThatDeletes)

    assert advice_db.update_advice(advice['uid'], advice_id, is_read=True) is None


def test_deleting_an_item_removes_it_from_the_feed(advice):
    import database.advice as advice_db

    assert advice_db.delete_advice(advice['uid'], advice['ids'][0]) is True
    assert _doc(advice, advice['ids'][0]) is None
    assert advice_db.delete_advice(advice['uid'], advice['ids'][0]) is False
