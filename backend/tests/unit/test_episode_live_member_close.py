"""Synthetic capture clocks; no account data or external clients."""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

import pytest

from config import episode_live_members as live
from database import episode_live_members as placement, episodes
from tests.unit.test_episode_batch_audio_close import timeline_store  # noqa: F401
from tests.unit.test_episode_composer import T0, UID, _c, _row, store  # noqa: F401
from utils.episodes import batch_close, composer, service


def active(start=T0, **changes):
    return {
        'status': 'in_progress',
        'record_lane_owner': 'batch_live_v1',
        'record_audio_closed': False,
        'private_cloud_sync_enabled': True,
        'started_at': start,
        'recorded_start': start,
        'clock': 'live_capture',
        'server_batch_audio_start': start.timestamp(),
        'source': 'desktop',
        **changes,
    }


def episode(**changes):
    return {
        'id': 'old',
        'status': 'closed',
        'close_reason': 'gap',
        'started_at': T0,
        'closed_at': T0 + timedelta(hours=1),
        'last_activity_at': T0 + timedelta(minutes=30),
        'recorded_end': T0 + timedelta(minutes=30),
        'state_version': 1,
        'conversation_ids': ['finished'],
        'member_activity': {},
        **changes,
    }


def seed(db, *, linked=False, status='closed', start=None):
    old = episode(status=status)
    if linked:
        old['conversation_ids'].append('live')
        old['last_activity_at'] = old['recorded_end'] = T0 + timedelta(hours=2)
    db.rows[('users', 'owner', 'episodes', 'old')] = old
    db.rows[('users', 'owner', 'conversations', 'finished')] = _row('finished', T0, 30)
    db.rows[('users', 'owner', 'conversations', 'live')] = active(
        start or old['closed_at'], **({'episode_id': 'old'} if linked else {})
    )
    if linked:
        db.rows[('users', 'owner', 'episode_links', 'live')] = {'episode_id': 'old'}
    if status == 'live':
        db.rows[('users', 'owner', 'episode_links', 'current')] = {'episode_id': 'old'}
    return old


def place(db):
    return placement.place('owner', 'live', template=episode(), firestore_client=db, admission=True)


@pytest.mark.parametrize('offset', [0, 1, 5])
@pytest.mark.parametrize('arrival_offset', [-1, 0])
def test_arrival_before_or_at_close_uses_capture_start(timeline_store, offset, arrival_offset):
    db = timeline_store
    old = seed(db, start=T0 + timedelta(hours=1, seconds=offset))
    db.rows[('users', 'owner', 'conversations', 'live')]['created_at'] = old['closed_at'] + timedelta(
        seconds=arrival_offset
    )
    result = place(db)
    assert result['id'] != 'old' and result['status'] == 'live'
    assert db.rows[('users', 'owner', 'episodes', 'old')] == old
    assert db.rows[('users', 'owner', 'episode_links', 'current')]['episode_id'] == result['id']


def test_existing_stuck_membership_rehomes_atomically_without_touching_audio(timeline_store):
    db = timeline_store
    seed(db, linked=True, start=T0 + timedelta(hours=1, seconds=5))
    path = ('users', 'owner', 'conversations', 'live')
    db.rows[path].update(sync_live_target=True, server_batch_audio_end=(T0 + timedelta(hours=2)).timestamp())
    original = deepcopy(db.rows[path])
    result = place(db)
    assert result['_live_member_rehomed']
    assert db.rows[path] == {**original, 'episode_id': result['id']}
    old = db.rows[('users', 'owner', 'episodes', 'old')]
    assert old['conversation_ids'] == ['finished']
    assert old['recorded_end'] == T0 + timedelta(minutes=30)
    assert old['summary_needs_regeneration'] and old['home_needs_prepare']
    before = deepcopy(db.rows)
    assert not place(db)['_live_member_rehomed']
    assert db.rows == before


