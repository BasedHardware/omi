"""Transactional state transitions for durable account deletion markers (neutral store port).

Called inside ``get_document_store().run_transaction(...)`` — each helper takes the port's transaction
handle ``tx`` and the document ``path`` instead of a raw Firestore ``(transaction, doc_ref)``. The
state-machine logic is unchanged; only the storage seam is neutral so it runs on Firestore or Mongo.
Also hosts deletion-scoped resource reads (e.g. Agent VM migration journals) through the same port.
"""

from datetime import datetime, timezone
from typing import Any

from database import document_store
from database.account_deletion_policy import account_deletion_blocks_access, normalize_account_deletion_status


def read_agent_vm_migration_journals(uid: str) -> list[dict[str, Any]]:
    """Read migration journals before deleting the user's subtree.

    The journal is the durable source of truth for provider resources created
    during an Agent VM migration.  Callers must validate each returned record
    against the provider before issuing destructive requests.
    """
    if not uid.strip():
        raise ValueError('uid is required')
    journals: list[dict[str, Any]] = []
    for snapshot in document_store.stream_collection(f'users/{uid}/agentVmMigrations'):
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


def record_late_agent_vm_cleanup(
    tx,
    path,
    vm_name: str,
    zone: str,
    expected_instance_id: str | None = None,
) -> bool:
    snapshot = tx.get(path)
    raw_status = (snapshot.to_dict() or {}).get('wipe_status') if snapshot.exists else None
    status = normalize_account_deletion_status(marker_exists=snapshot.exists, raw_status=raw_status)
    if not account_deletion_blocks_access(status):
        return False
    if expected_instance_id is not None and (not expected_instance_id.isascii() or not expected_instance_id.isdigit()):
        raise ValueError('late Agent VM cleanup instance identity must be numeric')
    pending = {'vmName': vm_name, 'zone': zone}
    if expected_instance_id is not None:
        pending['expectedInstanceId'] = expected_instance_id
    tx.set(
        path,
        {
            'late_agent_vm_cleanup': pending,
            'wipe_status': 'failed',
            'wipe_failed_at': datetime.now(timezone.utc),
        },
        merge=True,
    )
    return True


def adopt_legacy_late_agent_vm_cleanup(
    tx,
    path,
    vm_name: str,
    zone: str,
    expected_instance_id: str,
) -> bool:
    """Add a provider identity fence to an exact pre-fence cleanup record."""
    if not expected_instance_id.isascii() or not expected_instance_id.isdigit():
        raise ValueError('late Agent VM cleanup instance identity must be numeric')
    snapshot = tx.get(path)
    data = (snapshot.to_dict() or {}) if snapshot.exists else {}
    raw_status = data.get('wipe_status')
    status = normalize_account_deletion_status(marker_exists=snapshot.exists, raw_status=raw_status)
    pending = data.get('late_agent_vm_cleanup')
    if not account_deletion_blocks_access(status) or not isinstance(pending, dict):
        return False
    if pending.get('vmName') != vm_name or pending.get('zone') != zone:
        return False
    current_id = pending.get('expectedInstanceId')
    if current_id is not None:
        return current_id == expected_instance_id
    tx.update(path, {'late_agent_vm_cleanup.expectedInstanceId': expected_instance_id})
    return True
