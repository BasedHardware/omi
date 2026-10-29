"""Reported live/batch shapes enforce one recorded timeline and one owner per capture."""

from datetime import timedelta
from types import SimpleNamespace
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from database import episodes, episode_timeline
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from utils.episodes import service, policy, timeline
from utils.episodes.moment import MomentInput
from utils.episodes.visibility import visible_episode
from tests.unit.test_late_audio_recorded_time import T0, NOW


@pytest.fixture
def lane(monkeypatch):
    store = StrictFirestore()
    # Policy/storage unit seam only; query ordering/contention runs on the emulator.
    monkeypatch.setattr(
        episode_timeline,
        'recorded_candidates',
        lambda uid, *a, **kw: [
            dict(v, id=k[-1]) for k, v in store.rows.items() if len(k) == 4 and k[:3] == ('users', uid, 'episodes')
        ],
    )
    monkeypatch.setattr(service.client_gate, 'client_seen', lambda uid: True)
    monkeypatch.setattr(service, 'get_user_name', lambda *a, **kw: None)
    monkeypatch.setattr(service.episode_language, 'language_preference', lambda uid: 'en')
    monkeypatch.setenv('EPISODE_RECORDED_TIME_ENABLED', 'true')
    calls = []

    def model(*a, **kw):
        calls.append(a)
        return SimpleNamespace(
            content=json.dumps({'title': 'Planning', 'bullets': ['Reviewed the plan']}), usage_metadata={}
        )

    c = service.Collaborators(
        firestore_client=store,
        now=lambda: T0,
        invoke=model,
        owner_name=lambda uid: 'You',
        tz_name='UTC',
        saved_tasks=lambda *a: [],
    )
    return store, c, calls


def row(cid, start=T0, seconds=30, **extra):
    return dict(
        id=cid,
        source='omi',
        started_at=start,
        finished_at=NOW,
        status='completed',
        transcript_segments=[dict(id=cid + '-s', start=0, end=seconds, text='Okay.', is_user=True)],
        **extra,
    )


def all_episodes(store):
    return [episodes.unseal('u', v) for k, v in store.rows.items() if len(k) == 4 and k[2] == 'episodes']


def assert_timeline(store):
    rows = sorted(all_episodes(store), key=lambda e: e['started_at'])
    members = [cid for e in rows for cid in e['conversation_ids']]
    assert len(members) == len(set(members))
    for left, right in zip(rows, rows[1:]):
        assert left['last_activity_at'] <= right['started_at']


def test_48_moments_in_25_minutes_is_not_a_four_hour_cap():
    episode = dict(
        status='live',
        started_at=T0,
        last_activity_at=T0,
        conversation_ids=['long'],
        moments=[{'id': str(i)} for i in range(48)],
    )
    for minutes in (25, 59, 150, 180):
        facts = policy.MomentFacts('long', 'omi', T0 + timedelta(minutes=minutes), T0 + timedelta(minutes=minutes))
        assert policy.boundary(episode, facts).action == policy.CONTINUE
    assert policy.hard_cap_due(episode, T0 + timedelta(hours=4))


def test_live_member_stays_owned_after_cap_and_after_new_episode_opens(lane):
    store, c, calls = lane
    assert service.attach_conversation('u', 'long', 'omi', started_at=T0, collaborators=c) == 'opened'
    owner = episodes.get_current_episode('u', firestore_client=store)
    for minutes in range(1, 241):
        c.now = lambda m=minutes: T0 + timedelta(minutes=m)
        service.attach_conversation('u', 'long', 'omi', started_at=c.now(), collaborators=c)
    closed = episodes.get_episode('u', owner['id'], firestore_client=store)
    assert closed['close_reason'] == 'hard_cap'
    assert closed['closed_at'] == closed['last_activity_at'] == T0 + timedelta(hours=4)
    assert episodes.get_current_episode('u', firestore_client=store) is None
    c.now = lambda: T0 + timedelta(hours=4, minutes=10)
    assert service.attach_conversation('u', 'next', 'desktop', started_at=c.now(), collaborators=c) == 'opened'
    service.attach_conversation('u', 'long', 'omi', started_at=c.now(), collaborators=c)
    moment = MomentInput(
        'long',
        'omi',
        [{'id': 'tail', 'text': 'The old capture is still talking.', 'start': 15000, 'end': 15010}],
        T0,
        c.now(),
        'interval',
    )
    assert service.record_moment('u', moment, c) == 'skipped_closed'
    assert episodes.get_episode_for_conversation('u', 'long', firestore_client=store)['id'] == owner['id']
    assert_timeline(store)
    assert not calls


