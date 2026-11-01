"""Channel provenance retention; desktop source alone never asserts ownership."""

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from database import conversations as db
from models.conversation import Conversation, Structured
from models.transcript_segment import TranscriptSegment
from routers.listen import receiver as receiver_module
from routers.listen.contracts import ListenRequest
from routers.listen.runtime import ListenSessionRuntime
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from utils.conversations import speaker_resolution as processing_stage
from utils.stt.streaming import STTService


def post_process(segments, monkeypatch):
    now = datetime(2026, 10, 9, tzinfo=timezone.utc)
    conversation = Conversation(
        id='desktop',
        created_at=now,
        started_at=now,
        finished_at=now,
        source='desktop',
        structured=Structured(),
        transcript_segments=segments,
        private_cloud_sync_enabled=True,
    )
    # Exercise the stage called before finalization, with no enrolled embedding
    # service/evidence. Capture labels must survive and source alone adds none.
    monkeypatch.setattr(processing_stage, 'resolution_enabled', lambda: True)
    monkeypatch.setattr(processing_stage, 'speaker_embedding_configured', lambda: False)
    monkeypatch.setattr(processing_stage.conversations_db, 'get_manual_speaker_receipt', lambda uid, cid: {})
    assert processing_stage.resolve_speakers_for_processing('u', conversation)
    assert conversation.speaker_resolution.status == 'capture'
    return conversation


@pytest.mark.asyncio
async def test_two_channel_desktop_callbacks_survive_transcript_persistence(monkeypatch):
    runtime = ListenSessionRuntime(
        ListenRequest(
            websocket=SimpleNamespace(headers={}), uid='u', source='desktop', channels=2, codec='pcm', sample_rate=16000
        )
    )
    runtime._build_components()
    assert runtime.is_multi_channel
    receiver = runtime.receiver
    callbacks, queued = [], []

    async def socket(callback, *args, **kwargs):
        callbacks.append(callback)
        return SimpleNamespace()

    monkeypatch.setattr(receiver, '_create_stt_socket', socket)
    monkeypatch.setattr(receiver, '_enqueue_stt_segments', lambda segments: queued.extend(segments))
    monkeypatch.setattr(receiver_module, 'track_live_stt_socket', lambda socket, *a: socket)
    monkeypatch.setattr(receiver_module, 'record_live_connection', lambda *a: None)
    runtime.stt_service = STTService.parakeet
    assert await receiver.initialize_stt()
    assert [(c.channel_id, c.label) for c in receiver.channel_configs] == [(1, 'mic'), (2, 'system_audio')]
    for i, callback in enumerate(callbacks):
        callback([dict(id=f'channel-{i}', text='Synthetic channel speech', start=i * 6, end=i * 6 + 6, is_user=False)])
    segments = [TranscriptSegment(**s).model_dump(mode='python') for s in queued]
    assert [s['is_user'] for s in segments] == [True, False]
    assert [s['speaker_identity_status'] for s in segments] == ['user', 'not_user']
    finalized = post_process(segments, monkeypatch)
    assert [s.is_user for s in finalized.transcript_segments] == [True, False]
    assert [s.speaker_identity_status for s in finalized.transcript_segments] == ['user', 'not_user']
    segments = [s.model_dump(mode='python') for s in finalized.transcript_segments]
    store = StrictFirestore()
    path = ('users', 'u', 'conversations', 'desktop')
    store.rows[path] = dict(id='desktop', status='completed', source='desktop', transcript_segments=[])
    db.update_conversation_segments('u', 'desktop', segments, firestore_client=store)
    persisted = db._decode_transcript_segments_strict(
        'u', store.rows[path]['transcript_segments'], bool(store.rows[path].get('transcript_segments_compressed'))
    )
    assert [s['is_user'] for s in persisted] == [True, False]
    assert [s['speaker_id'] for s in persisted] == [0, 1]


def test_mono_desktop_has_no_channel_owner_labels(monkeypatch):
    runtime = ListenSessionRuntime(
        ListenRequest(
            websocket=SimpleNamespace(headers={}), uid='u', source='desktop', channels=1, codec='pcm', sample_rate=16000
        )
    )
    runtime._build_components()
    assert not runtime.is_multi_channel and runtime.receiver.channel_configs == []
    segment = TranscriptSegment(text='Synthetic mono export', speaker_id=0, start=0, end=6, is_user=False)
    assert not segment.is_user and segment.speaker_identity_status == 'unknown'

    finalized = post_process([segment], monkeypatch)
    assert not finalized.transcript_segments[0].is_user
    assert finalized.transcript_segments[0].speaker_identity_status == 'unknown'
