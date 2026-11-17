"""Synthetic loopback-only contention and finished-subset write fences."""

import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Barrier
from uuid import uuid4

import pytest
from google.auth.credentials import AnonymousCredentials
from google.cloud import firestore

from config import episode_live_members as live
from database import episode_live_members as placement, episodes, home_feed
from utils.episodes import composer, service

pytestmark = pytest.mark.integration
T0 = datetime(2026, 11, 16, tzinfo=timezone.utc)


@pytest.fixture
def db(monkeypatch):
    if not os.getenv('FIRESTORE_EMULATOR_HOST', '').startswith(('127.0.0.1:', 'localhost:')):
        pytest.fail('loopback Firestore emulator required; no cloud fallback')
    monkeypatch.setenv('ENCRYPTION_SECRET', 'live_member_emulator_synthetic_secret_32_bytes')
    monkeypatch.setenv('EPISODE_LIVE_MEMBER_CLOSE_ENABLED', 'true')
    monkeypatch.setenv('EPISODE_COMPOSER', 'on')
    client = firestore.Client(project='demo-live-members', credentials=AnonymousCredentials())
    try:
        yield client, 'synthetic-' + uuid4().hex
    finally:
        client.close()


def seed(client, uid):
    root = client.collection('users').document(uid)
    root.set({'data_protection_level': 'standard', 'private_cloud_sync_enabled': True})
    old = service.new_episode(
        conversation_id='finished',
        started_at=T0,
        last_activity_at=T0 + timedelta(minutes=30),
        calendar_identity=None,
        now=T0,
    )
    old.update(id='old', conversation_ids=['finished'], state_version=1)
    root.collection('episodes').document('old').set(episodes.seal(uid, old))
    root.collection('episode_links').document('current').set({'episode_id': 'old'})
    root.collection('conversations').document('finished').set(
        {
            'status': 'completed',
            'started_at': T0,
            'finished_at': T0 + timedelta(minutes=30),
            'structured': {'title': 'Synthetic finished summary', 'overview': 'Synthetic readable detail'},
            'transcript_segments': [{'text': 'Synthetic completed member words', 'start': 0, 'end': 30}],
            'source': 'desktop',
            'episode_id': 'old',
        }
    )
    start = T0 + timedelta(hours=1, seconds=5)
    root.collection('conversations').document('live').set(
        {
            'record_lane_owner': 'batch_live_v1',
            'private_cloud_sync_enabled': True,
            'status': 'in_progress',
            'source': 'desktop',
            'started_at': start,
            'recorded_start': start,
            'clock': 'live_capture',
            'server_batch_audio_start': start.timestamp(),
            'record_audio_closed': False,
        }
    )
    template = service.new_episode(
        conversation_id='live', started_at=start, last_activity_at=start, calendar_identity=None, now=start
    )
    return root, old, template


@pytest.mark.parametrize('order', ['close_first', 'assign_first', 'concurrent'])
@pytest.mark.parametrize('iteration', range(4))
def test_close_assignment_interleavings_have_one_live_successor(db, order, iteration):
    client, uid = db
    root, old, template = seed(client, uid)

    def close():
        return episodes.close_episode(
            uid,
            'old',
            'gap',
            closed_at=T0 + timedelta(hours=1),
            expected_activity_at=old['last_activity_at'],
            firestore_client=client,
        )

    def assign():
        return placement.place(uid, 'live', template=template, firestore_client=client, admission=True)

    if order == 'close_first':
        close()
        assign()
    elif order == 'assign_first':
        assign()
        close()
    else:
        barrier = Barrier(2)

        def run(fn):
            barrier.wait(timeout=10)
            return fn()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = [pool.submit(run, fn) for fn in (close, assign)]
            [future.result(timeout=60) for future in results]
    current = root.collection('episode_links').document('current').get().to_dict()['episode_id']
    assert current != 'old'
    live_owner = episodes.get_episode(uid, current, firestore_client=client)
    assert live_owner['status'] == 'live' and live_owner['conversation_ids'] == ['live']
    assert episodes.get_episode(uid, 'old', firestore_client=client)['conversation_ids'] == ['finished']
    assert root.collection('conversations').document('live').get().to_dict()['episode_id'] == current
    assert len([doc for doc in root.collection('episodes').stream() if doc.to_dict()['status'] == 'live']) == 1


