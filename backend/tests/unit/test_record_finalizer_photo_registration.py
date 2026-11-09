"""Photo-only server captures have no audio registration obligation."""

from datetime import datetime, timezone
from unittest.mock import Mock

import pytest

from utils.conversations import finalizer
from utils.enrichment import callback, outbox
from utils.batch_pipeline import live
from tests.unit.test_batch_pipeline_scheduler import MemoryStore
from tests.unit.test_sync_reprocess_coalesce import state
from utils.conversations.processing_trigger import ProcessingTrigger
from tests.unit.test_conversation_smart_merge_finalizer import harness, _Conversation, _finalize


@pytest.fixture
def preview_fallback(harness, state, monkeypatch):
    calls, row = harness
    rows, _ = state
    monkeypatch.setenv('FIRST_SUMMARY_DEADLINE_ENABLED', 'false')
    monkeypatch.setenv('PIPELINE_ATTENTION_MODE', 'serve')
    monkeypatch.setenv('PIPELINE_SEAL_FAST_ENABLED', 'true')
    monkeypatch.setattr(finalizer.pipeline_attention, 'serving', lambda _: True)
    monkeypatch.setattr(finalizer.pipeline_attention, 'admitted', lambda _: True)
    batch = MemoryStore()
    batch.namespace = 'batch_pipeline_prod'
    monkeypatch.setattr(outbox.record_attention, 'FirestoreStore', lambda *a, **k: batch)
    monkeypatch.setattr(outbox.conversations_db, 'get_conversation_raw_snapshot', lambda *a, **k: row)
    preview = [{'id': 'preview', 'text': 'word ' * 100, 'start': 0, 'end': 60, 'speaker_id': 0, 'is_user': True}]
    row.update(
        record_lane_owner='batch_live_v1',
        server_batch_only=True,
        server_batch_audio_closed=True,
        server_batch_audio_received=True,
        private_cloud_sync_enabled=True,
        transcript_segments=preview,
        status='processing',
        has_content=True,
        server_batch_audio_start=10,
        server_batch_audio_end=100,
        created_at=datetime.fromtimestamp(10, timezone.utc),
        started_at=datetime.fromtimestamp(10, timezone.utc),
        finished_at=datetime.fromtimestamp(100, timezone.utc),
        structured={'title': 'Pending', 'overview': ''},
        sync_content_revision=1,
        record_projection_revision=0,
        record_upload_revision=1,
    )
    conversation = _Conversation()
    conversation.status = finalizer.ConversationStatus.processing
    conversation.transcript_segments = preview
    conversation.photos = []
    monkeypatch.setattr(finalizer, 'deserialize_conversation', lambda _: conversation)
    original = finalizer.run_blocking

    async def no_meeting(*a, **k):
        return 'not_applicable'

    monkeypatch.setattr(finalizer, 'await_meeting_evidence', no_meeting)

    async def run(executor, function, *args, **kwargs):
        if function is finalizer.pipeline_attention.notes_serving:
            return function(*args, **kwargs)
        if function is finalizer.register_recording:
            calls.append(function)
            return function(*args, store=batch, now=100, **kwargs)
        if function is outbox.mark:
            calls.append(function)
            return function(*args, now=100, **kwargs)
        if function is finalizer.lifecycle_service.complete_server_batch_capture:
            calls.append(function)
            row['status'] = 'completed'
            return 'completed'
        if function is finalizer.process_with_episode_budget:
            calls.append(function)
            raise RuntimeError('legacy preview notes reached')
        return await original(executor, function, *args, **kwargs)

    monkeypatch.setattr(finalizer, 'run_blocking', run)
    return calls, row, rows, batch


@pytest.mark.asyncio
@pytest.mark.parametrize('failure', ['provider_failed', 'record_barrier_aged'])
async def test_batch_failure_keeps_durable_preview_notes_fallback(preview_fallback, monkeypatch, failure):
    calls, row, rows, batch = preview_fallback
    assert await _finalize() is finalizer.ConversationFinalizationDisposition.completed
    assert calls.index(finalizer.register_recording) < calls.index(outbox.mark)
    assert calls.index(outbox.mark) < calls.index(finalizer.lifecycle_service.complete_server_batch_capture)
    key = outbox.key('u', 'n')
    assert rows[key]['due_at'] == 700 and rows[key]['sync_hold']
    assert 'pipeline_dispatch_at' not in rows[key]  # Registration is durable; no native intake clock exists yet.
    _, segment = live.record_identity('u', 'n')
    assert batch.rows['jobs', segment]['state'] == 'record_pending'
    batch.rows['jobs', segment].update(state='dead', dead_letter_reason=failure)
    row['record_upload_failed'] = True
    monkeypatch.setattr(callback.time, 'time', lambda: 700)
    monkeypatch.setattr(callback.conversations_db, 'get_conversation', lambda *a, **k: dict(row))
    monkeypatch.setattr(callback, 'repair_fenced', lambda _: False)
    monkeypatch.setattr(callback, 'claim_from_snapshot', lambda *a: True)
    monkeypatch.setattr(callback, 'get_firestore_client', lambda: None)
    monkeypatch.setattr(callback.conversations_db, 'complete_sync_processing_hold', lambda *a, **k: True)
    monkeypatch.setattr(callback, 'schedule_after_finalization', Mock(return_value=True))

    def notes(**kwargs):
        row['structured'] = {'title': 'Recovered preview', 'overview': 'Notes survive the terminal batch'}
        return callback.deserialize_conversation(dict(row))

    process = Mock(side_effect=notes)
    monkeypatch.setattr(callback, 'process_conversation', process)
    assert outbox.run(key, rows[key]['task_token'], callback.enrich_conversation, now=700) == 'processed'
    process.assert_called_once()
    assert row['structured']['overview'] == 'Notes survive the terminal batch'
    assert key not in rows and batch.rows['jobs', segment]['state'] == 'dead'


@pytest.mark.asyncio
@pytest.mark.parametrize('mode,seal', [('serve', 'false'), ('off', 'true')])
async def test_seal_flag_or_mode_off_keeps_legacy_preview_notes_path(preview_fallback, monkeypatch, mode, seal):
    calls, _, rows, _ = preview_fallback
    monkeypatch.setenv('PIPELINE_ATTENTION_MODE', mode)
    monkeypatch.setenv('PIPELINE_SEAL_FAST_ENABLED', seal)
    # The fixture's serving seam represents the owner cohort; keep its mode check real here.
    monkeypatch.setattr(finalizer.pipeline_attention, 'serving', lambda _: mode == 'serve')
    with pytest.raises(finalizer.ConversationFinalizationError):
        await _finalize()
    assert finalizer.process_with_episode_budget in calls
    assert finalizer.lifecycle_service.complete_server_batch_capture not in calls
    assert not rows


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
