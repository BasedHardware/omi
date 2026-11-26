"""Content-free task-link fences for cards removed or hidden by V3 maintenance."""

from __future__ import annotations

import hashlib

from google.cloud import firestore


def removal_ref(user_ref: firestore.DocumentReference, cid: str) -> firestore.DocumentReference:
    # Hash the ID so even unchecked, legacy task links can be used as lookup keys.
    key = hashlib.sha256(cid.encode()).hexdigest()
    return user_ref.collection('conversations_v3_undo_removals').document(key)
