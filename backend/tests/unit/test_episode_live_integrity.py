"""Reported live/batch shapes enforce one recorded timeline and one owner per capture."""

from datetime import datetime, timedelta, timezone
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

T0 = datetime(2026, 10, 29, 1, 4, tzinfo=timezone.utc)
NOW = T0 + timedelta(hours=4)


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
        assert episode_timeline.recorded_end(left) <= right['started_at']


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


def test_new_capture_inside_explicit_close_window_cannot_open_an_overlapping_episode(lane):
    store, c, _ = lane
    store.rows[('users', 'u', 'conversations', 'first')] = row(
        'first', seconds=120, recorded_start=T0, recorded_end=T0 + timedelta(minutes=2), clock='live_capture'
    )
    service.attach_conversation('u', 'first', 'omi', started_at=T0, collaborators=c)
    owner = episodes.get_current_episode('u', firestore_client=store)
    c.now = lambda: T0 + timedelta(minutes=2)
    service.close_on_finalize('u', 'first', trigger='client_finalize', collaborators=c)
    at = T0 + timedelta(minutes=1)
    service.attach_conversation('u', 'before-close', 'desktop', started_at=at, collaborators=c)
    assert episodes.get_episode_for_conversation('u', 'before-close', firestore_client=store)['id'] == owner['id']
    assert len(all_episodes(store)) == 1
    closed = episodes.get_episode('u', owner['id'], firestore_client=store)
    assert closed['closed_at'] == T0 + timedelta(minutes=2)


def test_delayed_finalize_after_late_capture_never_overlaps_recorded_successor(lane):
    store, c, _ = lane
    start = datetime(2026, 10, 29, 11, 57, tzinfo=timezone.utc)
    speech_end = start + timedelta(minutes=3)  # 12:00, last recorded speech in A.
    c.now = lambda: start
    capture = row('A', start, seconds=30, recorded_start=start, recorded_end=speech_end, clock='live_capture')
    store.rows[('users', 'u', 'conversations', 'A')] = capture
    service.attach_conversation('u', 'A', 'omi', started_at=start, ended_at=speech_end, collaborators=c)
    owner = episodes.get_current_episode('u', firestore_client=store)
    c.now = lambda: start + timedelta(minutes=43)  # 12:40, late capture creates B.
    later = row('B', c.now(), seconds=30)
    store.rows[('users', 'u', 'conversations', 'B')] = later
    assert service.attach_synced_intake('u', 'B', later, collaborators=c) == 'recorded'
    c.now = lambda: start + timedelta(minutes=48)  # 12:45, delayed client finalize of A.
    assert service.close_on_finalize('u', 'A', trigger='client_finalize', collaborators=c) == 'closed'
    closed = episodes.get_episode('u', owner['id'], firestore_client=store)
    assert closed['recorded_end'] == speech_end
    assert closed['closed_at'] == c.now()
    assert_timeline(store)


@pytest.mark.parametrize('enabled', [True, False])
def test_live_cap_kill_switch_controls_activity_clamp_and_close(lane, monkeypatch, enabled):
    store, c, _ = lane
    monkeypatch.setenv('EPISODE_HARD_CAP_ACROSS_CONVERSATIONS', 'on' if enabled else 'off')
    service.attach_conversation('u', 'long', 'omi', started_at=T0, collaborators=c)
    owner = episodes.get_current_episode('u', firestore_client=store)
    c.now = lambda: T0 + timedelta(hours=4, minutes=10)
    service.attach_conversation('u', 'long', 'omi', started_at=T0, ended_at=c.now(), collaborators=c)
    owner = episodes.get_episode('u', owner['id'], firestore_client=store)
    assert owner['last_activity_at'] == (T0 + timedelta(hours=4) if enabled else c.now())
    assert owner['status'] == ('closed' if enabled else 'live')
    assert (service.live_episode('u', collaborators=c) is None) == enabled


