"""Incident regression: normal callbacks retain debt without poisoning dispatch."""

from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock

from google.api_core.exceptions import PermissionDenied
import pytest

from tests.unit.test_sync_reprocess_coalesce import state, pipeline, sweep_query  # noqa: F401
from utils.sync import reprocess


@pytest.fixture
def admitted(state, monkeypatch):
    monkeypatch.setenv('FIRST_SUMMARY_DEADLINE_ENABLED', 'true')
    monkeypatch.setenv('FIRST_SUMMARY_DEADLINE_PERCENT', '100')
    monkeypatch.setenv('FIRST_SUMMARY_PRESERVE_ADMITTED_ENABLED', 'true')
    monkeypatch.setenv('DEMAND_PROCESSING_ENABLED', 'false')
    reprocess.mark('u', 'c', 'en', now=0)
    monkeypatch.setenv('FIRST_SUMMARY_DEADLINE_PERCENT', '0')
    return state


def callback(pipeline, monkeypatch, data):
    monkeypatch.setattr(pipeline.conversations_db, 'get_conversation', lambda *_: deepcopy(data))
    monkeypatch.setattr(pipeline, 'repair_fenced', lambda *_: False)
    return pipeline._reprocess_conversation_after_update


def test_real_deleted_callback_is_terminal_after_percent_rollback(admitted, pipeline, monkeypatch):
    rows, tasks = admitted
    process = callback(pipeline, monkeypatch, {'deleted': True})
    assert reprocess.run(reprocess.key('u', 'c'), tasks[0]['task_token'], process, now=120) == 'processed'
    assert not rows  # No callback-pending exception, empty failure or model work.


def test_open_live_callback_durably_defers_before_ack_and_then_completes(admitted, pipeline, monkeypatch):
    rows, tasks = admitted
    key = reprocess.key('u', 'c')
    process = callback(pipeline, monkeypatch, {'sync_live_target': True, 'status': 'in_progress'})
    token = tasks[0]['task_token']
    assert reprocess.run(key, token, process, now=120) == 'deferred'
    assert rows[key]['deferred_reason'] == 'open_live_target'
    assert rows[key]['summary_deadline_at'] == 120 and rows[key]['first_pending_at'] == 0
    assert rows[key]['due_at'] == 240 and rows[key]['lease_until'] == 0
    assert not rows[key].get('summary_seen') and not rows[key].get('dormant')
    assert tasks[-1] == rows[key] and tasks[-1]['task_token'] != token
    assert reprocess.run(key, token, Mock(), now=121) == 'stale'
    output = SimpleNamespace(structured={'overview': 'Synthetic committed summary'})
    assert reprocess.run(key, tasks[-1]['task_token'], lambda *_: output, now=240) == 'processed'
    assert rows[key]['summary_seen']


def test_lost_deferred_enqueue_ack_keeps_custody_for_watchdog(admitted, pipeline, monkeypatch, sweep_query):
    rows, tasks = admitted
    key = reprocess.key('u', 'c')
    process = callback(pipeline, monkeypatch, {'sync_live_target': True, 'status': 'in_progress'})
    enqueue = Mock(side_effect=RuntimeError('synthetic lost ACK'))
    monkeypatch.setattr(reprocess, '_enqueue', enqueue)
    with pytest.raises(RuntimeError):
        reprocess.run(key, tasks[0]['task_token'], process, now=120)
    persisted = deepcopy(rows[key])
    assert persisted['deferred_reason'] == 'open_live_target'
    assert persisted['summary_deadline_at'] == 120
    # Lost ACK with a live task must not replace its valid wake.
    monkeypatch.setattr(reprocess, '_wake_exists', lambda *_: True)
    assert reprocess.sweep(now=240) == {'repaired': 0, 'error': 0}
    assert rows[key]['task_token'] == persisted['task_token']


def test_unknown_no_output_still_retries_instead_of_forging_completion(admitted):
    rows, tasks = admitted
    with pytest.raises(reprocess.FirstSummaryCallbackPending):
        reprocess.run(reprocess.key('u', 'c'), tasks[0]['task_token'], lambda *_: None, now=120)
    assert rows[reprocess.key('u', 'c')]['summary_deadline_at'] == 120


