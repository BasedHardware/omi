"""The actual lifecycle writer emits only after its transaction commits."""

from unittest.mock import Mock

import pytest
from google.api_core.exceptions import InvalidArgument
from database import conversations as db
from utils.conversations import summary_delivery as delivery
from tests.unit.test_conversation_persistence_transaction_expiry import _FakeFirestoreClient, EXPIRED_MESSAGE
from tests.unit.test_process_conversation_free_tier_branch import (
    pc,  # noqa: F401 - real process_conversation with isolated external dependencies
    _existing_desktop,
    _spy_managed_effects,
    _drive_reprocess,
)


@pytest.fixture
def writer(monkeypatch):
    monkeypatch.setenv('FIRST_SUMMARY_DEADLINE_ENABLED', 'true')
    monkeypatch.setenv('FIRST_SUMMARY_DEADLINE_PERCENT', '100')
    old = {
        'id': 'c',
        'status': 'completed',
        'data_protection_level': 'standard',
        'summary_first_pending_at': 100,
        'summary_due_at': 220,
        'summary_title_provenance': 'server_minimum',
        'sync_content_revision': 3,
    }
    client = _FakeFirestoreClient(old)
    monkeypatch.setattr(db, 'db', client)
    monkeypatch.setattr(db, 'invalidate_people_stats_cache', lambda _: None)
    monkeypatch.setattr(db, '_sync_conversation_search_index', lambda *_: None)
    monkeypatch.setattr(db, '_delete_conversation_search_index', lambda *_: None)
    return client


def payload(overview='Synthetic real summary'):
    return {
        'id': 'c',
        'status': 'completed',
        'sync_content_revision': 3,
        'data_protection_level': 'standard',
        'structured': {'title': 'Title', 'overview': overview},
    }


def test_terminal_receipt_after_fenced_commit_and_expired_transaction_retry(writer, monkeypatch):
    client = writer
    client.commit_errors = [InvalidArgument(EXPIRED_MESSAGE)]
    receipts = []

    def emit(receipt):
        assert len(client.commits) == 1
        assert client.commits[0]['summary_completed_at']
        receipts.append(receipt)

    monkeypatch.setattr(delivery, 'emit', emit)
    assert db.persist_processing_result_with_lifecycle('u', payload())
    assert len(client.transactions) == 2 and len(receipts) == 1
    assert receipts[0]['reason'] == 'summary' and receipts[0]['present']


@pytest.mark.parametrize('record_owner', ['batch_live_v1', 'batch_sync_v1'])
def test_summary_commit_preserves_record_lane_owner(writer, record_owner):
    writer.document['record_lane_owner'] = record_owner
    assert db.persist_processing_result_with_lifecycle('u', {**payload(), 'record_lane_owner': 'legacy_final_pass_v1'})
    assert writer.commits[0]['record_lane_owner'] == record_owner
    assert writer.commits[0]['summary_completed_at']


def test_record_owner_does_not_bypass_summary_processing_fence(writer):
    writer.document.update(record_lane_owner='batch_live_v1', summary_processing_owner='winner')
    token = delivery.PROCESS_CONTEXT.set({'owner': 'loser', 'claimed': True})
    try:
        assert not db.persist_processing_result_with_lifecycle('u', payload())
        assert all(value is None for value in writer.commits)
        assert writer.document['record_lane_owner'] == 'batch_live_v1'
    finally:
        delivery.PROCESS_CONTEXT.reset(token)


def test_empty_model_result_cannot_commit_or_emit(writer, monkeypatch):
    emit = Mock()
    monkeypatch.setattr(delivery, 'emit', emit)
    with pytest.raises(delivery.SummaryOutputUnavailable):
        db.persist_processing_result_with_lifecycle('u', payload(''))
    assert not writer.commits
    emit.assert_not_called()


def test_empty_model_result_without_open_obligation_commits(writer, monkeypatch):
    emit = Mock()
    monkeypatch.setattr(delivery, 'emit', emit)
    for marker in ('summary_title_provenance', 'summary_first_pending_at', 'summary_due_at'):
        writer.document.pop(marker, None)
    assert db.persist_processing_result_with_lifecycle('u', payload(''))
    emit.assert_called_once_with(None)


def test_empty_model_result_after_exhausted_empty_budget_commits(writer, monkeypatch):
    emit = Mock()
    monkeypatch.setattr(delivery, 'emit', emit)
    writer.document['summary_blocked_reason'] = 'empty_output_exhausted'
    writer.document['summary_due_at'] = None
    assert db.persist_processing_result_with_lifecycle('u', payload(''))
    emit.assert_called_once_with(None)


def test_stale_generation_and_failed_commit_emit_nothing(writer, monkeypatch):
    emit = Mock()
    monkeypatch.setattr(delivery, 'emit', emit)
    assert not db.persist_processing_result_with_lifecycle('u', {**payload(), 'sync_content_revision': 2})
    emit.assert_not_called()
    writer.commit_errors = [RuntimeError('synthetic commit failure')]
    with pytest.raises(RuntimeError):
        db.persist_processing_result_with_lifecycle('u', payload())
    emit.assert_not_called()


@pytest.mark.parametrize('record_owner', ['batch_live_v1', 'batch_sync_v1'])
def test_manual_edit_after_repair_admission_fences_write(writer, monkeypatch, record_owner):
    writer.document.update(user_title='Manually authored title', record_lane_owner=record_owner)
    token = delivery.REPAIR_CONTEXT.set({'summary_expected_revision': 3})
    try:
        assert not db.persist_processing_result_with_lifecycle('u', payload())
        assert all(value is None for value in writer.commits)
    finally:
        delivery.REPAIR_CONTEXT.reset(token)


def test_same_owners_lease_expires_during_long_process_conversation_but_summary_commits(writer, pc, monkeypatch):
    from models.structured import Structured

    # This lease test exercises funded processing, independently of cap admission.
    monkeypatch.setattr(pc.funded_processing, 'enabled', lambda uid, lane=None: False)
    _spy_managed_effects(monkeypatch, pc)
    conversation = _existing_desktop('c')
    conversation.sync_content_revision = 3
    clock = [100.0]
    monkeypatch.setattr(delivery, 'time', type('Clock', (), {'time': staticmethod(lambda: clock[0])}))
    writer.document.update(summary_processing_owner='same-owner', summary_processing_lease_until=220)
    context = {'owner': 'same-owner', 'claimed': True, 'lease_until': 220}

    def slow_notes(*_args, **_kwargs):
        clock[0] = 221  # Simulated model latency exceeds the original lease.
        assert writer.document['summary_processing_lease_until'] < clock[0]
        return Structured(title='Synthetic title', overview='Synthetic long-request summary'), False

    monkeypatch.setattr(pc, '_get_structured', slow_notes)
    monkeypatch.setattr(
        pc.lifecycle_service, 'persist_processed_conversation', db.persist_processing_result_with_lifecycle
    )
    token = delivery.PROCESS_CONTEXT.set(context)
    try:
        result = _drive_reprocess(pc, conversation, uid='u')
    finally:
        delivery.PROCESS_CONTEXT.reset(token)
    assert result.structured.overview == 'Synthetic long-request summary'
    assert len(writer.commits) == 1
    assert writer.commits[0]['structured']['overview'] == result.structured.overview
    assert writer.commits[0]['summary_completed_at'] == 221