def test_late_discard_purges_notes_before_valid_member_joins(lane):
    store, c, calls = lane
    service.attach_conversation('u', 'noise', 'omi', started_at=T0, collaborators=c)
    owner = episodes.get_current_episode('u', firestore_client=store)
    episodes.update_episode(
        'u',
        owner['id'],
        expected_version=owner['state_version'],
        updates={
            'title': 'Discarded noise',
            'bullets': ['Discarded noise'],
            'people': ['Noise'],
            'open_questions': ['Discarded noise?'],
            'moments': [{'id': 'noise-m', 'conversation_id': 'noise', 'heading': 'Discarded noise'}],
            'provisional_items': [
                {'id': 'noise-i', 'conversation_id': 'noise', 'text': 'Discarded noise', 'status': 'provisional'}
            ],
        },
        firestore_client=store,
    )
    capture = row('noise', discarded=True)
    store.rows[('users', 'u', 'conversations', 'noise')] = capture
    service.on_conversation_finalized('u', 'noise', capture, trigger='capture_end', collaborators=c)
    clean = episodes.get_episode('u', owner['id'], firestore_client=store)
    assert (
        clean['moments']
        == clean['provisional_items']
        == clean['bullets']
        == clean['people']
        == clean['open_questions']
        == []
    )
    assert clean['title'] == '' and clean['summary_needs_regeneration']
    c.now = lambda: T0 + timedelta(minutes=1)
    service.attach_conversation('u', 'valid', 'omi', started_at=c.now(), collaborators=c)
    moment = MomentInput(
        'valid',
        'omi',
        [{'id': 'valid-s', 'start': 0, 'end': 30, 'text': 'Useful planning discussion. ' * 20}],
        c.now(),
        c.now() + timedelta(seconds=30),
        'pause',
    )
    assert service.record_moment('u', moment, c) == 'applied'
    clean = episodes.get_episode('u', owner['id'], firestore_client=store)
    assert all(m.get('conversation_id') != 'noise' for m in clean['moments'])
    assert 'Discarded noise' not in str(calls)


@pytest.mark.parametrize('already_live', [False, True])
def test_paired_desktop_pendant_group_recovers_once_without_duplicate_moments(lane, monkeypatch, already_live):
    from utils.episodes import finalize

    store, c, calls = lane
    group = {'id': 'pair', 'primary_id': 'pendant', 'members': [{'id': 'pendant'}, {'id': 'desktop'}]}
    captures = {cid: row(cid, seconds=120, capture_group=group) for cid in ('pendant', 'desktop')}
    captures['desktop']['source'] = 'desktop'
    for cid, capture in captures.items():
        capture['transcript_segments'][0]['text'] = 'Plan the next milestone together. ' * 30
        store.rows[('users', 'u', 'conversations', cid)] = capture
    if already_live:
        service.attach_conversation('u', 'pendant', 'omi', started_at=T0, collaborators=c)
    c.now = lambda: T0 + timedelta(hours=2)
    recovered = []
    recover = service._record_recovered
    monkeypatch.setattr(
        service,
        '_record_recovered',
        lambda uid, eid, cid, row, collab: (recovered.append(cid), recover(uid, eid, cid, row, collab))[1],
    )
    finalized = service.on_conversation_finalized
    monkeypatch.setattr(
        service,
        'on_conversation_finalized',
        lambda uid, cid, row, **kw: finalized(uid, cid, row, collaborators=c, **kw),
    )
    monkeypatch.setattr(service.conversations_db, 'get_conversation', lambda uid, cid, **kw: captures.get(cid))
    raw_snapshot = service.conversations_db.get_conversation_raw_snapshot
    monkeypatch.setattr(
        service.conversations_db,
        'get_conversation_raw_snapshot',
        lambda uid, cid, **kw: (
            {'capture_group': group} if kw.get('field_paths') == ['capture_group'] else raw_snapshot(uid, cid, **kw)
        ),
    )
    monkeypatch.setattr(finalize.client_gate, 'client_seen_cached', lambda uid: True)
    monkeypatch.setattr(finalize, 'submit_with_context', lambda executor, fn, *args: fn(*args))
    finalize.schedule_group_attachments('u', ['desktop', 'pendant'])
    assert recovered == ['pendant']
    # A secondary's separate finalizer must not recover its copy or rerun the canonical recovery.
    finalized('u', 'desktop', captures['desktop'], trigger='capture_group', collaborators=c)
    assert recovered == ['pendant']
    owner = episodes.get_episode_for_conversation('u', 'pendant', firestore_client=store)
    assert owner['conversation_ids'] == ['pendant', 'desktop']
    assert owner['duplicate_conversation_ids'] == ['desktop']
    assert episodes.get_episode_for_conversation('u', 'desktop', firestore_client=store)['id'] == owner['id']
    assert owner['moments'] and {m['conversation_id'] for m in owner['moments']} == {'pendant'}
    assert service.to_wire(owner)['conversation_ids'] == ['pendant']
    assert len(calls) == 1


