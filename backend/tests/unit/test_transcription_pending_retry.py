"""Queued audio retries never spend a summary call; released clients get valid wire."""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from routers import conversations as routes
from models.conversation import Conversation
from utils.conversations import home_step, transcribing_hold
from utils.episodes import home_read
from config import transcription_pending as switches

T0 = datetime(2026, 11, 1, tzinfo=timezone.utc)


def capture(**changes):
    return {
        'id': 'capture',
        'created_at': T0,
        'started_at': T0,
        'finished_at': T0 + timedelta(minutes=1),
        'source': 'omi',
        'status': 'completed',
        'discarded': False,
        'has_content': True,
        'record_lane_owner': 'batch_live_v1',
        'home_transcription_pending_at': T0,
        'home_transcription_deadline_at': T0 + timedelta(hours=2),
        'episode_transcription_pending_at': T0,
        'episode_transcription_deadline_at': T0 + timedelta(hours=2),
        'transcript_segments': [],
        'structured': {'title': '', 'overview': '', 'emoji': '', 'category': 'other'},
        **changes,
    }


@pytest.mark.parametrize(
    'name,reader',
    [
        ('HOME_TRANSCRIPTION_SEAL_WAIT_ENABLED', switches.seal_wait_enabled),
        ('CONVERSATION_PENDING_TRANSCRIPTION_RETRY_ENABLED', switches.pending_retry_enabled),
        ('HOME_STALE_EMPTY_CAPTURE_NOISE_ENABLED', switches.stale_empty_noise_enabled),
    ],
)
@pytest.mark.parametrize('value,expected', [('', True), ('true', True), ('false', False), ('off', False)])
def test_ship_on_switches(monkeypatch, name, reader, value, expected):
    monkeypatch.setenv(name, value)
    assert reader() is expected


def test_first_seal_after_thirty_hours_gets_one_bounded_wait_then_real_transcript(monkeypatch):
    sealed = T0 + timedelta(hours=30)
    row = capture(record_admitted_at=sealed.timestamp(), record_sealed_at=sealed.timestamp())
    before = deepcopy(row)
    assert transcribing_hold.deadline(row) == sealed + timedelta(hours=24)
    assert transcribing_hold.deadline(row, prefix='episode_transcription') == sealed + timedelta(hours=24)
    for elapsed in (0, 2, 23):
        wire = transcribing_hold.project(row, now=sealed + timedelta(hours=elapsed))
        assert wire['structured']['title'] == 'Transcribing…' and wire['status'] == 'processing'
    row['record_sealed_at'] = (sealed + timedelta(hours=25)).timestamp()
    assert (
        transcribing_hold.project(row, now=sealed + timedelta(hours=24))['structured']['title'] == "Couldn't transcribe"
    )
    assert row['home_transcription_pending_at'] == before['home_transcription_pending_at']
    assert row['episode_transcription_deadline_at'] == before['episode_transcription_deadline_at']
    landed = {
        **row,
        'record_projection_revision': 1,
        'transcript_segments': [{'text': 'Speech'}],
        'structured': {'title': 'Real notes', 'overview': 'A useful summary'},
    }
    assert transcribing_hold.project(landed, now=sealed + timedelta(hours=2)) is landed
    assert home_step.classify(landed) == 'ready'
    monkeypatch.setenv('HOME_TRANSCRIPTION_SEAL_WAIT_ENABLED', 'false')
    assert transcribing_hold.deadline(row) == T0 + timedelta(hours=24)


@pytest.mark.parametrize('stamp', [None, False, True, -1, float('nan'), float('inf'), 1e30, 'yesterday'])
def test_invalid_seal_clock_never_renews_wait(stamp):
    assert transcribing_hold.deadline(capture(record_admitted_at=stamp)) == T0 + timedelta(hours=24)


def test_seal_before_finalize_does_not_shorten_the_wait():
    assert transcribing_hold.deadline(
        capture(record_admitted_at=(T0 - timedelta(hours=1)).timestamp())
    ) == T0 + timedelta(hours=24)


def test_pending_read_masks_carry_first_admission():
    assert 'record_admitted_at' in transcribing_hold.READ_FIELDS
    assert set(transcribing_hold.READ_FIELDS) <= set(home_read.MEMBER_FIELDS)


def test_seal_clock_is_shared_by_activity_and_episode_wire_without_job_reads():
    now = datetime.now(timezone.utc)
    row = capture(record_admitted_at=(now - timedelta(hours=1)).timestamp())
    before = deepcopy(row)
    activity = transcribing_hold.project(home_step.project(row))
    assert activity['home_step'] == 'transcribing' and activity['status'] == 'processing'
    ep = {
        'id': 'ep',
        'status': 'closed',
        'started_at': T0,
        'last_activity_at': T0,
        'conversation_ids': ['capture'],
        'moments': [],
        'provisional_items': [],
    }
    member = home_read.project_episode('synthetic', ep, members={'capture': row})['members'][0]
    assert member['title'] == 'Transcribing…' and member['home_step'] == 'transcribing'
    assert member['status'] == 'processing' and row == before


