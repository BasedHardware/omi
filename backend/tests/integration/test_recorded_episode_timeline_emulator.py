"""Real Firestore query/transaction contention. Loopback emulator only; no cloud fallback."""

import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from google.auth.credentials import AnonymousCredentials
from google.cloud import firestore

from database import episode_timeline, episodes
from utils.episodes.timeline import choose_recorded_episode, episode_owning_recorded_time

pytestmark = pytest.mark.integration
T0 = datetime(2026, 10, 29, 1, 4, tzinfo=timezone.utc)


@pytest.fixture
def store(monkeypatch):
    host = os.environ.get('FIRESTORE_EMULATOR_HOST', '')
    if not host.startswith(('127.0.0.1:', 'localhost:')):
        pytest.skip('loopback FIRESTORE_EMULATOR_HOST required; no cloud fallback')
    monkeypatch.setenv('ENCRYPTION_SECRET', 'recorded_time_emulator_synthetic_key_32_bytes')
    client = firestore.Client(project='demo-recorded-time', credentials=AnonymousCredentials())
    return client, 'recorded-test-' + uuid4().hex


def test_simultaneous_late_devices_converge_on_one_closed_episode(store):
    client, uid = store

    def attach(i):
        return episode_timeline.attach_recorded(
            uid,
            f'c{i}',
            'omi' if i % 2 else 'phone',
            T0 + timedelta(seconds=i * 20),
            T0 + timedelta(seconds=i * 20 + 18),
            choose=choose_recorded_episode,
            new_episode={'sources': [], 'conversation_ids': [], 'provisional_items': [], 'moments': []},
            firestore_client=client,
        )

    with ThreadPoolExecutor(max_workers=4) as pool:
        rows = list(pool.map(attach, range(8)))
    # An earlier prefix may replace a committed historical ID. Every returned
    # ID must resolve to the same persisted owner after all writers finish.
    assert len({episodes.get_episode(uid, row['id'], firestore_client=client)['id'] for row in rows}) == 1
    owner = episode_owning_recorded_time(uid, T0 + timedelta(seconds=35), firestore_client=client)
    assert owner['status'] == 'closed'
    assert len(owner['conversation_ids']) == 8
    assert owner['started_at'] == T0
    assert owner['last_activity_at'] == owner['closed_at'] == T0 + timedelta(seconds=158)
    assert episodes.get_current_episode(uid, firestore_client=client) is None


def test_metadata_window_finds_old_owner_and_preserves_new_live_pointer(store):
    client, uid = store
    root = client.collection('users').document(uid)
    old = {
        'id': 'old',
        'status': 'closed',
        'close_reason': 'gap',
        'started_at': T0,
        'last_activity_at': T0 + timedelta(minutes=22),
        'closed_at': T0 + timedelta(minutes=22),
        'conversation_ids': [],
        'state_version': 1,
    }
    live = dict(
        old,
        id='live',
        status='live',
        started_at=T0 + timedelta(hours=4),
        last_activity_at=T0 + timedelta(hours=4, minutes=5),
    )
    root.collection('episodes').document('old').set(episodes.seal(uid, old))
    root.collection('episodes').document('live').set(episodes.seal(uid, live))
    root.collection('episode_links').document('current').set({'episode_id': 'live'})
    owner = episode_owning_recorded_time(uid, T0 + timedelta(minutes=5), firestore_client=client)
    assert owner['id'] == 'old'
    result = episode_timeline.attach_recorded(
        uid,
        'offline',
        'omi',
        T0 + timedelta(minutes=5),
        T0 + timedelta(minutes=6),
        choose=choose_recorded_episode,
        new_episode={},
        firestore_client=client,
    )
    assert result['id'] == 'old' and result['status'] == 'closed'
    assert episodes.get_current_episode(uid, firestore_client=client)['id'] == 'live'