@pytest.mark.parametrize('relevance_first', [False, True])
def test_desktop_client_finalize_inside_pendant_occasion_claims_one_membership(lane, monkeypatch, relevance_first):
    from utils.conversations import relevance_io

    store, c, calls = lane
    pendant = row('pendant', seconds=44 * 60, recorded_start=T0, recorded_end=T0 + timedelta(minutes=44))
    store.rows[('users', 'u', 'conversations', 'pendant')] = pendant
    service.attach_conversation('u', 'pendant', 'omi', started_at=T0, collaborators=c)
    c.now = lambda: T0 + timedelta(minutes=44)
    service.attach_conversation('u', 'pendant', 'omi', started_at=c.now(), collaborators=c)
    owner = episodes.get_current_episode('u', firestore_client=store)
    shared_text = (
        'We agreed to ship the release on Friday after reviewing the remaining deployment checks together. '
        'Maya will verify the migration against the staging database and send the results before lunch. '
        'Alex will prepare the customer announcement once those checks pass. We also reviewed the support '
        'schedule and agreed that someone should monitor the rollout for the first hour. If the error '
        'rate rises we will pause the rollout and investigate before adding any more customers.'
    )
    pendant['transcript_segments'] = [dict(id='pendant-s', start=41 * 60, end=44 * 60, text=shared_text, is_user=True)]
    assert (
        service.record_moment(
            'u', MomentInput('pendant', 'omi', pendant['transcript_segments'], T0, c.now(), 'interval'), c
        )
        == 'applied'
    )
    content_before = episodes.get_current_episode('u', firestore_client=store)
    calls_before = len(calls)
    at = T0 + timedelta(minutes=41)
    desktop = row('desktop', at, seconds=180, recorded_start=at, recorded_end=c.now(), clock='imported')
    desktop['transcript_segments'][0]['text'] = shared_text
    desktop['source'] = 'desktop'
    desktop['has_photos'] = False
    store.rows[('users', 'u', 'conversations', 'desktop')] = desktop
    monkeypatch.setattr(episodes, 'get_firestore_client', lambda: store)
    monkeypatch.setattr(episode_timeline, 'get_firestore_client', lambda: store)
    monkeypatch.setattr(relevance_io.conversations_db, 'get_firestore_client', lambda: store)
    if relevance_first:
        reason = relevance_io.occasion_retention('u', SimpleNamespace(**desktop))
        assert reason == 'occasion_member'
        # The relevance result itself proves durable membership, before fanout or notes.
        assert episodes.get_episode_for_conversation('u', 'desktop', firestore_client=store)['id'] == owner['id']
        assert desktop['episode_id'] == owner['id']
        assert len(calls) == calls_before
    desktop['relevance_decision'] = dict(
        verdict='keep', reason='occasion_member', trigger='client_finalize', decided_by='policy'
    )
    for _ in range(2):
        assert (
            service.on_conversation_finalized('u', 'desktop', desktop, trigger='client_finalize', collaborators=c)
            != 'error'
        )
        assert episodes.get_episode_for_conversation('u', 'desktop', firestore_client=store)['id'] == owner['id']
    assert sum(e['conversation_ids'].count('desktop') for e in all_episodes(store)) == 1
    result = episodes.get_episode_for_conversation('u', 'desktop', firestore_client=store)
    assert result['moments'] == content_before['moments']
    assert result['bullets'] == content_before['bullets']
    assert len(calls) == calls_before
    assert_timeline(store)


