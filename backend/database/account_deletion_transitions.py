"""Transactional state transitions for durable account deletion markers."""

from datetime import datetime, timezone

from google.cloud.firestore_v1 import transactional

from database.account_deletion_policy import account_deletion_blocks_access, normalize_account_deletion_status


@transactional
def mark_wipe_completed(transaction, doc_ref) -> bool:
    snapshot = doc_ref.get(transaction=transaction)
    data = (snapshot.to_dict() or {}) if snapshot.exists else {}
    if data.get('late_agent_vm_cleanup'):
        transaction.set(
            doc_ref,
            {'wipe_status': 'failed', 'wipe_failed_at': datetime.now(timezone.utc)},
            merge=True,
        )
        return False
    transaction.set(
        doc_ref,
        {'wipe_status': 'completed', 'wipe_completed_at': datetime.now(timezone.utc)},
        merge=True,
    )
    return True


@transactional
def record_late_agent_vm_cleanup(transaction, doc_ref, vm_name: str, zone: str) -> bool:
    snapshot = doc_ref.get(transaction=transaction)
    raw_status = (snapshot.to_dict() or {}).get('wipe_status') if snapshot.exists else None
    status = normalize_account_deletion_status(marker_exists=snapshot.exists, raw_status=raw_status)
    if not account_deletion_blocks_access(status):
        return False
    transaction.set(
        doc_ref,
        {
            'late_agent_vm_cleanup': {'vmName': vm_name, 'zone': zone},
            'wipe_status': 'failed',
            'wipe_failed_at': datetime.now(timezone.utc),
        },
        merge=True,
    )
    return True
