from __future__ import annotations

import hashlib
import math
import os
import re
import time
from typing import Any, Mapping, TypedDict, cast

import google.auth
import google.auth.transport.requests
import httpx

from database import users as users_db
from database.account_deletion_transitions import read_agent_vm_migration_journals


def _gce_project_id() -> str | None:
    return (
        os.getenv('GCE_PROJECT_ID')
        or os.getenv('GOOGLE_CLOUD_PROJECT')
        or os.getenv('FIREBASE_PROJECT_ID')
        or os.getenv('GCP_PROJECT_ID')
    )


_GCE_NAME = re.compile(r'[a-z](?:[-a-z0-9]{0,61}[a-z0-9])?')
_GCE_NUMERIC_ID = re.compile(r'[0-9]+')
_AGENT_VM_MIGRATION_ID = re.compile(r'[0-9a-f]{24}')
_STATE_DISK_ROLE = 'state'
_SOURCE_DISK_ROLE = 'source'
_DEFAULT_AGENT_VM_ZONE = 'us-central1-a'


class _AgentVmMigrationCleanupPlan(TypedDict):
    migration_id: str
    zone: str
    old_vm_name: str
    old_instance_id: str
    candidate_vm_name: str
    candidate_instance_id: str
    state_disk_name: str
    state_disk_id: str
    state_disk_reused: bool
    source_clone_disk_name: str
    source_clone_disk_id: str
    old_is_active_pointer: bool


def _journal_required_string(journal: Mapping[str, Any], field: str) -> str:
    value = journal.get(field)
    if not isinstance(value, str) or not value.strip():
        raise RuntimeError(f'Agent VM migration journal field {field} is ambiguous')
    return value.strip()


def _journal_name(journal: Mapping[str, Any], field: str, *, required: bool = True) -> str:
    value = journal.get(field)
    if value in (None, '') and not required:
        return ''
    name = _journal_required_string(journal, field)
    if not _GCE_NAME.fullmatch(name):
        raise RuntimeError(f'Agent VM migration journal field {field} is invalid')
    return name


def _journal_numeric_id(journal: Mapping[str, Any], field: str, *, required: bool = True) -> str:
    value = journal.get(field)
    if value in (None, '') and not required:
        return ''
    if not isinstance(value, str) or not _GCE_NUMERIC_ID.fullmatch(value):
        raise RuntimeError(f'Agent VM migration journal field {field} is ambiguous')
    return value


def _migration_reconcile_lease_active(
    vm: Mapping[str, Any] | None, journals: list[dict[str, Any]], *, now: float | None = None
) -> bool:
    if not isinstance(vm, Mapping):
        return False
    reconcile = vm.get('reconcile')
    if not isinstance(reconcile, Mapping):
        return False
    if not journals and not isinstance(reconcile.get('migration'), Mapping):
        return False
    lease = reconcile.get('lease')
    if lease is None:
        return False
    if not isinstance(lease, Mapping):
        raise RuntimeError('Agent VM migration reconcile lease is ambiguous')
    raw_expires_at = lease.get('expiresAt')
    if not isinstance(raw_expires_at, (int, float, str)) or isinstance(raw_expires_at, bool):
        raise RuntimeError('Agent VM migration reconcile lease is ambiguous')
    try:
        expires_at = float(raw_expires_at)
    except (TypeError, ValueError) as exc:
        raise RuntimeError('Agent VM migration reconcile lease is ambiguous') from exc
    if not math.isfinite(expires_at):
        raise RuntimeError('Agent VM migration reconcile lease is ambiguous')
    return expires_at > (time.time() if now is None else now)


def _compute_instance_url(project: str, zone: str, vm_name: str) -> str:
    return f'https://compute.googleapis.com/compute/v1/projects/{project}/zones/{zone}/instances/{vm_name}'


def _compute_disk_url(project: str, zone: str, disk_name: str) -> str:
    return f'https://compute.googleapis.com/compute/v1/projects/{project}/zones/{zone}/disks/{disk_name}'


def _compute_resource(client: Any, headers: Mapping[str, str], url: str, resource_kind: str) -> dict[str, Any] | None:
    response = client.get(url, headers=headers)
    if response.status_code == 404:
        return None
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise RuntimeError(f'GCE {resource_kind} response is malformed')
    return cast(dict[str, Any], payload)


