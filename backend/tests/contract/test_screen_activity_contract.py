"""Dual-backend contract for screen activity (ADR-0044 facade + ADR-0002 store port).

`database/screen_activity.py` is the raw store behind the desktop screen recorder: the client uploads
OCR'd screenshots in pages, and the rest of the product reads them back by time window. It carries two
of the shapes the facade has to re-express, and both are visible to the person using the product:

    projection    get_screen_activity_ids asks for documents with NO fields — `coll.select([])` — and
                  keeps only the document ids. Nothing in a screen-activity document stores its own id,
                  so the projection is the ONLY place the id comes from. This list feeds bulk operations
                  like account deletion and the purge of the Pinecone vectors derived from each
                  screenshot. A projection that drops rows, or that comes back without usable ids, is
                  screenshots (and their derived vectors) that a user asked to have deleted and that
                  quietly stay; a projection the backend widens into a full fetch reads every OCR'd
                  screen the user ever captured to build a list of ids.

    batch         upsert_screen_activity writes each uploaded page in one commit, chunking at 500, and
                  it writes with a PLAIN `batch.set` — a full replace, not a merge. Two consequences a
                  user can see. First completeness: a row the batch drops is a minute of the day missing
                  from the timeline, and the function still reports it as written, so nothing retries it.
                  Second replacement: when the client re-uploads a screenshot whose window title or
                  device changed, the stored row must become the new row and not a union of both — a
                  backend that translated the batched set into a merge would leave the old
                  `deviceName`/`windowTitle` behind and attribute the screenshot to a machine it did not
                  come from.

The read path (`get_screen_activity`, and the summary built on top of it) is covered here too, because
it is the only way to see what the batch actually stored, and because its `>=`/`<=` window on a
lexicographic timestamp plus an equality filter on the app name is the pair of filters the port has to
translate for the timeline to show the right day.

Binding and skip rules: the shared ``bind_store`` fixture in ``conftest.py``. Every test runs TWICE.
"""

from __future__ import annotations

import uuid
from datetime import datetime

import pytest

# The one stored representation: 'YYYY-MM-DD HH:MM:SS.mmm', lexicographically sortable.
T0 = '2026-06-01 09:00:00.000'
T1 = '2026-06-01 09:01:00.000'
T2 = '2026-06-01 09:02:00.500'  # mid-second on purpose: it is what the end-of-second bound has to reach
T3 = '2026-06-01 09:03:00.000'


def _row(row_id: str, timestamp: str, app_name: str, **overrides):
    """A screen-activity row the way the module stores one. Note there is no `id` field: the document
    id is the only identifier, which is what makes the ids-only projection load-bearing."""
    data = {'timestamp': timestamp, 'appName': app_name, 'windowTitle': f'{app_name} — {row_id}', 'ocrText': 'ocr'}
    data.update(overrides)
    return data


@pytest.fixture
def activity(bind_store):
    """Four screenshots for one user, one minute apart, across three applications."""
    run = uuid.uuid4().hex[:8]
    uid = f'screen-{run}'
    ids = [f's{i}-{run}' for i in range(4)]
    seeded = [
        _row(ids[0], T0, 'Editor'),
        _row(ids[1], T1, 'Browser'),
        _row(ids[2], T2, 'Editor'),
        _row(ids[3], T3, 'Terminal'),
    ]
    for row_id, data in zip(ids, seeded):
        bind_store.set(f'users/{uid}/screen_activity/{row_id}', data)

    yield {'uid': uid, 'ids': ids, 'run': run, 'store': bind_store}

    for document in bind_store.query(f'users/{uid}/screen_activity'):
        bind_store.delete(document.path)


def _stored(activity, row_id):
    document = activity['store'].get(f"users/{activity['uid']}/screen_activity/{row_id}")
    return document.data if document is not None and document.exists else None


def _stored_ids(activity) -> set:
    return {document.id for document in activity['store'].query(f"users/{activity['uid']}/screen_activity")}


# --- projection -------------------------------------------------------------------------------------


def test_the_ids_only_projection_returns_every_screenshot_id(activity):
    """`.select([])` asks for documents with no fields at all, and the caller keeps `doc.id`.

    The assertion is on the ids themselves, not on their number, because the ids are the part the
    projection has to carry: no screen-activity document stores its own id (asserted here as a
    precondition), so a backend whose empty projection returned rows without a usable id would hand
    account deletion a list of blanks and delete nothing.
    """
    import database.screen_activity as screen_db

    assert all(
        'id' not in (_stored(activity, row_id) or {}) for row_id in activity['ids']
    ), 'precondition: the payload carries no id, so the projection is the only source of one'

    assert sorted(screen_db.get_screen_activity_ids(activity['uid'])) == sorted(activity['ids'])


