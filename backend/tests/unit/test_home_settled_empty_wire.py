"""Released Home fallback sees terminal emptiness consistently across both wires."""

from copy import deepcopy
from datetime import timedelta

import pytest

from tests.unit.test_episode_composer import T0, UID, _episode, _row
from utils.conversations import home_step, legacy_empty_wire
from utils.batch_pipeline import empty_transcription
from utils.episodes import home_read


def empty(**overrides):
    row = _row('empty', T0, 1, title='', overview='', lines=[])
    row.update(
        summary_blocked_reason='empty_output_exhausted',
        record_projection_revision=1,
        summary_output_present=False,
        notes_written_at=T0,
        episode_id='ep1',
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
    row.update(overrides)
    return row


def old_awaiting(row):
    """b78ea0112d82 home_member_fallback.dart:43-55, list/detail optional fields omitted."""
    return (
        row['status'] == 'completed'
        and not row.get('discarded')
        and not row.get('deleted')
        and not row.get('is_locked')
        and not row.get('summary_retryable')
        and not row.get('processing_deferred')
        and row.get('client_processing') is None
        and not row.get('photos')
        and not (row.get('structured') or {}).get('title', '').strip()
        and not (row.get('structured') or {}).get('overview', '').strip()
        and not any(s.get('text', '').strip() for s in row.get('transcript_segments') or [])
    )


def test_both_shapes_stop_old_fallback_without_mutating_stored_result():
    row = empty()
    before = deepcopy(row)
    assert old_awaiting(row)
    conversation = home_step.project(row)
    assert conversation['home_step'] == 'noise' and not old_awaiting(conversation)
    episode = home_read.project_episode(UID, _episode(conversation_ids=['empty']), members={'empty': row})
    member = episode['members'][0]
    assert member['title'] == legacy_empty_wire.TERMINAL_TITLE
    assert member['home_step'] == 'noise' and member['status'] == 'completed'
    # The old episode decoder copies title but ignores home_step and gist.
    assert not old_awaiting({'status': member['status'], 'structured': {'title': member['title']}})
    assert row == before
    assert conversation['structured']['overview'] == '' and conversation['transcript_segments'] == []


def test_owner_shape_before_after_preserves_gate_and_full_action_ids(monkeypatch):
    ready = {f'ready-{i}': _row(f'ready-{i}', T0 + timedelta(minutes=i), 1) for i in range(10)}
    noise = {f'noise-{i}': {**empty(), 'id': f'noise-{i}'} for i in range(3)}
    active = {'active': _row('active', T0 + timedelta(hours=2), 1, status='in_progress')}
    rows = {**ready, **noise, **active}
    episode = _episode(conversation_ids=[*rows, 'absent-1', 'absent-2', 'absent-3'])
    assert len(rows) == 14 and len(episode['conversation_ids']) == 17
    monkeypatch.setenv('HOME_SETTLED_EMPTY_WIRE_ENABLED', 'false')
    before = home_read.project_episode(UID, dict(episode), members=rows)
    assert sum(not m['title'] and m['status'] == 'completed' for m in before['members']) == 3
    before_list = [home_step.project(r) for r in [*ready.values(), *noise.values()]]
    assert any(old_awaiting(r) for r in before_list)  # old client: whole completed group Transcribing, count 13
    monkeypatch.delenv('HOME_SETTLED_EMPTY_WIRE_ENABLED')
    after = home_read.project_episode(UID, dict(episode), members=rows)
    after_list = [home_step.project(r) for r in [*ready.values(), *noise.values()]]
    assert not any(old_awaiting(r) for r in after_list)
    assert all(m['title'] for m in after['members'] if m['status'] == 'completed')
    assert len(after['conversation_ids']) == 14  # three absent IDs omitted by the preexisting wire rule
    assert 'active' in after['conversation_ids']  # No rolling subset or boundary change.
    assert not after.get('lede') and not after.get('composer_version')


@pytest.mark.parametrize(
    'overrides',
    [
        {'summary_due_at': T0},
        {'summary_completed_at': T0},
        {'summary_output_present': True},
        {'record_transcription_empty': None},
        {'status': 'processing'},
        {'structured': {'title': 'User title'}},
    ],
)
def test_nonterminal_or_nonempty_title_is_unchanged(overrides):
    row = empty(**overrides)
    assert legacy_empty_wire.project(row, noise=True) == row


def test_noise_classification_and_curation_are_respected():
    row = empty(starred=True)
    assert home_step.project(row)['home_step'] == 'ready'
    assert home_step.project(row)['structured']['title'] == ''
    assert legacy_empty_wire.project(empty(), noise=False)['structured']['title'] == ''


def test_stt_empty_receipt_needs_no_summary_failure_to_fix_both_wires():
    row = empty(summary_blocked_reason=None)
    assert home_step.project(row)['home_step'] == 'noise'
    assert not old_awaiting(home_step.project(row))
    episode = home_read.project_episode(UID, _episode(conversation_ids=['empty']), members={'empty': row})
    assert episode['members'][0]['title'] == legacy_empty_wire.TERMINAL_TITLE


def test_stt_only_noise_classification_rolls_back_with_wire_switch(monkeypatch):
    row = empty(summary_blocked_reason=None)
    monkeypatch.setenv('HOME_SETTLED_EMPTY_WIRE_ENABLED', 'false')
    assert home_step.classify(row) == 'transcribing'
    assert old_awaiting(home_step.project(row))
