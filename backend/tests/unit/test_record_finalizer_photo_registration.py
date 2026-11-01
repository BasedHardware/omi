"""Photo-only server captures have no audio registration obligation."""

import pytest

from utils.conversations import finalizer
from utils.conversations.processing_trigger import ProcessingTrigger
from tests.unit.test_conversation_smart_merge_finalizer import harness, _Conversation, _finalize


@pytest.mark.asyncio
@pytest.mark.parametrize('trigger', [ProcessingTrigger.CAPTURE_END, ProcessingTrigger.SILENT_BACKFILL])
@pytest.mark.parametrize(
    'change,proven_empty',
    [
        ({}, True),
        ({'server_batch_audio_closed': False}, False),
        ({'server_batch_audio_received': None}, False),
        ({'server_batch_audio_received': True}, False),
        ({'record_upload_failed': True}, False),
        ({'record_upload_sessions': {'pending': True}}, False),
    ],
)
async def test_photo_only_server_capture_requires_proven_empty_archive(
    harness, monkeypatch, trigger, change, proven_empty
):
    calls, row = harness
    row.update(
        record_lane_owner='batch_live_v1',
        server_batch_only=True,
        source='desktop',
        private_cloud_sync_enabled=True,
        server_batch_audio_closed=True,
        server_batch_audio_received=False,
        has_content=True,
        photos=[{'description': 'synthetic photo'}],
    )
    row.update(change)
    conversation = _Conversation()
    conversation.source = 'desktop'
    conversation.photos = row['photos']
    conversation.transcript_segments = []
    conversation.model_dump = lambda: {'id': 'n', 'status': 'completed', 'photos': row['photos']}
    monkeypatch.setattr(finalizer, 'deserialize_conversation', lambda _: conversation)
    original = finalizer.run_blocking

    async def run(executor, function, *args, **kwargs):
        if function is finalizer.register_recording:
            calls.append(function)
            # The real registrar refuses a server capture with no audio before
            # opening a store. Photos still use ordinary finalization.
            return function(*args, **kwargs)
        return await original(executor, function, *args, **kwargs)

    async def absorbed(*args, **kwargs):
        return True

    monkeypatch.setattr(finalizer, 'run_blocking', run)
    monkeypatch.setattr(finalizer, 'smart_merge_step', absorbed)
    if proven_empty:
        expected = (
            finalizer.ConversationFinalizationDisposition.fenced
            if trigger is ProcessingTrigger.SILENT_BACKFILL
            else finalizer.ConversationFinalizationDisposition.completed
        )
        assert await _finalize(trigger) is expected
        assert finalizer.register_recording not in calls
        if trigger is not ProcessingTrigger.SILENT_BACKFILL:
            assert finalizer.lifecycle_service.complete_finalization_fanout in calls
    else:
        with pytest.raises(finalizer.ConversationFinalizationError):
            await _finalize(trigger)
        assert finalizer.register_recording in calls
        assert finalizer.lifecycle_service.claim_finalization_fanout not in calls
