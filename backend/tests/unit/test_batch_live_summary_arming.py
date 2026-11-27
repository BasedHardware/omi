"""Commit real projection/session/assignment/codec writes, with external follow-ups deferred."""

from dataclasses import asdict, replace
from datetime import datetime, timezone
import logging

import pytest
from google.cloud import firestore
from google.cloud.firestore_v1 import _helpers

from database import conversations as db
from tests.unit.test_batch_pipeline_projection_donor_dedupe import batch_projection
from utils.conversations import summary_delivery as delivery


def setup_record(lane, **changes):
    binding = replace(lane.binding, record_origin=True, native_record=True)
    lane.client.rows[(f'{lane.namespace}_jobs', 'segment')]['projection_binding'] = asdict(binding)
    row = lane.client.rows[('users', 'u', 'conversations', 'live')]
    row.update(
        record_lane_owner='batch_live_v1',
        status='completed',
        private_cloud_sync_enabled=True,
        created_at=datetime.now(timezone.utc),
        structured={'title': '', 'overview': ''},
        finalization_job_id='finalizer',
        finalization_revision=1,
        finalization_status='queued',  # Seed a historical handoff before atomic settlement.
    )
    row.update(changes)
    for index, segment in enumerate(row['transcript_segments']):
        segment['id'] = f'live-{index}'
    lane.client.rows[('users', 'u')]['private_cloud_sync_enabled'] = True
    lane.client.rows[('conversation_finalization_jobs', 'finalizer')] = dict(
        uid='u',
        conversation_id='live',
        finalization_revision=1,
        status='completed',
        terminal_outcome='success',
        finalization_outcome='server_batch_capture',
        fanout_status='completed',
    )
    return row


@pytest.mark.parametrize('has_pending', [False, True])
@pytest.mark.parametrize('title', ['', 'Discussion notes'])
def test_projection_commit_arms_first_summary_with_retained_finalization_id(batch_projection, has_pending, title):
    lane = batch_projection
    pending = datetime.now(timezone.utc).timestamp() - 30 if has_pending else None
    setup_record(
        lane, summary_first_pending_at=pending, summary_due_at=None, structured={'title': title, 'overview': ''}
    )
    lane.projector.project('segment')
    stored = lane.client.rows[('users', 'u', 'conversations', 'live')]
    receipt = lane.client.rows[(f'{lane.namespace}_results', 'segment')]['projection']
    assert receipt['conversation_id'] == 'live'
    assert receipt['enrichment_required']
    assert stored['record_projection_revision'] == 1
    assert stored['summary_due_at'] is not None
    assert stored['summary_due_at'] == stored['summary_first_pending_at'] + delivery.deadline_seconds()
    if pending is not None:
        assert stored['summary_first_pending_at'] == pending
    assert stored['summary_title_provenance'] == 'server_minimum'
    # StrictFirestore retains transform sentinels. Check the real SDK emits a
    # delete (mask present, document field absent), then evaluate that stored view.
    update = _helpers.pbs_for_update(
        'projects/p/databases/(default)/documents/users/u/conversations/live', stored, None
    )[0]
    assert 'client_processing' in update.update_mask.field_paths
    assert 'client_processing' not in update.update.fields
    assert delivery.refusal({k: v for k, v in stored.items() if v is not firestore.DELETE_FIELD}) is None
    assert stored['finalization_job_id'] == 'finalizer'
    assert stored['finalization_status'] == 'completed'
    assert 'title_provenance' not in stored['structured']
    # Debt creation has no dispatch side effect; the existing projection follow-up owns it.
    lane.projector.finish_part.assert_called_once()
    before = stored['summary_due_at']
    assert not delivery.stamp_projection_debt(stored, now=before + 100)
    assert stored['summary_due_at'] == before


@pytest.mark.parametrize(
    'job_changes',
    [
        {'status': 'queued'},
        {'status': 'leased'},
        {'status': 'dead_letter'},
        {'terminal_outcome': 'fenced'},
        {'fanout_status': 'leased'},
        {'uid': 'other'},
        {'conversation_id': 'other'},
        {'finalization_revision': 2},
    ],
)
def test_projection_does_not_take_an_active_or_unrelated_generation(batch_projection, job_changes):
    lane = batch_projection
    setup_record(lane)
    lane.client.rows[('conversation_finalization_jobs', 'finalizer')].update(job_changes)
    lane.projector.project('segment')
    stored = lane.client.rows[('users', 'u', 'conversations', 'live')]
    assert stored['finalization_status'] == 'queued'
    assert stored.get('summary_due_at') is None
    assert 'summary_projection_finalization' not in stored


def test_successful_byok_finalizer_keeps_credential_custody_with_account_byok_off(batch_projection, caplog):
    lane = batch_projection
    setup_record(lane)
    lane.client.rows[('conversation_finalization_jobs', 'finalizer')]['requires_byok'] = True
    lane.client.rows[('users', 'u')]['byok'] = {'active': False}
    with caplog.at_level(logging.INFO, logger='database.batch_summary_debt'):
        lane.projector.project('segment')
    stored = lane.client.rows[('users', 'u', 'conversations', 'live')]
    assert stored['finalization_status'] == 'queued'
    assert stored.get('summary_due_at') is None
    assert 'summary_projection_finalization' not in stored
    assert 'phase=precommit outcome=refused reason=byok_required' in caplog.text