@pytest.mark.parametrize('writer', ['commit', 'update', 'reopen'])
def test_membership_claim_is_checked_before_any_transaction_write(lane, writer):
    store, c, _ = lane
    for eid, status, ids, start in [('x', 'closed', ['same'], T0), ('y', 'live', [], T0 + timedelta(hours=2))]:
        store.rows[('users', 'u', 'episodes', eid)] = episodes.seal(
            'u',
            dict(
                id=eid, status=status, conversation_ids=ids, started_at=start, last_activity_at=start, state_version=1
            ),
        )
    store.rows[('users', 'u', 'episode_links', 'same')] = {'episode_id': 'x'}
    store.rows[('users', 'u', 'episode_links', 'current')] = {'episode_id': 'y'}
    with pytest.raises(episodes.EpisodeConflict, match='conversation_already_owned'):
        if writer == 'commit':
            episodes.commit_moment(
                'u',
                expected_episode_id='y',
                expected_version=1,
                updates={'conversation_ids': ['same']},
                link_conversation_ids=['same'],
                firestore_client=store,
            )
        elif writer == 'update':
            episodes.update_episode(
                'u',
                'y',
                expected_version=1,
                updates={'conversation_ids': ['same']},
                link_conversation_ids=['same'],
                firestore_client=store,
            )
        else:
            store.rows[('users', 'u', 'episodes', 'y')]['status'] = 'closed'
            store.rows[('users', 'u', 'episode_links', 'current')] = {'episode_id': None}
            store.rows[('users', 'u', 'episode_links', 'last_closed')] = {'episode_id': 'y'}
            episodes.reopen_episode(
                'u',
                'y',
                expected_version=1,
                updates={'conversation_ids': ['same']},
                link_conversation_ids=['same'],
                firestore_client=store,
            )
    assert not store.transactions[-1].has_written
    assert_timeline(store)


@pytest.mark.parametrize(
    'source,seconds', [('omi', 1200), ('omi', 60), ('omi', 180), ('desktop', 1020), ('desktop', 1920)]
)
@pytest.mark.parametrize('group', ['capture_group', 'capture_group_member_context'])
def test_grouped_finalization_gets_metadata_membership_even_with_short_tail(lane, source, seconds, group):
    store, c, _ = lane
    c.now = lambda: NOW
    capture = row('grouped', seconds=seconds, **{group: {'id': 'group', 'primary_id': 'other'}})
    capture['source'] = source
    store.rows[('users', 'u', 'conversations', 'grouped')] = capture
    service.on_conversation_finalized('u', 'grouped', capture, trigger='capture_group', collaborators=c)
    owner = episodes.get_episode_for_conversation('u', 'grouped', firestore_client=store)
    assert owner and owner['last_activity_at'] == T0 + timedelta(seconds=seconds)
    assert owner['sources'] == [source]
    assert_timeline(store)


def test_discarded_noise_cannot_open_extend_or_feed_notes(lane):
    store, c, calls = lane
    for i in range(35):
        cid = f'noise-{i}'
        capture = row(cid, T0 + timedelta(minutes=i), discarded=True)
        store.rows[('users', 'u', 'conversations', cid)] = capture
        c.now = lambda r=capture: r['started_at']
        assert service.attach_conversation('u', cid, 'omi', started_at=c.now(), collaborators=c) == 'skipped_discarded'
        assert (
            service.on_conversation_finalized('u', cid, capture, trigger='capture_end', collaborators=c)
            == 'skipped_discarded'
        )
    assert all_episodes(store) == [] and not calls
    c.now = lambda: T0
    service.attach_conversation('u', 'kept', 'omi', started_at=T0, collaborators=c)
    c.now = lambda: T0 + timedelta(minutes=31)
    service.attach_conversation('u', 'noise-31', 'omi', started_at=c.now(), collaborators=c)
    owner = episodes.get_current_episode('u', firestore_client=store)
    assert owner['last_activity_at'] == T0
    assert service.live_episode('u', collaborators=c) is None


