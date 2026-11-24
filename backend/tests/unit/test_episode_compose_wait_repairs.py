"""Terminal outcomes and bounded waits preserve the all-members-complete gate."""

from datetime import datetime, timedelta, timezone

import pytest

from tests.unit.test_episode_composer import T0, UID, _c, _row, store  # noqa: F401
from utils.batch_pipeline import empty_transcription
from utils.episodes import composer, compose_wait


@pytest.fixture
def clock(monkeypatch):
    class Clock(datetime):
        current = T0 + timedelta(hours=4)

        @classmethod
        def now(cls, tz=None):
            return cls.current if tz else cls.current.replace(tzinfo=None)

    monkeypatch.setattr(composer, 'datetime', Clock)
    return Clock


def terminal(store, cid='empty'):
    row = _row(cid, T0 + timedelta(minutes=2), 1, title='', overview='', lines=[])
    row.update(
        summary_blocked_reason='empty_output_exhausted',
        summary_output_present=False,
        notes_written_at=T0 + timedelta(minutes=4),
        record_projection_revision=1,
        home_transcription_pending_at=T0 + timedelta(hours=4),
    )
    row.update(
        server_batch_audio_closed=True,
        server_batch_audio_start=row['started_at'].timestamp(),
        server_batch_audio_end=row['finished_at'].timestamp(),
    )
    empty_transcription.stamp(
        row,
        row,
        {
            'start': row['started_at'].timestamp(),
            'end': row['finished_at'].timestamp(),
            'terminal_empty_outcome': 'silence',
        },
    )
    store.rows[cid] = row
    if cid not in store.episode['conversation_ids']:
        store.episode['conversation_ids'].append(cid)
    return row


@pytest.mark.parametrize('episode_state', ['closed', 'live'])
@pytest.mark.parametrize('member_state', ['notes', 'terminal', 'pending', 'active', 'absent'])
def test_member_state_space(store, clock, episode_state, member_state):
    store.episode['conversation_ids'] = ['case']
    store.episode['status'] = episode_state
    if member_state == 'terminal':
        terminal(store, 'case')
    elif member_state != 'absent':
        row = _row('case', T0, 180, status='in_progress' if member_state == 'active' else 'completed')
        if member_state == 'pending':
            row.update(structured={}, transcript_segments=[], home_transcription_pending_at=clock.current)
        store.rows['case'] = row
    expected = (
        'live'
        if episode_state == 'live'
        else {'notes': 'composed', 'terminal': 'empty', 'pending': 'waiting', 'active': 'waiting', 'absent': 'empty'}[
            member_state
        ]
    )
    assert composer.compose(UID, 'ep1', collaborators=_c()) == expected


def test_terminal_empty_members_do_not_wait_and_late_speech_refreshes(store, clock, monkeypatch):
    row = terminal(store)
    calls = []
    assert composer._transcript_wait_until(row) is None
    assert composer.compose(UID, 'ep1', collaborators=_c(calls=calls)) == 'composed'
    assert len(calls) == 1
    row['transcript_segments'] = [{'start': 0, 'end': 10, 'text': 'A late transcript still matters.'}]
    row['episode_transcript_updated_at'] = clock.current
    assert composer.compose(UID, 'ep1', collaborators=_c(calls=calls)) == 'composed'
    assert len(calls) == 2
    row['transcript_segments'] = []
    row['home_transcription_pending_at'] = clock.current
    monkeypatch.setenv('EPISODE_COMPOSE_SETTLED_TERMINAL_ENABLED', 'false')
    assert composer._transcript_wait_until(row) == clock.current + timedelta(seconds=1200)
    assert composer.compose(UID, 'ep1', collaborators=_c(calls=calls)) == 'waiting'


@pytest.mark.parametrize(
    'overrides',
    [
        {'record_transcription_empty': None},
        {'summary_due_at': T0},
        {'summary_completed_at': T0},
        {'summary_output_present': True},
        {'structured': {'overview': 'Recovered summary'}},
        {'status': 'processing'},
    ],
)
def test_empty_text_alone_or_renewed_debt_is_not_terminal(store, overrides):

    row = terminal(store)
    row.update(overrides)
    assert not compose_wait.empty_terminal_result(row)


