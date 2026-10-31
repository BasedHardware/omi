"""Read-only window pagination and retained-member projection, without customer IO."""

from datetime import datetime, timedelta, timezone

import pytest
from fake_firestore import FakeFirestoreClient

from database import episodes
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
            'id': eid,
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
    rows, cursor = home_read.list_episode_window(
        'u', START + timedelta(hours=1), START + timedelta(hours=3), firestore_client=store
    )
    assert [row['id'] for row in rows] == ['live', 'cross-midnight']
    assert cursor is None


def test_empty_filtered_page_advances_the_storage_cursor(store):
    put(store, 'non-overlap', START + timedelta(minutes=1), START + timedelta(minutes=2))
    put(store, 'overlap', START, START + timedelta(hours=3))
    window = (START + timedelta(hours=1), START + timedelta(hours=3))
    rows, cursor = home_read.list_episode_window('u', *window, limit=1, firestore_client=store)
    assert rows == [] and cursor == 'non-overlap'
    rows, cursor = home_read.list_episode_window('u', *window, limit=1, cursor=cursor, firestore_client=store)
    assert [row['id'] for row in rows] == ['overlap'] and cursor is None


def test_equal_start_cursor_does_not_skip_or_repeat_members(store):
    for eid in ['a', 'b', 'c']:
        put(store, eid, START, START + timedelta(hours=1))
    seen, cursor = [], None
    while True:
        rows, cursor = home_read.list_episode_window(
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
        home_read.list_episode_window('other', START, START, cursor='private', firestore_client=store)


def test_window_reuses_phase_a_ownership_and_ignores_merged_donors(store):
    put(store, 'quiet', START, START + timedelta(minutes=10))
    root = store.collection('users').document('u').collection('episodes')
    root.document('quiet').update({'close_reason': 'gap'})
    put(store, 'explicit', START, START + timedelta(minutes=10))
    root.document('explicit').update({'close_reason': 'user', 'recorded_end': START + timedelta(hours=1)})
    put(store, 'donor', START, START + timedelta(hours=1))
    root.document('donor').update({'recorded_merged_into': 'explicit'})
    rows, cursor = home_read.list_episode_window(
        'u', START + timedelta(minutes=20), START + timedelta(minutes=30), firestore_client=store
    )
    assert {row['id'] for row in rows} == {'quiet', 'explicit'}
    assert cursor is None


def test_projection_removes_discarded_deleted_missing_members_and_their_content(monkeypatch):
    members = {'a': {'discarded': False}, 'b': {'discarded': True}, 'c': {'deleted': True}}
    monkeypatch.setattr(home_read, '_read_members', lambda uid, rows, **kw: members)
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
    assert projected['conversation_ids'] == ['a', 'b']
    assert [m['id'] for m in projected['members']] == ['a']
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


def test_each_page_has_bounded_episode_reads_and_chunked_member_reads(store, monkeypatch):
    from fake_firestore.query import FakeQuery

    # A large history must not make either page scan or hydrate the entire window.
    for index in range(250):
        at = START + timedelta(seconds=index)
        put(store, f'e{index:03}', at, at + timedelta(minutes=1))
    yielded = []
    stream = FakeQuery.stream

    def counted(query, *args, **kwargs):
        for snapshot in stream(query, *args, **kwargs):
            yielded.append(snapshot.id)
            yield snapshot

    monkeypatch.setattr(FakeQuery, 'stream', counted)
    rows, cursor = home_read.list_episode_window(
        'u', START, START + timedelta(hours=1), limit=2, firestore_client=store
    )
    assert len(yielded) == 3
    assert [row['id'] for row in rows] == ['e249', 'e248']
    yielded.clear()
    rows, cursor = home_read.list_episode_window(
        'u', START, START + timedelta(hours=1), limit=2, cursor=cursor, firestore_client=store
    )
    assert len(yielded) == 3
    assert [row['id'] for row in rows] == ['e247', 'e246']
    ids = [f'c{i}' for i in range(121)]
    root = store.collection('users').document('u').collection('conversations')
    for cid in ids:
        root.document(cid).set({'structured': {'title': cid}, 'started_at': START})
    rows[0]['conversation_ids'] = ids
    rows[1]['conversation_ids'] = ids[:10]  # Shared members are fetched once per page.
    batches = []
    get_all = store.get_all

    def counted_batch(refs, **kwargs):
        batches.append(len(refs))
        assert kwargs['field_paths'] == home_read.MEMBER_FIELDS
        return get_all(refs, **kwargs)

    monkeypatch.setattr(store, 'get_all', counted_batch)
    monkeypatch.setattr(home_read.conversations, 'prepare_conversation_for_read', lambda row, uid: row)
    projected = home_read.project_episodes('u', rows, firestore_client=store)
    assert batches == [50, 50, 21]
    assert [len(row['members']) for row in projected] == [121, 10]


@pytest.mark.parametrize('status', ['live', 'closed'])
@pytest.mark.parametrize('discarded', [False, True])
def test_only_finally_discarded_members_are_absent_from_live_and_list_http(store, monkeypatch, status, discarded):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from routers import episodes as router
    from utils.episodes import service
    from utils.other import endpoints as auth

    put(store, 'noise', START, START + timedelta(minutes=2), status)
    root = store.collection('users').document('u')
    root.collection('episodes').document('noise').update(
        {'conversation_ids': ['fragment'], 'discarded_conversation_ids': ['fragment']}
    )
    root.collection('episode_links').document('current').set({'episode_id': 'noise'})
    root.collection('conversations').document('fragment').set(
        {
            'id': 'fragment',
            'status': 'completed',
            'started_at': START,
            'discarded': discarded,
            'sync_relevance': 'keep',
            'relevance_decision': {'verdict': 'discard', 'decided_by': 'model', 'trigger': 'sync_update', 'arm': 'jev'},
        }
    )
    monkeypatch.setattr(router, '_admitted', lambda *a: True)
    monkeypatch.setattr(home_read, 'get_firestore_client', lambda: store)
    monkeypatch.setattr(home_read.conversations, 'prepare_conversation_for_read', lambda row, uid: row)
    live = service.live_episode
    c = service.Collaborators(firestore_client=store, now=lambda: START + timedelta(minutes=3))
    monkeypatch.setattr(service, 'live_episode', lambda uid: live(uid, collaborators=c))
    monkeypatch.setattr(service, 'last_closed_episode', lambda *a, **kw: None)
    app = FastAPI()
    app.include_router(router.router)
    app.dependency_overrides[auth.get_current_user_uid] = lambda: 'u'
    with TestClient(app) as client:
        live_response = client.get('/v1/episodes/live')
        assert live_response.status_code == 200 and live_response.json()['episode'] is None
        response = client.get(
            '/v1/episodes', params={'from': START.isoformat(), 'to': (START + timedelta(hours=1)).isoformat()}
        )
        assert response.status_code == 200 and response.json()['episodes'] == []
        # A later explicit restore outranks the older receipt and discard bookkeeping.
        root.collection('conversations').document('fragment').update(
            {'discarded': False, 'sync_relevance_user_kept': True}
        )
        restored = client.get(
            '/v1/episodes', params={'from': START.isoformat(), 'to': (START + timedelta(hours=1)).isoformat()}
        )
        assert restored.status_code == 200 and len(restored.json()['episodes']) == 1
        assert (client.get('/v1/episodes/live').json()['episode'] is not None) == (status == 'live')