def test_projection_kill_switch_preserves_the_generation_fence(batch_projection, monkeypatch):
    lane = batch_projection
    setup_record(lane)
    monkeypatch.setenv('SUMMARY_PROJECTION_DEBT_ENABLED', 'false')
    lane.projector.project('segment')
    stored = lane.client.rows[('users', 'u', 'conversations', 'live')]
    assert stored['finalization_status'] == 'completed'
    assert stored.get('summary_due_at') is None
    assert 'summary_projection_finalization' not in stored


def test_summary_custody_proof_cannot_cross_generation_or_bypass_byok(monkeypatch):
    row = dict(
        status='completed',
        record_lane_owner='batch_live_v1',
        record_projection_revision=1,
        finalization_job_id='job',
        finalization_revision=1,
        summary_title_provenance='server_minimum',
        summary_projection_finalization={'job_id': 'job', 'revision': 1},
    )
    assert delivery.refusal(row) is None
    for changes in [
        {'finalization_job_id': 'next'},
        {'finalization_revision': 2},
        {'record_lane_owner': 'batch_sync_v1'},
        {'record_projection_revision': None},
        {'finalization_status': 'blocked_byok'},
    ]:
        assert delivery.refusal({**row, **changes}) == 'generation_owned'
    monkeypatch.setenv('SUMMARY_PROJECTION_DEBT_ENABLED', 'false')
    assert delivery.refusal(row) == 'generation_owned'


@pytest.mark.parametrize('job_id', ['missing', 123, True, False, 0, {}, [], 'bad/job'])
def test_missing_or_invalid_finalizer_preserves_projection_but_does_not_arm(batch_projection, job_id):
    lane = batch_projection
    setup_record(lane, finalization_job_id=job_id)
    lane.projector.project('segment')
    stored = lane.client.rows[('users', 'u', 'conversations', 'live')]
    assert stored['record_projection_revision'] == 1
    assert stored['transcript_segments']
    assert stored.get('summary_due_at') is None
    assert 'summary_projection_finalization' not in stored


def test_projection_preserves_existing_unbound_record_debt_policy(batch_projection):
    lane = batch_projection
    setup_record(lane, finalization_job_id=None, finalization_revision=None, finalization_status=None)
    lane.client.rows.pop(('conversation_finalization_jobs', 'finalizer'))
    lane.projector.project('segment')
    stored = lane.client.rows[('users', 'u', 'conversations', 'live')]
    assert stored['record_projection_revision'] == 1
    assert stored['summary_due_at'] == stored['summary_first_pending_at'] + delivery.deadline_seconds()
    assert 'summary_projection_finalization' not in stored
    assert delivery.refusal({k: v for k, v in stored.items() if v is not firestore.DELETE_FIELD}) is None


@pytest.mark.parametrize('offset', [60, 10**12])
def test_future_pending_clock_cannot_postpone_the_first_summary(offset):
    now = datetime.now(timezone.utc).timestamp()
    row = dict(status='completed', summary_first_pending_at=now + offset, structured={'title': ''})
    assert delivery.stamp_projection_debt(row, now=now)
    assert row['summary_first_pending_at'] == now
    assert row['summary_due_at'] == now + delivery.deadline_seconds()


def test_acceptance_clock_alone_is_receipt_metadata_not_armed_debt():
    token = delivery.ACCEPT_CONTEXT.set(100.0)
    try:
        write = dict(status='completed', summary_output_present=False)
        assert delivery.merge_result({}, write, 'u', now=200) is None
        assert write['summary_first_pending_at'] == 100.0
        assert 'summary_due_at' not in write
    finally:
        delivery.ACCEPT_CONTEXT.reset(token)


def test_expired_pending_clock_is_not_armed_even_when_created_at_is_recent():
    now = datetime.now(timezone.utc).timestamp()
    row = dict(
        status='completed',
        created_at=datetime.fromtimestamp(now, timezone.utc),
        summary_first_pending_at=now - 4 * 86400,
        structured={'title': ''},
    )
    assert not delivery.stamp_projection_debt(row, now=now)
    assert row.get('summary_due_at') is None
    assert row['summary_first_pending_at'] == now - 4 * 86400


@pytest.mark.parametrize('pending', [None, False, 'invalid', float('nan'), float('inf'), 0, -1])
def test_invalid_pending_clock_gets_a_finite_projection_acceptance(pending):
    now = datetime.now(timezone.utc).timestamp()
    row = dict(status='completed', summary_first_pending_at=pending, structured={'title': ''})
    assert delivery.stamp_projection_debt(row, now=now)
    assert row['summary_first_pending_at'] == now
    assert row['summary_due_at'] == now + delivery.deadline_seconds()


def test_repair_does_not_dispatch_over_the_projection_enrichment_lease(batch_projection, monkeypatch):
    from services import summary_debt_repair as repair
    from utils.sync import reprocess

    lane = batch_projection
    setup_record(lane)
    lane.projector.project('segment')
    path = ('users', 'u', 'conversations', 'live')
    lane.client.rows[path].pop('client_processing')  # SDK-verified DELETE_FIELD materialization above.
    now = lane.client.rows[path]['summary_due_at'] + 1
    key = (reprocess.COLLECTION, reprocess.key('u', 'live'))
    active = {'lease_until': now + 60, 'summary_seen': False, 'owner': 'projection-worker'}
    lane.client.rows[key] = dict(active)
    monkeypatch.setattr(repair, 'account_deletion_blocks_user_work', lambda _: False)
    monkeypatch.setattr(reprocess, 'owns_runtime', lambda: True)
    assert not repair.redrive(lane.client, 'u', 'live', now=now)
    assert lane.client.rows[key] == active