def test_canonical_callback_still_requires_snapshot_receipt_fence(admitted, pipeline, monkeypatch):
    rows, tasks = admitted
    process = callback(pipeline, monkeypatch, {'status': 'completed', 'transcript_segments': []})
    claim = Mock(return_value=False)
    provider = Mock(side_effect=AssertionError('fenced processing must not start'))
    monkeypatch.setattr(pipeline, 'claim_from_snapshot', claim)
    monkeypatch.setattr(pipeline, 'get_firestore_client', lambda: None)
    monkeypatch.setattr(pipeline, 'process_conversation', provider)
    with pytest.raises(pipeline.SyncConversationPersistenceFenced):
        reprocess.run(reprocess.key('u', 'c'), tasks[0]['task_token'], process, now=120)
    claim.assert_called_once()
    provider.assert_not_called()
    assert rows[reprocess.key('u', 'c')]['summary_deadline_at'] == 120


def test_deleted_merge_donor_signals_canonical_custody_not_processing(admitted, pipeline, monkeypatch):
    process = callback(pipeline, monkeypatch, {'deleted': True, 'sync_merged_into': 'survivor'})
    resolve = Mock(return_value='survivor')
    monkeypatch.setattr(pipeline.conversations_db, 'resolve_sync_conversation_redirect', resolve)
    context = {}
    token = pipeline.PROCESS_CONTEXT.set(context)
    try:
        assert process('u', 'c', 'en') is None
    finally:
        pipeline.PROCESS_CONTEXT.reset(token)
    assert context == {'redirect_to': 'survivor'}
    resolve.assert_called_once_with('u', 'c')


def test_invalid_redirect_retains_deferred_debt_without_processing(admitted, pipeline, monkeypatch):
    rows, tasks = admitted
    process = callback(pipeline, monkeypatch, {'deleted': True, 'sync_merged_into': 'unresolved'})
    monkeypatch.setattr(pipeline.conversations_db, 'resolve_sync_conversation_redirect', lambda *_: None)
    assert reprocess.run(reprocess.key('u', 'c'), tasks[0]['task_token'], process, now=120) == 'deferred'
    assert rows[reprocess.key('u', 'c')]['deferred_reason'] == 'redirect_unresolved'


def test_watchdog_replaces_only_absent_exhausted_wake(admitted, sweep_query, monkeypatch):
    rows, tasks = admitted
    key, original = reprocess.key('u', 'c'), tasks[0]['task_token']
    exists = Mock(return_value=True)
    monkeypatch.setattr(reprocess, '_wake_exists', exists)
    for now in (240, 360, 480, 600):
        assert reprocess.sweep(now=now) == {'repaired': 0, 'error': 0}
    assert len(tasks) == 1 and rows[key]['task_token'] == original
    exists.return_value = False
    assert reprocess.sweep(now=900) == {'repaired': 1, 'error': 0}
    assert rows[key]['task_token'] != original and len(tasks) == 2
    assert rows[key]['summary_deadline_at'] == 120
    assert reprocess.run(key, original, Mock(), now=901) == 'stale'


def test_probe_permission_failure_retains_original_wake_and_debt(admitted, sweep_query, monkeypatch):
    rows, tasks = admitted
    original = tasks[0]['task_token']
    monkeypatch.setattr(reprocess, '_wake_exists', Mock(side_effect=PermissionDenied('synthetic')))
    assert reprocess.sweep(now=240) == {'repaired': 0, 'error': 1}
    assert rows[reprocess.key('u', 'c')]['task_token'] == original and len(tasks) == 1


def test_probe_racing_active_lease_cannot_rotate_its_token(admitted, sweep_query, monkeypatch):
    rows, tasks = admitted
    key, original = reprocess.key('u', 'c'), tasks[0]['task_token']

    def exhausted(*_):
        rows[key].update(owner='winner', lease_until=1000)
        return False

    monkeypatch.setattr(reprocess, '_wake_exists', exhausted)
    assert reprocess.sweep(now=240) == {'repaired': 0, 'error': 0}
    assert rows[key]['task_token'] == original and len(tasks) == 1