@pytest.mark.parametrize('exit_state', [None, 'finished', 'hidden', 'locked'])
def test_active_audio_appends_do_not_starve_finished_subset_but_finish_and_hide_fence_it(db, exit_state):
    client, uid = db
    root, old, _ = seed(client, uid)
    old.update(
        status='closed', close_reason='gap', closed_at=T0 + timedelta(hours=1), conversation_ids=['finished', 'live']
    )
    root.collection('episodes').document('old').set(episodes.seal(uid, old))
    member = root.collection('conversations').document('live')
    member.update({'episode_id': 'old', 'server_batch_audio_end': (T0 + timedelta(hours=2)).timestamp()})
    if exit_state == 'finished':
        member.update({'status': 'completed', 'record_audio_closed': True})
    elif exit_state == 'hidden':
        member.update({'deleted': True})
    elif exit_state == 'locked':
        member.update({'is_locked': True})

    def write():
        return episodes.update_episode(
            uid,
            'old',
            expected_version=1,
            updates={'lede': 'Finished subset detail'},
            expected_member_revisions={'live': live.CAPTURING_REVISION},
            firestore_client=client,
        )

    if exit_state:
        with pytest.raises(episodes.EpisodeConflict, match='member_revision_changed'):
            write()
    else:
        write()
        saved = episodes.get_episode(uid, 'old', firestore_client=client)
        assert saved['lede'] == 'Finished subset detail'
        assert saved['compose_excluded_live_member_ids'] == ['live']


def test_actual_compose_tick_rehomes_stuck_member_and_composes_finished_summary(db, monkeypatch):
    client, uid = db
    root, old, _ = seed(client, uid)
    old.update(
        status='closed',
        close_reason='gap',
        closed_at=T0 + timedelta(hours=1),
        conversation_ids=['finished', 'live'],
        compose_pending_since=T0,
    )
    root.collection('episodes').document('old').set(episodes.seal(uid, old))
    root.collection('episode_links').document('current').set({'episode_id': None})
    root.collection('episode_links').document('live').set({'episode_id': 'old'})
    root.collection('conversations').document('live').update({'episode_id': 'old'})
    monkeypatch.setattr(composer, 'episode_late_compose_enabled', lambda: False)
    c = service.Collaborators(firestore_client=client, people_names=lambda *a: {}, tz_name='UTC')
    assert composer.compose(uid, 'old', collaborators=c) == 'composed_single'
    saved = episodes.get_episode(uid, 'old', firestore_client=client)
    assert saved['composed_member_ids'] == ['finished']
    assert saved['lede'] == 'Synthetic readable detail'
    assert saved['conversation_ids'] == ['finished']
    assert root.collection('episode_links').document('current').get().to_dict()['episode_id'] != 'old'


def test_true_member_finished_subset_remains_readable_after_audio_append(db, monkeypatch):
    client, uid = db
    root, old, _ = seed(client, uid)
    old.update(
        status='closed', close_reason='gap', closed_at=T0 + timedelta(hours=1), conversation_ids=['finished', 'live']
    )
    root.collection('episodes').document('old').set(episodes.seal(uid, old))
    root.collection('episode_links').document('current').set({'episode_id': None})
    root.collection('episode_links').document('live').set({'episode_id': 'old'})
    member = root.collection('conversations').document('live')
    member.update(
        {
            'episode_id': 'old',
            'started_at': T0 + timedelta(minutes=59),
            'recorded_start': T0 + timedelta(minutes=59),
            'server_batch_audio_start': (T0 + timedelta(minutes=59)).timestamp(),
        }
    )
    monkeypatch.setattr(composer, 'episode_late_compose_enabled', lambda: False)
    c = service.Collaborators(firestore_client=client, people_names=lambda *a: {}, tz_name='UTC')
    assert composer.compose(uid, 'old', collaborators=c) == 'composed_single'
    assert episodes.get_episode(uid, 'old', firestore_client=client)['compose_excluded_live_member_ids'] == ['live']
    member.update({'server_batch_audio_end': (T0 + timedelta(hours=2)).timestamp()})
    for _ in range(20):
        if home_feed.prepare(uid, firestore_client=client)['ready']:
            break
    else:
        pytest.fail('synthetic Home preparation did not converge')
    saved = root.collection('episodes').document('old').get().to_dict()
    display = home_feed.reveal_display(uid, saved['home_display'])
    assert display['preview'] == 'Synthetic readable detail'
    assert saved['home_visible']