def _wait_for_compute_operation(
    client: Any, headers: Mapping[str, str], project: str, zone: str, response: Any, *, required: bool
) -> None:
    payload = response.json()
    if not isinstance(payload, dict):
        raise RuntimeError('GCE operation response is malformed')
    operation = payload.get('name')
    if not isinstance(operation, str) or not operation:
        if required:
            raise RuntimeError('GCE cleanup operation response omitted name')
        return
    self_link = payload.get('selfLink')
    if isinstance(self_link, str) and '/global/operations/' in self_link:
        operation_url = f'https://compute.googleapis.com/compute/v1/projects/{project}/global/operations/{operation}'
    else:
        operation_url = (
            f'https://compute.googleapis.com/compute/v1/projects/{project}/zones/{zone}/operations/{operation}'
        )
    for _ in range(36):
        status_response = client.get(operation_url, headers=headers)
        status_response.raise_for_status()
        result = status_response.json()
        if not isinstance(result, dict):
            raise RuntimeError('GCE cleanup operation response is malformed')
        if result.get('status') == 'DONE':
            if result.get('error'):
                raise RuntimeError('GCE Agent VM cleanup operation failed')
            return
        time.sleep(5)
    raise RuntimeError('GCE Agent VM cleanup operation timed out')


def _delete_compute_resource(
    client: Any,
    headers: Mapping[str, str],
    project: str,
    zone: str,
    url: str,
) -> None:
    response = client.delete(url, headers=headers)
    if response.status_code == 404:
        return
    response.raise_for_status()
    _wait_for_compute_operation(client, headers, project, zone, response, required=True)


def _delete_current_agent_vm(
    uid: str,
    vm: Mapping[str, Any],
    plans: list[_AgentVmMigrationCleanupPlan],
    project: str,
    client: Any,
    headers: Mapping[str, str],
) -> None:
    vm_name = _journal_name(vm, 'vmName')
    zone = str(vm.get('zone') or _DEFAULT_AGENT_VM_ZONE)
    instance_url = _compute_instance_url(project, zone, vm_name)
    instance = _compute_resource(client, headers, instance_url, 'current instance')
    if instance is None:
        users_db.clear_late_agent_vm_cleanup(uid, vm_name)
        return
    _validate_current_instance_identity(
        instance,
        expected_id=_current_vm_instance_id(vm, plans),
        owner_label=_owner_disk_label(uid),
    )
    response = client.delete(instance_url, headers=headers)
    if response.status_code == 404:
        users_db.clear_late_agent_vm_cleanup(uid, vm_name)
        return
    response.raise_for_status()
    _wait_for_compute_operation(client, headers, project, zone, response, required=True)
    users_db.clear_late_agent_vm_cleanup(uid, vm_name)


def _owner_disk_label(uid: str) -> str:
    return hashlib.sha256(uid.encode()).hexdigest()[:20]


def _validate_instance_identity(
    instance: Mapping[str, Any],
    *,
    expected_id: str,
    migration_id: str,
    predecessor_id: str | None = None,
    require_migration_label: bool = True,
) -> None:
    if str(instance.get('id') or '') != expected_id:
        raise RuntimeError('Agent VM migration instance identity is ambiguous')
    labels = instance.get('labels')
    if require_migration_label and (
        not isinstance(labels, Mapping) or labels.get('omi-agent-migration') != migration_id
    ):
        raise RuntimeError('Agent VM migration instance identity is ambiguous')
    if predecessor_id is not None and (
        not isinstance(labels, Mapping) or labels.get('omi-agent-predecessor') != predecessor_id
    ):
        raise RuntimeError('Agent VM migration candidate identity is ambiguous')


def _current_vm_instance_id(vm: Mapping[str, Any], plans: list[_AgentVmMigrationCleanupPlan]) -> str:
    stored_value = vm.get('instanceId')
    stored_id = ''
    if stored_value not in (None, ''):
        if not isinstance(stored_value, str) or not _GCE_NUMERIC_ID.fullmatch(stored_value):
            raise RuntimeError('current Agent VM instance identity is ambiguous')
        stored_id = stored_value

    journaled_ids: set[str] = set()
    vm_name = _journal_name(vm, 'vmName')
    for plan in plans:
        if vm_name == plan['old_vm_name']:
            journaled_ids.add(plan['old_instance_id'])
        if vm_name == plan['candidate_vm_name']:
            candidate_id = plan['candidate_instance_id']
            if not candidate_id:
                raise RuntimeError('current Agent VM candidate identity is ambiguous')
            journaled_ids.add(candidate_id)

    if stored_id and journaled_ids and journaled_ids != {stored_id}:
        raise RuntimeError('current Agent VM instance identity is ambiguous')
    if stored_id:
        return stored_id
    if len(journaled_ids) == 1:
        return next(iter(journaled_ids))
    raise RuntimeError('current Agent VM instance identity is ambiguous')