def test_long_capture_caps_and_only_fresh_live_resume_changes_navigation(store):
    client, uid = store
    root = client.collection('users').document(uid)
    root.collection('episode_links').document('last_closed').set({'episode_id': 'previous'})
    result = episode_timeline.attach_recorded(
        uid,
        'long',
        'phone',
        T0,
        T0 + timedelta(hours=5),
        choose=choose_recorded_episode,
        new_episode={'sources': [], 'conversation_ids': [], 'provisional_items': [], 'moments': []},
        firestore_client=client,
    )
    windows = result['_recorded_windows']
    assert len(windows) == 1 and windows[0]['status'] == 'closed'
    assert windows[0]['last_activity_at'] == T0 + timedelta(hours=4)
    assert episodes.get_current_episode(uid, firestore_client=client) is None
    assert len(episode_timeline.member_episodes(uid, 'long', firestore_client=client)) == 1
    # A different conversation starts the successor, never the capped member.
    successor = episode_timeline.attach_recorded(
        uid,
        'next',
        'desktop',
        T0 + timedelta(hours=5),
        T0 + timedelta(hours=5, minutes=1),
        choose=choose_recorded_episode,
        new_episode={},
        firestore_client=client,
    )
    assert successor['id'] != result['id'] and successor['conversation_ids'] == ['next']
    retry = episode_timeline.attach_recorded(
        uid,
        'long',
        'phone',
        T0,
        T0 + timedelta(hours=6),
        choose=choose_recorded_episode,
        new_episode={},
        firestore_client=client,
    )
    assert retry['id'] == result['id']
    assert len(episode_timeline.member_episodes(uid, 'long', firestore_client=client)) == 1
    assert root.collection('episode_links').document('last_closed').get().to_dict()['episode_id'] == 'previous'


def test_live_commit_cannot_steal_membership_or_overlap_recorded_owner(store):
    client, uid = store
    old = episode_timeline.attach_recorded(
        uid,
        'long',
        'omi',
        T0,
        T0 + timedelta(minutes=110),
        choose=choose_recorded_episode,
        new_episode={},
        firestore_client=client,
    )
    for cid in ('long', 'different'):
        proposed = dict(
            id='overlap',
            status='live',
            started_at=T0 + timedelta(minutes=35),
            last_activity_at=T0 + timedelta(minutes=36),
            conversation_ids=[cid],
        )
        with pytest.raises(episodes.EpisodeConflict, match='conversation_already_owned|recorded_window_overlap'):
            episodes.commit_moment(
                uid,
                expected_episode_id=None,
                expected_version=None,
                new_episode=proposed,
                link_conversation_ids=[cid],
                firestore_client=client,
            )
    assert episodes.get_episode_for_conversation(uid, 'long', firestore_client=client)['id'] == old['id']
    assert episodes.get_episode(uid, 'overlap', firestore_client=client) is None
    assert episodes.get_current_episode(uid, firestore_client=client) is None


def test_concurrent_live_and_recorded_attachments_preserve_timeline(store):
    client, uid = store

    def attach(i):
        at = T0 + timedelta(seconds=i * 20)
        if i % 2:
            return episode_timeline.attach_recorded(
                uid,
                f'c{i}',
                'desktop',
                at,
                at + timedelta(seconds=18),
                choose=choose_recorded_episode,
                new_episode={},
                firestore_client=client,
            )
        try:
            return episodes.commit_moment(
                uid,
                expected_episode_id=None,
                expected_version=None,
                new_episode=dict(
                    id=f'live-{i}',
                    status='live',
                    started_at=at,
                    last_activity_at=at + timedelta(minutes=5),
                    conversation_ids=[f'c{i}'],
                ),
                link_conversation_ids=[f'c{i}'],
                firestore_client=client,
            )
        except episodes.EpisodeConflict:
            return episode_timeline.attach_recorded(
                uid,
                f'c{i}',
                'omi',
                at,
                at + timedelta(seconds=18),
                choose=choose_recorded_episode,
                new_episode={},
                firestore_client=client,
            )

    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(attach, range(8)))
    # Phase A retains redirects when an earlier prefix replaces a historical
    # window. Compare active canonical owners, just as the time index does.
    owners = [
        episodes.get_episode(uid, d.id, firestore_client=client)
        for d in client.collection('users').document(uid).collection('episodes').stream()
    ]
    rows = sorted({e['id']: e for e in owners}.values(), key=lambda e: e['started_at'])
    members = [cid for row in rows for cid in row['conversation_ids']]
    assert len(members) == len(set(members)) == 8
    assert all(episode_timeline.recorded_end(a) <= b['started_at'] for a, b in zip(rows, rows[1:]))
    for row in rows:
        for cid in row['conversation_ids']:
            assert episodes.get_episode_for_conversation(uid, cid, firestore_client=client)['id'] == row['id']


