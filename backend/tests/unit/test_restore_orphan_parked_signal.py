"""Restore orphans remain parked; seal telemetry never grants write authority."""

from copy import deepcopy
import logging

import pytest

from database.batch_pipeline_store import FirestoreStore
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from utils.batch_pipeline import live, record_seal_nojob as nojob, record_seal_repair as repair
from utils.batch_pipeline.metrics import RECORD_SEAL_ORPHAN_PARKED

UID, CID = 'private-owner-sentinel', 'private-conversation-sentinel'
JOB_ID = live.record_identity(UID, CID)[1]
ROW_PATH = ('users', UID, 'conversations', CID)
JOB_PATH = ('batch_pipeline_dev_jobs', JOB_ID)
PATH = '/'.join(ROW_PATH)
SERVER = {'K_SERVICE': 'test', 'BATCH_PIPELINE_PERCENT': '5', 'BATCH_LIVE_STT_RETIRE_PERCENT': '0'}
SITES = ('repair_plan', 'repair_apply', 'nojob_plan', 'nojob_apply')


@pytest.fixture
def source(monkeypatch):
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    client = StrictFirestore(
        {
            ROW_PATH: {
                'record_lane_owner': 'batch_live_v1',
                'status': 'completed',
                'private_cloud_sync_enabled': True,
                'discarded': True,
            },
            JOB_PATH: {
                'segment_id': JOB_ID,
                'owner_id': UID,
                'conversation_id': CID,
                'state': 'record_pending',
                'record_content_id': 'private-content-sentinel',
                'registration_origin': 'restore',
                'privacy_generation': 0,
            },
        }
    )
    return FirestoreStore('batch_pipeline_dev', firestore_client=client), client


def run_pass(source, site):
    store, client = source
    if site == 'repair_plan':
        plan = repair.plan_seals(store, [JOB_ID], None, None)
        # Applying a refused plan must not emit a second signal for that pass.
        assert repair.apply_seals(store, plan, plan['plan_sha256']) == {'privacy_refused': 1}
        assert plan['entries'][0]['disposition'] == 'privacy_refused'
    elif site == 'nojob_plan':
        plan = nojob.plan_backfill(store, [PATH], None, None, server_flags=SERVER)
        assert nojob.apply_backfill(store, plan, plan['plan_sha256']) == {'already_registered': 1}
        assert plan['entries'][0]['disposition'] == 'already_registered'
    elif site == 'repair_apply':
        # Exercise the defensive commit-time refusal with an exact matching
        # snapshot; this synthetic approval grants no write past the refusal.
        plan = {
            'namespace': store.namespace,
            'entries': [
                {
                    'job_id': JOB_ID,
                    'job': deepcopy(client.rows[JOB_PATH]),
                    'row': repair.seal_row_state(client.rows[ROW_PATH]),
                    'disposition': 'eligible',
                }
            ],
            'producer_proof': None,
            'producers_stopped': False,
        }
        plan['plan_sha256'] = repair.plan_digest(plan)
        assert repair.apply_seals(store, plan, plan['plan_sha256']) == {'privacy_refused': 1}
    else:
        # A job can appear between the no-job plan and apply. It must still
        # return already_registered, even when that job is a restore orphan.
        plan = {
            'operation': nojob.OPERATION,
            'namespace': store.namespace,
            'entries': [{'path': PATH, 'job': deepcopy(client.rows[JOB_PATH]), 'disposition': 'eligible'}],
            'producer_proof': None,
        }
        plan['plan_sha256'] = repair.plan_digest(plan)
        assert nojob.apply_backfill(store, plan, plan['plan_sha256']) == {'already_registered': 1}


def check_pass(source, site, caplog, expected):
    _, client = source
    before = deepcopy(client.rows)
    seal_path = site.split('_')[0]
    counter = RECORD_SEAL_ORPHAN_PARKED.labels(seal_path)
    count_before = counter._value.get()
    caplog.clear()
    with caplog.at_level(logging.INFO, logger=repair.__name__):
        run_pass(source, site)
    signals = [record.getMessage() for record in caplog.records if 'outcome=orphan_parked' in record.getMessage()]
    assert len(signals) == expected
    if expected:
        assert signals == [f'event=record_seal_refused outcome=orphan_parked seal_path={seal_path} count=1']
    assert all(value not in caplog.text for value in (UID, CID, JOB_ID, 'private-content-sentinel'))
    assert counter._value.get() - count_before == expected
    assert client.rows == before
    assert client.rows[JOB_PATH]['state'] == 'record_pending'
    assert all(not tx.updates and not tx.sets and not tx.deletes for tx in client.transactions)


@pytest.mark.parametrize('site', SITES)
def test_restore_discarded_emits_exactly_once_and_stays_parked(source, site, caplog):
    check_pass(source, site, caplog, 1)


@pytest.mark.parametrize('site', SITES)
@pytest.mark.parametrize('origin', (None, 'live'))
def test_non_restore_discarded_emits_nothing_and_stays_parked(source, site, origin, caplog):
    if origin is None:
        source[1].rows[JOB_PATH].pop('registration_origin')
    else:
        source[1].rows[JOB_PATH]['registration_origin'] = origin
    check_pass(source, site, caplog, 0)


@pytest.mark.parametrize('site', SITES)
def test_restore_not_discarded_emits_nothing(source, site, caplog):
    source[1].rows[ROW_PATH].update(discarded=False, private_cloud_sync_enabled=False)
    check_pass(source, site, caplog, 0)


@pytest.mark.parametrize('site', ('repair_apply', 'nojob_apply'))
def test_transaction_callback_repetition_does_not_duplicate_signal(source, site, caplog, monkeypatch):
    module = repair if site == 'repair_apply' else nojob
    original = module.run_transactional

    def repeated(client, callback, **kwargs):
        original(client, callback, **kwargs)
        return original(client, callback, **kwargs)

    monkeypatch.setattr(module, 'run_transactional', repeated)
    check_pass(source, site, caplog, 1)


def test_restore_origin_job_with_deleted_conversation_neither_raises_nor_signals(source, caplog):
    store, client = source
    client.rows.pop(ROW_PATH)
    caplog.clear()
    with caplog.at_level(logging.INFO, logger=repair.__name__):
        plan = nojob.plan_backfill(store, [PATH], None, None, server_flags=SERVER)
        assert nojob.apply_backfill(store, plan, plan['plan_sha256']) == {'already_registered': 1}
    assert plan['entries'][0]['disposition'] == 'already_registered'
    assert not [record for record in caplog.records if 'outcome=orphan_parked' in record.getMessage()]
    assert client.rows[JOB_PATH]['state'] == 'record_pending'


def test_repair_observer_tolerates_missing_conversation_row(caplog):
    job = {'registration_origin': 'restore', 'state': 'record_pending'}
    with caplog.at_level(logging.INFO, logger=repair.__name__):
        repair.observe_orphan_parked(job, None, 'privacy_refused', seal_path='repair')
    assert not [record for record in caplog.records if 'outcome=orphan_parked' in record.getMessage()]