def _validate_current_instance_identity(instance: Mapping[str, Any], *, expected_id: str, owner_label: str) -> None:
    if not _GCE_NUMERIC_ID.fullmatch(expected_id) or str(instance.get('id') or '') != expected_id:
        raise RuntimeError('current Agent VM instance identity is ambiguous')
    labels = instance.get('labels')
    if not isinstance(labels, Mapping) or labels.get('omi-agent-owner') != owner_label:
        raise RuntimeError('current Agent VM owner identity is ambiguous')


def _provider_numeric_id(resource: Mapping[str, Any], resource_kind: str) -> str:
    resource_id = str(resource.get('id') or '')
    if not _GCE_NUMERIC_ID.fullmatch(resource_id):
        raise RuntimeError(f'Agent VM migration {resource_kind} identity is ambiguous')
    return resource_id


def _validate_disk_identity(
    disk: Mapping[str, Any],
    *,
    expected_id: str,
    migration_id: str,
    owner_label: str,
    role: str,
    reused_state_disk: bool = False,
) -> None:
    if str(disk.get('id') or '') != expected_id:
        raise RuntimeError('Agent VM migration disk identity is ambiguous')
    labels = disk.get('labels')
    if not isinstance(labels, Mapping):
        raise RuntimeError('Agent VM migration disk identity is ambiguous')
    if labels.get('omi-agent-role') != role or labels.get('omi-agent-owner') != owner_label:
        raise RuntimeError('Agent VM migration disk owner identity is ambiguous')
    migration_label = labels.get('omi-agent-migration')
    if role != _STATE_DISK_ROLE or not reused_state_disk:
        if migration_label != migration_id:
            raise RuntimeError('Agent VM migration disk identity is ambiguous')
    # A reused state disk may retain the label from the migration that first
    # created it. Numeric ID, owner, and role are the authoritative fences.


def _validate_disk_users(disk: Mapping[str, Any], *, zone: str, allowed_vm_names: set[str]) -> None:
    users = disk.get('users')
    if users is None:
        return
    if not isinstance(users, list):
        raise RuntimeError('Agent VM migration disk attachment identity is ambiguous')
    allowed_suffixes = {f'/zones/{zone}/instances/{name}' for name in allowed_vm_names}
    for user in users:
        if not isinstance(user, str) or not any(user.rstrip('/').endswith(suffix) for suffix in allowed_suffixes):
            raise RuntimeError('Agent VM migration disk is attached to an ambiguous instance')