def test_owner_wait_reset_sequence_has_independent_blocker_caps(store, clock, monkeypatch):

    monkeypatch.setenv('EPISODE_COMPOSE_TRANSCRIPT_WAIT_SECONDS', '21600')
    first = datetime(2026, 11, 15, 12, 24, 51, tzinfo=timezone.utc)
    joined = datetime(2026, 11, 15, 13, 0, 37, tzinfo=timezone.utc)
    clock.current = first
    store.rows['c1'].update(
        structured={}, transcript_segments=[], home_transcription_pending_at=first.replace(hour=11, minute=4, second=17)
    )
    assert composer.compose(UID, 'ep1', collaborators=_c()) == 'waiting'
    assert store.episode['compose_transcript_wait_started_at'] == first
    clock.current = joined
    store.rows['new'] = _row('new', joined, 1, title='', overview='', lines=[])
    store.rows['new']['home_transcription_pending_at'] = joined
    store.episode['conversation_ids'].append('new')
    assert composer.compose(UID, 'ep1', collaborators=_c()) == 'waiting'
    observations = store.episode[compose_wait.OBSERVATIONS]
    assert observations['c1']['observed_at'] == first
    assert observations['new']['observed_at'] == joined
    assert store.episode['compose_transcript_wait_started_at'] == first
    # An old image overwrites the legacy start after membership changes; it cannot erase additive fields.
    store.episode['compose_transcript_wait_started_at'] = joined
    monkeypatch.setenv('EPISODE_COMPOSE_TRANSCRIPT_WAIT_SECONDS', '1200')
    assert composer._stored_wait_until(store.episode) <= first + timedelta(seconds=1200)
    assert composer.needs_compose(store.episode)
    assert composer.compose(UID, 'ep1', collaborators=_c()) == 'waiting'
    assert store.episode['compose_transcript_wait_members'] == ['new']
    assert store.episode['compose_transcript_wait_until'] == joined + timedelta(seconds=1200)
    assert not composer.needs_compose(store.episode)
    clock.current += timedelta(seconds=1200)
    assert composer.needs_compose(store.episode)
    assert composer.compose(UID, 'ep1', collaborators=_c()) == 'composed'


def test_reopened_same_member_gets_a_new_generation_clock(store, clock):

    row = store.rows['c1']
    row.update(transcript_segments=[], home_transcription_pending_at=clock.current)
    assert composer.compose(UID, 'ep1', collaborators=_c()) == 'waiting'
    first = clock.current
    clock.current += timedelta(seconds=600)
    row['home_transcription_pending_at'] = clock.current
    assert composer.compose(UID, 'ep1', collaborators=_c()) == 'waiting'
    assert store.episode[compose_wait.OBSERVATIONS]['c1']['observed_at'] == clock.current
    assert store.episode['compose_transcript_wait_until'] == first + timedelta(seconds=1800)


def test_anchored_wait_rollback_restores_membership_reset(store, clock, monkeypatch):
    monkeypatch.setenv('EPISODE_COMPOSE_ANCHORED_WAIT_ENABLED', 'false')
    store.rows['c1'].update(transcript_segments=[], home_transcription_pending_at=clock.current)
    assert composer.compose(UID, 'ep1', collaborators=_c()) == 'waiting'
    clock.current += timedelta(seconds=60)
    store.episode['conversation_ids'].append('absent-new')
    assert composer.compose(UID, 'ep1', collaborators=_c()) == 'waiting'
    assert store.episode['compose_transcript_wait_started_at'] == clock.current
    assert 'compose_transcript_wait_observations' not in store.episode


def test_absent_ids_do_not_reopen_visible_membership_wait_forever(store, clock, monkeypatch):
    from utils.episodes import home_read

    store.episode['conversation_ids'].extend(['absent-1', 'absent-2', 'absent-3'])
    store.rows['c2'].update(structured={}, transcript_segments=[], home_transcription_pending_at=clock.current)
    assert composer.compose(UID, 'ep1', collaborators=_c()) == 'waiting'
    projected = home_read.project_episode(UID, store.episode, members=store.rows)
    visible = [m['id'] for m in projected['members']]
    assert visible == ['c1', 'c2']
    assert not composer.needs_compose(store.episode, visible_member_ids=visible)
    monkeypatch.setenv('EPISODE_EMPTY_MEMBER_CLEANUP_ENABLED', 'false')
    assert not composer.needs_compose(store.episode, visible_member_ids=visible)
    monkeypatch.delenv('EPISODE_EMPTY_MEMBER_CLEANUP_ENABLED')
    clock.current += timedelta(seconds=1201)
    assert composer.compose(UID, 'ep1', collaborators=_c()) == 'composed'
    assert not composer.needs_compose(store.episode, visible_member_ids=visible)