@pytest.mark.parametrize('status,reason', [('live', None), ('closed', 'gap'), ('closed', 'user')])
def test_discard_after_attach_shrinks_both_recorded_bounds(lane, status, reason):
    store, c, _ = lane
    captures = [
        row('early-noise', seconds=120),
        row('speech', T0 + timedelta(minutes=21), seconds=360),
        row('late-noise', T0 + timedelta(minutes=29), seconds=120),
    ]
    for capture in captures:
        cid = capture['id']
        store.rows[('users', 'u', 'conversations', cid)] = capture
        c.now = lambda r=capture: r['started_at']
        service.attach_conversation(
            'u', cid, 'omi', started_at=c.now(), ended_at=c.now() + timedelta(seconds=120), collaborators=c
        )
    owner = episodes.get_current_episode('u', firestore_client=store)
    if status == 'closed':
        episodes.close_episode('u', owner['id'], reason, closed_at=T0 + timedelta(minutes=32), firestore_client=store)
    for capture in (captures[0], captures[-1]):
        # Reproduce the stale intake hint plus a final model discard, even on a legacy row
        # whose discarded projection has not caught up with the stored verdict.
        capture.update(
            sync_relevance='keep',
            relevance_decision=dict(verdict='discard', decided_by='model', trigger='sync_update', arm='jev'),
        )
        assert (
            service.on_conversation_finalized('u', capture['id'], capture, trigger='sync_update', collaborators=c)
            == 'skipped_discarded'
        )
    clean = episodes.get_episode('u', owner['id'], firestore_client=store)
    assert clean['started_at'] == T0 + timedelta(minutes=21)
    assert clean['last_activity_at'] == T0 + timedelta(minutes=27)
    if status == 'closed':
        assert clean['recorded_end'] == T0 + timedelta(minutes=27)
    else:
        assert service.to_wire(clean)['timer_started_at'] == T0 + timedelta(minutes=21)
    assert set(clean['member_activity']) == {'speech'}
    assert_timeline(store)


def test_final_discard_overrules_intake_keep_for_every_attach_path(lane):
    store, c, calls = lane
    capture = row('noise', sync_relevance='keep', relevance_decision={'verdict': 'discard', 'decided_by': 'model'})
    store.rows[('users', 'u', 'conversations', 'noise')] = capture
    assert service.attach_conversation('u', 'noise', 'omi', started_at=T0, collaborators=c) == 'skipped_discarded'
    assert service.attach_synced_intake('u', 'noise', capture, collaborators=c) == 'skipped_discarded'
    assert (
        service.on_conversation_finalized('u', 'noise', capture, trigger='client_finalize', collaborators=c)
        == 'skipped_discarded'
    )
    assert not all_episodes(store) and not calls


@pytest.mark.parametrize('live', [False, True])
def test_new_member_cannot_restore_a_discarded_anchor(lane, live):
    store, c, _ = lane
    noise = row('noise', seconds=120)
    store.rows[('users', 'u', 'conversations', 'noise')] = noise
    if live:
        service.attach_conversation('u', 'noise', 'omi', started_at=T0, collaborators=c)
    else:
        service.attach_synced_intake('u', 'noise', noise, collaborators=c)
    owner = episodes.get_episode_for_conversation('u', 'noise', firestore_client=store)
    noise['discarded'] = True
    service.on_conversation_finalized('u', 'noise', noise, trigger='sync_update', collaborators=c)
    at = T0 + timedelta(minutes=21)
    speech = row('speech', at, seconds=360)
    store.rows[('users', 'u', 'conversations', 'speech')] = speech
    c.now = lambda: at
    service.attach_synced_intake('u', 'speech', speech, collaborators=c)
    clean = episodes.get_episode_for_conversation('u', 'speech', firestore_client=store)
    assert clean['id'] == owner['id']
    assert clean['started_at'] == at
    assert clean['last_activity_at'] == at + timedelta(minutes=6)
    assert set(clean['member_activity']) == {'speech'}


def test_discard_repairs_bounds_after_losing_a_notes_cas(lane, monkeypatch):
    store, c, _ = lane
    for cid, start in [('noise', T0), ('speech', T0 + timedelta(minutes=21))]:
        store.rows[('users', 'u', 'conversations', cid)] = row(cid, start)
        c.now = lambda start=start: start
        service.attach_conversation('u', cid, 'omi', started_at=start, collaborators=c)
    noise = store.rows[('users', 'u', 'conversations', 'noise')]
    noise['discarded'] = True
    update = episodes.update_episode
    versions = []

    def race(uid, eid, **kwargs):
        versions.append(kwargs['expected_version'])
        if len(versions) == 1:
            # A notes writer commits between the finalizer's read and discard CAS.
            update(uid, eid, **{**kwargs, 'updates': {'title': 'Concurrent notes'}})
        return update(uid, eid, **kwargs)

    monkeypatch.setattr(episodes, 'update_episode', race)
    assert (
        service.on_conversation_finalized('u', 'noise', noise, trigger='sync_update', collaborators=c)
        == 'skipped_discarded'
    )
    assert len(versions) == 2 and versions[1] == versions[0] + 1
    clean = episodes.get_current_episode('u', firestore_client=store)
    assert clean['started_at'] == T0 + timedelta(minutes=21)
    assert clean['last_activity_at'] == T0 + timedelta(minutes=21, seconds=30)
    assert set(clean['member_activity']) == {'speech'}


