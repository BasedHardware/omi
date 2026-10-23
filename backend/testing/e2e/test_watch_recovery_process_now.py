"""Watch uploads remain retryable when the batch route declines admission.

The retired legacy processing route cannot prove batch recovery visibility.
Batch projection and overlapping phone/Watch S1 serving evidence remain release gates.
"""

import struct
import time

from testing.e2e.sync_helpers import patch_fresh_sync_lane
from config.policy import BatchUnitPolicy


def test_watch_upload_keeps_audio_retryable_after_legacy_retirement(client, auth_headers, monkeypatch):
    import routers.sync as sync_router

    patch_fresh_sync_lane(monkeypatch)
    monkeypatch.setattr(sync_router, 'resolve_batch_policy', lambda uid: BatchUnitPolicy(batch_enabled=False))
    monkeypatch.setattr(sync_router.legacy_dark, 'read_ledger_row', lambda uid, content_id: None)
    monkeypatch.setattr(sync_router, 'get_hard_restriction_status', lambda uid: (False, None))
    monkeypatch.setattr(sync_router, 'has_transcription_credits', lambda uid: True)
    monkeypatch.setattr(sync_router, 'has_byok_keys', lambda: False)

    async def decline_batch(**kwargs):
        return None

    monkeypatch.setattr(sync_router, 'accept_batch_upload', decline_batch)
    timestamp = int(time.time()) - 60
    filename = f'audio_omibatchwatch0123456789abcdef0123456789abcdefs0_pcm16_16000_1_fs160_{timestamp}.bin'
    # Same framing as the native Watch archive: 100 PCM16 frames = one second.
    raw = (struct.pack('<I', 320) + struct.pack('<160h', *range(160))) * 100
    response = client.post(
        '/v2/sync-local-files', headers=auth_headers, files=[('files', (filename, raw, 'application/octet-stream'))]
    )
    assert response.status_code == 409, response.text
    assert response.json()['code'] == 'sync_content_in_progress'
    assert response.json()['job_id'] is None
    assert int(response.headers['retry-after']) >= 60
