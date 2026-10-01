"""Account-deletion state transitions and deletion-scoped resource reads."""

from datetime import datetime, timezone
from typing import Any

from database._client import get_firestore_client
from google.cloud.firestore_v1 import transactional

from database.account_deletion_policy import account_deletion_blocks_access, normalize_account_deletion_status


def read_agent_vm_migration_journals(uid: Any, *, firestore_client: Any | None = None) -> list[dict[str, Any]]:
    """Read migration journals before deleting the user's Firestore subtree.

    The journal is the durable source of truth for provider resources created
    during an Agent VM migration.  Callers must validate each returned record
    against the provider before issuing destructive requests.
    """
    if not isinstance(uid, str) or not uid.strip():
        raise ValueError('uid is required')
    clean_uid = uid.strip()
    if any(c in clean_uid for c in ("/", "\\", "\0", "..")) or len(clean_uid) > 128:
        raise ValueError('uid must be a valid identifier without path traversal')
    client = firestore_client if firestore_client is not None else get_firestore_client()
    migration_ref = client.collection('users').document(clean_uid).collection('agentVmMigrations')
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
    data = (snapshot.to_dict() or {}) if getattr(snapshot, 'exists', False) else {}
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
def record_late_agent_vm_cleanup(
    transaction,
    doc_ref,
    vm_name: Any,
    zone: Any,
    expected_instance_id: Any = None,
) -> bool:
    if not isinstance(vm_name, str) or not vm_name.strip():
        raise ValueError('vm_name must be a non-empty string')
    if not isinstance(zone, str) or not zone.strip():
        raise ValueError('zone must be a non-empty string')
    snapshot = doc_ref.get(transaction=transaction)
    exists = getattr(snapshot, 'exists', False)
    raw_status = (snapshot.to_dict() or {}).get('wipe_status') if exists else None
    status = normalize_account_deletion_status(marker_exists=exists, raw_status=raw_status)
    if not account_deletion_blocks_access(status):
        return False
    if expected_instance_id is not None and (
        not isinstance(expected_instance_id, str)
        or not expected_instance_id.isascii()
        or not expected_instance_id.isdigit()
    ):
        raise ValueError('late Agent VM cleanup instance identity must be numeric')
    pending: dict[str, Any] = {'vmName': vm_name.strip(), 'zone': zone.strip()}
    if expected_instance_id is not None:
        pending['expectedInstanceId'] = expected_instance_id
    transaction.set(
        doc_ref,
        {
            'late_agent_vm_cleanup': pending,
            'wipe_status': 'failed',
            'wipe_failed_at': datetime.now(timezone.utc),
        },
        merge=True,
    )
    return True


@transactional
def adopt_legacy_late_agent_vm_cleanup(
    transaction,
    doc_ref,
    vm_name: Any,
    zone: Any,
    expected_instance_id: Any,
) -> bool:
    """Add a provider identity fence to an exact pre-fence cleanup record."""
    if not isinstance(vm_name, str) or not vm_name.strip():
        raise ValueError('vm_name must be a non-empty string')
    if not isinstance(zone, str) or not zone.strip():
        raise ValueError('zone must be a non-empty string')
    if (
        not isinstance(expected_instance_id, str)
        or not expected_instance_id.isascii()
        or not expected_instance_id.isdigit()
    ):
        raise ValueError('late Agent VM cleanup instance identity must be numeric')
    snapshot = doc_ref.get(transaction=transaction)
    exists = getattr(snapshot, 'exists', False)
    data = (snapshot.to_dict() or {}) if exists else {}
    raw_status = data.get('wipe_status')
    status = normalize_account_deletion_status(marker_exists=exists, raw_status=raw_status)
    pending = data.get('late_agent_vm_cleanup')
    if not account_deletion_blocks_access(status) or not isinstance(pending, dict):
        return False
    if pending.get('vmName') != vm_name.strip() or pending.get('zone') != zone.strip():
        return False
    current_id = pending.get('expectedInstanceId')
    if current_id is not None:
        return current_id == expected_instance_id
    transaction.update(doc_ref, {'late_agent_vm_cleanup.expectedInstanceId': expected_instance_id})
    return True