def test_relevance_claim_survives_historical_repartition(lane):
    store, _, _ = lane
    first = episode_timeline.attach_recorded(
        'u',
        'first',
        'omi',
        T0,
        T0 + timedelta(minutes=2),
        choose=timeline.choose_recorded_episode,
        new_episode={},
        firestore_client=store,
    )
    at = T0 + timedelta(minutes=1)
    claimed = episode_timeline.attach_existing_recorded(
        'u',
        'desktop',
        'desktop',
        at,
        at,
        episode_id=first['id'],
        choose=timeline.choose_recorded_episode,
        firestore_client=store,
    )
    assert claimed['recorded_members']['desktop'] == {'start': at, 'end': at, 'source': 'desktop'}
    episodes.update_episode(
        'u',
        first['id'],
        expected_version=claimed['state_version'],
        updates={'moments': [{'id': 'desktop-m', 'conversation_id': 'desktop', 'started_at': at}]},
        firestore_client=store,
    )
    later = at + timedelta(minutes=2)
    joined = episode_timeline.attach_recorded(
        'u',
        'later',
        'omi',
        later,
        later,
        choose=timeline.choose_recorded_episode,
        new_episode={},
        firestore_client=store,
    )
    assert set(joined['conversation_ids']) == {'first', 'desktop', 'later'}
    assert joined['parallel_content_spans'] == {'desktop': {'start': T0, 'end': T0 + timedelta(minutes=2)}}
    assert {m['id'] for m in joined['moments']} == {'desktop-m'}
    assert episodes.get_episode_for_conversation('u', 'desktop', firestore_client=store)['id'] == joined['id']


@pytest.mark.parametrize('level', ['standard', 'enhanced'])
@pytest.mark.parametrize('has_clocks', [False, True])
@pytest.mark.parametrize('wal_tail', [False, True])
def test_discard_rebuilds_legacy_encoded_speech_without_processing_end(lane, level, has_clocks, wal_tail):
    from database.conversations import encode_conversation_for_write

    store, c, _ = lane
    noise = row('noise', seconds=120)
    store.rows[('users', 'u', 'conversations', 'noise')] = noise
    service.attach_conversation('u', 'noise', 'omi', started_at=T0, collaborators=c)
    origin = T0 + timedelta(minutes=21)
    speech = row('speech', origin, seconds=60)
    speech['transcript_segments'][0]['start'] = 30
    if wal_tail:
        speech.update(sync_content_revision=1, sync_live_target=False, finished_at=origin + timedelta(seconds=75))
    encoded = encode_conversation_for_write('u', speech, level)
    for key in ('recorded_start', 'recorded_end', 'arrival_at', 'clock'):
        encoded.pop(key, None)
    encoded['data_protection_level'] = level
    store.rows[('users', 'u', 'conversations', 'speech')] = encoded
    c.now = lambda: origin
    service.attach_conversation(
        'u', 'speech', 'omi', started_at=origin, ended_at=origin + timedelta(seconds=60), collaborators=c
    )
    owner = episodes.get_current_episode('u', firestore_client=store)
    if not has_clocks:
        store.rows[('users', 'u', 'episodes', owner['id'])].pop('member_activity')
    noise['discarded'] = True
    assert (
        service.on_conversation_finalized('u', 'noise', noise, trigger='sync_update', collaborators=c)
        == 'skipped_discarded'
    )
    clean = episodes.get_episode('u', owner['id'], firestore_client=store)
    assert clean['started_at'] == origin + timedelta(seconds=30)
    assert clean['last_activity_at'] == origin + timedelta(seconds=75 if wal_tail else 60)


