"""Read-only window pagination and retained-member projection, without customer IO."""

from datetime import datetime, timedelta, timezone

import pytest
from fake_firestore import FakeFirestoreClient

from database import episode_home, episodes
from utils.episodes import home_read

START = datetime(2026, 10, 29, 22, tzinfo=timezone.utc)


@pytest.fixture
def store(monkeypatch):
    client = FakeFirestoreClient()
    monkeypatch.setattr(episodes, 'unseal', lambda uid, row: row)
    return client


def put(store, eid, start, end, status='closed'):
    store.collection('users').document('u').collection('episodes').document(eid).set(
        {
            'started_at': start,
            'last_activity_at': end,
            'status': status,
        }
    )


def test_cross_midnight_overlap_and_live_use_the_same_started_at_window(store):
    put(store, 'cross-midnight', START, START + timedelta(hours=3))
    put(store, 'before', START - timedelta(hours=1), START - timedelta(minutes=30))
    put(store, 'live', START + timedelta(hours=2), START + timedelta(hours=3), 'live')
    put(store, 'after', START + timedelta(hours=4), START + timedelta(hours=5))
    rows, cursor = episode_home.list_episode_window(
        'u', START + timedelta(hours=1), START + timedelta(hours=3), firestore_client=store
    )
    assert [row['id'] for row in rows] == ['live', 'cross-midnight']
    assert cursor is None


def test_cursor_advances_even_if_scanned_page_has_no_overlap(store):
    put(store, 'non-overlap', START + timedelta(minutes=1), START + timedelta(minutes=2))
    put(store, 'overlap', START, START + timedelta(hours=3))
    window = (START + timedelta(hours=1), START + timedelta(hours=3))
    rows, cursor = episode_home.list_episode_window('u', *window, limit=1, firestore_client=store)
    assert rows == [] and cursor == 'non-overlap'
    rows, cursor = episode_home.list_episode_window('u', *window, limit=1, cursor=cursor, firestore_client=store)
    assert [row['id'] for row in rows] == ['overlap'] and cursor is None


def test_equal_start_cursor_does_not_skip_or_repeat_members(store):
    for eid in ['a', 'b', 'c']:
        put(store, eid, START, START + timedelta(hours=1))
    seen, cursor = [], None
    while True:
        rows, cursor = episode_home.list_episode_window(
            'u', START, START + timedelta(hours=2), limit=1, cursor=cursor, firestore_client=store
        )
        seen.extend(row['id'] for row in rows)
        if cursor is None:
            break
    assert sorted(seen) == ['a', 'b', 'c']
    assert len(seen) == 3


def test_cursor_is_scoped_to_the_authenticated_user(store):
    put(store, 'private', START, START)
    with pytest.raises(ValueError):
        episode_home.list_episode_window('other', START, START, cursor='private', firestore_client=store)


def test_projection_removes_discarded_deleted_missing_members_and_their_content(monkeypatch):
    members = {'a': {'discarded': False}, 'b': {'discarded': True}, 'c': {'deleted': True}}
    monkeypatch.setattr(
        home_read.conversations, 'get_conversation_raw_snapshot', lambda uid, cid, **kw: members.get(cid)
    )
    monkeypatch.setattr(home_read.conversations, 'prepare_conversation_for_read', lambda row, uid: row)
    episode = {
        'id': 'e',
        'status': 'closed',
        'started_at': START,
        'last_activity_at': START,
        'conversation_ids': ['a', 'b', 'c', 'missing'],
        'moments': [{'id': cid, 'conversation_id': cid, 'started_at': START} for cid in ['a', 'b']],
        'provisional_items': [
            {'id': cid, 'text': 'Task', 'conversation_id': cid, 'created_at': START} for cid in ['a', 'b']
        ],
    }
    projected = home_read.project_episode('u', episode)
    assert projected['conversation_ids'] == ['a']
    assert [m['conversation_id'] for m in projected['moments']] == ['a']
    assert [i['conversation_id'] for i in projected['provisional_items']] == ['a']
    members['a']['discarded'] = True
    assert home_read.project_episode('u', episode) is None


def test_internal_close_reasons_preserve_the_released_nullable_enum_without_mutating_storage():
    from models.episode import Episode

    stored = {'id': 'e', 'status': 'closed', 'started_at': START, 'last_activity_at': START, 'close_reason': 'boundary'}
    wire = home_read.wire_episode(stored)
    assert wire['close_reason'] is None
    assert stored['close_reason'] == 'boundary'
    assert Episode.model_validate(wire).close_reason is None