def test_true_preboundary_live_member_keeps_ownership(timeline_store):
    db = timeline_store
    old = seed(db, linked=True, start=T0 + timedelta(minutes=59))
    before = deepcopy(db.rows)
    assert place(db)['id'] == old['id']
    assert db.rows == before


def test_assignment_before_close_rotates_old_episode(timeline_store):
    db = timeline_store
    old = seed(db, status='live', start=T0 + timedelta(hours=1, seconds=5))
    result = place(db)
    assert result['id'] != old['id']
    closed = db.rows[('users', 'owner', 'episodes', 'old')]
    assert closed['closed_at'] == T0 + timedelta(hours=1)
    assert 'live' not in closed['conversation_ids']
    # The stale close cannot close the successor or erase its navigation pointer.
    assert episodes.close_episode('owner', 'old', 'gap', firestore_client=db) is None
    assert db.rows[('users', 'owner', 'episode_links', 'current')]['episode_id'] == result['id']


def test_stale_gap_close_refuses_assignment_winner(timeline_store):
    db = timeline_store
    old = seed(db, status='live', start=T0 + timedelta(minutes=40))
    prior = old['last_activity_at']
    assert place(db)['id'] == 'old'
    assert (
        episodes.close_episode(
            'owner', 'old', 'gap', closed_at=T0 + timedelta(hours=1), expected_activity_at=prior, firestore_client=db
        )
        is None
    )
    assert db.rows[('users', 'owner', 'episodes', 'old')]['status'] == 'live'


@pytest.mark.parametrize('closed_field', ['record_audio_closed', 'server_batch_audio_closed'])
def test_delayed_admission_cannot_reopen_finished_capture(timeline_store, closed_field):
    db = timeline_store
    seed(db, linked=True)
    db.rows[('users', 'owner', 'conversations', 'live')][closed_field] = True
    before = deepcopy(db.rows)
    assert place(db) == 'closed'
    assert db.rows == before


def test_finished_subset_composes_and_finished_live_member_recomposes(store):
    row = _row('live', T0, 1, status='in_progress') | active()
    store.rows['live'] = row
    store.episode['conversation_ids'].append('live')
    # Belongs before the close, so exclude readiness without changing membership.
    calls = []
    c = _c(calls=calls)
    assert composer.compose(UID, 'ep1', collaborators=c) == 'composed'
    assert 'live' not in store.episode['composed_member_ids']
    assert len(calls) == 1
    row.update(status='completed', record_audio_closed=True)
    assert composer.needs_compose(store.episode, visible_member_ids=store.episode['conversation_ids'])
    assert composer.compose(UID, 'ep1', collaborators=c) == 'composed'
    assert 'live' in store.episode['composed_member_ids']
    assert len(calls) == 2


def test_existing_stuck_pending_state_self_heals_on_next_compose(store):
    store.rows['live'] = _row('live', T0, 1, status='in_progress') | active()
    store.episode['conversation_ids'].append('live')
    store.episode.update(
        compose_pending_since=T0, compose_pending_membership=['c1'], compose_transcript_wait_until=None
    )
    assert composer.needs_compose(store.episode)
    assert composer.compose(UID, 'ep1', collaborators=_c()) == 'composed'
    assert store.episode['compose_pending_since'] is None


def test_kill_switch_restores_waiting_and_recorded_placement(store, monkeypatch):
    monkeypatch.setenv(live.EPISODE_LIVE_MEMBER_CLOSE_ENABLED_ENV, 'false')
    store.rows['live'] = _row('live', T0, 1, status='in_progress') | active()
    store.episode['conversation_ids'].append('live')
    assert composer.compose(UID, 'ep1', collaborators=_c()) == 'waiting'
    place_live = Mock(side_effect=AssertionError('switch disabled'))
    legacy = Mock(return_value={'id': 'old'})
    monkeypatch.setattr(service.live_members_db, 'place', place_live)
    monkeypatch.setattr(service.episode_timeline, 'attach_recorded', legacy)
    assert service.attach_recorded(UID, 'live', active(), T0, T0, _c())['id'] == 'old'
    legacy.assert_called_once()


