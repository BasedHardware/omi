"""Dual-backend contract for the daily summary shelf (ADR-0044 facade + ADR-0002 store port).

`database/daily_summaries.py` owns the per-user shelf of generated day recaps that `/v1/users/
daily-summaries` reads. One at-risk shape lives here:

    aggregation   get_summaries_count counts the user's `daily_summaries` subcollection with
                  `.count()` and unwraps the answer as `result[0][0].value`. Two things have to
                  translate for that line to survive: the count must be SCOPED to the one user's
                  subcollection (a group-wide count returns everybody's summaries), and an empty
                  collection must yield a zero ROW rather than an empty result — the unwrap raises
                  IndexError on the latter, so "the new user opens the app" is the case that breaks.

                  Honest caveat, because rule 2 asks for a user-visible consequence and this one has
                  none TODAY: `get_summaries_count` has no caller anywhere in the tree (verified by
                  grep over backend/ and app/). Nothing a user can reach is broken by it right now.
                  What the tests below hold is that the shape agrees with the collection on both
                  backends, so the first caller to wire it up does not discover a Mongo/Firestore
                  divergence in production — the folders badge is the same `.count()` unwrap and it
                  IS on screen, which is what the failure would look like once routed.

The rest of the module is plain reads and writes, not ratcheted shapes, but they are the part the
user actually sees and they route through the same facade, so they are covered here too: the ordered
+ paged list behind the summaries screen, the by-date lookup that stops the notifier regenerating a
recap that already exists, the in-place regenerate that must not spawn a second doc for the same day,
and the visibility patch that must touch one field and leave the recap intact.

Redis is not under contract here. `delete_daily_summary` also drops a share pointer in Redis, a
DIFFERENT datastore with no bearing on the document-store translation; the one test that deletes
stubs that call out rather than requiring a Redis in the rig.

Binding and skip rules: the shared ``bind_store`` fixture in ``conftest.py``. Every test runs TWICE.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

DATES = ['2026-05-30', '2026-05-31', '2026-06-01']


def _payload(summary_id: str, date: str, **extra):
    return {
        'id': summary_id,
        'date': date,
        'created_at': datetime(2026, 6, 1, 9, 0, tzinfo=timezone.utc),
        'headline': f'Day of {date}',
        'overview': 'a long day',
        'day_emoji': '🌤️',
        'visibility': 'private',
        **extra,
    }


@pytest.fixture
def shelf(bind_store):
    """One user with three summaries, one per consecutive day."""
    run = uuid.uuid4().hex[:8]
    uid = f'dsum-{run}'
    ids = [f's{index}-{run}' for index in range(3)]
    paths: list[str] = []

    def _track(path: str) -> str:
        paths.append(path)
        return path

    for summary_id, date in zip(ids, DATES):
        bind_store.set(_track(f'users/{uid}/daily_summaries/{summary_id}'), _payload(summary_id, date))

    yield {'uid': uid, 'ids': ids, 'run': run, 'store': bind_store, 'track': _track}

    for path in paths:
        bind_store.delete(path)


def _doc(shelf, summary_id):
    stored = shelf['store'].get(f"users/{shelf['uid']}/daily_summaries/{summary_id}")
    return stored.data if stored is not None and stored.exists else None


# --- aggregation ------------------------------------------------------------------------------------


def test_the_count_agrees_with_the_shelf(shelf):
    """`.count()` behind one parent. Three summaries on the shelf, so the answer is three."""
    import database.daily_summaries as daily_summaries_db

    assert daily_summaries_db.get_summaries_count(shelf['uid']) == 3


def test_a_user_with_no_summaries_counts_zero_rather_than_raising(shelf):
    """The empty-collection case, and the reason it is its own test: the module unwraps the answer as
    `result[0][0].value`, so a backend that returned an empty result instead of a zero row would raise
    IndexError for every brand-new account rather than answering 0."""
    import database.daily_summaries as daily_summaries_db

    assert daily_summaries_db.get_summaries_count(f"dsum-empty-{shelf['run']}") == 0


def test_the_count_is_scoped_to_one_user(shelf):
    """A `.count()` that lost its parent scope would answer with every user's summaries — a number that
    grows with the size of the deployment instead of with what this person recorded."""
    import database.daily_summaries as daily_summaries_db

    stranger = f"dsum-other-{shelf['run']}"
    stranger_paths = [f'users/{stranger}/daily_summaries/x{index}-{shelf["run"]}' for index in range(4)]
    for index, path in enumerate(stranger_paths):
        shelf['store'].set(path, _payload(path.rsplit('/', 1)[1], DATES[index % len(DATES)]))

    try:
        assert daily_summaries_db.get_summaries_count(shelf['uid']) == 3
        assert daily_summaries_db.get_summaries_count(stranger) == 4
    finally:
        for path in stranger_paths:
            shelf['store'].delete(path)


def test_the_count_follows_a_deletion(shelf, monkeypatch):
    """The count is derived, not stored, so it has to move when the shelf does. Redis is stubbed: the
    share pointer it drops is a different datastore and not what this suite is about."""
    import database.daily_summaries as daily_summaries_db
    from database import redis_db

    monkeypatch.setattr(redis_db, 'remove_daily_summary_to_uid', lambda summary_id: None)

    assert daily_summaries_db.delete_daily_summary(shelf['uid'], shelf['ids'][0]) is True

    assert _doc(shelf, shelf['ids'][0]) is None
    assert daily_summaries_db.get_summaries_count(shelf['uid']) == 2


# --- the reads the user sees ------------------------------------------------------------------------


def test_the_shelf_is_newest_first(shelf):
    """`/v1/users/daily-summaries` promises reverse chronological order. Lose the direction and the
    user's most recent day is buried at the bottom of the list."""
    import database.daily_summaries as daily_summaries_db

    found = daily_summaries_db.get_daily_summaries(shelf['uid'])

    assert [summary['date'] for summary in found] == sorted(DATES, reverse=True)