def test_late_discard_removes_activity_and_all_hidden_episode_is_absent_from_live_api(lane, monkeypatch):
    from routers import episodes as router
    from utils.other import endpoints as auth

    store, c, _ = lane
    service.attach_conversation('u', 'kept', 'omi', started_at=T0, collaborators=c)
    c.now = lambda: T0 + timedelta(minutes=1)
    service.attach_conversation('u', 'noise', 'omi', started_at=c.now(), collaborators=c)
    c.now = lambda: T0 + timedelta(minutes=25)
    service.attach_conversation('u', 'noise', 'omi', started_at=c.now(), collaborators=c)
    capture = row('noise', discarded=True)
    store.rows[('users', 'u', 'conversations', 'noise')] = capture
    service.on_conversation_finalized('u', 'noise', capture, trigger='capture_end', collaborators=c)
    owner = episodes.get_current_episode('u', firestore_client=store)
    assert owner['last_activity_at'] == T0
    store.rows[('users', 'u', 'conversations', 'kept')] = row('kept', discarded=True)
    assert visible_episode('u', owner, firestore_client=store) is None
    live = service.live_episode
    monkeypatch.setattr(router, '_admitted', lambda *a: True)
    monkeypatch.setattr(service, 'live_episode', lambda uid: live(uid, collaborators=c))
    monkeypatch.setattr(service, 'last_closed_episode', lambda *a, **kw: None)
    app = FastAPI()
    app.include_router(router.router)
    app.dependency_overrides[auth.get_current_user_uid] = lambda: 'u'
    response = TestClient(app).get('/v1/episodes/live')
    assert response.status_code == 200 and response.json()['episode'] is None


def test_34_fragments_uploaded_hours_later_form_one_24_minute_episode(lane):
    store, c, _ = lane
    for i in range(34):
        start = T0 + timedelta(seconds=i * (24 * 60 - 20) / 33)
        capture = row(f'offline-{i}', start, seconds=20)
        capture['finished_at'] = T0 + timedelta(hours=2, minutes=25) + timedelta(seconds=i * 8100 / 33)
        c.now = lambda r=capture: r['finished_at']
        store.rows[('users', 'u', 'conversations', capture['id'])] = capture
        assert service.attach_synced_intake('u', capture['id'], capture, collaborators=c) == 'recorded'
    rows = all_episodes(store)
    assert len(rows) == 1 and len(rows[0]['conversation_ids']) == 34
    assert rows[0]['started_at'] == T0
    assert rows[0]['last_activity_at'] == T0 + timedelta(minutes=24)
    assert_timeline(store)


def test_adding_a_member_also_claims_its_link_when_caller_omits_link_argument(lane):
    store, c, _ = lane
    service.attach_conversation('u', 'first', 'omi', started_at=T0, collaborators=c)
    owner = episodes.get_current_episode('u', firestore_client=store)
    episodes.update_episode(
        'u',
        owner['id'],
        expected_version=owner['state_version'],
        updates={'conversation_ids': ['first', 'second']},
        firestore_client=store,
    )
    assert episodes.get_episode_for_conversation('u', 'second', firestore_client=store)['id'] == owner['id']


def test_stale_notes_cannot_restore_discarded_activity(lane):
    store, c, _ = lane
    service.attach_conversation('u', 'kept', 'omi', started_at=T0, collaborators=c)
    c.now = lambda: T0 + timedelta(minutes=1)
    service.attach_conversation('u', 'noise', 'omi', started_at=c.now(), collaborators=c)
    capture = row('noise', discarded=True)
    store.rows[('users', 'u', 'conversations', 'noise')] = capture
    service.on_conversation_finalized('u', 'noise', capture, trigger='capture_end', collaborators=c)
    owner = episodes.get_current_episode('u', firestore_client=store)
    stored = episodes.update_episode(
        'u',
        owner['id'],
        expected_version=owner['state_version'],
        updates={
            'member_activity': {'noise': T0 + timedelta(minutes=29)},
            'last_activity_at': T0 + timedelta(minutes=29),
        },
        firestore_client=store,
    )
    assert stored['last_activity_at'] == T0
    assert 'noise' not in stored['member_activity']