def test_repair_on_compose_reloads_membership(store, monkeypatch):
    def repair(uid, episode, c):
        store.episode['conversation_ids'] = ['c1']
        return True

    monkeypatch.setattr(service, 'repair_closed_live_members', repair)
    assert composer.compose(UID, 'ep1', collaborators=_c()) == 'composed'
    assert store.episode['composed_member_ids'] == ['c1']


@pytest.mark.parametrize(
    'field,value',
    [
        ('record_audio_closed', True),
        ('server_batch_audio_closed', True),
        ('status', 'completed'),
        ('deleted', True),
        ('is_locked', True),
    ],
)
def test_exclusion_stops_at_finish_or_privacy_exit(field, value):
    assert not live.capturing(active(**{field: value}))


def test_readiness_fences_capture_state_instead_of_audio_revision(store):
    store.rows['live'] = _row('live', T0, 1, status='in_progress') | active()
    store.episode['conversation_ids'].append('live')
    revisions = {}
    state, members = composer._members(UID, store.episode, _c(), revisions=revisions)
    assert state == 'ok' and len(members) == 2
    assert revisions['live'] == live.CAPTURING_REVISION


def test_rehome_is_independent_of_attach_optimization_switch(timeline_store, monkeypatch):
    monkeypatch.setenv('EPISODE_ATTACH_OPTIMIZATIONS_ENABLED', 'false')
    seed(timeline_store, linked=True, start=T0 + timedelta(hours=1, seconds=5))
    assert place(timeline_store)['_live_member_rehomed']


def test_rehome_joins_successor_when_its_start_arrived_later(timeline_store):
    db = timeline_store
    seed(db, linked=True, start=T0 + timedelta(hours=1, seconds=5))
    following = episode(
        id='next',
        status='live',
        close_reason=None,
        closed_at=None,
        started_at=T0 + timedelta(hours=1, seconds=10),
        last_activity_at=T0 + timedelta(hours=1, minutes=2),
        conversation_ids=['next-member'],
    )
    db.rows[('users', 'owner', 'episodes', 'next')] = following
    db.rows[('users', 'owner', 'episode_links', 'current')] = {'episode_id': 'next'}
    result = place(db)
    assert result['id'] == 'next'
    assert result['started_at'] == T0 + timedelta(hours=1, seconds=5)
    assert set(result['conversation_ids']) == {'next-member', 'live'}
    assert 'recorded_members' not in db.rows[('users', 'owner', 'episodes', 'old')]


@pytest.mark.parametrize(
    'changes',
    [
        {'private_cloud_sync_enabled': False},
        {'uses_custom_stt': True},
        {'data_protection_level': 'private'},
        {'deleted': True},
        {'status': 'completed'},
    ],
)
def test_stale_live_placement_refuses_finish_or_privacy_change(timeline_store, changes):
    db = timeline_store
    seed(db, linked=True)
    db.rows[('users', 'owner', 'conversations', 'live')].update(changes)
    before = deepcopy(db.rows)
    with pytest.raises(episodes.EpisodeConflict, match='live_member_capture_changed'):
        placement.place('owner', 'live', template=episode(), firestore_client=db)
    assert db.rows == before


def test_rotation_preserves_hard_cap_reason(timeline_store):
    db = timeline_store
    old = seed(db, status='live', start=T0 + timedelta(hours=4, seconds=5))
    old['last_activity_at'] = T0 + timedelta(hours=3, minutes=50)
    assert place(db)['id'] != 'old'
    closed = db.rows[('users', 'owner', 'episodes', 'old')]
    assert closed['close_reason'] == 'hard_cap'
    assert closed['closed_at'] == T0 + timedelta(hours=4)