@pytest.mark.parametrize('has_discarded', [False, True])
def test_crossing_attachment_preserves_the_next_recorded_boundary(lane, has_discarded):
    store, _, _ = lane
    for cid, start, seconds in [
        ('kept', T0, 600),
        ('crossing', T0 + timedelta(minutes=15), 600),
        ('next', T0 + timedelta(minutes=20), 120),
    ]:
        capture = row(cid, start, seconds=seconds)
        store.rows[('users', 'u', 'conversations', cid)] = capture
    old = dict(
        id='old',
        status='closed',
        close_reason='gap',
        started_at=T0,
        last_activity_at=T0 + timedelta(minutes=10),
        recorded_end=T0 + timedelta(minutes=10),
        closed_at=T0 + timedelta(minutes=10),
        state_version=1,
        conversation_ids=['kept'],
        member_activity={'kept': T0 + timedelta(minutes=10)},
    )
    if has_discarded:
        old.update(conversation_ids=['kept', 'noise'], discarded_conversation_ids=['noise'])
        store.rows[('users', 'u', 'conversations', 'noise')] = row('noise', discarded=True)
    following = dict(
        id='following',
        status='live',
        started_at=T0 + timedelta(minutes=20),
        last_activity_at=T0 + timedelta(minutes=22),
        state_version=1,
        conversation_ids=['next'],
    )
    for episode in (old, following):
        store.rows[('users', 'u', 'episodes', episode['id'])] = episodes.seal('u', episode)
    joined = episode_timeline.attach_recorded(
        'u',
        'crossing',
        'desktop',
        T0 + timedelta(minutes=15),
        T0 + timedelta(minutes=25),
        choose=timeline.choose_recorded_episode,
        new_episode={},
        firestore_client=store,
    )
    assert joined['id'] == 'old'
    assert joined['last_activity_at'] == joined['recorded_end'] == T0 + timedelta(minutes=20)
    assert joined['member_activity']['crossing'] == T0 + timedelta(minutes=20)
    assert episodes.get_episode_for_conversation('u', 'crossing', firestore_client=store)['id'] == 'old'
    assert_timeline(store)


@pytest.mark.parametrize('status', ['live', 'closed'])
def test_discard_rebases_four_hour_cap_on_retained_start(lane, status):
    store, c, _ = lane
    at = T0 + timedelta(minutes=21)
    end = T0 + timedelta(hours=4, minutes=8)
    for capture in [row('noise', seconds=120), row('speech', at, seconds=(end - at).total_seconds())]:
        store.rows[('users', 'u', 'conversations', capture['id'])] = capture
    base = dict(
        id='owner',
        status=status,
        close_reason='gap' if status == 'closed' else None,
        started_at=T0,
        last_activity_at=T0 + timedelta(hours=4),
        state_version=1,
        conversation_ids=['noise', 'speech'],
        member_activity={'noise': T0 + timedelta(minutes=2), 'speech': T0 + timedelta(hours=4)},
    )
    if status == 'closed':
        base.update(closed_at=T0 + timedelta(hours=4), recorded_end=T0 + timedelta(hours=4))
    store.rows[('users', 'u', 'episodes', 'owner')] = episodes.seal('u', base)
    clean = episodes.update_episode(
        'u', 'owner', expected_version=1, updates={'discarded_conversation_ids': ['noise']}, firestore_client=store
    )
    assert clean['started_at'] == at
    assert clean['last_activity_at'] == clean['member_activity']['speech'] == end
    if status == 'closed':
        assert clean['recorded_end'] == end


@pytest.mark.parametrize('writer', ['commit', 'update'])
def test_notes_after_discard_reuse_repaired_bounds_without_member_reads(lane, monkeypatch, writer):
    from tests.unit.fixtures.strict_firestore_transaction import StrictFirestoreDocument

    store, c, _ = lane
    for cid, start in [('noise', T0), ('speech', T0 + timedelta(minutes=21))]:
        store.rows[('users', 'u', 'conversations', cid)] = row(cid, start)
        c.now = lambda start=start: start
        service.attach_conversation('u', cid, 'omi', started_at=start, collaborators=c)
    owner = episodes.get_current_episode('u', firestore_client=store)
    clean = episodes.update_episode(
        'u',
        owner['id'],
        expected_version=owner['state_version'],
        updates={'discarded_conversation_ids': ['noise']},
        firestore_client=store,
    )
    get = StrictFirestoreDocument.get
    reads = []

    def track(ref, *args, **kwargs):
        if ref.path[2] == 'conversations':
            reads.append(ref.path)
        return get(ref, *args, **kwargs)

    monkeypatch.setattr(StrictFirestoreDocument, 'get', track)
    monkeypatch.setattr(
        episodes, 'decode_transcript_segments_verified', lambda *a: pytest.fail('notes decoded member transcript')
    )
    for i in range(3):
        kwargs = dict(expected_version=clean['state_version'], updates={'title': f'Notes {i}'}, firestore_client=store)
        if writer == 'commit':
            clean = episodes.commit_moment('u', expected_episode_id=owner['id'], **kwargs)
        else:
            clean = episodes.update_episode('u', owner['id'], **kwargs)
    assert reads == []
    assert clean['started_at'] == T0 + timedelta(minutes=21)


