"""Deletion races must preserve privacy without wedging the owner's result log."""

from dataclasses import replace
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from database.batch_pipeline_privacy import BatchPrivacyBlocked, privacy_owner_key
from database.batch_pipeline_projection_protocol import ProjectionBlocked
from database.legal_holds import acquire_destructive_operation, finish_destructive_operation
from tests.integration.test_batch_pipeline_projection_firestore import lane, active_rows
from utils.batch_pipeline import projection
from utils.batch_pipeline.scheduler import owner_key

pytestmark = pytest.mark.integration


def overlap(lane, batch, *, tombstoned):
    """The incident's older live row plus a legitimate closest candidate."""
    incoming = projection.build_incoming(replace(batch.items[0], capture_at=880.0), batch.binding, lane.payload)
    incoming.update(id='synthetic-overlap', finished_at=datetime.fromtimestamp(1000, timezone.utc))
    row, _, _ = lane.conversations.assign_sync_conversation(lane.uid, incoming, firestore_client=lane.client)
    blocked = lane.user.collection('conversations').document(row['id'])
    if tombstoned:
        lane.user.collection('deleted_conversations').document(row['id']).set({'deleted': True})
    live = {**blocked.get().to_dict(), 'id': 'synthetic-live'}
    live.update(
        started_at=datetime.fromtimestamp(990, timezone.utc), finished_at=datetime.fromtimestamp(1004, timezone.utc)
    )
    lane.user.collection('conversations').document(live['id']).set(live)
    return blocked, live


def test_historical_409_tombstone_live_row_self_heals_on_owner_sweep(lane, monkeypatch):
    head = lane.seed(('head-a', 'head-b'))
    later = lane.seed(('later-a', 'later-b'), capture_at=2000)
    blocked, live = overlap(lane, head, tombstoned=True)
    before = blocked.get().to_dict()
    monkeypatch.setattr(lane.conversations, 'get_closest_conversation_to_timestamps', lambda *args: live)
    for batch in (head, later):
        for index in range(len(batch.ids)):
            lane.finish(batch, index)
    lane.projector.project_owner(lane.uid, limit=16, budget_seconds=60)
    assert blocked.get().to_dict() == before
    assert lane.projector.store.projection_watermark(owner_key(lane.uid)) == later.ids[-1]
    assert all(batch.ledger.get().to_dict()['status'] == 'completed' for batch in (head, later))
    for snapshot in lane.user.collection('conversations').stream():
        if snapshot.id != blocked.id:
            assert blocked.id not in snapshot.to_dict().get('sync_merged_from', [])
    assert head.ledger.get().to_dict()['result']['new_memories'] == []
    assert head.ledger.get().to_dict()['result']['updated_memories'] == [live['id']]


def test_busy_delete_and_same_window_late_upload_leave_no_half_state(lane, monkeypatch):
    from routers import conversations as routes

    batch = lane.seed()
    blocked, live = overlap(lane, batch, tombstoned=False)
    before = blocked.get().to_dict()
    service = MagicMock()
    monkeypatch.setattr(routes, 'MemoryService', lambda **kwargs: service)
    monkeypatch.setattr(routes, 'retraction_can_be_skipped', lambda *args, **kwargs: False)

    app = FastAPI()
    app.include_router(routes.router)
    app.dependency_overrides[routes.auth.get_current_user_uid] = lambda: lane.uid
    acquire_destructive_operation(
        lane.uid, kind='explicit_memory_deletion', token='synthetic-peer', firestore_client=lane.client
    )
    try:
        response = TestClient(app).delete(f'/v1/conversations/{blocked.id}?cascade=true')
    finally:
        finish_destructive_operation(
            lane.uid,
            kind='explicit_memory_deletion',
            token='synthetic-peer',
            outcome='completed',
            firestore_client=lane.client,
        )
    assert response.status_code == 409 and response.headers['Retry-After'] == '2'
    assert not lane.user.collection('deleted_conversations').document(blocked.id).get().exists
    assert blocked.get().to_dict() == before
    service.retract_conversation_memories.assert_not_called()
    monkeypatch.setattr(lane.conversations, 'get_closest_conversation_to_timestamps', lambda *args: live)
    lane.finish(batch)
    assert lane.projector.project(batch.ids[0]) is not None
    assert batch.ledger.get().to_dict()['status'] == 'completed'


