"""Transactional state transitions for durable account deletion markers (neutral store port).

Called inside ``get_document_store().run_transaction(...)`` — each helper takes the port's transaction
handle ``tx`` and the document ``path`` instead of a raw Firestore ``(transaction, doc_ref)``. The
state-machine logic is unchanged; only the storage seam is neutral so it runs on Firestore or Mongo.
"""

from datetime import datetime, timezone

from database.account_deletion_policy import account_deletion_blocks_access, normalize_account_deletion_status


def mark_wipe_completed(tx, path) -> bool:
    snapshot = tx.get(path)
    data = (snapshot.to_dict() or {}) if snapshot.exists else {}
    if data.get('late_agent_vm_cleanup'):
        tx.set(
            path,
            {'wipe_status': 'failed', 'wipe_failed_at': datetime.now(timezone.utc)},
            merge=True,
        )
        return False
    tx.set(
        path,
        {'wipe_status': 'completed', 'wipe_completed_at': datetime.now(timezone.utc)},
        merge=True,
    )
    return True


def record_late_agent_vm_cleanup(tx, path, vm_name: str, zone: str) -> bool:
    snapshot = tx.get(path)
    raw_status = (snapshot.to_dict() or {}).get('wipe_status') if snapshot.exists else None
    status = normalize_account_deletion_status(marker_exists=snapshot.exists, raw_status=raw_status)
    if not account_deletion_blocks_access(status):
        return False
    tx.set(
        path,
        {
            'late_agent_vm_cleanup': {'vmName': vm_name, 'zone': zone},
            'wipe_status': 'failed',
            'wipe_failed_at': datetime.now(timezone.utc),
        },
        merge=True,
    )
    return True
