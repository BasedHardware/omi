"""Account-deletion state transitions and deletion-scoped resource reads."""

from datetime import datetime, timezone
import re
from typing import Any

from database._client import get_firestore_client
from google.cloud.firestore_v1 import transactional

from database.account_deletion_marker import _clean_uid
from database.account_deletion_policy import account_deletion_blocks_access, normalize_account_deletion_status

_GCE_VM_NAME_RE = re.compile(r'^[a-z]([-a-z0-9]{0,61}[a-z0-9])?$')
_GCE_ZONE_RE = re.compile(r'^[a-z][a-z0-9]*-[a-z0-9]+-[a-z0-9]+$')


def _validate_gce_vm_and_zone(vm_name: str, zone: str) -> tuple[str, str]:
    """Validate GCE instance and zone names according to RFC 1035 label constraints."""
    if not isinstance(vm_name, str) or not _GCE_VM_NAME_RE.match(vm_name):
        raise ValueError(f"Invalid GCE vm_name: {vm_name!r}")
    if not isinstance(zone, str) or not _GCE_ZONE_RE.match(zone):
        raise ValueError(f"Invalid GCE zone: {zone!r}")
    return vm_name, zone


def read_agent_vm_migration_journals(uid: str, *, firestore_client: Any | None = None) -> list[dict[str, Any]]:
    """Read migration journals before deleting the user's Firestore subtree.

    The journal is the durable source of truth for provider resources created
    during an Agent VM migration. Callers must validate each returned record
    against the provider before issuing destructive requests.
    """
    clean = _clean_uid(uid)
    if not clean:
        raise ValueError('uid is required and must be a valid string identifier')
    client = firestore_client if firestore_client is not None else get_firestore_client()
    migration_ref = client.collection('users').document(clean).collection('agentVmMigrations')
    journals: list[dict[str, Any]] = []
    for snapshot in migration_ref.stream():
        to_dict = getattr(snapshot, 'to_dict', None)
        data = to_dict() if callable(to_dict) else None
        if not isinstance(data, dict):
            raise RuntimeError('Agent VM migration journal is malformed')
        journal = dict(data)
        snap_id = getattr(snapshot, 'id', '')
        if journal.get('migrationId') not in (None, snap_id):
            raise RuntimeError('Agent VM migration journal identity is ambiguous')
        journal['migrationId'] = snap_id
        journals.append(journal)
    journals.sort(key=lambda journal: str(journal.get('migrationId') or ''))
    return journals


@transactional
def mark_wipe_completed(transaction, doc_ref) -> bool:
    snapshot = doc_ref.get(transaction=transaction)
    exists = bool(getattr(snapshot, 'exists', False))
    data = (getattr(snapshot, 'to_dict', lambda: {})() or {}) if exists else {}
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
    vm_name: str,
    zone: str,
    expected_instance_id: str | None = None,
) -> bool:
    valid_vm, valid_zone = _validate_gce_vm_and_zone(vm_name, zone)
    snapshot = doc_ref.get(transaction=transaction)
    exists = bool(getattr(snapshot, 'exists', False))
    raw_status = (getattr(snapshot, 'to_dict', lambda: {})() or {}).get('wipe_status') if exists else None
    status = normalize_account_deletion_status(marker_exists=exists, raw_status=raw_status)
    if not account_deletion_blocks_access(status):
        return False
    if expected_instance_id is not None and (not expected_instance_id.isascii() or not expected_instance_id.isdigit()):
        raise ValueError('late Agent VM cleanup instance identity must be numeric')
    pending = {'vmName': valid_vm, 'zone': valid_zone}
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
    vm_name: str,
    zone: str,
    expected_instance_id: str,
) -> bool:
    """Add a provider identity fence to an exact pre-fence cleanup record."""
    valid_vm, valid_zone = _validate_gce_vm_and_zone(vm_name, zone)
    if not expected_instance_id.isascii() or not expected_instance_id.isdigit():
        raise ValueError('late Agent VM cleanup instance identity must be numeric')
    snapshot = doc_ref.get(transaction=transaction)
    exists = bool(getattr(snapshot, 'exists', False))
    data = (getattr(snapshot, 'to_dict', lambda: {})() or {}) if exists else {}
    raw_status = data.get('wipe_status')
    status = normalize_account_deletion_status(marker_exists=exists, raw_status=raw_status)
    pending = data.get('late_agent_vm_cleanup')
    if not account_deletion_blocks_access(status) or not isinstance(pending, dict):
        return False
    if pending.get('vmName') != valid_vm or pending.get('zone') != valid_zone:
        return False
    current_id = pending.get('expectedInstanceId')
    if current_id is not None:
        return current_id == expected_instance_id
    transaction.update(doc_ref, {'late_agent_vm_cleanup.expectedInstanceId': expected_instance_id})
    return True