def test_the_ids_only_projection_of_a_user_with_no_screenshots_is_empty(activity):
    """An empty projection must be an empty list, not an error: account deletion runs this for every
    user, including the ones who never used the desktop recorder."""
    import database.screen_activity as screen_db

    assert screen_db.get_screen_activity_ids(f"nobody-{activity['run']}") == []


def test_the_ids_only_projection_does_not_leak_across_users(activity):
    """The projection is scoped to one user's subcollection. A backend that resolved `select([])` against
    the collection NAME rather than the user's path would hand one user's deletion job another user's
    screenshot ids — and the purge would run on them."""
    import database.screen_activity as screen_db

    other = f"other-{activity['run']}"
    other_path = f'users/{other}/screen_activity/x-{activity["run"]}'
    activity['store'].set(other_path, _row('x', T0, 'Editor'))
    try:
        assert sorted(screen_db.get_screen_activity_ids(activity['uid'])) == sorted(activity['ids'])
        assert screen_db.get_screen_activity_ids(other) == [f'x-{activity["run"]}']
    finally:
        activity['store'].delete(other_path)


# --- batch ------------------------------------------------------------------------------------------


def test_a_batched_upload_stores_every_row_it_reports_as_written(activity):
    """The count the uploader believes and the rows that exist have to agree: the client treats the
    return value as an acknowledgement and does not re-send the page."""
    import database.screen_activity as screen_db

    run = activity['run']
    rows = [{'id': f'u{i}-{run}', 'timestamp': T0, 'appName': 'Editor', 'windowTitle': f'w{i}'} for i in range(3)]

    assert screen_db.upsert_screen_activity(activity['uid'], rows) == 3

    assert {f'u{i}-{run}' for i in range(3)} <= _stored_ids(activity)
    assert _stored(activity, f'u0-{run}')['windowTitle'] == 'w0'


def test_an_upload_with_no_rows_writes_nothing(activity):
    import database.screen_activity as screen_db

    assert screen_db.upsert_screen_activity(activity['uid'], []) == 0
    assert _stored_ids(activity) == set(activity['ids'])


def test_the_client_storage_id_wins_over_the_row_id_as_the_document_key(activity):
    """The desktop client assigns `storageId` when it has already named the blob; keying the document
    by anything else would store the same screenshot twice on the next re-upload."""
    import database.screen_activity as screen_db

    run = activity['run']
    screen_db.upsert_screen_activity(
        activity['uid'], [{'id': f'ignored-{run}', 'storageId': f'blob-{run}', 'timestamp': T0, 'appName': 'Editor'}]
    )

    assert _stored(activity, f'blob-{run}') is not None
    assert _stored(activity, f'ignored-{run}') is None


def test_optional_device_fields_are_stored_only_when_the_client_sent_them(activity):
    """`deviceName`/`clientDeviceId` are written conditionally: a row with no device must not acquire an
    empty one, because the timeline groups by device and an empty group is a machine that never existed."""
    import database.screen_activity as screen_db

    run = activity['run']
    screen_db.upsert_screen_activity(
        activity['uid'],
        [
            {'id': f'with-{run}', 'timestamp': T0, 'appName': 'Editor', 'deviceName': 'mac', 'clientDeviceId': 'd1'},
            {'id': f'without-{run}', 'timestamp': T0, 'appName': 'Editor', 'deviceName': ''},
        ],
    )

    assert _stored(activity, f'with-{run}')['deviceName'] == 'mac'
    assert _stored(activity, f'with-{run}')['clientDeviceId'] == 'd1'
    assert 'deviceName' not in _stored(activity, f'without-{run}')
    assert 'clientDeviceId' not in _stored(activity, f'without-{run}')


def test_the_ocr_text_is_truncated_before_it_is_batched(activity):
    """A full screen of OCR can be far larger than the row's budget; the module caps it at 1000
    characters on the way into the batch."""
    import database.screen_activity as screen_db

    run = activity['run']
    screen_db.upsert_screen_activity(
        activity['uid'], [{'id': f'ocr-{run}', 'timestamp': T0, 'appName': 'Editor', 'ocrText': 'x' * 4000}]
    )

    assert len(_stored(activity, f'ocr-{run}')['ocrText']) == 1000


def test_re_uploading_a_screenshot_replaces_the_row_instead_of_merging_into_it(activity):
    """The batched write is a plain `set`: a full replace.

    This is the consequence a merge-shaped translation would break. The client re-uploads the same
    screenshot after the window title changed and the device field is no longer sent; the stored row has
    to BE the new row. Under a merge the old `deviceName` survives and the timeline keeps attributing
    that screenshot to a laptop the user has since stopped using — with no error anywhere.
    """
    import database.screen_activity as screen_db

    run = activity['run']
    row_id = f'again-{run}'
    screen_db.upsert_screen_activity(
        activity['uid'],
        [{'id': row_id, 'timestamp': T0, 'appName': 'Editor', 'windowTitle': 'draft', 'deviceName': 'mac'}],
    )
    assert _stored(activity, row_id)['deviceName'] == 'mac', 'precondition'

    screen_db.upsert_screen_activity(
        activity['uid'], [{'id': row_id, 'timestamp': T1, 'appName': 'Editor', 'windowTitle': 'final'}]
    )

    stored = _stored(activity, row_id)
    assert stored['windowTitle'] == 'final'
    assert stored['timestamp'] == T1
    assert 'deviceName' not in stored, 'the re-upload must replace the row, not merge into the old one'


