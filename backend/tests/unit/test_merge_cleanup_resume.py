"""Sealed manual merge cleanup retries do not rerun transcription or discard targets."""

from unittest.mock import Mock
import pytest
from utils.conversations import merge_conversations_job as coordinator
from utils.conversations import merge_conversations as merge
from database import conversations
from utils import notification_dispatch


@pytest.mark.parametrize('failed_source', ['a', 'b'])
def test_cleanup_failure_withholds_completion_and_retry_uses_same_survivor(monkeypatch, failed_source):
    job = {
        'uid': 'synthetic-owner',
        'job_id': 'job',
        'lease_epoch': 2,
        'merge_target_id': 'target',
        'conversation_ids': ['a', 'b'],
    }
    rows = {
        'target': {'id': 'target', 'status': 'completed'},
        **{cid: {'id': cid, 'merge_job_id': 'job', 'transcript_corrections_moved_to': 'target'} for cid in ['a', 'b']},
    }
    monkeypatch.setattr(coordinator, 'checkpoint', lambda *_args: None)
    monkeypatch.setattr(conversations, 'get_conversation', lambda _owner, cid: rows.get(cid))
    notify = Mock()
    process = Mock(side_effect=AssertionError('cleanup cannot reprocess'))
    monkeypatch.setattr(notification_dispatch, 'dispatch_merge_completed', notify)
    monkeypatch.setattr(merge, 'perform_merge_async', process)
    failed = False
    deleted = []

    def delete(owner, cid, target):
        nonlocal failed
        assert owner == 'synthetic-owner' and target == 'target'
        if cid == failed_source and not failed:
            failed = True
            raise RuntimeError('synthetic unavailable')
        del rows[cid]
        deleted.append(cid)

    monkeypatch.setattr(merge, 'delete_merged_source', delete)
    with pytest.raises(RuntimeError, match='synthetic unavailable'):
        coordinator.resume_source_cleanup(job)
    notify.assert_not_called()
    assert rows['target']['status'] == 'completed'
    assert coordinator.resume_source_cleanup(job)
    assert deleted == ['a', 'b']
    assert set(rows) == {'target'}
    process.assert_not_called()
    notify.assert_called_once_with('synthetic-owner', 'target', ['a', 'b'])


def test_cleanup_refuses_to_delete_a_rebound_source(monkeypatch):
    job = {
        'uid': 'owner',
        'job_id': 'job',
        'lease_epoch': 2,
        'merge_target_id': 'target',
        'conversation_ids': ['a', 'b'],
    }
    monkeypatch.setattr(coordinator, 'checkpoint', lambda *_args: None)
    monkeypatch.setattr(
        conversations,
        'get_conversation',
        lambda _owner, cid: {'id': 'target'} if cid == 'target' else {'merge_job_id': 'new-job'},
    )
    delete = Mock()
    monkeypatch.setattr(merge, 'delete_merged_source', delete)
    with pytest.raises(coordinator.MergeLeaseLost):
        coordinator.resume_source_cleanup(job)
    delete.assert_not_called()
