from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock

import pytest
from google.api_core.exceptions import Forbidden, NotFound

from database import stranded_artifact_receipts as repair
from scripts.sweep_stranded_artifact_receipts import sweep
from utils.batch_pipeline.retention import delete_batch_object

NOW = datetime(2026, 11, 19, tzinfo=timezone.utc)
CREATED = NOW - timedelta(days=1)


def receipt(**overrides):
    data = {
        'owner_id': 'test-owner',
        'owner_key': repair.privacy_owner_key('test-owner'),
        'conversation_ids': ['test-conversation'],
        'erasure_requested': True,
        'write_pending_until': CREATED + timedelta(minutes=30),
        'cleanup_after': CREATED + timedelta(minutes=30),
    }
    data.update(overrides)
    return SimpleNamespace(
        create_time=CREATED,
        update_time=CREATED + timedelta(minutes=15),
        to_dict=lambda: data,
        reference=Mock(),
        id='test-receipt',
    )


@pytest.mark.parametrize(
    'change',
    [
        {'erasure_requested': False},
        {'write_pending_until': None},
        {'write_pending_until': NOW + timedelta(days=1), 'cleanup_after': NOW + timedelta(days=1)},
        {'cleanup_after': None},
        {'expires_at': None},
        {'owner_key': 'other'},
        {'conversation_ids': []},
        {'conversation_ids': ['first', 'second']},
        {'conversation_ids': ['folder/id']},
        {'source_conversation_id': 'another'},
        {'uri': 'gs://foreign/object'},
    ],
)
def test_skips_invalid_signature(change):
    assert repair.signature(receipt(**change), NOW)[1] is None


@pytest.mark.parametrize('created', [repair.START - timedelta(seconds=1), repair.CUTOFF])
def test_creation_bounds(created):
    row = receipt()
    row.create_time = created
    assert repair.signature(row, NOW)[1] is None


@pytest.mark.parametrize('error', [None, NotFound('missing'), Forbidden('private')])
def test_exact_storage_generation(monkeypatch, error):
    monkeypatch.setenv('BUCKET_BATCH_PIPELINE', 'test')
    gcs = Mock()
    bare, versioned = Mock(generation=12), Mock()
    gcs.bucket.return_value.blob.side_effect = [bare, versioned]
    versioned.delete.side_effect = error
    uid = 'test-owner'
    name = f'batch-pipeline/batch_pipeline_prod/owners/{repair.privacy_owner_key(uid)}/audio/seg/key.enc'
    kwargs = dict(storage_client=gcs, timeout=5, resolve_generation=True)
    if isinstance(error, Forbidden):
        with pytest.raises(Forbidden):
            delete_batch_object(uid, f'gs://test/{name}', **kwargs)
    else:
        delete_batch_object(uid, f'gs://test/{name}', **kwargs)
    bare.reload.assert_called_once_with(timeout=5, retry=None)
    gcs.bucket.return_value.blob.assert_called_with(name, generation=12)
    versioned.delete.assert_called_once_with(if_generation_match=12, timeout=5, retry=None)


def test_conflict_aborts_before_storage(monkeypatch):
    row = receipt()
    db = MagicMock()
    row.reference.get.return_value = SimpleNamespace(update_time=NOW)
    delete = Mock()
    monkeypatch.setattr(repair, 'delete_batch_object', delete)
    assert not repair.erase(db, row, NOW, Mock())
    delete.assert_not_called()
    db._firestore_api.commit.assert_not_called()
    db._firestore_api.rollback.assert_called_once()


def test_dry_run_only_reports_counts(monkeypatch):
    db = MagicMock()
    query = db.collection.return_value.where.return_value.order_by.return_value
    query.limit.return_value.get.side_effect = [[receipt()], []]
    monkeypatch.setattr('scripts.sweep_stranded_artifact_receipts.proof', lambda *args: (True, NOW))
    monkeypatch.setattr('scripts.sweep_stranded_artifact_receipts.time.sleep', lambda _: None)
    writer = Mock(side_effect=AssertionError)
    monkeypatch.setattr('scripts.sweep_stranded_artifact_receipts.erase', writer)
    report = {'namespaces': {}, 'reads': 0, 'erasures': 0}
    args = SimpleNamespace(max_reads=100, max_erasures=50, rows_per_second=10, apply=False)
    assert sweep(db, None, args, {}, writer, report) == 'complete'
    assert report['namespaces']['batch_pipeline_prod']['matched'] == 1
    assert 'test-' not in str(report)
    writer.assert_not_called()


