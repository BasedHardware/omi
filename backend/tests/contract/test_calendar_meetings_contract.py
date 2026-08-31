"""Dual-backend contract for calendar meetings (ADR-0044 facade + ADR-0002 store port).

`database/calendar_meetings.py` mirrors an external calendar into a user-scoped collection. A sync
poll re-delivers the same events over and over, and a retention sweep clears the ones that have
already ended, so the module carries exactly two shapes the facade has to translate:

    transaction   create_meeting derives a deterministic id from (uid, calendar_source,
                  calendar_event_id) and upserts it through `_upsert_meeting_transaction`, which
                  READS the document inside the transaction and only stamps `created_at` when it is
                  absent, then writes with `merge=True`. Both halves are user-visible. Without the
                  read every sync poll re-stamps `created_at`, so a meeting the user added last month
                  reports as created seconds ago and any "added recently" ordering is scrambled;
                  without the merge the poll's slimmer payload erases fields an earlier, richer sync
                  had written (attendees, the conversation the meeting was linked to) with no error
                  anywhere.
    batch         delete_old_meetings streams every meeting whose `end_time` is before the cutoff and
                  deletes them in batches of 500. A sweep that deletes nothing lets the calendar grow
                  without bound and keeps ended meetings in the user's list forever; a sweep whose
                  filter is lost deletes meetings that have not happened yet, which is the user losing
                  tomorrow's calendar.

The 500-per-commit rollover itself is NOT held here: neither the emulator nor Mongo enforces
Firestore's writes-per-commit limit, so a build that never rolled over passes too (verified by
mutation, same as the folders and memories suites). What the bulk test holds is COMPLETENESS — not
one ended meeting may survive the sweep — which is the part a user could observe.

One section below is NOT one of the eight guarded shapes and says so where it starts: the overlap
window in `get_meetings_in_time_range`, which brackets a value with TWO range filters on TWO different
fields and then orders by a third clause. It is here because that is the module's most delicate
translation and the one whose failure is invisible — meeting-context enrichment simply attaches the
wrong meeting, or none, to a conversation.

Binding and skip rules: the shared ``bind_store`` fixture in ``conftest.py``. Every test runs TWICE.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

# Off-boundary on purpose: the cutoff sits mid-interval, several hours away from every seeded
# `end_time`, so nothing passes or fails the sweep by a rounding difference between the two backends.
CUTOFF = datetime(2026, 6, 1, 12, 34, tzinfo=timezone.utc)
SOURCE = 'google'


def _payload(event_id: str, *, ends: datetime, **overrides):
    """A meeting the way `routers/calendar.py` hands one over: already UTC, natural key included."""
    data = {
        'calendar_source': SOURCE,
        'calendar_event_id': event_id,
        'title': f'Meeting {event_id}',
        'start_time': ends - timedelta(hours=1),
        'end_time': ends,
    }
    data.update(overrides)
    return data


@pytest.fixture
def calendar(bind_store):
    run = uuid.uuid4().hex[:8]
    uid = f'cal-{run}'

    yield {'uid': uid, 'run': run, 'store': bind_store}

    for document in bind_store.query(f'users/{uid}/meetings'):
        bind_store.delete(document.path)


def _stored(calendar, meeting_id: str):
    document = calendar['store'].get(f"users/{calendar['uid']}/meetings/{meeting_id}")
    return document.data if document is not None and document.exists else None


def _ids(calendar) -> set[str]:
    return {document.id for document in calendar['store'].query(f"users/{calendar['uid']}/meetings")}


# --- transaction ------------------------------------------------------------------------------------


def test_the_first_sync_of_an_event_creates_it_with_both_timestamps(calendar):
    """`created_at` is stamped by the in-transaction branch that saw no document, `synced_at` by every
    write. A meeting that arrives with neither is one the sweep can never age out."""
    import database.calendar_meetings as calendar_db

    meeting_id = calendar_db.create_meeting(calendar['uid'], _payload(f"e1-{calendar['run']}", ends=CUTOFF))

    stored = _stored(calendar, meeting_id)
    assert stored is not None, 'the upsert wrote nothing'
    assert stored['title'] == f"Meeting e1-{calendar['run']}"
    assert stored['created_at'] is not None and stored['synced_at'] is not None


def test_re_syncing_an_event_keeps_its_first_created_at_and_its_earlier_fields(calendar):
    """What the in-transaction read is FOR, and the only way to see it.

    A sync poll re-delivers the same event with whatever the provider returned this time. The second
    payload here carries no `attendees` and no `conversation_id`, exactly like a provider response
    that dropped its optional blocks. The contract is that the stored meeting keeps its original
    `created_at` (the read decided not to re-stamp it) and keeps the fields the second payload does
    not mention (`merge=True`), while the fields it does mention move on.

    Asserting only "one document under one id" would pass for a write that never reads — the
    deterministic id alone guarantees that — which is why the assertions below are about the
    SURVIVING state, not the document count.
    """
    import database.calendar_meetings as calendar_db

    event_id = f"e2-{calendar['run']}"
    first = _payload(event_id, ends=CUTOFF, attendees=['ada@example.com'], conversation_id=f"conv-{calendar['run']}")
    meeting_id = calendar_db.create_meeting(calendar['uid'], first)
    created_at = _stored(calendar, meeting_id)['created_at']

    second = _payload(event_id, ends=CUTOFF, title='Renamed by the provider')
    assert calendar_db.create_meeting(calendar['uid'], second) == meeting_id, 'the natural key must be stable'

    stored = _stored(calendar, meeting_id)
    assert stored['created_at'] == created_at, 'a re-sync re-stamped created_at; the meeting looks brand new'
    assert stored['attendees'] == ['ada@example.com'], 'the slimmer re-sync erased the attendee list'
    assert stored['conversation_id'] == f"conv-{calendar['run']}", 'the re-sync erased the meeting-to-conversation link'
    assert stored['title'] == 'Renamed by the provider', 'the fields the payload DID carry must move on'
    assert _ids(calendar) == {meeting_id}, 'the re-sync must not fork a second meeting'


def test_the_same_event_from_two_sources_stays_two_meetings(calendar):
    """The natural key includes the source. Collapsing them would silently merge the user's work and
    personal calendars into one row."""
    import database.calendar_meetings as calendar_db

    event_id = f"e3-{calendar['run']}"
    google_id = calendar_db.create_meeting(calendar['uid'], _payload(event_id, ends=CUTOFF))
    outlook_id = calendar_db.create_meeting(calendar['uid'], _payload(event_id, ends=CUTOFF, calendar_source='outlook'))

    assert google_id != outlook_id
    assert _ids(calendar) == {google_id, outlook_id}


def test_the_upserted_meeting_is_readable_back_through_the_module(calendar):
    """End to end through the real chain, including the natural-key lookup the sync loop uses to decide
    whether it has seen an event before. A lookup that misses re-creates the meeting every poll."""
    import database.calendar_meetings as calendar_db

    event_id = f"e4-{calendar['run']}"
    meeting_id = calendar_db.create_meeting(calendar['uid'], _payload(event_id, ends=CUTOFF))

    assert calendar_db.get_meeting_id_by_calendar_event(calendar['uid'], event_id, SOURCE) == meeting_id
    assert calendar_db.get_meeting(calendar['uid'], meeting_id)['id'] == meeting_id
    assert calendar_db.get_meeting(calendar['uid'], f'absent-{meeting_id}') is None


# --- batch ------------------------------------------------------------------------------------------


@pytest.fixture
def swept(calendar):
    """Three meetings that ended before the cutoff and two that end after it."""
    import database.calendar_meetings as calendar_db

    ended = [
        calendar_db.create_meeting(
            calendar['uid'], _payload(f"old{i}-{calendar['run']}", ends=CUTOFF - timedelta(days=i + 1))
        )
        for i in range(3)
    ]
    upcoming = [
        calendar_db.create_meeting(
            calendar['uid'], _payload(f"new{i}-{calendar['run']}", ends=CUTOFF + timedelta(days=i + 1))
        )
        for i in range(2)
    ]
    return {**calendar, 'ended': ended, 'upcoming': upcoming}


def test_the_retention_sweep_deletes_only_the_meetings_that_already_ended(swept):
    """One batch, one inequality filter. The count is what the caller logs; the surviving set is what
    the user opens their calendar to."""
    import database.calendar_meetings as calendar_db

    assert calendar_db.delete_old_meetings(swept['uid'], CUTOFF) == 3

    assert _ids(swept) == set(swept['upcoming']), 'the sweep took meetings that have not happened yet'


def test_a_sweep_with_nothing_to_delete_commits_nothing_and_keeps_everything(swept):
    """A cutoff older than every meeting. An empty batch must not be committed as a delete-all, and it
    must not raise — this runs on a schedule for every user, most of whom have nothing to sweep."""
    import database.calendar_meetings as calendar_db

    assert calendar_db.delete_old_meetings(swept['uid'], CUTOFF - timedelta(days=365)) == 0

    assert _ids(swept) == set(swept['ended']) | set(swept['upcoming'])


def test_a_sweep_of_a_user_with_no_meetings_is_a_no_op(calendar):
    import database.calendar_meetings as calendar_db

    assert calendar_db.delete_old_meetings(f"nobody-{calendar['run']}", CUTOFF) == 0


def test_a_sweep_larger_than_one_commit_leaves_nothing_behind(bind_store):
    """550 ended meetings, so the module rolls over into a second batch at 500.

    It holds COMPLETENESS, not the chunking: neither the emulator nor Mongo enforces Firestore's
    500-writes-per-commit limit, so a build that never rolled over passes here too (verified by
    mutation, same as the folders and memories suites). Completeness is the part a heavy calendar user
    would notice — a straggler the sweep never revisits stays in the list until the account is deleted.
    """
    import database.calendar_meetings as calendar_db

    run = uuid.uuid4().hex[:8]
    uid = f'cal-bulk-{run}'
    total = 550
    for index in range(total):
        bind_store.set(
            f'users/{uid}/meetings/b{index}-{run}',
            _payload(f'b{index}-{run}', ends=CUTOFF - timedelta(days=1)),
        )

    try:
        assert calendar_db.delete_old_meetings(uid, CUTOFF) == total
        stragglers = [document.id for document in bind_store.query(f'users/{uid}/meetings')]
        assert not stragglers, f'{len(stragglers)} ended meetings survived the sweep'
    finally:
        for document in bind_store.query(f'users/{uid}/meetings'):
            bind_store.delete(document.path)


# --- range windows (not a guarded shape; see the module docstring) ------------------------------------


@pytest.fixture
def windowed(calendar):
    """Four meetings around a one-hour window, each differing from the next ONLY in when it happens.

    Window: 12:30 -> 13:30. `during` starts before and ends inside it, `across` starts inside and ends
    after, `later` is entirely after, `earlier` is entirely before. `later` can only be excluded by the
    `start_time < window_end` clause and `earlier` only by the `end_time > window_start` clause, so
    neither clause can be dropped without a visible difference.
    """
    import database.calendar_meetings as calendar_db

    ids = {
        name: calendar_db.create_meeting(
            calendar['uid'],
            _payload(f"{name}-{calendar['run']}", ends=CUTOFF.replace(hour=hour, minute=0) + timedelta(hours=1)),
        )
        for name, hour in (('earlier', 10), ('during', 12), ('across', 13), ('later', 14))
    }
    return {**calendar, 'ids': ids}


def test_the_overlap_window_returns_exactly_the_meetings_that_touch_it(windowed):
    """Two range filters on two different fields, bracketing one interval. A backend that keeps only one
    of them attaches a meeting that was already over — or one that has not started — to whatever the
    caller is enriching."""
    import database.calendar_meetings as calendar_db

    window_start = CUTOFF.replace(hour=12, minute=30)
    window_end = CUTOFF.replace(hour=13, minute=30)

    overlapping = calendar_db.get_meetings_in_time_range(windowed['uid'], window_start, window_end)

    assert [meeting['id'] for meeting in overlapping] == [
        windowed['ids']['during'],
        windowed['ids']['across'],
    ], 'the overlap window is not bracketed by both range filters, or is not ordered by start_time'


def test_the_meeting_list_comes_back_newest_first_and_honours_its_bounds(windowed):
    """The list the user reads. Reversed ordering puts last week's meeting at the top; a bound the
    backend drops shows meetings the caller explicitly filtered out."""
    import database.calendar_meetings as calendar_db

    everything = calendar_db.list_meetings(windowed['uid'])

    assert [meeting['id'] for meeting in everything] == [
        windowed['ids']['later'],
        windowed['ids']['across'],
        windowed['ids']['during'],
        windowed['ids']['earlier'],
    ], 'the list is not ordered by start_time descending'

    from_noon = calendar_db.list_meetings(windowed['uid'], start_date=CUTOFF.replace(hour=13, minute=0))

    assert [meeting['id'] for meeting in from_noon] == [windowed['ids']['later'], windowed['ids']['across']]
