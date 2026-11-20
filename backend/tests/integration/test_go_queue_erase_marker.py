"""Drive the Go erase receipt state through a loopback Firestore emulator."""

from datetime import datetime, timedelta, timezone
import os
from urllib.parse import urlsplit
from uuid import uuid4

from google.auth.credentials import AnonymousCredentials
from google.cloud import firestore
import pytest

from database import go_queue_erase as receipts
from database import users as users_db
from database.legal_holds import acquire_destructive_operation, LegalHoldAuthorityUnavailable

pytestmark = pytest.mark.integration


@pytest.mark.parametrize('path', ['workerd', 'postgres'])
def test_go_queue_erase_receipt_requires_held_due_generation(monkeypatch, path):
    host = os.getenv('FIRESTORE_EMULATOR_HOST', '')
    if urlsplit(f'//{host}').hostname not in {'localhost', '127.0.0.1', '::1'}:
        pytest.fail('requires loopback Firestore emulator')
    uid = uuid4().hex
    db = firestore.Client(project=f'demo-erase-{uid[:10]}', credentials=AnonymousCredentials())
    monkeypatch.setattr(receipts, 'account_deletion_firestore_client', lambda: db)
    ref = db.collection('account_deletions').document(uid)

    def arm(claim: str, duration: timedelta = receipts.ERASE_GRANT_DURATION):
        return receipts.record(uid, 'job', claim, 'arm', expires=datetime.now(timezone.utc) + duration)

    try:
        ref.set({'wipe_job_id': 'job', 'wipe_status': 'running', receipts.CLAIM: 'claim'})
        with pytest.raises(LegalHoldAuthorityUnavailable):
            arm('claim')
        acquire_destructive_operation(
            uid, kind='account_deletion', token=f'account-deletion:{uid}', firestore_client=db
        )
        ref.update({'wipe_due_at': datetime.now(timezone.utc) + timedelta(days=1)})
        with pytest.raises(RuntimeError, match='due wipe generation'):
            arm('claim')
        ref.update({'wipe_due_at': firestore.DELETE_FIELD})
        with pytest.raises(RuntimeError, match='expired before arming'):
            arm('claim', -timedelta(seconds=1))
        arm('claim')
        with pytest.raises(RuntimeError, match='claim changed'):
            receipts.record(uid, 'job', 'old-claim', 'receipt', 'workerd')
        with pytest.raises(RuntimeError, match='receipt missing'):
            receipts.record(uid, 'job', 'claim', 'wipe')
        if path == 'postgres':
            with pytest.raises(RuntimeError, match='missing verified queue identity'):
                receipts.record(uid, 'job', 'claim', 'receipt', path)
            assert ref.get().to_dict().get(receipts.RECEIPT_AT) is None
            receipts.record(uid, 'job', 'claim', 'receipt', path, queue_id='a' * 64)
        else:
            receipts.record(uid, 'job', 'claim', 'receipt', path)
        ref.update({receipts.CLAIM: 'new-claim', receipts.CLAIM_EXPIRES_AT: None})
        arm('new-claim')
        receipts.record(uid, 'job', 'new-claim', 'wipe')
        marker = ref.get().to_dict()
        assert marker['wipe_due_at'] == marker[receipts.ARMED_AT]
        assert marker[receipts.ARMED_AT] <= marker[receipts.RECEIPT_AT] <= marker[receipts.WIPE_AT]
        assert marker[receipts.PATH] == path
        assert marker.get(receipts.RECOVERY_QUEUE_ID) == ('a' * 64 if path == 'postgres' else None)
        assert receipts.readback(
            datetime.now(timezone.utc) + timedelta(minutes=16), db.collection('account_deletions')
        ) == {
            'met': 1,
            'eligible': 1,
            'overdue_pending': 0,
        }
    finally:
        db.close()


def test_enabled_billing_retry_preserves_known_wipe_order():
    host = os.getenv('FIRESTORE_EMULATOR_HOST', '')
    if urlsplit(f'//{host}').hostname not in {'localhost', '127.0.0.1', '::1'}:
        pytest.fail('requires loopback Firestore emulator')
    uid = uuid4().hex
    db = firestore.Client(project=f'demo-erase-{uid[:10]}', credentials=AnonymousCredentials())
    try:
        ref = db.collection('account_deletions').document(uid)
        ref.set({'wipe_job_id': 'job', 'wipe_status': 'retrying'})
        assert not receipts.mark_wipe_running(db.transaction(), ref, 'job', 'first', 'first-attempt')
        users_db._heartbeat_user_deletion_wipe_txn(db.transaction(), ref, True)
        ref.update({'wipe_status': 'retrying'})
        assert not receipts.mark_wipe_running(db.transaction(), ref, 'job', 'second', 'second-attempt')
        assert receipts.ORDER_UNKNOWN not in ref.get().to_dict()

        users_db._heartbeat_user_deletion_wipe_txn(db.transaction(), ref)
        ref.update({'wipe_status': 'retrying'})
        assert not receipts.mark_wipe_running(db.transaction(), ref, 'job', 'legacy', 'legacy-attempt')
        assert ref.get().to_dict()[receipts.ORDER_UNKNOWN] is True
    finally:
        db.close()


def test_restored_grace_deadline_does_not_delay_a_replacement_immediate_wipe(monkeypatch):
    host = os.getenv('FIRESTORE_EMULATOR_HOST', '')
    if urlsplit(f'//{host}').hostname not in {'localhost', '127.0.0.1', '::1'}:
        pytest.fail('requires loopback Firestore emulator')
    uid = uuid4().hex
    db = firestore.Client(project=f'demo-erase-{uid[:10]}', credentials=AnonymousCredentials())
    monkeypatch.setattr(receipts, 'account_deletion_firestore_client', lambda: db)
    ref = db.collection('account_deletions').document(uid)
    try:
        now = datetime.now(timezone.utc)
        ref.set(
            {
                'wipe_job_id': 'old-grace',
                'wipe_status': 'cancelled',
                'wipe_due_at': now + timedelta(days=1),
                'wipe_restored_at': now - timedelta(minutes=1),
                'grace_actions_completed_at': now - timedelta(minutes=2),
            }
        )
        users_db._mark_user_deletion_wipe_intent_txn(db.transaction(), ref, 'immediate')
        ref.update({'wipe_status': 'retrying'})
        receipts.mark_wipe_running(db.transaction(), ref, 'immediate', 'claim', 'attempt')
        acquire_destructive_operation(
            uid, kind='account_deletion', token=f'account-deletion:{uid}', firestore_client=db
        )
        expires = datetime.now(timezone.utc) + receipts.ERASE_GRANT_DURATION
        receipts.record(uid, 'immediate', 'claim', 'arm', expires=expires)
        marker = ref.get().to_dict()
        assert marker['wipe_due_at'] == marker[receipts.ARMED_AT]
        assert marker['wipe_due_at'] < now + timedelta(minutes=1)
    finally:
        db.close()
