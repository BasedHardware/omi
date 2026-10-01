"""Account-deletion state transitions and deletion-scoped resource reads.

Design: identifier and parameter validation fails fast with ValueError/TypeError;
timestamps are strictly normalized to timezone-aware UTC.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from google.api_core.exceptions import NotFound
from google.cloud.firestore_v1 import transactional

from database._client import get_firestore_client
from database.account_deletion_policy import account_deletion_blocks_access, normalize_account_deletion_status

MAX_MIGRATION_JOURNALS_LIMIT = 500


def _ensure_utc(dt: datetime | None) -> datetime:
    """Normalize datetime to timezone-aware UTC, defaulting to now."""
    if dt is None:
        return datetime.now(timezone.utc)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def read_agent_vm_migration_journals(
    uid: str,
    *,
    limit: int = 100,
    firestore_client: Any | None = None,
) -> list[dict[str, Any]]:
    """Read migration journals before deleting the user's Firestore subtree.

    The journal is the durable source of truth for provider resources created
    during an Agent VM migration. Callers must validate each returned record
    against the provider before issuing destructive requests.
    """
    if not isinstance(uid, str) or not uid.strip():
        raise ValueError('uid is required')
    if '/' in uid:
        raise ValueError('uid cannot contain path delimiters')
    if not isinstance(limit, int) or limit <= 0:
        raise ValueError('limit must be a positive integer')

    effective_limit = min(limit, MAX_MIGRATION_JOURNALS_LIMIT)
    client = firestore_client if firestore_client is not None else get_firestore_client()
    clean_uid = uid.strip()
    migration_ref = client.collection('users').document(clean_uid).collection('agentVmMigrations')
    journals: list[dict[str, Any]] = []

    try:
        stream_iter = migration_ref.stream()
        for snapshot in stream_iter:
            raw_data = snapshot.to_dict() if hasattr(snapshot, 'to_dict') else None
            if not isinstance(raw_data, dict):
                raise RuntimeError('Agent VM migration journal is malformed')
            journal = dict(raw_data)
            if journal.get('migrationId') not in (None, snapshot.id):
                raise RuntimeError('Agent VM migration journal identity is ambiguous')
            journal['migrationId'] = snapshot.id
            journals.append(journal)
            if len(journals) >= effective_limit:
                break
    except NotFound:
        return []

    journals.sort(key=lambda journal: str(journal.get('migrationId') or ''))
    return journals


@transactional
def mark_wipe_completed(transaction, doc_ref, *, now: datetime | None = None) -> bool:
    if doc_ref is None:
        raise ValueError('doc_ref is required')
    timestamp = _ensure_utc(now)
    snapshot = doc_ref.get(transaction=transaction)
    raw_data = snapshot.to_dict() if getattr(snapshot, 'exists', False) and hasattr(snapshot, 'to_dict') else None
    data = raw_data if isinstance(raw_data, dict) else {}
    if data.get('late_agent_vm_cleanup'):
        transaction.set(
            doc_ref,
            {'wipe_status': 'failed', 'wipe_failed_at': timestamp},
            merge=True,
        )
        return False
    transaction.set(
        doc_ref,
        {'wipe_status': 'completed', 'wipe_completed_at': timestamp},
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
    *,
    now: datetime | None = None,
) -> bool:
    if doc_ref is None:
        raise ValueError('doc_ref is required')
    if not isinstance(vm_name, str) or not vm_name.strip():
        raise ValueError('vm_name must be a non-empty string')
    if not isinstance(zone, str) or not zone.strip():
        raise ValueError('zone must be a non-empty string')
    if expected_instance_id is not None:
        if (
            not isinstance(expected_instance_id, str)
            or not expected_instance_id.strip()
            or not expected_instance_id.isascii()
            or not expected_instance_id.isdigit()
        ):
            raise ValueError('late Agent VM cleanup instance identity must be numeric')

    timestamp = _ensure_utc(now)
    snapshot = doc_ref.get(transaction=transaction)
    exists = getattr(snapshot, 'exists', False)
    raw_data = snapshot.to_dict() if exists and hasattr(snapshot, 'to_dict') else None
    raw_status = raw_data.get('wipe_status') if isinstance(raw_data, dict) else None
    status = normalize_account_deletion_status(marker_exists=exists, raw_status=raw_status)
    if not account_deletion_blocks_access(status):
        return False

    pending = {'vmName': vm_name.strip(), 'zone': zone.strip()}
    if expected_instance_id is not None:
        pending['expectedInstanceId'] = expected_instance_id.strip()
    transaction.set(
        doc_ref,
        {
            'late_agent_vm_cleanup': pending,
            'wipe_status': 'failed',
            'wipe_failed_at': timestamp,
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
    if doc_ref is None:
        raise ValueError('doc_ref is required')
    if not isinstance(vm_name, str) or not vm_name.strip():
        raise ValueError('vm_name must be a non-empty string')
    if not isinstance(zone, str) or not zone.strip():
        raise ValueError('zone must be a non-empty string')
    if (
        not isinstance(expected_instance_id, str)
        or not expected_instance_id.strip()
        or not expected_instance_id.isascii()
        or not expected_instance_id.isdigit()
    ):
        raise ValueError('late Agent VM cleanup instance identity must be numeric')

    snapshot = doc_ref.get(transaction=transaction)
    exists = getattr(snapshot, 'exists', False)
    raw_data = snapshot.to_dict() if exists and hasattr(snapshot, 'to_dict') else None
    data = raw_data if isinstance(raw_data, dict) else {}
    raw_status = data.get('wipe_status')
    status = normalize_account_deletion_status(marker_exists=exists, raw_status=raw_status)
    pending = data.get('late_agent_vm_cleanup')
    if not account_deletion_blocks_access(status) or not isinstance(pending, dict):
        return False
    if pending.get('vmName') != vm_name.strip() or pending.get('zone') != zone.strip():
        return False
    current_id = pending.get('expectedInstanceId')
    if current_id is not None:
        return current_id == expected_instance_id.strip()
    transaction.update(doc_ref, {'late_agent_vm_cleanup.expectedInstanceId': expected_instance_id.strip()})
    return True