def test_paging_the_shelf_skips_what_the_previous_page_showed(shelf):
    """limit + offset, the endpoint's own arguments. An offset that did not apply would serve the first
    page again forever and the user could never scroll past it."""
    import database.daily_summaries as daily_summaries_db

    first = daily_summaries_db.get_daily_summaries(shelf['uid'], limit=2, offset=0)
    second = daily_summaries_db.get_daily_summaries(shelf['uid'], limit=2, offset=2)

    assert [summary['date'] for summary in first] == ['2026-06-01', '2026-05-31']
    assert [summary['date'] for summary in second] == ['2026-05-30']


def test_a_date_range_bounds_the_shelf_at_both_ends(shelf):
    """Two inequality filters on the same field, which is the pair a backend is most likely to collapse
    into one. Dropping either end silently widens the range the caller asked for."""
    import database.daily_summaries as daily_summaries_db

    found = daily_summaries_db.get_daily_summaries(shelf['uid'], start_date='2026-05-31', end_date='2026-05-31')

    assert [summary['date'] for summary in found] == ['2026-05-31']


def test_a_summary_is_found_by_the_day_it_covers(shelf):
    """The notifier looks a day up before generating. A lookup that misses re-runs the generator and the
    user gets a second recap — and a second push — for a day they already have."""
    import database.daily_summaries as daily_summaries_db

    found = daily_summaries_db.get_daily_summary_by_date(shelf['uid'], '2026-05-31')

    assert found is not None and found['id'] == shelf['ids'][1]
    assert daily_summaries_db.get_daily_summary_by_date(shelf['uid'], '2026-04-01') is None


def test_a_day_lookup_does_not_reach_into_another_user(shelf):
    import database.daily_summaries as daily_summaries_db

    stranger = f"dsum-bydate-{shelf['run']}"
    path = f'users/{stranger}/daily_summaries/only-{shelf["run"]}'
    shelf['store'].set(path, _payload(f'only-{shelf["run"]}', '2026-04-01'))

    try:
        assert daily_summaries_db.get_daily_summary_by_date(shelf['uid'], '2026-04-01') is None
    finally:
        shelf['store'].delete(path)


# --- the writes -------------------------------------------------------------------------------------


def test_creating_a_summary_puts_it_under_its_own_id(shelf):
    import database.daily_summaries as daily_summaries_db

    summary_id = f"new-{shelf['run']}"
    shelf['track'](f"users/{shelf['uid']}/daily_summaries/{summary_id}")

    assert daily_summaries_db.create_daily_summary(shelf['uid'], _payload(summary_id, '2026-06-02')) == summary_id

    assert _doc(shelf, summary_id)['headline'] == 'Day of 2026-06-02'
    assert daily_summaries_db.get_daily_summary(shelf['uid'], summary_id)['date'] == '2026-06-02'


def test_regenerating_replaces_the_recap_in_place_and_keeps_its_id(shelf):
    """The module's own reason for existing: the generator always allocates a fresh UUID, so a
    regenerate that stored it would leave the user with two recaps for one day and a screen pointing at
    the stale one. The written id must stay the id the user is looking at."""
    import database.daily_summaries as daily_summaries_db

    regenerated = _payload(f"fresh-uuid-{shelf['run']}", '2026-05-31', headline='Rewritten')

    daily_summaries_db.update_daily_summary(shelf['uid'], shelf['ids'][1], regenerated)

    stored = _doc(shelf, shelf['ids'][1])
    assert stored['id'] == shelf['ids'][1], 'the generator UUID must not leak into the payload'
    assert stored['headline'] == 'Rewritten'
    assert daily_summaries_db.get_summaries_count(shelf['uid']) == 3, 'a regenerate is not a new summary'
    assert _doc(shelf, f"fresh-uuid-{shelf['run']}") is None


def test_sharing_a_summary_changes_the_visibility_and_nothing_else(shelf):
    """An update, not a set. A backend that translated it as a whole-document write would blank the
    recap the share link points at — the reader would open a share and find an empty page."""
    import database.daily_summaries as daily_summaries_db

    daily_summaries_db.set_daily_summary_visibility(shelf['uid'], shelf['ids'][2], 'shared')

    stored = _doc(shelf, shelf['ids'][2])
    assert stored['visibility'] == 'shared'
    assert stored['headline'] == 'Day of 2026-06-01', 'the recap itself must survive the patch'
    assert stored['date'] == '2026-06-01'
