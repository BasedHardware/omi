"""Expired empty placeholders leave attention without deleting a row or its audio."""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

import pytest

from routers import conversations as routes
from models.conversation import Conversation
from utils.conversations import empty_capture, home_step, transcribing_hold
from utils.episodes import home_read

NOW = datetime.now(timezone.utc)
OLD = NOW - timedelta(hours=25)


def placeholder(**changes):
    return {
        'id': 'empty',
        'source': 'omi',
        'status': 'in_progress',
        'created_at': OLD,
        'started_at': OLD,
        'finished_at': OLD,
        'record_lane_owner': 'batch_live_v1',
        'has_content': False,
        # Production shape: a frame was buffered but no span was committed.
        'server_batch_audio_received': True,
        'episode_transcription_pending_at': OLD,
        'episode_transcription_deadline_at': OLD + timedelta(hours=2),
        'transcript_segments': [],
        'structured': {'title': '', 'overview': ''},
        **changes,
    }


def episode():
    return {
        'id': 'ep',
        'status': 'closed',
        'started_at': OLD,
        'last_activity_at': OLD,
        'conversation_ids': ['empty'],
        'moments': [],
        'provisional_items': [],
    }


@pytest.mark.parametrize('closed', [None, True])
def test_closed_and_unclosed_expired_empty_shapes_are_read_only_noise(closed):
    row = placeholder(server_batch_audio_closed=closed, record_audio_closed=closed)
    before = deepcopy(row)
    assert empty_capture.applies(row, now=NOW)
    assert home_step.classify(row) == 'noise'
    for wire in (empty_capture.project(row), home_step.project(row), transcribing_hold.project(row)):
        assert wire['home_step'] == 'noise'
        assert wire['status'] == 'completed' and wire['structured']['title'] == 'No summary'
        assert wire['transcript_segments'] == [] and not wire.get('record_projection_revision')
    member = home_read.project_episode('synthetic', episode(), members={'empty': row})['members'][0]
    assert member['home_step'] == 'noise' and member['title'] == 'No summary'
    assert member['status'] == 'completed'  # deadline must not overwrite noise with failure
    assert home_read.project_episode('synthetic', episode(), members={'empty': row}, list_row=True) is None
    assert row == before


@pytest.mark.parametrize(
    'changes',
    [
        {'has_content': True},
        {'has_content': None},
        {'is_locked': True},
        {'deleted': True},
        {'discarded': True},
        {'sync_merged_into': 'survivor'},
        {'finalization_status': 'dead_letter'},
        {'home_transcription_queue_observed_at': NOW.timestamp()},
        {'photos': [{'id': 'photo'}]},
        {'record_upload_sessions': {'producer': {}}},
        {'record_upload_failed': True},
        {'record_audio_partial': {'reason': 'tail'}},
        {'record_projection_revision': 1},
        {'record_admitted_at': NOW.timestamp()},
        {'sync_content_revision': 1},
        {'server_batch_audio_start': 0},
        {'server_batch_audio_end': 0},
        {'transcript_segments': [{'text': 'late speech'}]},
        {'transcript_segments': b'opaque-unknown-content'},
        {'summary_due_at': NOW},
        {'summary_completed_at': NOW},
        {'summary_output_present': True},
        {'structured': {'title': 'A title'}},
        {'structured': {'overview': 'Recovered notes'}},
        {'structured': {'sections': [{'body_markdown': 'Recovered body'}]}},
        {'user_title': 'Keep'},
        {'starred': True},
        {'sync_relevance_user_kept': True},
        {'status': 'completed'},
        {'record_lane_owner': 'legacy_final_pass_v1'},
        {'episode_transcription_pending_at': None},
        {'episode_transcription_pending_at': NOW - timedelta(hours=1)},
        {'home_transcription_pending_at': NOW - timedelta(hours=1)},
    ],
)
def test_content_curation_producers_unknown_or_new_wait_release_noise(changes):
    row = placeholder(**changes)
    assert not empty_capture.applies(row, now=NOW)
    assert empty_capture.project(row, now=NOW) is row


