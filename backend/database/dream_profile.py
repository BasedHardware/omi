"""Dream's profile v2 side field on the user doc (shadow; no product reader yet).

Kept apart from the legacy profile accessors in ``database.users``: the served
``ai_user_profile`` and its cache are never touched here.
"""

import time
from typing import Optional

from google.cloud.firestore_v1 import transactional

from ._client import db

FIELD = 'ai_user_profile_v2'


def get_profile_v2(uid: str) -> Optional[dict]:
    """Never cached: only the weekly state pass reads it."""
    doc = db.collection('users').document(uid).get([FIELD])
    if not doc.exists:
        return None
    return (doc.to_dict() or {}).get(FIELD)


def write_profile_v2(uid: str, profile_v2: dict, *, not_after: float | None = None) -> str:
    """Replace only the v2 field, unless a newer run already wrote it.

    ``profile_v2['run_started_at']`` (ISO) fences late writes from an older run, and
    ``not_after`` (epoch seconds) refuses a write that starts past its run's deadline.
    Returns 'written', 'superseded' (a newer run owns the field) or 'expired'.
    """
    ref = db.collection('users').document(uid)

    @transactional
    def write(transaction):
        # A run past its deadline never starts (or retries) the write.
        if not_after is not None and time.time() > not_after:
            return 'expired'
        snapshot = ref.get([FIELD], transaction=transaction)
        current = (snapshot.to_dict() or {}).get(FIELD) if snapshot.exists else None
        previous = str((current or {}).get('run_started_at') or '')
        if previous and previous > str(profile_v2.get('run_started_at') or ''):
            return 'superseded'
        transaction.update(ref, {FIELD: profile_v2})
        return 'written'

    return write(db.transaction())
