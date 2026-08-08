"""Account-deletion state transitions and deletion-scoped resource reads."""

from datetime import datetime, timezone
from typing import Any

from database._client import get_firestore_client
from google.cloud.firestore_v1 import transactional

from database.account_deletion_policy import account_deletion_blocks_access, normalize_account_deletion_status


def read_agent_vm_migration_journals(uid: str) -> list[dict[str, Any]]:
    """Read migration journals before deleting the user's Firestore subtree.

    The journal is the durable source of truth for provider resources created
    during an Agent VM migration.  Callers must validate each returned record
    against the provider before issuing destructive requests.
    """
    if not uid.strip():
        raise ValueError('uid is required')
    client = get_firestore_client()
    migration_ref = client.collection('users').document(uid).collection('agentVmMigrations')
    journals: list[dict[str, Any]] = []
    for snapshot in migration_ref.stream():
        data = snapshot.to_dict()
        if not isinstance(data, dict):
            raise RuntimeError('Agent VM migration journal is malformed')
        journal = dict(data)
        if journal.get('migrationId') not in (None, snapshot.id):
            raise RuntimeError('Agent VM migration journal identity is ambiguous')
        journal['migrationId'] = snapshot.id
        journals.append(journal)
    journals.sort(key=lambda journal: str(journal.get('migrationId') or ''))
    return journals


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
