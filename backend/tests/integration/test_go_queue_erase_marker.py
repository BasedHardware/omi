"""Drive the Go erase receipt state through a loopback Firestore emulator."""

from datetime import datetime, timedelta, timezone
import os
from urllib.parse import urlsplit
from uuid import uuid4

from google.auth.credentials import AnonymousCredentials
from google.cloud import firestore
import pytest

from database import go_queue_erase as receipts
from database.legal_holds import acquire_destructive_operation, LegalHoldAuthorityUnavailable

pytestmark = pytest.mark.integration


def test_go_queue_erase_receipt_requires_held_due_generation(monkeypatch):
    host = os.getenv('FIRESTORE_EMULATOR_HOST', '')
    if urlsplit(f'//{host}').hostname not in {'localhost', '127.0.0.1', '::1'}:
        pytest.fail('requires loopback Firestore emulator')
    uid = uuid4().hex
    db = firestore.Client(project=f'demo-erase-{uid[:10]}', credentials=AnonymousCredentials())
    monkeypatch.setattr(receipts, 'account_deletion_firestore_client', lambda: db)
    ref = db.collection('account_deletions').document(uid)
    try:
        ref.set({'wipe_job_id': 'job', 'wipe_status': 'running', receipts.CLAIM: 'claim'})
        with pytest.raises(LegalHoldAuthorityUnavailable):
            receipts.record(uid, 'job', 'claim', 'arm')
        acquire_destructive_operation(
            uid, kind='account_deletion', token=f'account-deletion:{uid}', firestore_client=db
        )
        ref.update({'wipe_due_at': datetime.now(timezone.utc) + timedelta(days=1)})
        with pytest.raises(RuntimeError, match='due wipe generation'):
            receipts.record(uid, 'job', 'claim', 'arm')
        ref.update({'wipe_due_at': datetime.now(timezone.utc) - timedelta(days=1)})
        receipts.record(uid, 'job', 'claim', 'arm')
        with pytest.raises(RuntimeError, match='claim changed'):
            receipts.record(uid, 'job', 'old-claim', 'receipt', 'workerd')
        with pytest.raises(RuntimeError, match='receipt missing'):
            receipts.record(uid, 'job', 'claim', 'wipe')
        receipts.record(uid, 'job', 'claim', 'receipt', 'workerd')
        ref.update({receipts.CLAIM: 'new-claim', receipts.CLAIM_EXPIRES_AT: None})
        receipts.record(uid, 'job', 'new-claim', 'arm')
        receipts.record(uid, 'job', 'new-claim', 'wipe')
        marker = ref.get().to_dict()
        assert marker[receipts.ARMED_AT] <= marker[receipts.RECEIPT_AT] <= marker[receipts.WIPE_AT]
        assert marker[receipts.PATH] == 'workerd'
        assert receipts.readback(
            datetime.now(timezone.utc) + timedelta(minutes=16), db.collection('account_deletions')
        ) == {
            'met': 1,
            'eligible': 1,
            'overdue_pending': 0,
        }
    finally:
        db.close()