def test_owner_shape_still_waits_for_active_then_composes_and_refreshes(store, clock):
    for i in range(3):
        terminal(store, f'noise-{i}')
    for i in range(8):
        cid = f'ready-{i}'
        store.rows[cid] = _row(cid, T0 + timedelta(minutes=i), 1)
        store.episode['conversation_ids'].append(cid)
    store.episode['conversation_ids'].extend(['absent-1', 'absent-2', 'absent-3', 'active'])
    store.rows['active'] = _row('active', T0 + timedelta(hours=3), 1, status='in_progress')
    calls = []
    assert len(store.episode['conversation_ids']) == 17
    assert composer.compose(UID, 'ep1', collaborators=_c(calls=calls)) == 'waiting'
    assert not calls and not store.episode.get('compose_transcript_wait_until')
    store.rows['joined'] = _row('joined', T0 + timedelta(hours=3, minutes=5), 1)
    store.episode['conversation_ids'].append('joined')
    assert composer.compose(UID, 'ep1', collaborators=_c(calls=calls)) == 'waiting'
    assert not calls
    store.rows['active']['status'] = 'completed'
    assert composer.compose(UID, 'ep1', collaborators=_c(calls=calls)) == 'composed'
    assert len(calls) == 1
    assert composer.compose(UID, 'ep1', collaborators=_c(calls=calls)) == 'unchanged'
    store.rows['noise-0']['transcript_segments'] = [{'text': 'Late speech', 'start': 0, 'end': 10}]
    store.rows['noise-0']['episode_transcript_updated_at'] = clock.current
    assert composer.compose(UID, 'ep1', collaborators=_c(calls=calls)) == 'composed'
    assert len(calls) == 2


def test_cas_retry_cannot_overwrite_winning_replica_first_observation(clock):
    first = clock.current
    pending = first - timedelta(seconds=100)
    winner = {
        'c': {'pending_at': pending, 'observed_at': first},
        'other': {'pending_at': pending, 'observed_at': first},
    }
    later = first + timedelta(seconds=60)
    patch = compose_wait.observation_updates(
        {'c': {'pending_at': pending, 'observed_at': later}},
        ['c'],
        later,
        current={compose_wait.OBSERVATIONS: winner},
        due=later + timedelta(seconds=1200),
    )
    assert patch[compose_wait.OBSERVATIONS]['c']['observed_at'] == first
    assert patch['compose_transcript_wait_started_at'] == first
    assert patch['compose_transcript_wait_until'] == first + timedelta(seconds=1200)
    assert patch[compose_wait.OBSERVATIONS]['other'] == winner['other']


@pytest.mark.parametrize('enabled', [True, False])
def test_detached_absent_id_reconciles_membership_without_rebuy(store, clock, monkeypatch, enabled):
    store.episode['conversation_ids'].append('absent')
    calls = []
    assert composer.compose(UID, 'ep1', collaborators=_c(calls=calls)) == 'composed'
    store.episode['conversation_ids'].remove('absent')
    monkeypatch.setenv('EPISODE_EMPTY_MEMBER_CLEANUP_ENABLED', str(enabled).lower())
    assert composer.needs_compose(store.episode, visible_member_ids=['c1', 'c2'])
    assert composer.compose(UID, 'ep1', collaborators=_c(calls=calls)) == 'unchanged'
    assert len(calls) == 1
    assert not composer.needs_compose(store.episode, visible_member_ids=['c1', 'c2'])


@pytest.mark.parametrize(
    'extra',
    [
        {},
        {'server_batch_audio_received': True, 'server_batch_audio_closed': True},
        {'record_projection_revision': 1},
        {'summary_blocked_reason': 'content_below_floor'},
    ],
)
def test_summary_exhaustion_with_pending_stt_keeps_waiting(store, clock, extra):
    row = terminal(store)
    row.pop('record_transcription_empty', None)
    row.update(extra)
    assert not compose_wait.empty_terminal_result(row)
    assert composer._transcript_wait_until(row) == clock.current + timedelta(seconds=1200)
    calls = []
    if row.get('summary_blocked_reason') != 'content_below_floor':
        assert composer.compose(UID, 'ep1', collaborators=_c(calls=calls)) == 'waiting'
        assert not calls