def _load_agent_vm_migration_cleanup_plans(
    uid: str,
    journals: list[dict[str, Any]],
    active_vm: Mapping[str, Any] | None,
    project: str,
    client: Any,
    headers: Mapping[str, str],
) -> list[_AgentVmMigrationCleanupPlan]:
    active_vm_name = active_vm.get('vmName') if isinstance(active_vm, Mapping) else None
    owner_label = _owner_disk_label(uid)
    plans: list[_AgentVmMigrationCleanupPlan] = []
    for journal in journals:
        migration_id = _journal_required_string(journal, 'migrationId')
        if not _AGENT_VM_MIGRATION_ID.fullmatch(migration_id):
            raise RuntimeError('Agent VM migration journal identity is ambiguous')
        zone = _journal_name(journal, 'oldZone')
        old_vm_name = _journal_name(journal, 'oldVmName')
        old_instance_id = _journal_numeric_id(journal, 'oldInstanceId')
        candidate_vm_name = _journal_name(journal, 'candidateVmName')
        candidate_instance_id = _journal_numeric_id(journal, 'candidateInstanceId', required=False)
        state_disk_name = _journal_name(journal, 'stateDiskName')
        state_disk_id = _journal_numeric_id(journal, 'stateDiskId', required=False)
        state_disk_reused = journal.get('stateDiskReused')
        if not isinstance(state_disk_reused, bool):
            raise RuntimeError('Agent VM migration journal state disk reuse flag is ambiguous')
        source_clone_disk_name = _journal_name(journal, 'sourceCloneDiskName', required=False)
        source_clone_disk_id = _journal_numeric_id(journal, 'sourceCloneDiskId', required=False)
        if not source_clone_disk_name and source_clone_disk_id:
            raise RuntimeError('Agent VM migration source clone identity is ambiguous')
        old_is_active_pointer = active_vm_name == old_vm_name
        candidate_is_active_pointer = active_vm_name == candidate_vm_name
        if old_is_active_pointer and candidate_is_active_pointer:
            raise RuntimeError('Agent VM migration journal names are ambiguous')

        old_instance = _compute_resource(client, headers, _compute_instance_url(project, zone, old_vm_name), 'instance')
        if old_instance is not None:
            _validate_instance_identity(
                old_instance,
                expected_id=old_instance_id,
                migration_id=migration_id,
                require_migration_label=not old_is_active_pointer,
            )

        candidate_instance = _compute_resource(
            client, headers, _compute_instance_url(project, zone, candidate_vm_name), 'candidate instance'
        )
        if candidate_instance is not None:
            if not candidate_instance_id:
                candidate_instance_id = _provider_numeric_id(candidate_instance, 'candidate instance')
            _validate_instance_identity(
                candidate_instance,
                expected_id=candidate_instance_id,
                migration_id=migration_id,
                predecessor_id=old_instance_id,
            )

        state_disk = _compute_resource(client, headers, _compute_disk_url(project, zone, state_disk_name), 'state disk')
        if state_disk is not None:
            if not state_disk_id:
                state_disk_id = _provider_numeric_id(state_disk, 'state disk')
            _validate_disk_identity(
                state_disk,
                expected_id=state_disk_id,
                migration_id=migration_id,
                owner_label=owner_label,
                role=_STATE_DISK_ROLE,
                reused_state_disk=state_disk_reused,
            )
            _validate_disk_users(state_disk, zone=zone, allowed_vm_names={old_vm_name, candidate_vm_name})

        source_clone_disk = None
        if source_clone_disk_name:
            source_clone_disk = _compute_resource(
                client, headers, _compute_disk_url(project, zone, source_clone_disk_name), 'source clone disk'
            )
            if source_clone_disk is not None:
                if not source_clone_disk_id:
                    source_clone_disk_id = _provider_numeric_id(source_clone_disk, 'source clone disk')
                _validate_disk_identity(
                    source_clone_disk,
                    expected_id=source_clone_disk_id,
                    migration_id=migration_id,
                    owner_label=owner_label,
                    role=_SOURCE_DISK_ROLE,
                )
                _validate_disk_users(source_clone_disk, zone=zone, allowed_vm_names={candidate_vm_name})

        plans.append(
            {
                'migration_id': migration_id,
                'zone': zone,
                'old_vm_name': old_vm_name,
                'old_instance_id': old_instance_id,
                'candidate_vm_name': candidate_vm_name,
                'candidate_instance_id': candidate_instance_id,
                'state_disk_name': state_disk_name,
                'state_disk_id': state_disk_id,
                'state_disk_reused': state_disk_reused,
                'source_clone_disk_name': source_clone_disk_name,
                'source_clone_disk_id': source_clone_disk_id,
                'old_is_active_pointer': old_is_active_pointer,
            }
        )
    return plans