@pytest.mark.parametrize('title', ['', "Couldn't transcribe", 'My recording'])
@pytest.mark.parametrize('status', ['completed', 'in_progress', 'processing', 'failed'])
def test_guard_uses_stored_capture_evidence_not_the_wire_title(title, status):
    assert transcribing_hold.retry_pending(capture(status=status, structured={'title': title}))
    assert transcribing_hold.retry_pending(capture(user_title='A user title'))


@pytest.mark.parametrize(
    'changes',
    [
        {'record_projection_revision': 1},
        {'transcript_segments': [{'text': 'landed'}]},
        {'record_lane_owner': 'legacy_final_pass_v1'},
        {'home_transcription_deadline_at': None, 'episode_transcription_deadline_at': None},
    ],
)
def test_unrelated_rows_keep_existing_reprocess(changes):
    assert not transcribing_hold.retry_pending(capture(**changes))


@pytest.fixture
def no_paid_path(monkeypatch):
    process = Mock(side_effect=AssertionError('summary model must not run'))
    execute = Mock(side_effect=AssertionError('summary writer must not be claimed'))
    monkeypatch.setattr(routes, 'process_conversation', process)
    monkeypatch.setattr(routes, 'execute_reprocess', execute)
    return process, execute


@pytest.mark.parametrize('job_shape', ['ready/audio', 'retry/audio', 'record_pending'])
def test_route_200_pending_wire_matches_build_1563_and_main(monkeypatch, no_paid_path, job_shape):
    # Job shape is deliberately not read: the endpoint does not query or mutate jobs.
    now = datetime.now(timezone.utc)
    row = capture(record_admitted_at=(now - timedelta(hours=1)).timestamp())
    before = deepcopy(row)
    monkeypatch.setattr(routes, '_get_valid_conversation_by_id', lambda *a: row)
    app = FastAPI()
    app.include_router(routes.router)
    app.dependency_overrides[routes.auth.get_current_user_uid] = lambda: 'synthetic'
    with TestClient(app) as client:
        response = client.post('/v1/conversations/capture/reprocess')
    assert response.status_code == 200, response.text
    wire = response.json()
    Conversation.model_validate(wire)
    # b78ea0112d82 and main: 200 decodes ReprocessSuccess; apply removes the
    # failed ID and moves processing + nonfailed home_step to processing.
    assert wire['status'] == 'processing' and wire['home_step'] == 'transcribing'
    assert wire['structured']['title'] == 'Transcribing…'
    assert wire['summary_retryable'] is False
    assert 'record_admitted_at' not in wire
    assert row == before
    for call in no_paid_path:
        call.assert_not_called()


@pytest.mark.parametrize('changes', [{}, {'record_upload_failed': True}, {'finalization_status': 'dead_letter'}])
def test_expired_or_explicit_failure_is_clear_non200_without_model(monkeypatch, no_paid_path, changes):
    row = capture(**changes)
    monkeypatch.setattr(routes, '_get_valid_conversation_by_id', lambda *a: row)
    with pytest.raises(HTTPException) as caught:
        routes.reprocess_conversation('capture', uid='synthetic')
    assert caught.value.status_code == 409
    assert caught.value.detail['code'] == 'transcription_pending'
    # The mobile app maps this to ReprocessTranscriptionPending: it shows a
    # "Not transcribed yet" status and stops offering the summary retry.
    assert caught.value.detail['code'] != 'conversation_processing_in_progress'
    for call in no_paid_path:
        call.assert_not_called()


def test_guard_can_roll_back_independently(monkeypatch):
    monkeypatch.setenv('CONVERSATION_PENDING_TRANSCRIPTION_RETRY_ENABLED', 'false')
    assert not transcribing_hold.retry_pending(capture())


def test_episode_only_stamp_uses_the_same_seal_bound_and_rolls_back(monkeypatch):
    now = datetime.now(timezone.utc)
    row = capture(
        home_transcription_pending_at=None,
        home_transcription_deadline_at=None,
        record_admitted_at=(now - timedelta(hours=1)).timestamp(),
    )
    assert transcribing_hold.project(row)['status'] == 'processing'
    assert home_step.classify(row) == 'transcribing'
    monkeypatch.setenv('HOME_TRANSCRIPTION_SEAL_WAIT_ENABLED', 'false')
    assert transcribing_hold.project(row) is row