def test_exact_occasion_claim_rejects_different_past_cap_owner(lane):
    store, _, _ = lane
    old = dict(
        id='old',
        status='closed',
        close_reason='hard_cap',
        started_at=T0,
        last_activity_at=T0 + timedelta(hours=4),
        recorded_end=T0 + timedelta(hours=4),
        state_version=1,
        conversation_ids=['desktop'],
    )
    new = dict(
        old,
        id='new',
        status='live',
        started_at=T0 + timedelta(hours=5),
        last_activity_at=T0 + timedelta(hours=5, minutes=10),
        conversation_ids=['pendant'],
    )
    for item in [old, new]:
        store.rows[('users', 'u', 'episodes', item['id'])] = episodes.seal('u', item)
    store.rows[('users', 'u', 'episode_links', 'desktop')] = {'episode_id': 'old'}
    before = dict(store.rows)
    with pytest.raises(episodes.EpisodeConflict, match='recorded_owner_changed'):
        episode_timeline.attach_existing_recorded(
            'u',
            'desktop',
            'desktop',
            new['started_at'],
            new['last_activity_at'],
            episode_id='new',
            choose=timeline.choose_recorded_episode,
            firestore_client=store,
        )
    assert store.rows == before


def test_parallel_desktop_keeps_new_speech_after_the_pendant_overlap(lane):
    store, c, calls = lane
    primary = row('pendant', seconds=180, has_photos=False)
    store.rows[('users', 'u', 'conversations', 'pendant')] = primary
    service.attach_conversation('u', 'pendant', 'omi', started_at=T0, collaborators=c)
    c.now = lambda: T0 + timedelta(minutes=3)
    service.attach_conversation('u', 'pendant', 'omi', started_at=T0, ended_at=c.now(), collaborators=c)
    desktop = row('desktop', T0 + timedelta(minutes=2), seconds=180, has_photos=False)
    desktop['source'] = 'desktop'
    desktop['transcript_segments'] = [
        dict(id='overlap', start=0, end=60, text='The pendant already captured this discussion.', is_user=True),
        dict(
            id='new',
            start=61,
            end=180,
            text=' '.join(['We also agreed to meet on Monday to review the migration results.'] * 8),
            is_user=True,
        ),
    ]
    store.rows[('users', 'u', 'conversations', 'desktop')] = desktop
    c.now = lambda: T0 + timedelta(minutes=5)
    assert (
        service.on_conversation_finalized('u', 'desktop', desktop, trigger='client_finalize', collaborators=c)
        != 'error'
    )
    owner = episodes.get_episode_for_conversation('u', 'desktop', firestore_client=store)
    assert owner['moments'] and {m['conversation_id'] for m in owner['moments']} == {'desktop'}
    assert len(calls) == 1
    assert 'pendant already captured' not in str(calls)
    assert 'meet on Monday' in str(calls)


def test_discarded_anchor_cannot_let_a_later_component_overwrite_its_old_id(lane):
    store, _, _ = lane

    def attach(cid, lo, hi):
        store.rows[('users', 'u', 'conversations', cid)] = dict(id=cid, recorded_start=lo, recorded_end=hi)
        return episode_timeline.attach_recorded(
            'u', cid, 'omi', lo, hi, choose=timeline.choose_recorded_episode, new_episode={}, firestore_client=store
        )

    attach('noise', T0, T0 + timedelta(minutes=20))
    speech = attach('speech', T0 + timedelta(minutes=40), T0 + timedelta(minutes=45))
    repaired = episodes.update_episode(
        'u',
        speech['id'],
        expected_version=speech['state_version'],
        updates={
            'discarded_conversation_ids': ['noise'],
            'moments': [{'id': 'speech-note', 'conversation_id': 'speech'}],
        },
        firestore_client=store,
    )
    assert repaired['started_at'] == T0 + timedelta(minutes=40)
    fresh = attach('fresh', T0, T0 + timedelta(minutes=1))
    assert fresh['id'] != repaired['id']
    retained = episodes.get_episode('u', repaired['id'], firestore_client=store)
    assert retained == repaired
    assert episodes.get_episode_for_conversation('u', 'speech', firestore_client=store)['id'] == repaired['id']
    assert episodes.get_episode_for_conversation('u', 'noise', firestore_client=store)['id'] == repaired['id']
    assert episodes.get_episode_for_conversation('u', 'fresh', firestore_client=store)['id'] == fresh['id']
    replay = attach('fresh', T0, T0 + timedelta(minutes=2))
    assert replay['id'] == fresh['id']
    assert episodes.get_episode('u', repaired['id'], firestore_client=store) == repaired
    assert_timeline(store)


