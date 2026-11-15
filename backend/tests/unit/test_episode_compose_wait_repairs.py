"""Terminal outcomes and bounded waits preserve the all-members-complete gate."""

from datetime import datetime, timedelta, timezone

import pytest

from tests.unit.test_episode_composer import T0, UID, _c, _row, store  # noqa: F401
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
        home_transcription_pending_at=T0 + timedelta(minutes=3),
    )
    store.rows[cid] = row
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
        {'summary_blocked_reason': None},
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
