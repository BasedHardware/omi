"""Registry of users enrolled in the X (Twitter) incremental sync job.

Top-level collection ``x_connector_users``; each document id is a uid. Kept inside
``database/`` so the X connector logic in ``utils/`` never touches the Firestore client
directly (persistence boundary).
"""

from datetime import datetime, timezone
from typing import List

from ._client import db

_REGISTRY_COLLECTION = 'x_connector_users'


def register_sync_user(uid: str) -> None:
    """Enroll (or refresh) a user in the X sync registry."""
    db.collection(_REGISTRY_COLLECTION).document(uid).set(
        {'uid': uid, 'updated_at': datetime.now(timezone.utc)}, merge=True
    )


def unregister_sync_user(uid: str) -> None:
    """Remove a user from the X sync registry."""
    db.collection(_REGISTRY_COLLECTION).document(uid).delete()


def list_sync_user_ids() -> List[str]:
    """Return the uids of every user enrolled in the X sync registry."""
    return [d.id for d in db.collection(_REGISTRY_COLLECTION).stream()]