def test_time_index_paginates_and_membership_is_atomic(store, monkeypatch):
    from utils.episodes import service

    client, uid = store
    root = client.collection('users').document(uid)
    for i in range(5):
        start = T0 + timedelta(hours=i)
        root.collection('conversations').document(f'c{i}').set({'id': f'c{i}'})
        episode_timeline.attach_recorded(
            uid,
            f'c{i}',
            'omi',
            start,
            start + timedelta(minutes=5),
            choose=choose_recorded_episode,
            new_episode={},
            firestore_client=client,
        )
    monkeypatch.setattr(episode_timeline, 'PAGE_LIMIT', 2)
    found = service.episodes_between(uid, T0, T0 + timedelta(hours=5), firestore_client=client)
    assert len(found) == 5
    for i, episode in enumerate(found):
        assert (
            service.episode_at(uid, T0 + timedelta(hours=i, minutes=1), firestore_client=client)['id'] == episode['id']
        )
        assert root.collection('conversations').document(f'c{i}').get().to_dict()['episode_id'] == episode['id']
        assert root.collection('episode_links').document(f'c{i}').get().to_dict()['episode_id'] == episode['id']


def test_reverse_prefixes_repartition_new_historical_caps_without_moving_live_navigation(store):
    client, uid = store
    root = client.collection('users').document(uid)
    root.collection('episode_links').document('current').set({'episode_id': 'unrelated-live'})
    for i in reversed(range(5)):
        root.collection('conversations').document(f'prefix-{i}').set({'id': f'prefix-{i}'})
        episode_timeline.attach_recorded(
            uid,
            f'prefix-{i}',
            'omi',
            T0 + timedelta(hours=i),
            T0 + timedelta(hours=i + 1),
            choose=choose_recorded_episode,
            new_episode={},
            firestore_client=client,
        )
    rows = episode_timeline.between(uid, T0, T0 + timedelta(hours=5), firestore_client=client)
    assert [(row['started_at'], row['last_activity_at']) for row in rows] == [
        (T0, T0 + timedelta(hours=4)),
        (T0 + timedelta(hours=4), T0 + timedelta(hours=5)),
    ]
    assert root.collection('episode_links').document('current').get().to_dict() == {'episode_id': 'unrelated-live'}
    for i in range(5):
        assert (
            root.collection('conversations').document(f'prefix-{i}').get().to_dict()['episode_id'] == rows[i // 4]['id']
        )


def test_more_than_fifty_captures_repartition_with_atomic_reverse_membership(store):
    client, uid = store
    root = client.collection('users').document(uid)
    facts = {
        f'c{i:02}': {
            'start': T0 + timedelta(seconds=30 * i),
            'end': T0 + timedelta(seconds=30 * i + 20),
            'source': 'omi',
        }
        for i in range(50)
    }
    original = dict(
        id='original',
        status='closed',
        close_reason='gap',
        started_at=T0,
        last_activity_at=T0 + timedelta(seconds=1490),
        recorded_members=facts,
        conversation_ids=list(facts),
        state_version=1,
    )
    batch = client.batch()
    batch.set(root.collection('episodes').document('original'), episodes.seal(uid, original))
    for cid in facts:
        batch.set(root.collection('conversations').document(cid), {'id': cid, 'episode_id': 'original'})
        batch.set(
            root.collection('episode_links').document(cid), {'episode_id': 'original', 'episode_ids': ['original']}
        )
    batch.set(root.collection('conversations').document('c50'), {'id': 'c50'})
    batch.commit()

    result = episode_timeline.attach_recorded(
        uid,
        'c50',
        'omi',
        T0 + timedelta(seconds=1500),
        T0 + timedelta(seconds=1520),
        choose=choose_recorded_episode,
        new_episode={},
        firestore_client=client,
    )

    assert set(result['conversation_ids']) == {*facts, 'c50'}
    assert episodes.get_episode(uid, 'original', firestore_client=client)['id'] == result['id']
    refs = [
        root.collection(collection).document(cid)
        for cid in result['conversation_ids']
        for collection in ('conversations', 'episode_links')
    ]
    snapshots = list(client.get_all(refs))
    assert len(snapshots) == 2 * len(result['conversation_ids'])
    for snapshot in snapshots:
        assert snapshot.to_dict()['episode_id'] == result['id']


@pytest.mark.parametrize('status', ['live', 'closed'])
def test_occasion_claim_and_late_discard_recompute_retained_recorded_window(store, status):
    client, uid = store
    root = client.collection('users').document(uid)
    for cid, start, end in [
        ('noise', T0, T0 + timedelta(minutes=2)),
        ('speech', T0 + timedelta(minutes=21), T0 + timedelta(minutes=27)),
    ]:
        root.collection('conversations').document(cid).set(
            {
                'id': cid,
                'started_at': start,
                'recorded_start': start,
                'recorded_end': end,
                'clock': 'live_capture',
                'discarded': False,
                'sync_relevance': 'keep',
            }
        )
    owner = {
        'id': 'occasion',
        'status': status,
        'close_reason': 'gap' if status == 'closed' else None,
        'started_at': T0,
        'last_activity_at': T0 + timedelta(minutes=27),
        'recorded_end': T0 + timedelta(minutes=27),
        'state_version': 1,
        'conversation_ids': ['noise', 'speech'],
        'member_activity': {'noise': T0 + timedelta(minutes=2), 'speech': T0 + timedelta(minutes=27)},
    }
    if status == 'closed':
        owner['recorded_members'] = {
            'noise': {'start': T0, 'end': T0 + timedelta(minutes=2), 'source': 'omi'},
            'speech': {'start': T0 + timedelta(minutes=21), 'end': T0 + timedelta(minutes=27), 'source': 'omi'},
        }
    root.collection('episodes').document('occasion').set(episodes.seal(uid, owner))
    for cid in owner['conversation_ids']:
        root.collection('episode_links').document(cid).set({'episode_id': 'occasion'})
    at = T0 + timedelta(minutes=25)
    desktop = root.collection('conversations').document('desktop')
    desktop.set({'id': 'desktop', 'source': 'desktop', 'recorded_start': at, 'recorded_end': at, 'clock': 'imported'})
    for _ in range(2):
        episode_timeline.attach_existing_recorded(
            uid,
            'desktop',
            'desktop',
            at,
            at,
            episode_id='occasion',
            choose=choose_recorded_episode,
            firestore_client=client,
        )
    assert desktop.get().to_dict()['episode_id'] == 'occasion'
    assert root.collection('episode_links').document('desktop').get().to_dict()['episode_ids'] == ['occasion']
    assert episodes.get_episode(uid, 'occasion', firestore_client=client)['conversation_ids'].count('desktop') == 1
    root.collection('conversations').document('noise').update(
        {'relevance_decision': {'verdict': 'discard', 'decided_by': 'model'}}
    )
    before = episodes.get_episode(uid, 'occasion', firestore_client=client)
    after = episodes.update_episode(
        uid,
        'occasion',
        expected_version=before['state_version'],
        updates={'discarded_conversation_ids': ['noise']},
        firestore_client=client,
    )
    assert after['started_at'] == T0 + timedelta(minutes=21)
    assert after['last_activity_at'] == T0 + timedelta(minutes=27)
    assert set(after['member_activity']) == {'speech', 'desktop'}
    if status == 'closed':
        assert after['recorded_end'] == T0 + timedelta(minutes=27)
    later = T0 + timedelta(minutes=28)
    root.collection('conversations').document('later').set(
        {'id': 'later', 'started_at': later, 'recorded_start': later, 'recorded_end': later, 'clock': 'imported'}
    )
    joined = episode_timeline.attach_recorded(
        uid, 'later', 'desktop', later, later, choose=choose_recorded_episode, new_episode={}, firestore_client=client
    )
    assert joined['id'] == 'occasion' and joined['started_at'] == T0 + timedelta(minutes=21)


def test_occasion_claim_refuses_changed_owner_before_writing_any_membership(store):
    client, uid = store
    with pytest.raises(episodes.EpisodeConflict, match='recorded_owner_changed'):
        episode_timeline.attach_existing_recorded(
            uid,
            'desktop',
            'desktop',
            T0,
            T0,
            episode_id='missing',
            choose=choose_recorded_episode,
            firestore_client=client,
        )
    root = client.collection('users').document(uid)
    assert not root.collection('episode_links').document('desktop').get().exists
    assert list(root.collection('episodes').stream()) == []