def test_pending_stt_cap_expiry_then_late_transcript_buys_exactly_one_recompose(store, clock):
    row = terminal(store)
    row.pop('record_transcription_empty', None)
    calls = []
    assert composer.compose(UID, 'ep1', collaborators=_c(calls=calls)) == 'waiting'
    assert not calls
    clock.current += timedelta(seconds=1200)
    assert composer.compose(UID, 'ep1', collaborators=_c(calls=calls)) == 'composed'
    assert len(calls) == 1
    row['transcript_segments'] = [{'text': 'Speech after the legitimate cap', 'start': 0, 'end': 10}]
    row['episode_transcript_updated_at'] = clock.current
    assert composer.compose(UID, 'ep1', collaborators=_c(calls=calls)) == 'composed'
    assert len(calls) == 2
    assert composer.compose(UID, 'ep1', collaborators=_c(calls=calls)) == 'unchanged'
    assert len(calls) == 2


def test_old_writer_stale_map_cannot_shorten_a_new_blocker_generation(store, clock):
    row = store.rows['c1']
    row.update(transcript_segments=[], home_transcription_pending_at=clock.current)
    calls = []
    assert composer.compose(UID, 'ep1', collaborators=_c(calls=calls)) == 'waiting'
    first = clock.current
    clock.current += timedelta(seconds=1100)
    row['home_transcription_pending_at'] = clock.current
    # Old image preserves the unknown map but stamps its new-generation legacy fields.
    store.episode.update(
        compose_transcript_wait_started_at=clock.current,
        compose_transcript_wait_until=clock.current + timedelta(seconds=1200),
    )
    clock.current = first + timedelta(seconds=1201)
    assert composer.needs_compose(store.episode)  # stale map can cause a harmless early wake
    assert composer.compose(UID, 'ep1', collaborators=_c(calls=calls)) == 'waiting'
    assert not calls
    assert store.episode['compose_transcript_wait_until'] == first + timedelta(seconds=2300)
    assert not composer.needs_compose(store.episode)
    clock.current = first + timedelta(seconds=2300)
    assert composer.compose(UID, 'ep1', collaborators=_c(calls=calls)) == 'composed'
    assert len(calls) == 1


def test_committed_stt_empty_needs_no_summary_exhaustion_verdict(store, clock):
    row = terminal(store)
    row.pop('summary_blocked_reason')
    assert composer._transcript_wait_until(row) is None
    assert composer.compose(UID, 'ep1', collaborators=_c()) == 'composed'


def test_registered_audio_without_legacy_pending_stamp_uses_first_observation(store, clock, monkeypatch):
    row = terminal(store)
    row.pop(empty_transcription.FIELD)
    row.pop('home_transcription_pending_at')
    row.update(server_batch_audio_received=True, finished_at=T0)
    assert composer._transcript_wait_until(row) == clock.current + timedelta(seconds=1200)
    calls = []
    assert composer.compose(UID, 'ep1', collaborators=_c(calls=calls)) == 'waiting'
    assert not calls
    first = clock.current
    clock.current += timedelta(seconds=600)
    assert composer.compose(UID, 'ep1', collaborators=_c(calls=calls)) == 'waiting'
    assert store.episode['compose_transcript_wait_until'] == first + timedelta(seconds=1200)
    clock.current += timedelta(seconds=600)
    assert composer.compose(UID, 'ep1', collaborators=_c(calls=calls)) == 'composed'
    assert len(calls) == 1
    monkeypatch.setenv('EPISODE_COMPOSE_SETTLED_TERMINAL_ENABLED', 'false')
    assert composer._transcript_wait_until(row) is None
    monkeypatch.setenv('EPISODE_COMPOSE_SETTLED_TERMINAL_ENABLED', 'true')
    monkeypatch.setenv('EPISODE_COMPOSE_ANCHORED_WAIT_ENABLED', 'false')
    assert composer._transcript_wait_until(row) is None
