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
    assert len({row['id'] for row in rows}) == 1
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
    rows = sorted(
        [
            episodes.unseal(uid, d.to_dict())
            for d in client.collection('users').document(uid).collection('episodes').stream()
        ],
        key=lambda e: e['started_at'],
    )
    members = [cid for row in rows for cid in row['conversation_ids']]
    assert len(members) == len(set(members)) == 8
    assert all(a['last_activity_at'] <= b['started_at'] for a, b in zip(rows, rows[1:]))
