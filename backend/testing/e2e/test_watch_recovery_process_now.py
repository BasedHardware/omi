"""Real sync routes and PCM decode; external speech/cloud seams stay hermetic."""

import struct
import time

from testing.e2e.sync_helpers import patch_fresh_sync_lane
from testing.e2e.test_sync_lifecycle import _drain_background_coroutines, _patch_sync_pipeline, _poll_sync_job


def test_watch_process_now_keeps_recovered_speech_visible(client, auth_headers, monkeypatch, live_user):
    import database.conversations as conversations_db
    import utils.conversations.lifecycle as lifecycle
    import utils.conversations.demand_processing as demand_processing
    import utils.sync.pipeline as pipeline

    patch_fresh_sync_lane(monkeypatch)
    real_decode = pipeline.decode_files_to_wav
    reprocessed = []
    pending = _patch_sync_pipeline(monkeypatch, transcript_text='Testing one two three.', reprocessed=reprocessed)
    monkeypatch.setattr(pipeline, 'decode_files_to_wav', real_decode)
    monkeypatch.setattr(demand_processing, 'promote_conversation_effects', lambda *args: None)
    ingest = lifecycle.ingest_sync_conversation

    def retain_discarded_speech(*args, **kwargs):
        row, created, segments = ingest(*args, **kwargs)
        row.update(discarded=True, sync_relevance='review')
        lifecycle.discard(args[0], row['id'])
        return row, created, segments

    monkeypatch.setattr(lifecycle, 'ingest_sync_conversation', retain_discarded_speech)
    timestamp = int(time.time()) - 60
    filename = f'audio_omibatchwatch0123456789abcdef0123456789abcdefs0_pcm16_16000_1_fs160_{timestamp}.bin'
    # Same framing as the native Watch archive: 100 PCM16 frames = one second.
    raw = (struct.pack('<I', 320) + struct.pack('<160h', *range(160))) * 100
    response = client.post(
        '/v2/sync-local-files', headers=auth_headers, files=[('files', (filename, raw, 'application/octet-stream'))]
    )
    assert response.status_code == 202, response.text
    _drain_background_coroutines(pending)
    job = _poll_sync_job(client, auth_headers, response.json()['job_id'])
    assert job['status'] == 'completed', job
    assert job['result']['new_memories'] == ['sync-created-conversation']
    conversation = client.get('/v1/conversations/sync-created-conversation', headers=auth_headers)
    assert conversation.status_code == 200, conversation.text
    assert conversation.json()['discarded'] is False
    row = conversations_db.get_conversation('123', 'sync-created-conversation')
    assert row['sync_relevance_user_kept'] is True
    assert reprocessed == ['sync-created-conversation']
