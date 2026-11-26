"""Exercise both authenticated metadata routes and the unchanged multipart decision."""

import hashlib
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from routers import sync
from tests.unit.test_sync_poll_limit import poll_client, poll_lua, poll_redis  # noqa: F401
from utils.batch_pipeline import live_upload
from utils.sync import capture_manifest

URL = '/v2/sync-local-files'
DEVICE = 'android_abcdef01'
CLAIMS = [{'name': 'audio_fixture_1790000000.bin', 'sha256': 'a' * 64}]


@pytest.fixture
def retry(monkeypatch):
    monkeypatch.setenv('SYNC_CONTENT_ID_SECRET', 'synthetic-test-key')
    return capture_manifest.issue_retry_handle('owner', DEVICE, 'target', CLAIMS)


@pytest.mark.parametrize('change', ['owner', 'device', 'target', 'name', 'bytes', 'extra', 'expired', 'signature'])
def test_handle_requires_exact_authenticated_identity_and_live_expiry(retry, monkeypatch, change):
    owner, device, target = 'owner', DEVICE, 'target'
    claims = [dict(CLAIMS[0])]
    if change == 'owner':
        owner = 'other'
    elif change == 'device':
        device = 'ios_abcdef01'
    elif change == 'target':
        target = 'other'
    elif change == 'name':
        claims[0]['name'] = 'renamed.bin'
    elif change == 'bytes':
        claims[0]['sha256'] = 'b' * 64
    elif change == 'extra':
        claims *= 2
    elif change == 'expired':
        monkeypatch.setattr(capture_manifest.time, 'time', lambda: int(retry.split('.')[0]))
    else:
        retry = retry[:-1] + ('a' if retry[-1] != 'a' else 'b')
    assert not capture_manifest.valid_retry_handle(retry, owner, device, target, claims)


def test_live_manifest_and_probe_recheck_state_independently(poll_client, monkeypatch, retry):
    payload = {'conversation_id': 'target', 'files': CLAIMS}
    headers = {'X-App-Platform': 'android', 'X-Device-Id-Hash': 'abcdef01', 'X-Omi-Wal-Retry': retry}
    renewed = AsyncMock()
    monkeypatch.setattr(sync, '_renew_custody_lease', renewed)
    monkeypatch.setattr(sync, '_capture_matches_server_conversation', lambda *args: True)
    monkeypatch.setattr(sync, 'claim_conversation_manifest', lambda *args: True)
    monkeypatch.setattr(sync, 'record_product_event', lambda *args, **kwargs: None)
    monkeypatch.setattr(live_upload, 'cached_record_wait', lambda *args: 'record_jobs_missing')
    monkeypatch.setattr(live_upload.record_wal_handoff, 'handoff_enabled', lambda: False)
    has_receipts = False
    monkeypatch.setattr(live_upload.record_wal_handoff.receipts, 'has_receipts', lambda *args: has_receipts)
    manifest = poll_client.post('/v2/sync-capture-manifest', json=payload, headers=headers)
    renewed.assert_awaited_once_with('owner', 'target')
    assert manifest.status_code == 200 and manifest.json()['manifest']
    assert manifest.headers['x-omi-wal-retry'] == 'check'
    wait = poll_client.put(URL, json=payload, headers=headers)
    assert wait.status_code == 503 and wait.json()['code'] == 'record_capture_pending'
    assert 'retry-after' not in wait.headers and 'x-omi-wal-retry' not in wait.headers
    has_receipts = True
    assert poll_client.put(URL, json=payload, headers=headers).status_code == 204
    has_receipts = False
    monkeypatch.setattr(live_upload.record_wal_handoff, 'handoff_enabled', lambda: True)
    assert poll_client.put(URL, json=payload, headers=headers).status_code == 204
    monkeypatch.setattr(live_upload.record_wal_handoff, 'handoff_enabled', lambda: False)
    monkeypatch.setattr(sync, 'memoized_record_wait', AsyncMock(side_effect=TimeoutError))
    assert poll_client.put(URL, json=payload, headers=headers).status_code == 204
    renewed.assert_awaited_once()
    monkeypatch.setattr(live_upload, 'cached_record_wait', lambda *args: None)
    miss = poll_client.post('/v2/sync-capture-manifest', json=payload, headers=headers)
    assert miss.status_code == 200 and 'x-omi-wal-retry' not in miss.headers


