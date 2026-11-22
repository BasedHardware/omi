"""Missing recovery input closes a task; storage outages remain retryable."""

from copy import deepcopy
import json
from unittest.mock import Mock

from google.api_core.exceptions import DeadlineExceeded, Forbidden, NotFound, ServiceUnavailable
import pytest

from tests.unit.test_batch_pipeline_quarantine_recovery import row, setup  # noqa: F401
from tests.unit.test_batch_pipeline_invalid_manifest_hold import ref, serve
from utils.batch_pipeline.artifacts import ArtifactStore, ProtectionContext
from utils.batch_pipeline.source_audio import MAGIC
from utils.metrics import OMI_FALLBACK_TOTAL


def metric():
    return OMI_FALLBACK_TOTAL.labels(
        component='stt_selection', from_mode='batch', to_mode='none', reason='input_missing', outcome='degraded'
    )._value.get()


@pytest.mark.parametrize('missing', ['manifest', 'chunk'])
def test_missing_input_answers_2xx_and_holds_once(setup, monkeypatch, missing):
    client, _, binding, artifacts, stt, recovery = setup
    job = row(client)
    job.update(unit_kind='capture_span', conversation_id='c')
    recovery.protocol.prepare('bad', binding.owner_id, 100)
    before = deepcopy(row(client))
    if missing == 'manifest':
        artifacts.fetch_audio.side_effect = NotFound('synthetic absent manifest')
    else:
        # Execute the real manifest -> pinned source reader, with synthetic storage only.
        storage = Mock()
        storage.bucket.return_value.blob.return_value.reload.side_effect = NotFound('synthetic absent chunk')
        source = ArtifactStore(
            storage,
            bucket='synthetic',
            namespace='batch_pipeline_prod',
            authorize=lambda _: ProtectionContext('standard', 0),
            key_for_owner=lambda _: b'0' * 32,
            register_artifact=lambda *args: None,
        )
        source._read = Mock(
            return_value=MAGIC
            + json.dumps(
                {
                    'owner_id': binding.owner_id,
                    'conversation_id': 'c',
                    'capture_at': 1,
                    'context': {},
                    'references': [
                        {**ref(0, 8000), 'bucket': 'omi-private-cloud-sync', 'path': 'chunks/synthetic-owner/c/x.bin'}
                    ],
                }
            ).encode()
        )
        artifacts.fetch_audio.side_effect = source.fetch_audio
    start = metric()
    http = serve(setup, monkeypatch)
    payload = {'stage': 'prod', 'segment_id': 'bad'}
    response = http.post('/v2/batch-pipeline/recover-quarantine', json=payload)
    assert response.status_code == 200 and response.json() == {'status': 'failed_held'}
    job = row(client)
    assert job['recovery_state'] == 'failed_held'
    assert job['recovery']['refusal'] == {'reason': 'input_missing'}
    assert job['recovery']['settled_at'] == 100 and 'started_at' not in job['recovery']
    assert {k: v for k, v in job.items() if k not in {'recovery', 'recovery_state', 'held_deadline_at'}} == {
        k: v for k, v in before.items() if k not in {'recovery', 'recovery_state', 'held_deadline_at'}
    }
    assert metric() == start + 1
    assert recovery.protocol.prepare('bad', binding.owner_id, 200) is None
    assert http.post('/v2/batch-pipeline/recover-quarantine', json=payload).json() == {'status': 'held'}
    assert metric() == start + 1
    artifacts.fetch_audio.assert_called_once()
    stt.assert_not_called()
    assert not [name for name, *_ in artifacts.mock_calls if 'delete' in name or 'persist' in name]


@pytest.mark.parametrize(
    'error', [ServiceUnavailable('synthetic'), DeadlineExceeded('synthetic'), TimeoutError(), Forbidden('synthetic')]
)
def test_storage_outage_or_permission_error_remains_retryable(setup, monkeypatch, error):
    client, _, binding, artifacts, stt, recovery = setup
    artifacts.fetch_audio.side_effect = error
    start = metric()
    response = serve(setup, monkeypatch).post(
        '/v2/batch-pipeline/recover-quarantine', json={'stage': 'prod', 'segment_id': 'bad'}
    )
    assert response.status_code == 500
    assert row(client)['recovery_state'] == 'prepared'
    assert not set(row(client)['recovery']) & {'refusal', 'started_at', 'settled_at'}
    with pytest.raises(type(error)):
        recovery.recover('bad', binding.owner_id)
    assert metric() == start
    stt.assert_not_called()


def test_missing_input_hold_loses_race_without_counting(setup, monkeypatch):
    client, _, _, artifacts, stt, _ = setup

    def lose_intent(_):
        row(client)['recovery']['token'] = 'new-token'
        raise NotFound('synthetic absent input')

    artifacts.fetch_audio.side_effect = lose_intent
    start = metric()
    response = serve(setup, monkeypatch).post(
        '/v2/batch-pipeline/recover-quarantine', json={'stage': 'prod', 'segment_id': 'bad'}
    )
    assert response.status_code == 200 and response.json() == {'status': 'held'}
    assert row(client)['recovery_state'] == 'prepared'
    assert 'refusal' not in row(client)['recovery']
    assert metric() == start
    stt.assert_not_called()
