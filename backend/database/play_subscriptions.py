"""Google Play subscription purchases bound to Omi accounts.

One document per purchase token (keyed by its SHA-256). ``uid`` is written once by an exclusive
create, so a token can never move to a second account. ``users/{uid}.play_current_purchase``
names the token that owns the user's current Play entitlement.
"""

import hashlib
from typing import Any, Mapping, Optional

from google.api_core.exceptions import AlreadyExists, Conflict

from database._client import get_firestore_client

COLLECTION = 'play_subscription_purchases'
USER_POINTER_FIELD = 'play_current_purchase'


def token_key(purchase_token: str) -> str:
    return hashlib.sha256(purchase_token.encode('utf-8')).hexdigest()


def get_purchase(token_hash: str, *, firestore_client: Optional[Any] = None) -> Optional[dict]:
    client = firestore_client or get_firestore_client()
    snapshot = client.collection(COLLECTION).document(token_hash).get()
    return snapshot.to_dict() if snapshot.exists else None


def bind_purchase(token_hash: str, uid: str, record: Mapping[str, Any], *, firestore_client: Optional[Any] = None):
    """Bind the token to ``uid``. Returns the owning uid (``uid`` itself when this call or an earlier one bound it)."""
    client = firestore_client or get_firestore_client()
    ref = client.collection(COLLECTION).document(token_hash)
    try:
        ref.create({**dict(record), 'uid': uid})
        return uid
    except (AlreadyExists, Conflict):
        existing = ref.get().to_dict() or {}
        owner = existing.get('uid')
        if owner == uid:
            ref.set({key: value for key, value in record.items() if key != 'uid'}, merge=True)
        return owner


def record_unbound(token_hash: str, record: Mapping[str, Any], *, firestore_client: Optional[Any] = None) -> None:
    """Keep a notification for a token no account has claimed yet; never sets ``uid``."""
    client = firestore_client or get_firestore_client()
    client.collection(COLLECTION).document(token_hash).set(
        {key: value for key, value in record.items() if key != 'uid'}, merge=True
    )


def update_purchase(token_hash: str, fields: Mapping[str, Any], *, firestore_client: Optional[Any] = None) -> None:
    client = firestore_client or get_firestore_client()
    client.collection(COLLECTION).document(token_hash).set(
        {key: value for key, value in fields.items() if key != 'uid'}, merge=True
    )


def due_for_reconcile(now: int, limit: int, *, firestore_client: Optional[Any] = None) -> list[dict]:
    """Non-terminal purchases whose ``next_check_at`` has passed, oldest first."""
    client = firestore_client or get_firestore_client()
    query = client.collection(COLLECTION).where('next_check_at', '<=', now).order_by('next_check_at').limit(limit)
    return [snapshot.to_dict() | {'_key': snapshot.id} for snapshot in query.stream()]


def get_user_pointer(uid: str, *, firestore_client: Optional[Any] = None) -> Optional[str]:
    client = firestore_client or get_firestore_client()
    snapshot = client.collection('users').document(uid).get([USER_POINTER_FIELD])
    if not snapshot.exists:
        return None
    return (snapshot.to_dict() or {}).get(USER_POINTER_FIELD)


def set_user_pointer(uid: str, token_hash: str, *, firestore_client: Optional[Any] = None) -> None:
    client = firestore_client or get_firestore_client()
    client.collection('users').document(uid).update({USER_POINTER_FIELD: token_hash})
