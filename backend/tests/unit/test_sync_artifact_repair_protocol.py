"""HTTP capability and complete-bundle fence, with no provider/storage calls."""

import pytest
from types import SimpleNamespace
from fastapi import HTTPException

from routers import sync
from tests.unit.test_sync_poll_limit import poll_client, poll_redis, poll_lua  # noqa: F401


@pytest.mark.parametrize('protocol', [None, '0', '1', '2'])
def test_wire_negotiates_terminal_retry_only_for_exact_bundle_client(poll_client, monkeypatch, protocol):
    seen = []

    def durable(job, uid, **kwargs):
        capable = kwargs.get('artifact_retry', False)
        seen.append(capable)
        return {
            'job_id': job,
            'status': 'failed' if capable else 'processing',
            'reason_code': 'batch_artifact_missing',
            'poll_after_ms': 0 if capable else 300000,
        }

    monkeypatch.setattr(sync, 'get_durable_job_status', durable)
    headers = {'X-Omi-Custody-Repair-Protocol': protocol} if protocol is not None else {}
    response = poll_client.get('/v2/sync-local-files/bp_original', headers=headers)
    capable = protocol == '1'
    assert response.status_code == 200 and seen == [capable]
    assert response.json()['status'] == ('failed' if capable else 'processing')
    assert response.json()['poll_after_ms'] == (0 if capable else 300000)


@pytest.mark.parametrize('repair', [False, True])
def test_empty_repair_cannot_acknowledge_a_changed_original_bundle(poll_client, monkeypatch, repair):
    def empty(*args, **kwargs):
        raise sync.EmptySyncUpload()

    monkeypatch.setattr(sync, 'prepare_sync_uploads', empty)
    query = '?repair_job_id=bp_original' if repair else ''
    response = poll_client.post(
        '/v2/sync-local-files' + query, files=[('files', ('audio_1000.bin', b'\0\0\0\0', 'application/octet-stream'))]
    )
    assert response.status_code == (409 if repair else 200)
    if repair:
        assert response.json()['code'] == 'sync_repair_bundle_changed'


@pytest.mark.parametrize('repair, matches, expected', [(False, False, 422), (True, False, 409), (True, True, 410)])
def test_accepted_repair_reaches_exact_owner_check_after_new_upload_lookback(
    poll_client, monkeypatch, repair, matches, expected
):
    monkeypatch.setattr(sync, 'prepare_sync_uploads', lambda files, *args, **kwargs: files)
    monkeypatch.setattr(sync, 'get_sync_ledger_fence_mode', lambda: sync.SyncLedgerFenceMode.ACTIVE)
    monkeypatch.setattr(sync.legacy_dark, 'current_mode', lambda *args: sync.legacy_dark.LegacySyncMode.DARK)
    monkeypatch.setattr(
        sync,
        'classify_sync_lane',
        lambda *args, **kwargs: SimpleNamespace(
            lane=sync.SyncLane.BACKFILL,
            trust=sync.CaptureTimeTrust.LEGACY,
            reason='lookback_exceeded',
            maximum_age_seconds=40 * 86400,
            automatic_recovery_allowed=False,
        ),
    )
    monkeypatch.setattr(sync, 'validate_backfill_uploads', lambda *args: None)
    monkeypatch.setattr(
        sync,
        'resolve_transcription_allowance',
        lambda *args: SimpleNamespace(managed=True, reason='plan_within_allowance'),
    )
    monkeypatch.setattr(sync, 'is_cloud_tasks_dispatch_enabled', lambda: False)
    monkeypatch.setattr(sync, 'has_byok_keys', lambda: False)
    # A staged name with a parseable capture time: admission reads it since #24501.
    monkeypatch.setattr(sync, '_retrieve_file_paths_v2', lambda *args: ['omi_1792152000.bin'])
    monkeypatch.setattr(sync, 'compute_sync_content_id', lambda *args: 'original-content')
    checks = []

    def owned(uid, content, job):
        checks.append((uid, content, job))
        return matches

    monkeypatch.setattr(sync, 'repair_upload_owner_matches', owned)
    archives = []

    def archive(*args, **kwargs):
        archives.append(True)
        raise HTTPException(status_code=410, detail='synthetic verified-owner archive checkpoint')

    monkeypatch.setattr(sync, 'archive_mobile_batch_raw_files', archive)
    query = '?repair_job_id=bp_original' if repair else ''
    response = poll_client.post(
        '/v2/sync-local-files' + query, files=[('files', ('audio_1000.bin', b'\0\0\0\0', 'application/octet-stream'))]
    )
    assert response.status_code == expected
    assert checks == ([('owner', 'original-content', 'bp_original')] if repair else [])
    assert archives == ([True] if repair and matches else [])
