"""Historical tier (T1+): the batch acknowledgement keeps the projection store's custody.

A settled historical output is acknowledged inside ``mark_enrichment``'s transaction,
so the privacy guard still runs over every output and a record-notes job still gets
its recording-wide dispatch. Only the ordinary first-summary enqueue is skipped.
"""

from unittest.mock import Mock

import pytest

from config.policy import ProjectionPolicy
from database.batch_pipeline_projection import ProjectionStore
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from tests.unit.test_record_complete_notes import NOW, POLICY, recording  # noqa: F401  (fixture)
from utils.batch_pipeline.contracts import ProjectionBinding
from utils.sync import reprocess


def test_a_settled_historical_output_is_acknowledged_after_the_privacy_guard(monkeypatch):
    binding = ProjectionBinding('synthetic-owner', 'job', 'content', ('segment',))
    client = StrictFirestore()
    store = ProjectionStore(Mock(client=client))
    receipt_ref = client.collection('receipts').document('segment')
    receipt_ref.create({'state': 'persisted'})
    session = Mock()
    session.job = {'priority': 1}
    session.ledger = {}
    session.prepare.side_effect = lambda transaction, **_: receipt_ref.get(transaction=transaction)
    session.guard.side_effect = lambda transaction, _: receipt_ref.get(transaction=transaction)
    session.receipt.return_value = {'state': 'persisted', 'historical': True}
    session.write_receipt.side_effect = lambda transaction, receipt: transaction.set(receipt_ref, receipt)
    monkeypatch.setattr(store, 'session', lambda *a, **k: session)
    monkeypatch.setattr(store, 'run', lambda operation, **kwargs: operation(client.transaction()))
    monkeypatch.setattr(reprocess, 'owns_runtime', lambda: True)
    monkeypatch.setattr(reprocess, '_enqueue', Mock(side_effect=AssertionError('no first-summary wake')))
    store.mark_enrichment('segment', binding, 0, 'c', 'en', policy=ProjectionPolicy(), historical_settled=True)
    transaction = client.transactions[0]
    session.guard.assert_called_once_with(transaction, ['c'])
    assert [path for path, _ in transaction.sets] == [('receipts', 'segment')]
    assert receipt_ref.get().to_dict()['state'] == 'ready'
    assert not client.collection(reprocess.COLLECTION).document(reprocess.key('synthetic-owner', 'c')).get().exists


@pytest.mark.parametrize('recording', [1], indirect=True)
def test_a_record_notes_job_keeps_its_recording_wide_dispatch(recording):
    f = recording
    f.store.mark_enrichment('first', f.binding, NOW, 'capture', 'en', policy=POLICY, historical_settled=True)
    row = f.client.collection(reprocess.COLLECTION).document(reprocess.key(f.binding.owner_id, 'capture'))
    assert row.get().exists and row.get().to_dict()['version'] == 1