def test_rehome_carries_live_provisional_state_and_consumption_offsets(timeline_store):
    db = timeline_store
    old = seed(db, linked=True, start=T0 + timedelta(hours=1, seconds=5))
    old.update(
        provisional_items=[{'id': 'reminder', 'conversation_id': 'live', 'status': 'provisional'}],
        moments=[{'id': 'moment', 'conversation_id': 'live'}],
        applied={'live': 12, 'finished': 20},
    )
    result = place(db)
    assert result['provisional_items'][0]['id'] == 'reminder'
    assert result['moments'][0]['id'] == 'moment'
    assert result['applied'] == {'live': 12}
    saved = db.rows[('users', 'owner', 'episodes', 'old')]
    assert saved['provisional_items'] == saved['moments'] == []
    assert saved['applied'] == {'finished': 20}


@pytest.mark.parametrize(
    'changes,reason',
    [
        ({'server_batch_audio_start': (datetime.now(timezone.utc) + timedelta(minutes=1)).timestamp()}, 'future'),
        ({'server_batch_audio_start': (T0 + timedelta(minutes=59, seconds=50)).timestamp()}, 'disagreement'),
        ({'server_batch_audio_start': (T0 + timedelta(hours=1, seconds=20)).timestamp()}, 'disagreement'),
        ({'started_at': None}, 'missing'),
        ({'recorded_start': None}, 'missing'),
        ({'recorded_start': T0 + timedelta(minutes=59, seconds=50)}, 'disagreement'),
        ({'capture_time_trust': 'untrusted'}, 'untrusted'),
        ({'clock': 'estimated_device'}, 'untrusted'),
        ({'clock': None}, 'untrusted'),
        ({'server_batch_audio_start': float('nan')}, 'missing'),
        ({'server_batch_audio_start': None}, 'missing'),
        ({'server_batch_audio_start': True}, 'missing'),
        # Within the five-second tolerance, but opposite sides of the boundary.
        ({'started_at': T0 + timedelta(minutes=59, seconds=59)}, 'disagreement'),
    ],
)
def test_uncertain_capture_clocks_keep_membership_without_any_writes(timeline_store, changes, reason):
    db = timeline_store
    seed(db, linked=True, start=T0 + timedelta(hours=1, seconds=1))
    db.rows[('users', 'owner', 'conversations', 'live')].update(changes)
    before = deepcopy(db.rows)
    result = place(db)
    assert result['id'] == 'old'
    assert not result['_live_member_rehomed']
    assert result['_live_member_clock_refusal'] == reason
    assert db.rows == before


def test_agreeing_interval_just_after_boundary_rehomes_using_earliest_source(timeline_store):
    db = timeline_store
    seed(db, linked=True, start=T0 + timedelta(hours=1, seconds=2))
    db.rows[('users', 'owner', 'conversations', 'live')].update(
        server_batch_audio_start=(T0 + timedelta(hours=1, seconds=3)).timestamp(),
        recorded_start=T0 + timedelta(hours=1, seconds=1),
    )
    result = place(db)
    assert result['_live_member_rehomed']
    assert result['started_at'] == T0 + timedelta(hours=1, seconds=1)


def test_refused_repair_counts_reason_and_keeps_finished_subset_composable(store, monkeypatch):
    store.episode['close_reason'] = 'gap'
    row = _row('live', T0, 1, status='in_progress') | active(started_at=None)
    store.rows['live'] = row
    store.episode['conversation_ids'].append('live')
    placed = Mock(return_value={**store.episode, '_live_member_clock_refusal': 'missing'})
    monkeypatch.setattr(service.live_members_db, 'place', placed)
    counted = Mock()
    monkeypatch.setattr(service.metrics, 'record_live_member_clock_refusal', counted)
    c = _c()
    c.firestore_client = object()
    assert composer.compose(UID, 'ep1', collaborators=c) == 'composed'
    placed.assert_called_once()
    counted.assert_called_once_with('missing')
    assert store.episode['conversation_ids'] == ['c1', 'c2', 'live']
    assert 'live' not in store.episode['composed_member_ids']


