"""Registry of users enrolled in the X (Twitter) incremental sync job.

Top-level collection ``x_connector_users``; each document id is a uid. Kept inside
``database/`` so the X connector logic in ``utils/`` never touches the storage client
directly (persistence boundary).
"""

from datetime import datetime, timezone
from typing import List

from database.store import get_document_store

_REGISTRY_COLLECTION = 'x_connector_users'


def _store():
    return get_document_store()


def register_sync_user(uid: str) -> None:
    """Enroll (or refresh) a user in the X sync registry."""
    _store().set(
        f'{_REGISTRY_COLLECTION}/{uid}',
        {'uid': uid, 'updated_at': datetime.now(timezone.utc)},
        merge=True,
    )


def unregister_sync_user(uid: str) -> None:
    """Remove a user from the X sync registry."""
    _store().delete(f'{_REGISTRY_COLLECTION}/{uid}')


def list_sync_user_ids() -> List[str]:
    """Return the uids of every user enrolled in the X sync registry."""
    return _store().list_ids(_REGISTRY_COLLECTION)
