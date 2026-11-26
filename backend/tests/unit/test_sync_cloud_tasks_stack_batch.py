"""Regression coverage for the batch gauntlet's scoped admission retry."""

from types import SimpleNamespace
from unittest.mock import Mock

import httpx

from testing.sync_cloud_tasks_stack import batch


def test_serving_kill_scenario_admission_retries_same_capture(monkeypatch, tmp_path):
    monkeypatch.setenv('OMI_SYNC_STACK_STATE_DIR', str(tmp_path))
    stack = Mock(spec=batch.BatchStack)
    stack.admission_url = 'http://127.0.0.1:8000'
    stack.control_dir = tmp_path
    stack.control_headers = {'X-Sync-Stack-Control': 'synthetic'}
    stack.firestore = Mock()
    (tmp_path / 'policy.json').write_text('{}')
    stack.owner_variants = 0
    stack.scenario_uid.return_value = 'synthetic-owner'
    stack.http = Mock()
    stack.http.post.side_effect = [
        httpx.Response(204),
        httpx.Response(200, json={'manifest': 'signed-manifest'}),
        httpx.Response(
            503,
            json={
                'code': 'sync_batch_unavailable',
                'detail': 'Sync is temporarily unavailable; retain local audio',
            },
        ),
        httpx.Response(202, json={'job_id': 'bp_capture', 'lane': 'fresh'}),
    ]
    stack.doc.side_effect = [
        {'owner_id': 'synthetic-owner', 'segment_ids': ['segment'], 'content_id': 'content'},
        {'policy': {}, 'requires_compute_admission': True, 'audio_uri': 'gs://synthetic/audio'},
    ]
    sleep = Mock()
    monkeypatch.setattr(batch, 'time', SimpleNamespace(sleep=sleep))

    upload = batch._upload(stack, 'batch-serving-killed', words='empty', admission_retry_delays=(1, 2, 4, 8, 15))

    assert upload.job_id == 'bp_capture'
    assert upload.segment_ids == ['segment']
    provenance, manifest, first_upload, retry = stack.http.post.call_args_list
    assert '/capture-provenance/' in provenance.args[0]
    assert manifest.args[0].endswith('/v2/sync-capture-manifest')
    assert first_upload == retry
    sleep.assert_called_once_with(1)