def test_deleted_source_settles_terminally_and_later_speech_advances(lane):
    head = lane.seed()
    later = lane.seed(('later',), capture_at=2000)
    lane.finish(head)
    lane.finish(later)
    lane.user.collection('deleted_conversations').document(head.items[0].conversation_id).set({'deleted': True})
    lane.projector.project_owner(lane.uid, limit=16, budget_seconds=60)
    result = head.ledger.get().to_dict()['result']
    assert result['reason_code'] == 'conversation_deleted'
    assert not result['new_memories'] and not result['updated_memories']
    assert later.ledger.get().to_dict()['status'] == 'completed'
    assert lane.projector.store.projection_watermark(owner_key(lane.uid)) == later.ids[-1]
    assert all(row['id'] != head.items[0].conversation_id for row in active_rows(lane))
    assert 'projection' not in (lane.projector.store.ref('jobs', head.ids[0]).get().to_dict().get('policy_parts') or {})
    assert lane.projector.project(head.ids[0]) == result


@pytest.mark.parametrize('fence', ['account', 'generation', 'protection', 'ledger', 'predecessor', 'missing_redirect'])
def test_privacy_settlement_cannot_skip_other_transactional_fences(lane, fence):
    head = lane.seed(('predecessor', 'head')) if fence == 'predecessor' else lane.seed()
    index = 1 if fence == 'predecessor' else 0
    for part in range(len(head.ids)):
        lane.finish(head, part)
    session = lane.projector.store.session(head.ids[index], head.binding, lane.clock())
    lane.user.collection('deleted_conversations').document(head.items[index].conversation_id).set({'deleted': True})
    if fence == 'account':
        lane.client.collection('account_deletions').document(lane.uid).set({'wipe_status': 'queued'})
    elif fence == 'generation':
        lane.client.collection('batch_pipeline_privacy').document(privacy_owner_key(lane.uid)).set({'generation': 1})
    elif fence == 'protection':
        lane.user.update({'data_protection_level': 'e2ee'})
    elif fence == 'ledger':
        head.ledger.update({'job_id': 'synthetic-other-job'})
    elif fence == 'missing_redirect':
        lane.user.collection('conversations').document('synthetic-broken-redirect').set(
            {'deleted': True, 'sync_merged_into': 'synthetic-missing-survivor'}
        )
        lane.projector.store.ref('jobs', head.ids[index]).update({'conversation_ids': ['synthetic-broken-redirect']})
    with pytest.raises((BatchPrivacyBlocked, ProjectionBlocked)):
        session.persist_empty(superseded=True, privacy_deleted=True)
    assert not lane.projector.store.ref('results', head.ids[index]).get().to_dict().get('projection')
    assert head.ledger.get().to_dict()['status'] == 'processing'
    assert not lane.tasks and not lane.published


def test_second_plan_refusal_settles_and_owner_sweep_continues(lane, monkeypatch):
    head = lane.seed()
    later = lane.seed(('later',), capture_at=2000)
    lane.finish(head)
    lane.finish(later)
    original = lane.conversations.assign_sync_conversation
    calls = []

    def refused(owner, incoming, **kwargs):
        if incoming['started_at'].timestamp() == 1000:
            calls.append(True)
            raise BatchPrivacyBlocked('conversation_deleted', conversation_id='synthetic-deleted-ancestor')
        return original(owner, incoming, **kwargs)

    monkeypatch.setattr(lane.conversations, 'assign_sync_conversation', refused)
    lane.projector.project_owner(lane.uid, limit=16, budget_seconds=60)
    assert len(calls) == 1
    assert head.ledger.get().to_dict()['result']['reason_code'] == 'conversation_deleted'
    assert later.ledger.get().to_dict()['status'] == 'completed'