@pytest.mark.parametrize('case', ['exact', 'legacy', 'mixed_torn', 'stale_manifest', 'coverage', 'empty', 'future'])
def test_handle_only_after_exact_nonempty_verified_post(case, poll_client, monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('SYNC_CONTENT_ID_SECRET', 'synthetic-test-key')
    stamp = int(time.time()) + (40 if case == 'future' else -10)
    name = f'audio_omi_{stamp}.bin'
    audio = b'\0\0\0\x01x' if case != 'empty' else b'\0\0'
    parts = [(name, audio)]
    if case == 'mixed_torn':
        parts.append((f'audio_omi_{stamp - 1}.bin', b'\0'))
    claims = [{'name': n, 'sha256': hashlib.sha256(data).hexdigest()} for n, data in parts]
    token = capture_manifest.issue_capture_manifest('owner', DEVICE, 'target', claims)
    headers = {'X-App-Platform': 'android', 'X-Device-Id-Hash': 'abcdef01', 'X-Omi-Sync-Capture-Manifest': token}
    if case != 'legacy':
        headers['X-Omi-Wal-Retry'] = '1'
    if case == 'stale_manifest':
        parts[0] = (name, audio + b'y')
    monkeypatch.setattr(sync, 'memoized_record_wait', AsyncMock(return_value=None))
    monkeypatch.setattr(sync, 'get_sync_ledger_fence_mode', lambda: sync.SyncLedgerFenceMode.ACTIVE)
    monkeypatch.setattr(sync, '_capture_matches_server_conversation', lambda *a, **kw: True)
    monkeypatch.setattr(sync.legacy_dark, 'current_mode', lambda *_: sync.legacy_dark.LegacySyncMode.ON)
    monkeypatch.setattr(sync.legacy_dark, 'read_ledger_row', lambda _uid, _content_id: None)
    monkeypatch.setattr(sync, 'get_hard_restriction_status', lambda *_: (False, None))
    monkeypatch.setattr(sync, 'is_daily_audio_ceiling_exceeded', lambda *_: False)
    monkeypatch.setattr(sync, 'lever_enabled', lambda *_: True)
    monkeypatch.setattr(sync, 'resolve_transcription_allowance', lambda *_: SimpleNamespace(managed=True))
    monkeypatch.setattr(sync, 'retained_source_offsets', lambda *a, **kw: {})
    monkeypatch.setattr(sync, 'ramp_admission_policy', lambda uid, policy, **kw: policy)
    monkeypatch.setattr(live_upload, 'remember_record_wait', lambda *_: None)

    async def decide(**kwargs):
        if case == 'coverage':
            return live_upload._pending(live_upload.RecordUploadWait.AUDIO_COVERAGE_UNPROVEN, path='coverage')
        return await live_upload.conversation_pending(
            live_upload.RecordUploadWait.RECORD_JOBS_MISSING, 'owner', 'target'
        )

    monkeypatch.setattr(sync, 'registered_record_response', decide)
    response = poll_client.post(
        URL + '?conversation_id=target', headers=headers, files=[('files', (n, data)) for n, data in parts]
    )
    assert response.status_code == {'empty': 200, 'stale_manifest': 422}.get(case, 503), response.text
    handle = response.headers.get('x-omi-wal-retry')
    if case == 'exact':
        assert capture_manifest.valid_retry_handle(handle, 'owner', DEVICE, 'target', claims)
    else:
        assert handle is None
