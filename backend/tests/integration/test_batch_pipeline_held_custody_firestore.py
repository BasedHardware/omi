"""Projected transcripts stay visible while unresolved audio remains in custody."""

from types import SimpleNamespace

import pytest

from tests.integration.test_batch_pipeline_projection_firestore import lane, active_rows  # noqa: F401
from utils.batch_pipeline import intake

pytestmark = pytest.mark.integration


def test_partial_transcript_visible_after_30_minutes_without_upload_ack(lane, monkeypatch):
    batch = lane.seed(('healthy', 'held'))
    good, held = batch.ids
    lane.finish(batch, 0)
    job = lane.projector.store.ref('jobs', held)
    job.update(
        {
            'state': 'quarantined',
            'quarantine_reason': 'worker_failed',
            'recovery_state': 'failed_held',
            'merge_pending': False,
            'token': '',
            'lease_until': 0,
        }
    )
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
    result = lane.projector.complete_held(batch.binding)
    assert result['held_segments'] == 1 and result['new_memories']
    for now in (10000, 10000 + 1801, 10000 + 14 * 86400):
        monkeypatch.setattr(intake, 'time', SimpleNamespace(time=lambda: now))
        status = intake.durable_status(lane.store, lane.uid, batch.binding.job_id)
        assert status['status'] == 'processing' and status['reason_code'] == 'batch_unit_held'
        assert status['poll_after_ms'] == 300000 and status['result'] == result
        rows = active_rows(lane)
        assert len(rows) == 1 and rows[0]['status'] == 'completed'
        assert rows[0]['transcript_segments'] and rows[0]['sync_content_revision'] == 1
    assert batch.ledger.get().to_dict()['status'] == 'partial'
    assert job.get().to_dict()['recovery_state'] == 'failed_held'
    assert not lane.published
    assert lane.loads == [good]
