"""Real finish receipt atomicity after a commit succeeds but its response is lost."""

import hashlib
import os
import uuid
from datetime import datetime, timezone
from unittest.mock import Mock

from google.api_core.exceptions import ServiceUnavailable
from google.auth.credentials import AnonymousCredentials
from google.cloud import firestore
import pytest
from starlette.responses import JSONResponse

from config.record_audio import record_identity
from database import record_custody_append as custody, record_token_lease_metrics as metrics
from database.batch_pipeline_record_lease_recovery import recovery_segment
from utils.sync import record_token_lease as request

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not os.getenv('FIRESTORE_EMULATOR_HOST', '').startswith(('127.0.0.1:', 'localhost:')),
        reason='isolated loopback Firestore emulator required',
    ),
]


@pytest.mark.parametrize('lose_reply', [False, True])
async def test_finish_receipt_survives_a_real_committed_transaction(monkeypatch, tmp_path, lose_reply):
    monkeypatch.setenv('RECORD_TOKEN_LEASE_MODE', 'serve')
    monkeypatch.setenv('RECORD_TOKEN_LEASE_MODE_SERVE_PERCENT', '100')
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    client = firestore.Client(project='demo-tokenlease-round4', credentials=AnonymousCredentials())
    uid, cid, session = 'synthetic-r4-' + uuid.uuid4().hex, 'record', 'custody:ambiguous'
    user = client.collection('users').document(uid)
    row = user.collection('conversations').document(cid)
    receipt = row.collection('record_custody_recoveries').document(hashlib.sha256(session.encode()).hexdigest())
    user.set({'private_cloud_sync_enabled': True})
    row.set(
        {
            'record_lane_owner': 'batch_live_v1',
            'status': 'completed',
            'private_cloud_sync_enabled': True,
            'record_audio_closed': False,
            'record_upload_revision': 7,
            'record_upload_sessions': {},
            'finished_at': datetime.now(timezone.utc),
        }
    )
    monkeypatch.setattr(custody, 'get_firestore_client', lambda: client)
    recovery = Mock(side_effect=AssertionError('committed finish was recovered a second time'))
    monkeypatch.setattr(custody, 'recover_committed', recovery)
    original_commit = client._firestore_api.commit
    lost = []

    def commit_then_lose_reply(*args, **kwargs):
        result = original_commit(*args, **kwargs)
        rpc = kwargs.get('request') or args[0]
        if lose_reply and not lost and any(write.update.name.endswith('/' + receipt.path) for write in rpc['writes']):
            # The real emulator has committed both the revision and receipt.
            # Only the response is lost; run_transactional must re-read them.
            assert receipt.get().exists
            lost.append(True)
            raise ServiceUnavailable('synthetic response lost after real commit')
        return result

    monkeypatch.setattr(client._firestore_api, 'commit', commit_then_lose_reply)
    counter = metrics.LATE_APPEND._value.get()
    response = JSONResponse(status_code=202, content={'status': 'queued'})
    artifact = tmp_path / 'committed-audio'

    @request.custody_upload
    async def upload():
        await request.begin_upload(uid, cid, 'ambiguous')
        artifact.write_bytes(b'synthetic retained audio')
        request.stored(['local-audio'], [str(artifact)])
        return response

    try:
        assert await upload() is response
        current = row.get().to_dict()
        assert current['record_upload_revision'] == 8
        assert not current['record_upload_sessions'] and not current.get('record_audio_partial')
        assert receipt.get().to_dict()['upload_revision'] == 8
        assert lost == ([True] if lose_reply else [])
        assert artifact.read_bytes() == b'synthetic retained audio'
        assert not custody.finish(uid, cid, session, accepted=True, firestore_client=client)
        assert row.get().to_dict() == current
        recovery.assert_not_called()
        assert metrics.LATE_APPEND._value.get() == counter
    finally:
        # Only this test's exact synthetic owner and document ids are removed.
        for job_id in (record_identity(uid, cid)[1], recovery_segment(uid, cid)):
            ref = client.collection('batch_pipeline_dev_jobs').document(job_id)
            if (ref.get().to_dict() or {}).get('owner_id') == uid:
                ref.delete()
        receipt.delete()
        row.delete()
        user.delete()
        client.close()
