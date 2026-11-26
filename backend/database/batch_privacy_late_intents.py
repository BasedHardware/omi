"""Atomically schedule post-window checks for in-flight batch artifact receipts."""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from google.cloud.firestore_v1.types import Document, DocumentTransform, Value, Write

from database.batch_account_authority_schema import ACCOUNT_DELETION_COLLECTION

COLLECTION = 'batch_privacy_late_sweeps'
DELAY = timedelta(minutes=10)
PROTECTION_FIELDS = frozenset({'data_protection_level', 'migration_status'})


def _field(write: Write, field: str) -> Value | None:
    mask = write.update_mask.field_paths
    if not write.update.name or (Write.pb(write).HasField('update_mask') and field not in mask):
        return None
    return write.update.fields.get(field)


def _denies_recording(write: Write, field: str) -> bool:
    value = _field(write, field)
    return (
        value is not None
        and Value.pb(value).WhichOneof('value_type') == 'boolean_value'
        and value.boolean_value == (field == 'uses_custom_stt')
    )


def _scopes(write: Write, parts: list[str]) -> list[tuple[str, str]]:
    family = parts[5]
    if family == ACCOUNT_DELETION_COLLECTION and len(parts) == 7:
        status = _field(write, 'wipe_status')
        return [('account_deleted', '')] if status is not None and status.string_value == 'completed' else []
    if family != 'users':
        return []
    if len(parts) == 7:
        reasons = []
        mask = write.update_mask.field_paths
        protection = _field(write, 'data_protection_level')
        migration = _field(write, 'migration_status')
        # Root creation commonly supplies the default protection level. A
        # full replacement arms only when it explicitly starts denying data.
        restricted_replacement = not mask and (
            (protection is not None and protection.string_value == 'e2ee')
            or (migration is not None and Value.pb(migration).WhichOneof('value_type') != 'null_value')
        )
        if PROTECTION_FIELDS.intersection(mask) or restricted_replacement:
            reasons.append(('data_protection', ''))
        # Only a batch capture denial can erase batch artifacts. The
        # separate playback-storage preference still invalidates decisions.
        if _denies_recording(write, 'private_cloud_sync_enabled'):
            reasons.append(('recording_policy', ''))
        return reasons
    if len(parts) == 9 and parts[7] == 'conversations':
        # A masked edit may omit the lane. The reconciler verifies the scope
        # at the policy commit before it can act on this candidate.
        maskless = not Write.pb(write).HasField('update_mask')
        lane = _field(write, 'record_lane_owner')
        if (maskless or lane is not None) and (lane is None or lane.string_value != 'batch_live_v1'):
            return []
        sync = _field(write, 'private_cloud_sync_enabled')
        clears_sync = (maskless or 'private_cloud_sync_enabled' in write.update_mask.field_paths) and (
            sync is None or Value.pb(sync).WhichOneof('value_type') == 'null_value'
        )
        if (
            clears_sync
            or _denies_recording(write, 'private_cloud_sync_enabled')
            or _denies_recording(write, 'uses_custom_stt')
        ):
            return [('recording_policy', parts[8])]
    return []


def late_sweep_writes(writes) -> list[Write]:
    scopes = set()
    for raw in writes:
        write = Write(raw) if isinstance(raw, dict) else raw
        parts = write.update.name.split('/')
        if len(parts) >= 7 and parts[0] == 'projects' and parts[2] == 'databases' and parts[4] == 'documents':
            root, uid = '/'.join(parts[:5]), parts[6]
            scopes.update((root, uid, reason, source) for reason, source in _scopes(write, parts))
    if not scopes:
        return []
    now = datetime.now(timezone.utc)
    return [
        Write(
            update=Document(
                name=f'{root}/{COLLECTION}/{uuid4().hex}',
                fields={
                    'uid': Value(string_value=uid),
                    'reason': Value(string_value=reason),
                    'conversation_id': Value(string_value=source),
                    'due_at': Value(timestamp_value=now if source else now + DELAY),
                },
            ),
            update_transforms=[
                DocumentTransform.FieldTransform(
                    field_path='changed_at',
                    set_to_server_value=DocumentTransform.FieldTransform.ServerValue.REQUEST_TIME,
                )
            ],
        )
        for root, uid, reason, source in sorted(scopes)
    ]