def test_an_upload_larger_than_one_chunk_leaves_no_row_behind(bind_store):
    """600 rows, so the module rolls over into a second batch at 500.

    What this holds is COMPLETENESS: every row of a page the uploader was told was written must be
    readable back, because the client will not send it again. It does NOT hold the chunking itself —
    neither the emulator nor Mongo enforces Firestore's 500-writes-per-commit limit, so a build that
    never rolled over passes here too (verified by mutation, same as the folders and memories suites).
    The rollover belongs to the unit suite; completeness is the part a user would notice as a gap in
    their day.
    """
    import database.screen_activity as screen_db

    run = uuid.uuid4().hex[:8]
    uid = f'screen-bulk-{run}'
    total = 600
    rows = [{'id': f'b{i}-{run}', 'timestamp': T0, 'appName': 'Editor', 'windowTitle': f'w{i}'} for i in range(total)]

    try:
        assert screen_db.upsert_screen_activity(uid, rows) == total
        assert sorted(screen_db.get_screen_activity_ids(uid)) == sorted(row['id'] for row in rows)
    finally:
        for document in bind_store.query(f'users/{uid}/screen_activity'):
            bind_store.delete(document.path)


# --- reading back what the batch stored ---------------------------------------------------------------


def test_the_timeline_window_excludes_rows_outside_it_and_comes_back_oldest_first(activity):
    """`>=` and `<=` on the stored lexicographic timestamp, ordered ascending. A window the backend
    widens shows the user minutes from a different hour; one it narrows leaves a hole in the day."""
    import database.screen_activity as screen_db

    rows = screen_db.get_screen_activity(
        activity['uid'], start_date=datetime(2026, 6, 1, 9, 1), end_date=datetime(2026, 6, 1, 9, 2)
    )

    assert [row['timestamp'] for row in rows] == [T1, T2]
    assert [row['id'] for row in rows] == [activity['ids'][1], activity['ids'][2]]


def test_the_upper_bound_includes_the_whole_final_second(activity):
    """`end_of_second=True` turns a whole-second end bound into `.999`.

    The screenshot at 09:02:00.500 is what makes this observable: a whole-second bound normalises to
    `.000`, so without the widening the row captured half a second into the closing second falls outside
    the window. Asking for "up to 09:02" would silently drop it, and the last second of any window the
    user picks would be missing from their timeline.
    """
    import database.screen_activity as screen_db

    rows = screen_db.get_screen_activity(activity['uid'], end_date=datetime(2026, 6, 1, 9, 2))

    assert [row['timestamp'] for row in rows] == [T0, T1, T2]


def test_the_app_filter_narrows_the_window_without_losing_the_range(activity):
    """An equality filter and a range filter in the same query — the pair a backend most easily
    mistranslates by honouring one and dropping the other."""
    import database.screen_activity as screen_db

    rows = screen_db.get_screen_activity(activity['uid'], start_date=datetime(2026, 6, 1, 9, 1), app_filter='Editor')

    assert [row['id'] for row in rows] == [activity['ids'][2]]


def test_the_window_is_bounded_by_the_limit(activity):
    import database.screen_activity as screen_db

    rows = screen_db.get_screen_activity(activity['uid'], limit=2)

    assert [row['timestamp'] for row in rows] == [T0, T1]


def test_the_summary_counts_each_app_over_the_window_it_was_given(activity):
    """The per-app roll-up the user reads. It is built in Python on top of the windowed query, so a
    mistranslated filter shows up here as a usage number for the wrong span of the day."""
    import database.screen_activity as screen_db

    summary = screen_db.get_screen_activity_summary(activity['uid'], end_date=datetime(2026, 6, 1, 9, 2))

    assert summary['total_screenshots'] == 3
    assert summary['apps']['Editor']['count'] == 2
    assert summary['apps']['Editor']['first_seen'] == T0
    assert summary['apps']['Editor']['last_seen'] == T2
    assert summary['apps']['Browser']['count'] == 1
    assert 'Terminal' not in summary['apps'], 'the 09:03 screenshot is outside the window'


def test_the_summary_of_an_empty_window_is_zero_rather_than_an_error(activity):
    import database.screen_activity as screen_db

    assert screen_db.get_screen_activity_summary(activity['uid'], start_date=datetime(2026, 6, 2, 0, 0)) == {
        'apps': {},
        'total_screenshots': 0,
    }