@pytest.mark.parametrize('overlap', [False, True])
def test_earlier_desktop_speech_survives_adjacency_and_partial_overlap(lane, overlap):
    store, c, calls = lane
    start = T0 + timedelta(minutes=10)
    c.now = lambda: start
    primary = row('pendant', start, seconds=120, has_photos=False)
    store.rows[('users', 'u', 'conversations', 'pendant')] = primary
    service.attach_conversation('u', 'pendant', 'omi', started_at=start, collaborators=c)
    c.now = lambda: start + timedelta(minutes=2)
    service.attach_conversation('u', 'pendant', 'omi', started_at=c.now(), collaborators=c)
    desktop = row('desktop', T0, seconds=12 * 60 if overlap else 120, has_photos=False)
    desktop['source'] = 'desktop'
    desktop['transcript_segments'] = [
        dict(
            id='prefix',
            start=0,
            end=120,
            text=' '.join(['Before the meeting I confirmed the customer migration schedule for next Monday.'] * 8),
            is_user=True,
        )
    ]
    if overlap:
        desktop['transcript_segments'].append(
            dict(
                id='shared',
                start=10 * 60,
                end=12 * 60,
                text='This speech overlaps the already captured meeting.',
                is_user=True,
            )
        )
    store.rows[('users', 'u', 'conversations', 'desktop')] = desktop
    assert (
        service.on_conversation_finalized('u', 'desktop', desktop, trigger='client_finalize', collaborators=c)
        != 'error'
    )
    owner = episodes.get_episode_for_conversation('u', 'desktop', firestore_client=store)
    assert 'desktop' in owner['conversation_ids']
    assert {m['conversation_id'] for m in owner['moments']} == {'desktop'}
    assert len(calls) == 1
    assert 'customer migration schedule' in str(calls)
    assert 'speech overlaps' not in str(calls)


@pytest.mark.parametrize('decided_by', ['model', 'jev'])
def test_meaningful_sync_append_is_admitted_after_old_model_discard(lane, monkeypatch, decided_by):
    from tests.unit.test_sync_cross_job_assignment import chunk, intake
    from utils.conversations.fragment_visibility import is_relevance_discarded

    store, c, _ = lane
    service.attach_conversation('u', 'pendant', 'omi', started_at=T0, collaborators=c)
    first, _, _ = intake(store, chunk('fragment', (T0 + timedelta(minutes=1)).timestamp(), 'Mm-hmm.'))
    stored = store.rows[('users', 'u', 'conversations', first['id'])]
    stored.update(
        discarded=True, relevance_decision=dict(verdict='discard', decided_by=decided_by, reason='model_discard')
    )
    expanded, _, _ = intake(
        store,
        chunk(
            'speech',
            (T0 + timedelta(minutes=2)).timestamp(),
            'Please send the migration checklist to the team tomorrow.',
        ),
    )
    monkeypatch.setattr(service.client_gate, 'client_seen_cached', lambda uid: True)
    monkeypatch.setattr(service, '_record_recovered', lambda *a: 'skipped_applied')
    c.now = lambda: T0 + timedelta(minutes=3)
    assert not is_relevance_discarded(expanded)
    assert service.attach_synced_intake('u', expanded['id'], expanded, collaborators=c) == 'recorded'
    owner = episodes.get_episode_for_conversation('u', expanded['id'], firestore_client=store)
    assert owner['id'] == episodes.get_episode_for_conversation('u', 'pendant', firestore_client=store)['id']
    assert visible_episode('u', owner, firestore_client=store) is not None
