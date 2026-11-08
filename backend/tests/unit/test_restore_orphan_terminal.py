"""Register-first orphans settle through seal callers without publishing content."""

from copy import deepcopy
from unittest.mock import Mock

import pytest

from database import batch_pipeline_recovery as recovery
from database import conversations as conversations_db
from database.batch_pipeline_store import FirestoreStore, is_queue_dispositioned
from tests.unit.test_restore_recording_obligation import restore_store, UID, CID, ROW_PATH, JOB_PATH, SEGMENT
from utils.batch_pipeline import live, record_seal_nojob as nojob, record_seal_repair as repair
from utils.conversations import lifecycle

SERVER = {'K_SERVICE': 'synthetic', 'BATCH_PIPELINE_PERCENT': '5', 'BATCH_LIVE_STT_RETIRE_PERCENT': '0'}


def make_plan(caller, client):
    store = FirestoreStore('batch_pipeline_dev', firestore_client=client)
    if caller == 'repair':
        plan = repair.plan_seals(store, [SEGMENT], object(), object(), repair_closed=True)
    else:
        plan = nojob.plan_backfill(store, ['/'.join(ROW_PATH)], object(), object(), server_flags=SERVER)
    return store, plan


def apply(caller, store, plan):
    function = repair.apply_seals if caller == 'repair' else nojob.apply_backfill
    return function(store, plan, plan['plan_sha256'])


@pytest.fixture
def no_content_work(monkeypatch):
    forbidden = Mock(side_effect=AssertionError('orphan must not read/transcribe audio or publish content'))
    monkeypatch.setattr(repair, 'retained_tail_proof', forbidden)
    monkeypatch.setattr(nojob, 'retained_tail_proof', forbidden)
    monkeypatch.setattr(live, 'admit_record_units', forbidden)
    monkeypatch.setattr(conversations_db, '_sync_conversation_search_index', forbidden)
    monkeypatch.setattr(conversations_db, 'invalidate_people_stats_cache', forbidden)
    return forbidden


@pytest.mark.parametrize('caller', ['repair', 'nojob'])
def test_failed_restore_metadata_orphan_terminalizes_once_through_each_caller(
    restore_store, monkeypatch, no_content_work, caplog, caller
):
    client = restore_store
    client.rows[ROW_PATH]['audio_files'] = ['retained-synthetic-audio']
    metadata = Mock(side_effect=RuntimeError('synthetic metadata failure'))
    monkeypatch.setattr(conversations_db, 'restore_conversation_from_discarded', metadata)
    with pytest.raises(lifecycle.RestoredRecordingRegistrationUnavailable, match='retry restore'):
        lifecycle.restore_discarded(UID, CID)
    assert client.rows[JOB_PATH]['registration_origin'] == 'restore'
    assert client.rows[JOB_PATH]['state'] == 'record_pending'
    retained = deepcopy(client.rows)
    first_apply = len(client.transactions)
    with caplog.at_level('INFO', logger=recovery.logger.name):
        store, plan = make_plan(caller, client)
        assert plan['entries'][0]['disposition'] == 'privacy_refused'
        assert client.rows == retained  # Planning grants no write authority.
        assert apply(caller, store, plan) == {'discarded': 1}
        settled = deepcopy(client.rows)
        assert apply(caller, store, plan) == {'discarded': 1}
        assert recovery.terminalize_discarded_restore(client, store.namespace, SEGMENT, 999) == 'discarded'
        assert client.rows == settled
        # A fresh second pass is also a no-op, regardless of its refusal label.
        next_store, next_plan = make_plan(caller, client)
        apply(caller, next_store, next_plan)
        assert client.rows == settled
    job = client.rows[JOB_PATH]
    assert job['state'] == 'privacy_blocked'
    assert job['disposition'] == 'discarded'
    assert is_queue_dispositioned(job)
    assert job['record_content_id'] == retained[JOB_PATH]['record_content_id']
    assert sum(path[0] == 'batch_pipeline_dev_jobs' for path in client.rows) == 1
    assert {path: row for path, row in client.rows.items() if path != JOB_PATH} == {
        path: row for path, row in retained.items() if path != JOB_PATH
    }
    transactions = client.transactions[first_apply:]
    updates = [update for tx in transactions for update in tx.updates]
    assert len(updates) == 1 and updates[0][0] == JOB_PATH
    assert all(not tx.sets and not tx.creates and not tx.deletes for tx in transactions)
    assert sum('event=restore_recording_terminal outcome=discarded' in r.message for r in caplog.records) == 1
    metadata.assert_called_once_with(UID, CID)
    no_content_work.assert_not_called()