def test_clock_refusal_metric_has_closed_labels(monkeypatch):
    counter = Mock()
    monkeypatch.setattr(service.metrics, 'LIVE_MEMBER_CLOCK_REFUSAL', counter)
    service.metrics.record_live_member_clock_refusal('disagreement')
    service.metrics.record_live_member_clock_refusal('arbitrary-value')
    assert counter.labels.call_args_list[0].kwargs == {'reason': 'disagreement'}
    assert counter.labels.call_args_list[1].kwargs == {'reason': 'other'}


def test_agreeing_but_future_clocks_cannot_move_membership(timeline_store):
    db = timeline_store
    future = datetime.now(timezone.utc) + timedelta(minutes=1)
    seed(db, linked=True, start=future)
    before = deepcopy(db.rows)
    assert place(db)['_live_member_clock_refusal'] == 'future'
    assert db.rows == before


@pytest.mark.parametrize('started_at', [True, False])
def test_initial_admission_uses_row_clocks_without_optional_audio_metadata(timeline_store, started_at):
    db = timeline_store
    seed(db, start=T0 + timedelta(hours=1, seconds=1))
    row = db.rows[('users', 'owner', 'conversations', 'live')]
    for key in ('server_batch_audio_start', 'recorded_start', 'clock'):
        row.pop(key)
    row['created_at'] = row['started_at']
    if not started_at:
        row.pop('started_at')
    result = place(db)
    assert result['status'] == 'live' and result['id'] != 'old'
    assert not result['_live_member_rehomed']
    assert result['started_at'] == T0 + timedelta(hours=1, seconds=1)
    before = deepcopy(db.rows)
    retry = place(db)
    assert retry['id'] == result['id']
    assert '_live_member_clock_refusal' not in retry
    assert db.rows == before


def test_initial_admission_without_any_start_keeps_main_skip_behavior(timeline_store, monkeypatch):
    db = timeline_store
    seed(db)
    row = db.rows[('users', 'owner', 'conversations', 'live')]
    row['started_at'] = row['created_at'] = row['server_batch_audio_start'] = None
    row['external_data'] = {'server_batch_only': True}
    monkeypatch.setattr(batch_close, 'episodes_enabled_for', lambda uid: True)
    monkeypatch.setattr(batch_close, 'recorded_episodes_enabled', lambda: True)
    monkeypatch.setattr(batch_close, 'batch_admission_attach_enabled', lambda: True)
    before = deepcopy(db.rows)
    assert place(db) is None
    assert (
        batch_close.attach_admitted_batch_capture(
            'owner', 'live', row, collaborators=service.Collaborators(firestore_client=db)
        )
        == 'skipped'
    )
    assert db.rows == before


def test_rehome_carries_recovered_classification(timeline_store):
    db = timeline_store
    old = seed(db, linked=True)
    old['recovered_conversation_ids'] = ['finished', 'live']
    result = place(db)
    assert result['recovered_conversation_ids'] == ['live']
    assert db.rows[('users', 'owner', 'episodes', 'old')]['recovered_conversation_ids'] == ['finished']


def test_rotation_cleans_pending_state_and_schedules_closed_summary(timeline_store, monkeypatch):
    db = timeline_store
    old = seed(db, status='live', start=T0 + timedelta(hours=1, seconds=1))
    old.update(
        pending_boundary={'finished': {'pending': True}},
        provisional_items=[{'id': 'draft', 'status': 'provisional'}, {'id': 'kept', 'status': 'confirmed'}],
    )
    scheduled = Mock()
    monkeypatch.setattr(service.composer, 'schedule_after_close', scheduled)
    c = service.Collaborators(firestore_client=db, now=lambda: T0 + timedelta(hours=2))
    start = T0 + timedelta(hours=1, seconds=1)
    result = service.attach_recorded('owner', 'live', active(start), start, start, c, admission=True)
    assert result['id'] != 'old'
    assert '_live_member_closed_episode' not in result
    closed = db.rows[('users', 'owner', 'episodes', 'old')]
    assert closed['pending_boundary'] == {}
    assert [item['status'] for item in closed['provisional_items']] == ['dropped', 'confirmed']
    assert closed['summary_needs_regeneration']
    scheduled.assert_called_once_with('owner', 'old', episode=closed, collaborators=c, trigger='close')