@pytest.mark.parametrize(
    'deleted_at, pending, expected',
    [
        (None, (False, False), False),
        (CREATED, (False, False), False),
        (CREATED + timedelta(minutes=20), (False, False), False),
        (CREATED + timedelta(minutes=30), (False, False), False),
        (CREATED + timedelta(minutes=5), (True, False), False),
        (CREATED + timedelta(minutes=5), (False, True), False),
        (CREATED + timedelta(minutes=5), (False, False), True),
    ],
)
def test_tombstone_and_both_obligations(monkeypatch, deleted_at, pending, expected):
    db = MagicMock()
    transaction = Mock()
    tombstone_ref = db.collection.return_value.document.return_value.collection.return_value.document.return_value
    tombstone_ref.get.return_value = SimpleNamespace(to_dict=lambda: {'deleted_at': deleted_at}, update_time=NOW)
    refs = [Mock(**{'get.return_value.exists': exists}) for exists in pending]
    monkeypatch.setattr(repair.jobs, 'job_ref', lambda *args: refs[0])
    monkeypatch.setattr(repair.jobs, 'erasure_job_ref', lambda *args: refs[1])
    assert repair.proof(db, receipt(), ('test-owner', 'test-conversation'), transaction=transaction) == (expected, NOW)
    for ref in refs:
        ref.get.assert_called_once_with(transaction=transaction, field_paths=[], **repair.RPC)


def test_storage_error_rolls_back_without_receipt_delete(monkeypatch):
    row = receipt(uri='gs://test/object')
    db = MagicMock()
    row.reference.get.return_value = row
    monkeypatch.setattr(repair, 'signature', lambda *args: ('eligible', ('test-owner', 'test-conversation')))
    monkeypatch.setattr(repair, 'proof', lambda *args, **kwargs: (True, NOW))
    monkeypatch.setattr(repair, 'delete_batch_object', Mock(side_effect=Forbidden('private')))
    with pytest.raises(Forbidden):
        repair.erase(db, row, NOW, Mock())
    db._firestore_api.commit.assert_not_called()
    db._firestore_api.rollback.assert_called_once()


def test_overlong_owner_id_is_ambiguous():
    assert repair.signature(receipt(owner_id='x' * 257), NOW) == ('ambiguous', None)


def test_storage_delete_precedes_receipt_commit(monkeypatch):
    row = receipt(uri='gs://test/object')
    db = MagicMock()
    row.reference.get.return_value = row
    row.reference._document_path = 'test/path'
    events = []
    monkeypatch.setattr(repair, 'signature', lambda *args: ('eligible', ('test-owner', 'test-conversation')))
    monkeypatch.setattr(repair, 'proof', lambda *args, **kwargs: (True, NOW))
    monkeypatch.setattr(repair, 'delete_batch_object', lambda *args, **kwargs: events.append('storage'))
    db._firestore_api.commit.side_effect = lambda **kwargs: events.append('receipt')
    assert repair.erase(db, row, NOW, Mock())
    assert events == ['storage', 'receipt']
    assert db._firestore_api.commit.call_args.kwargs['request']['writes'] == [{'delete': 'test/path'}]
    db._firestore_api.rollback.assert_not_called()


def test_apply_resumes_after_cap_and_obeys_read_limit(monkeypatch):
    db = MagicMock()
    collection = db.collection.return_value
    query = collection.where.return_value.order_by.return_value
    first, second = receipt(), receipt()
    first.id, second.id = 'first', 'second'
    query.limit.return_value.get.return_value = [first]
    query.start_after.return_value.limit.return_value.get.return_value = [second]
    monkeypatch.setattr('scripts.sweep_stranded_artifact_receipts.proof', lambda *args: (True, NOW))
    monkeypatch.setattr('scripts.sweep_stranded_artifact_receipts.time.sleep', lambda _: None)
    eraser = Mock(return_value=True)
    monkeypatch.setattr('scripts.sweep_stranded_artifact_receipts.erase', eraser)
    cursor = {}
    checkpoint = Mock()
    args = SimpleNamespace(max_reads=8, max_erasures=1, rows_per_second=10, apply=True)

    def run():
        report = {'namespaces': {}, 'reads': 0, 'erasures': 0}
        status = sweep(db, None, args, cursor, checkpoint, report)
        assert report['reads'] <= args.max_reads
        return status

    assert run() == 'erasure_limit'
    assert cursor['batch_pipeline_prod'] == first.id
    assert run() == 'erasure_limit'
    collection.document.assert_called_once_with(first.id)
    assert cursor['batch_pipeline_prod'] == second.id
    assert [call.args[1] for call in eraser.call_args_list] == [first, second]
    third = receipt()
    third.id = 'third'
    query.start_after.return_value.limit.return_value.get.return_value = [third]
    args.max_erasures = 2
    assert run() == 'read_limit'
    assert cursor['batch_pipeline_prod'] == third.id
    assert [call.args[1] for call in eraser.call_args_list] == [first, second, third]
