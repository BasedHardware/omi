from datetime import datetime, timezone
from unittest.mock import AsyncMock

import routers.conversations as route
import utils.conversations.finalizer as finalizer
import utils.conversations.speaker_resolution as speaker_stage
from database import conversations as db
from models.conversation_enums import ConversationStatus
from tests.unit.test_manual_speaker_assignments import read, world
from utils.conversations.factory import deserialize_conversation

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _capture_segment():
    return dict(
        id='s0',
        text='first line.',
        speaker='SPEAKER_00',
        speaker_id=0,
        start=0.0,
        end=1.0,
        is_user=False,
        person_id=None,
        audio_capture_start=100.0,
        audio_capture_end=101.0,
    )


def _readable(world):
    data = read(world)
    data.pop('client_processing', None)
    return data


def _row():
    return dict(
        id='c',
        created_at=NOW,
        started_at=NOW,
        finished_at=NOW,
        structured={},
        status='in_progress',
        language='en',
        source='desktop',
        transcript_segments=[_capture_segment()],
    )


def _stub_process(calls, processed=None):
    def process(uid, language, conversation, **kwargs):
        calls.append(conversation.id)
        if processed is not None:
            processed.append(conversation)
        assert conversation.transcript_segments[0].audio_capture_start == 100.0
        assert speaker_stage.resolve_speakers_for_processing(uid, conversation)
        db.update_conversation_segments(
            uid, conversation.id, [s.model_dump() for s in conversation.transcript_segments]
        )
        conversation.status = ConversationStatus.completed
        if kwargs.get('speaker_receipt_observer'):
            kwargs['speaker_receipt_observer'](True)
        return conversation

    return process


def test_reprocess_conversation_preserves_capture_and_identity(world, monkeypatch):
    store, path, _ = world
    store.rows[path] = _row()
    calls = []
    monkeypatch.setattr(speaker_stage, 'resolution_enabled', lambda: False)
    monkeypatch.setattr(
        db,
        'get_manual_speaker_receipt',
        lambda *args, **kwargs: {'speakers': {'0': {'is_user': True, 'generation': 1}}},
    )
    monkeypatch.setattr(route, '_get_valid_conversation_by_id', lambda uid, conversation_id, **kwargs: read(world))
    monkeypatch.setattr(route, 'process_conversation', _stub_process(calls))

    result = route.reprocess_conversation(conversation_id='c', uid='u')

    assert calls == ['c']
    segment = result.transcript_segments[0]
    assert segment.audio_capture_start == 100.0 and segment.audio_capture_end == 101.0
    assert segment.is_user is True
    stored = read(world)['transcript_segments']
    assert stored[0]['audio_capture_start'] == 100.0 and stored[0]['audio_capture_end'] == 101.0
    decoded = deserialize_conversation(_readable(world))
    assert decoded.transcript_segments[0].audio_capture_start == 100.0
    assert decoded.transcript_segments[0].is_user is True


async def test_finalize_persisted_conversation_preserves_capture_and_identity(world, monkeypatch):
    store, path, _ = world
    store.rows[path] = _row()
    calls = []
    processed = []
    monkeypatch.setattr(speaker_stage, 'resolution_enabled', lambda: False)
    monkeypatch.setattr(
        db,
        'get_manual_speaker_receipt',
        lambda *args, **kwargs: {'speakers': {'0': {'is_user': True, 'generation': 1}}},
    )
    monkeypatch.setattr(finalizer.conversations_db, 'get_conversation', lambda *args, **kwargs: read(world))

    async def direct(_executor, fn, *args, **kwargs):
        return fn(*args, **kwargs)

    monkeypatch.setattr(finalizer, 'run_blocking', direct)
    monkeypatch.setattr(finalizer.lifecycle_service, 'ensure_processing', lambda *args, **kwargs: True)
    monkeypatch.setattr(finalizer, 'await_meeting_evidence', AsyncMock(return_value='not_applicable'))
    monkeypatch.setattr(finalizer, 'get_cached_user_geolocation', lambda *args, **kwargs: None)
    monkeypatch.setattr(finalizer, '_maybe_start_shadow', lambda *args, **kwargs: None)
    monkeypatch.setattr(finalizer, 'process_conversation', _stub_process(calls, processed))
    monkeypatch.setattr(
        finalizer.lifecycle_service,
        'claim_finalization_fanout',
        lambda *args, **kwargs: {'status': 'completed'},
    )
    monkeypatch.setattr(finalizer, 'link_duplicate_captures', lambda *args, **kwargs: None)
    monkeypatch.setattr(finalizer, 'schedule_person_voice_learning_retry', lambda *args, **kwargs: None)

    disposition = await finalizer.finalize_persisted_conversation(
        'u', 'c', finalization_job_id='job', dispatch_generation=1, lease_epoch=1
    )

    assert disposition.name == 'completed'
    assert calls == ['c']
    stored = read(world)['transcript_segments']
    assert stored[0]['audio_capture_start'] == 100.0 and stored[0]['audio_capture_end'] == 101.0
    assert stored[0]['is_user'] is True
    decoded = deserialize_conversation(_readable(world))
    assert decoded.transcript_segments[0].audio_capture_start == 100.0
    assert processed[0].status == ConversationStatus.completed
    assert processed[0].transcript_segments[0].audio_capture_start == 100.0