def test_recorded_time_rollback_stops_repair_but_keeps_finished_subset_readiness(store, monkeypatch):
    monkeypatch.setenv('EPISODE_RECORDED_TIME_ENABLED', 'false')
    store.episode['close_reason'] = 'gap'
    store.rows['live'] = _row('live', T0, 1, status='in_progress') | active()
    store.episode['conversation_ids'].append('live')
    placed = Mock(side_effect=AssertionError('recorded placement disabled'))
    monkeypatch.setattr(service.live_members_db, 'place', placed)
    assert composer.compose(UID, 'ep1', collaborators=_c()) == 'composed'
    placed.assert_not_called()
    assert 'live' not in store.episode['composed_member_ids']


@pytest.mark.parametrize('field', ['started_at', 'created_at'])
def test_initial_admission_preserves_main_acceptance_of_future_row_clocks(timeline_store, field):
    db = timeline_store
    seed(db)
    row = db.rows[('users', 'owner', 'conversations', 'live')]
    row.pop('started_at')
    row.pop('server_batch_audio_start')
    row[field] = datetime.now(timezone.utc) + timedelta(minutes=1)
    result = place(db)
    assert result['status'] == 'live'
    assert result['started_at'] == row[field]
    assert not result['_live_member_rehomed']


def test_initial_admission_does_not_require_optional_audio_clocks_to_agree(timeline_store):
    db = timeline_store
    seed(db, start=T0 + timedelta(hours=1, seconds=1))
    row = db.rows[('users', 'owner', 'conversations', 'live')]
    row.update(
        created_at=T0 + timedelta(hours=2),
        recorded_start=T0,
        server_batch_audio_start=(datetime.now(timezone.utc) + timedelta(minutes=1)).timestamp(),
        clock=None,
    )
    result = place(db)
    assert result['status'] == 'live' and result['id'] != 'old'
    assert result['started_at'] == datetime.fromtimestamp(row['server_batch_audio_start'], timezone.utc)
    assert not result['_live_member_rehomed']


@pytest.mark.parametrize(
    'changes',
    [
        {'capture_time_trust': 'untrusted'},
        {'started_at': None, 'created_at': None},
        {'started_at': None, 'created_at': T0 - timedelta(days=10)},
    ],
    ids=['untrusted', 'batch-only', 'stale-created-at'],
)
def test_initial_admission_uses_mains_batch_clock_and_acceptance_policy(timeline_store, monkeypatch, changes):
    db = timeline_store
    seed(db, start=T0 + timedelta(hours=1, seconds=1))
    row = db.rows[('users', 'owner', 'conversations', 'live')]
    row.update(changes)
    row['external_data'] = {'server_batch_only': True}
    monkeypatch.setattr(batch_close, 'episodes_enabled_for', lambda uid: True)
    monkeypatch.setattr(batch_close, 'recorded_episodes_enabled', lambda: True)
    monkeypatch.setattr(batch_close, 'batch_admission_attach_enabled', lambda: True)
    assert (
        batch_close.attach_admitted_batch_capture(
            'owner', 'live', row, collaborators=service.Collaborators(firestore_client=db)
        )
        == 'attached'
    )
    result = db.rows[('users', 'owner', 'episodes', row['episode_id'])]
    assert result['status'] == 'live' and result['id'] != 'old'
    assert result['started_at'] == datetime.fromtimestamp(row['server_batch_audio_start'], timezone.utc)
