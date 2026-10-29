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
    assert len(windows) == 2 and all(w['status'] == 'closed' for w in windows)
    assert windows[0]['last_activity_at'] == windows[1]['started_at'] == T0 + timedelta(hours=4)
    assert episodes.get_current_episode(uid, firestore_client=client) is None
    assert len(episode_timeline.member_episodes(uid, 'long', firestore_client=client)) == 2
    resumed = episode_timeline.resume_recorded(
        uid,
        windows[1]['id'],
        T0 + timedelta(hours=5, seconds=30),
        expected_version=windows[1]['state_version'],
        choose=choose_recorded_episode,
        firestore_client=client,
    )
    assert resumed['status'] == 'live'
    assert episodes.get_current_episode(uid, firestore_client=client)['id'] == windows[1]['id']
    assert root.collection('episode_links').document('last_closed').get().to_dict()['episode_id'] == 'previous'
    assert (
        episode_timeline.resume_recorded(
            uid,
            windows[0]['id'],
            T0 + timedelta(minutes=5),
            expected_version=windows[0]['state_version'],
            choose=choose_recorded_episode,
            firestore_client=client,
        )
        is None
    )  # A competing current owner cannot be replaced.