def _cleanup_agent_vm_migration_resources(
    uid: str,
    plans: list[_AgentVmMigrationCleanupPlan],
    project: str,
    client: Any,
    headers: Mapping[str, str],
) -> None:
    owner_label = _owner_disk_label(uid)
    for plan in plans:
        candidate_instance = _compute_resource(
            client,
            headers,
            _compute_instance_url(project, plan['zone'], plan['candidate_vm_name']),
            'candidate instance',
        )
        if candidate_instance is not None:
            if not plan['candidate_instance_id']:
                raise RuntimeError('Agent VM migration candidate ID is ambiguous')
            _validate_instance_identity(
                candidate_instance,
                expected_id=plan['candidate_instance_id'],
                migration_id=plan['migration_id'],
                predecessor_id=plan['old_instance_id'],
            )
            _delete_compute_resource(
                client,
                headers,
                project,
                plan['zone'],
                _compute_instance_url(project, plan['zone'], plan['candidate_vm_name']),
            )
        if not plan['old_is_active_pointer']:
            old_instance = _compute_resource(
                client,
                headers,
                _compute_instance_url(project, plan['zone'], plan['old_vm_name']),
                'predecessor instance',
            )
            if old_instance is None:
                continue
            _validate_instance_identity(
                old_instance,
                expected_id=plan['old_instance_id'],
                migration_id=plan['migration_id'],
            )
            _delete_compute_resource(
                client,
                headers,
                project,
                plan['zone'],
                _compute_instance_url(project, plan['zone'], plan['old_vm_name']),
            )

    for plan in plans:
        state_disk = _compute_resource(
            client,
            headers,
            _compute_disk_url(project, plan['zone'], plan['state_disk_name']),
            'state disk',
        )
        if state_disk is not None:
            if not plan['state_disk_id']:
                raise RuntimeError('Agent VM migration state disk ID is ambiguous')
            _validate_disk_identity(
                state_disk,
                expected_id=plan['state_disk_id'],
                migration_id=plan['migration_id'],
                owner_label=owner_label,
                role=_STATE_DISK_ROLE,
                reused_state_disk=plan['state_disk_reused'],
            )
            _validate_disk_users(state_disk, zone=plan['zone'], allowed_vm_names=set())
            _delete_compute_resource(
                client,
                headers,
                project,
                plan['zone'],
                _compute_disk_url(project, plan['zone'], plan['state_disk_name']),
            )

        if plan['source_clone_disk_name']:
            source_clone_disk = _compute_resource(
                client,
                headers,
                _compute_disk_url(project, plan['zone'], plan['source_clone_disk_name']),
                'source clone disk',
            )
            if source_clone_disk is not None:
                if not plan['source_clone_disk_id']:
                    raise RuntimeError('Agent VM migration source clone ID is ambiguous')
                _validate_disk_identity(
                    source_clone_disk,
                    expected_id=plan['source_clone_disk_id'],
                    migration_id=plan['migration_id'],
                    owner_label=owner_label,
                    role=_SOURCE_DISK_ROLE,
                )
                _validate_disk_users(source_clone_disk, zone=plan['zone'], allowed_vm_names=set())
                _delete_compute_resource(
                    client,
                    headers,
                    project,
                    plan['zone'],
                    _compute_disk_url(project, plan['zone'], plan['source_clone_disk_name']),
                )


def _delete_agent_vm_for_account_impl(uid: str) -> None:
    """Delete owner VMs and all identity-fenced migration resources.

    Migration journals are read before the user's Firestore subtree is wiped.
    Provider resources are validated in a read-only pass first; a mismatch or
    incomplete identity raises so the account wipe remains retryable.
    """
    journals = read_agent_vm_migration_journals(uid)
    vm = users_db.get_agent_vm(uid) or users_db.get_late_agent_vm_cleanup(uid)
    if not isinstance(vm, Mapping) or not vm.get('vmName'):
        vm = None
    if _migration_reconcile_lease_active(vm, journals):
        raise RuntimeError('Agent VM migration reconcile lease is active')
    if vm is None and not journals:
        return
    project = _gce_project_id()
    if not project:
        raise RuntimeError('GCE project is not configured for account-deletion VM cleanup')
    credentials, _ = google.auth.default(scopes=['https://www.googleapis.com/auth/cloud-platform'])
    credentials.refresh(google.auth.transport.requests.Request())
    headers = {'Authorization': f'Bearer {credentials.token}'}
    with httpx.Client(timeout=180) as client:
        plans = _load_agent_vm_migration_cleanup_plans(uid, journals, vm, project, client, headers)
        if vm is not None:
            _delete_current_agent_vm(uid, vm, plans, project, client, headers)
        _cleanup_agent_vm_migration_resources(uid, plans, project, client, headers)


def delete_agent_vm_for_account(uid: str) -> None:
    """Delete the owner VM before the Firestore pointer becomes unreachable.

    Provisioning rechecks the durable deletion marker before and after GCE
    creation, so a create already in flight either loses before insert or
    deletes its late-created instance here/on its post-create fence.
    """
    _delete_agent_vm_for_account_impl(uid)
