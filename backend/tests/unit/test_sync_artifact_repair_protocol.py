"""HTTP capability and complete-bundle fence, with no provider/storage calls."""

import pytest

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
