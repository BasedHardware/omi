from unittest.mock import Mock

import pytest

from scripts import rearm_conversation_artifact_purges as repair


@pytest.mark.parametrize('apply', [False, True])
def test_rearm_requires_apply(monkeypatch, apply):
    candidate = ('owner', 'conversation', object())
    monkeypatch.setattr(repair, 'candidates', lambda *args: iter([candidate]))
    arm = Mock(return_value=True)
    monkeypatch.setattr(repair, 'rearm', arm)
    counts = {'rearmed': 0}
    repair.run(None, None, None, None, apply, 1, counts)
    assert counts['rearmed'] == int(apply)
    assert arm.call_count == int(apply)


def test_incomplete_scan_cannot_arm_partial_batch(monkeypatch):
    def incomplete(*args):
        yield 'owner', 'conversation', object()
        raise repair.Incomplete('request_budget_exhausted')

    arm = Mock()
    monkeypatch.setattr(repair, 'candidates', incomplete)
    monkeypatch.setattr(repair, 'rearm', arm)
    with pytest.raises(repair.Incomplete, match='request_budget_exhausted'):
        repair.run(None, None, None, None, True, 1, {})
    arm.assert_not_called()


def test_metadata_scan_finds_directly_attributed_receipt():
    from tests.unit.test_audit_conversation_purge_remainders import CID, END, START, UID, Query, Snapshot

    db = Mock()
    tombstone = Snapshot({})
    tombstone.update_time = object()
    db.collection_group.return_value = Query([tombstone])

    def collection(name):
        ref = Mock()
        rows = [Snapshot({'conversation_ids': [CID], 'uri': 'unused-in-metadata-scan'})]
        ref.where.return_value = Query(rows if name == 'batch_pipeline_prod_artifacts' else [])
        ref.document.return_value.get.return_value.exists = False
        ref.document.return_value.collection.return_value.where.return_value = Query([])
        return ref

    db.collection.side_effect = collection
    counts = dict(terminal_checked=0, candidates=0)
    assert list(repair.candidates(db, START, END, repair.Budget(100), counts)) == [(UID, CID, tombstone.update_time)]
    assert counts == {'terminal_checked': 1, 'candidates': 1}


@pytest.mark.parametrize('changed', ['none', 'tombstone', 'batch', 'cascade'])
def test_transaction_rechecks_tombstone_version_and_both_obligations(monkeypatch, changed):
    db, batch, cascade = Mock(), Mock(), Mock()
    tx = db.transaction.return_value
    tombstone = db.collection.return_value.document.return_value.collection.return_value.document.return_value
    version = object()
    tombstone.get.return_value.update_time = object() if changed == 'tombstone' else version
    batch.get.return_value.exists = changed == 'batch'
    cascade.get.return_value.exists = changed == 'cascade'
    monkeypatch.setattr(repair.firestore, 'transactional', lambda fn: fn)
    monkeypatch.setattr(repair.jobs, 'job_ref', lambda *args: batch)
    monkeypatch.setattr(repair.jobs, 'erasure_job_ref', lambda *args: cascade)

    assert repair.rearm(db, 'owner', 'conversation', version) == (changed == 'none')
    tombstone.get.assert_called_once_with(transaction=tx, timeout=10)
    if changed == 'none':
        batch.get.assert_called_once_with(transaction=tx, timeout=10)
        cascade.get.assert_called_once_with(transaction=tx, timeout=10)
        assert tx.create.call_args.args[0] is batch
        assert tx.create.call_args.args[1]['conversation_id'] == 'conversation'
    else:
        tx.create.assert_not_called()
