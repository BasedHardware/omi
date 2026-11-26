"""Account-deletion state transitions and deletion-scoped resource reads."""

from datetime import datetime, timezone
from typing import Any

from database._client import get_firestore_client
from google.cloud.firestore_v1 import transactional

from database.batch_account_authority import write_account_authority
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
def mark_wipe_completed(transaction, doc_ref, *, operation_id: str) -> bool:
    snapshot = doc_ref.get(transaction=transaction)
    data = (snapshot.to_dict() or {}) if snapshot.exists else {}
    erase_armed = data.get('go_queue_erase_armed_at') is not None
    erase_verified = isinstance(data.get('go_queue_erase_receipt_at'), datetime) and isinstance(
        data.get('go_queue_erase_wipe_started_at'), datetime
    )
    if data.get('late_agent_vm_cleanup') or (erase_armed and not erase_verified):
        write_account_authority(
            transaction,
            doc_ref,
            {'wipe_status': 'failed', 'wipe_failed_at': datetime.now(timezone.utc)},
            merge=True,
            preimage=snapshot,
            operation_id=operation_id,
        )
        return False
    write_account_authority(
        transaction,
        doc_ref,
        {'wipe_status': 'completed', 'wipe_completed_at': datetime.now(timezone.utc)},
        merge=True,
        preimage=snapshot,
        operation_id=operation_id,
    )
    return True


@transactional
def record_late_agent_vm_cleanup(
    transaction,
    doc_ref,
    vm_name: str,
    zone: str,
    expected_instance_id: str | None = None,
    *,
    operation_id: str,
) -> bool:
    snapshot = doc_ref.get(transaction=transaction)
    raw_status = (snapshot.to_dict() or {}).get('wipe_status') if snapshot.exists else None
    status = normalize_account_deletion_status(marker_exists=snapshot.exists, raw_status=raw_status)
    if not account_deletion_blocks_access(status):
        return False
    if expected_instance_id is not None and (not expected_instance_id.isascii() or not expected_instance_id.isdigit()):
        raise ValueError('late Agent VM cleanup instance identity must be numeric')
    pending = {'vmName': vm_name, 'zone': zone}
    if expected_instance_id is not None:
        pending['expectedInstanceId'] = expected_instance_id
    write_account_authority(
        transaction,
        doc_ref,
        {
            'late_agent_vm_cleanup': pending,
            'wipe_status': 'failed',
            'wipe_failed_at': datetime.now(timezone.utc),
        },
        merge=True,
        preimage=snapshot,
        operation_id=operation_id,
    )
    return True


@transactional
def adopt_legacy_late_agent_vm_cleanup(
    transaction,
    doc_ref,
    vm_name: str,
    zone: str,
    expected_instance_id: str,
) -> bool:
    """Add a provider identity fence to an exact pre-fence cleanup record."""
    if not expected_instance_id.isascii() or not expected_instance_id.isdigit():
        raise ValueError('late Agent VM cleanup instance identity must be numeric')
    snapshot = doc_ref.get(transaction=transaction)
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
    transaction.update(doc_ref, {'late_agent_vm_cleanup.expectedInstanceId': expected_instance_id})
    return True
