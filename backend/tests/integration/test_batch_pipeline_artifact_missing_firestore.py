"""Real projection publishes a healthy sibling without acknowledging absent audio."""

from copy import deepcopy
import hashlib

import pytest

from database.batch_pipeline_artifact_missing import ArtifactMissingStore
from tests.integration.test_batch_pipeline_projection_firestore import lane, active_rows  # noqa: F401
from utils.batch_pipeline.intake import durable_status

pytestmark = pytest.mark.integration


def test_missing_artifact_sibling_releases_once_and_status_never_acknowledges(lane):
    batch = lane.seed(('healthy', 'absent'))
    good, missing = batch.ids
    lane.finish(batch, 0)
    missing_ref = lane.projector.store.ref('jobs', missing)
    missing_ref.update(
        {
            'state': 'quarantined',
            'quarantine_reason': 'worker_failed',
            'recovery_state': 'failed_held',
            'merge_pending': False,
            'token': '',
            'lease_until': 0,
        }
    )
    snapshot = deepcopy(missing_ref.get().to_dict())
    proof = {
        'status': 404,
        'generation': 1,
        'verified_at': 10000,
        'uri_sha256': hashlib.sha256(snapshot['audio_uri'].encode()).hexdigest(),
    }
    assert ArtifactMissingStore(lane.store).apply(missing, snapshot, proof, 'a' * 64, 10000)
    lane.projector.store.ref('intakes', batch.binding.job_id).set(
        {
            'owner_id': lane.uid,
            'content_id': batch.binding.content_id,
            'segment_ids': list(batch.ids),
            'lane': 'backfill',
            'total_files': 1,
        }
    )
    assert lane.projector.project(good) is None
    rows = active_rows(lane)
    assert len(rows) == 1 and rows[0]['status'] == 'completed'
    assert rows[0]['sync_content_revision'] == 1
    result = lane.projector.complete_held(batch.binding)
    assert result['reason_code'] == 'batch_artifact_missing'
    assert result['new_memories'] == [rows[0]['id']]
    assert batch.ledger.get().to_dict()['status'] == 'partial'
    assert lane.projector.complete_held(batch.binding) == result
    assert lane.projector.project(good) is None
    assert active_rows(lane)[0]['sync_content_revision'] == 1
    status = durable_status(lane.store, lane.uid, batch.binding.job_id)
    assert status['status'] == 'failed' and status['reason_code'] == 'batch_artifact_missing'
    assert not lane.published
    held_job = missing_ref.get().to_dict()
    assert held_job['state'] == 'quarantined' and held_job['recovery_state'] == 'failed_held'
    assert not held_job.get('result') and not held_job.get('expires_at') and not held_job.get('client_status')
    assert lane.loads == [good]