@pytest.mark.parametrize('caller', ['repair', 'nojob'])
def test_non_restore_origin_discarded_job_remains_parked(restore_store, no_content_work, caller):
    client = restore_store
    client.rows[ROW_PATH]['discarded'] = False
    store = FirestoreStore('batch_pipeline_dev', firestore_client=client)
    assert live.register_recording(UID, client.rows[ROW_PATH], store=store)
    assert 'registration_origin' not in client.rows[JOB_PATH]
    client.rows[ROW_PATH]['discarded'] = True
    before = deepcopy(client.rows)
    store, plan = make_plan(caller, client)
    expected = 'privacy_refused' if caller == 'repair' else 'already_registered'
    assert apply(caller, store, plan) == {expected: 1}
    assert client.rows == before
    assert client.rows[JOB_PATH]['state'] == 'record_pending'
    no_content_work.assert_not_called()


@pytest.mark.parametrize('caller', ['repair', 'nojob'])
def test_restore_origin_currently_visible_is_not_terminated_from_stale_discard_plan(
    restore_store, no_content_work, caller
):
    client = restore_store
    store = FirestoreStore('batch_pipeline_dev', firestore_client=client)
    assert live.register_recording(UID, client.rows[ROW_PATH], store=store, restoring=True)
    store, plan = make_plan(caller, client)
    assert plan['entries'][0]['disposition'] == 'privacy_refused'
    client.rows[ROW_PATH]['discarded'] = False
    before = deepcopy(client.rows)
    assert apply(caller, store, plan) == {'privacy_refused': 1}
    assert client.rows == before
    no_content_work.assert_not_called()


@pytest.mark.parametrize('caller', ['repair', 'nojob'])
@pytest.mark.parametrize('reason', [{'private_cloud_sync_enabled': False}, {'deleted': True}])
def test_non_discard_privacy_refusal_does_not_terminalize_restore_origin(
    restore_store, no_content_work, caller, reason
):
    client = restore_store
    store = FirestoreStore('batch_pipeline_dev', firestore_client=client)
    assert live.register_recording(UID, client.rows[ROW_PATH], store=store, restoring=True)
    client.rows[ROW_PATH].update(discarded=False, **reason)
    before = deepcopy(client.rows)
    store, plan = make_plan(caller, client)
    assert plan['entries'][0]['disposition'] == 'privacy_refused'
    assert apply(caller, store, plan) == {'privacy_refused': 1}
    assert client.rows == before
    no_content_work.assert_not_called()


@pytest.mark.parametrize('state', ['ready', 'leased', 'committed', 'privacy_blocked'])
def test_terminal_helper_will_not_advance_a_nonpending_job(restore_store, state):
    client = restore_store
    store = FirestoreStore('batch_pipeline_dev', firestore_client=client)
    assert live.register_recording(UID, client.rows[ROW_PATH], store=store, restoring=True)
    client.rows[JOB_PATH]['state'] = state
    before = deepcopy(client.rows)
    assert recovery.terminalize_discarded_restore(client, store.namespace, SEGMENT, 999) is None
    assert client.rows == before


def test_terminal_helper_never_recreates_a_missing_job(restore_store):
    before = deepcopy(restore_store.rows)
    assert recovery.terminalize_discarded_restore(restore_store, 'batch_pipeline_dev', SEGMENT, 999) is None
    assert restore_store.rows == before