def test_exact_existing_age_bound_and_naive_stamp():
    row = placeholder(episode_transcription_pending_at=OLD.replace(tzinfo=None), server_batch_audio_closed=True)
    assert not empty_capture.applies(row, now=OLD + timedelta(hours=2) - timedelta(seconds=1))
    assert empty_capture.applies(row, now=OLD + timedelta(hours=2))


def test_empty_rule_is_independent_of_completed_stt_empty_wire_switch(monkeypatch):
    # Closed audio, past the 2h deadline but inside the 24h age bound.
    start = NOW - timedelta(hours=17)
    row = placeholder(
        server_batch_audio_closed=True,
        created_at=start,
        started_at=start,
        finished_at=start,
        episode_transcription_pending_at=start,
        episode_transcription_deadline_at=start + timedelta(hours=2),
    )
    monkeypatch.setenv('HOME_SETTLED_EMPTY_WIRE_ENABLED', 'false')
    assert home_step.classify(row) == 'noise'
    monkeypatch.setenv('HOME_STALE_EMPTY_CAPTURE_NOISE_ENABLED', 'false')
    assert home_step.classify(row) is None
    assert empty_capture.project(row) is row
    member = home_read.project_episode('synthetic', episode(), members={'empty': row})['members'][0]
    assert member['title'] == 'Transcribing…'


def test_old_attention_retry_for_no_job_empty_shape_never_reaches_summary(monkeypatch):
    row = placeholder()
    before = deepcopy(row)
    monkeypatch.setattr(routes, '_get_valid_conversation_by_id', lambda *a: row)
    process = Mock(side_effect=AssertionError('no summary for an empty pending capture'))
    monkeypatch.setattr(routes, 'execute_reprocess', process)
    monkeypatch.setattr(routes, 'process_conversation', process)
    wire = routes.reprocess_conversation('empty', uid='synthetic')
    parsed = Conversation.model_validate(wire)
    assert parsed.status.value == 'completed' and parsed.home_step == 'noise'
    assert parsed.structured.title == 'No summary'
    process.assert_not_called()
    assert row == before


def test_empty_caption_survives_legacy_home_step_omission(monkeypatch):
    monkeypatch.setenv('HOME_STEP_PROJECTION', 'false')
    row = placeholder()
    wire = transcribing_hold.project(row)
    assert wire['status'] == 'completed' and wire['structured']['title'] == 'No summary'
    assert 'home_step' not in wire
    member = home_read.project_episode('synthetic', episode(), members={'empty': row})['members'][0]
    assert member['status'] == 'completed' and member['title'] == 'No summary'
    assert 'home_step' not in member


def test_unclosed_received_audio_waits_out_the_full_age_bound():
    # A buffered first frame can still commit at teardown: not noise at 3h or 23h.
    for hours in (3, 23):
        start = NOW - timedelta(hours=hours)
        row = placeholder(
            episode_transcription_pending_at=start,
            episode_transcription_deadline_at=start + timedelta(hours=2),
        )
        assert not empty_capture.applies(row, now=NOW)
        assert empty_capture.project(row, now=NOW) is row
    start = NOW - timedelta(hours=24)
    row = placeholder(
        episode_transcription_pending_at=start, episode_transcription_deadline_at=start + timedelta(hours=2)
    )
    assert empty_capture.applies(row, now=NOW)


@pytest.mark.parametrize('field', ['episode_transcription_deadline_at', 'home_transcription_deadline_at'])
def test_future_transcription_deadline_is_live_work(field):
    row = placeholder(server_batch_audio_closed=True, **{field: NOW + timedelta(minutes=5)})
    assert not empty_capture.applies(row, now=NOW)


def test_read_masks_carry_the_open_audio_evidence():
    assert {'server_batch_audio_received', 'server_batch_audio_closed'} <= set(transcribing_hold.READ_FIELDS)
