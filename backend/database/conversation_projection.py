from typing import Any, Dict, Optional

from models.conversation_version import server_version_data

CONVERSATION_LIST_FIELDS = (
    'id',
    'created_at',
    'started_at',
    'finished_at',
    'structured',
    'source',
    'language',
    'status',
    'discarded',
    'deleted',
    'is_locked',
    'starred',
    'folder_id',
    'client_device_id',
    'deferred',
    'visibility',
    'data_protection_level',
)


def apply_conversation_list_field_mask(query):
    """Restrict a Firestore query to the desktop list projection."""
    return query.select(CONVERSATION_LIST_FIELDS)


def conversation_snapshot_data(snapshot) -> Optional[Dict[str, Any]]:
    """Project a Firestore snapshot with server-owned freshness metadata.

    Firestore ``update_time`` is an opaque server version. Keeping this small
    projection pure makes the authority contract easy to test without importing
    database clients or constructing infrastructure at test collection time.
    """
    if snapshot is None or not getattr(snapshot, 'exists', False):
        return None
    data = snapshot.to_dict()
    if data is None:
        return None
    data.setdefault('id', snapshot.id)
    update_time = getattr(snapshot, 'update_time', None)
    if update_time is not None:
        updated_at, revision = server_version_data(update_time)
        data['updated_at'] = updated_at
        data['revision'] = revision
    return data