@pytest.mark.parametrize(
    'changes,reason',
    [
        ({'server_batch_audio_start': (datetime.now(timezone.utc) + timedelta(minutes=1)).timestamp()}, 'future'),
        ({'server_batch_audio_start': (T0 + timedelta(minutes=59, seconds=59)).timestamp()}, 'disagreement'),
        ({'server_batch_audio_start': (T0 + timedelta(hours=1, seconds=20)).timestamp()}, 'disagreement'),
        ({'started_at': None}, 'missing'),
        (
            {
                'started_at': T0 + timedelta(minutes=59, seconds=59),
                'recorded_start': T0 + timedelta(hours=1, seconds=1),
                'server_batch_audio_start': (T0 + timedelta(hours=1, seconds=1)).timestamp(),
            },
            'disagreement',
        ),
        ({'clock': 'estimated_device'}, 'untrusted'),
    ],
)
def test_uncertain_clocks_retain_membership_but_real_compose_tick_self_heals(db, monkeypatch, changes, reason):
    client, uid = db
    root, old, _ = seed(client, uid)
    old.update(
        status='closed',
        close_reason='gap',
        closed_at=T0 + timedelta(hours=1),
        conversation_ids=['finished', 'live'],
        compose_pending_since=T0,
    )
    root.collection('episodes').document('old').set(episodes.seal(uid, old))
    root.collection('episode_links').document('current').set({'episode_id': None})
    root.collection('episode_links').document('live').set({'episode_id': 'old'})
    member = root.collection('conversations').document('live')
    member.update({'episode_id': 'old', **changes})
    before = member.get().to_dict()
    counted = []
    monkeypatch.setattr(service.metrics, 'record_live_member_clock_refusal', counted.append)
    monkeypatch.setattr(composer, 'episode_late_compose_enabled', lambda: False)
    c = service.Collaborators(firestore_client=client, people_names=lambda *a: {}, tz_name='UTC')
    assert composer.compose(uid, 'old', collaborators=c) == 'composed_single'
    saved = episodes.get_episode(uid, 'old', firestore_client=client)
    assert saved['conversation_ids'] == ['finished', 'live']
    assert saved['composed_member_ids'] == ['finished']
    assert saved['compose_excluded_live_member_ids'] == ['live']
    assert saved['compose_pending_since'] is None
    assert saved['lede'] == 'Synthetic readable detail'
    assert member.get().to_dict() == before
    assert root.collection('episode_links').document('current').get().to_dict() == {'episode_id': None}
    assert counted == [reason]


@pytest.mark.parametrize('started_at', [True, False])
def test_admission_before_first_frame_opens_live_successor_without_rehoming(db, started_at):
    client, uid = db
    root, old, template = seed(client, uid)
    root.collection('conversations').document('live').update(
        {
            'started_at': template['started_at'] if started_at else firestore.DELETE_FIELD,
            'created_at': template['started_at'],
            'server_batch_audio_start': firestore.DELETE_FIELD,
            'recorded_start': firestore.DELETE_FIELD,
            'clock': firestore.DELETE_FIELD,
        }
    )
    result = placement.place(uid, 'live', template=template, firestore_client=client, admission=True)
    assert result['id'] != 'old' and result['status'] == 'live'
    assert not result['_live_member_rehomed']
    closed = episodes.get_episode(uid, 'old', firestore_client=client)
    assert closed['status'] == 'closed'
    assert closed['summary_needs_regeneration']
    assert root.collection('episode_links').document('current').get().to_dict()['episode_id'] == result['id']


@pytest.mark.parametrize(
    'changes',
    [
        {'capture_time_trust': 'untrusted'},
        {'started_at': None, 'created_at': None},
        {'started_at': None, 'created_at': T0 - timedelta(days=10)},
    ],
    ids=['untrusted', 'batch-only', 'stale-created-at'],
)
def test_initial_admission_preserves_main_batch_clock_selection(db, changes):
    client, uid = db
    root, old, template = seed(client, uid)
    member = root.collection('conversations').document('live')
    member.update(changes)
    before = member.get().to_dict()
    result = placement.place(uid, 'live', template=template, firestore_client=client, admission=True)
    assert result['id'] != 'old' and result['status'] == 'live'
    assert result['started_at'] == datetime.fromtimestamp(before['server_batch_audio_start'], timezone.utc)
    assert not result['_live_member_rehomed']
    after = member.get().to_dict()
    assert after['episode_id'] == result['id']
    assert {key: value for key, value in after.items() if key not in {'episode_id', 'home_source_version'}} == {
        key: value for key, value in before.items() if key not in {'episode_id', 'home_source_version'}
    }
    assert episodes.get_episode(uid, 'old', firestore_client=client)['conversation_ids'] == ['finished']
