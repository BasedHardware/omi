"""Google Play subscription purchases bound to Omi accounts.

One document per purchase token (keyed by its SHA-256). ``uid`` is written once by an exclusive
create, so a token can never move to a second account. ``users/{uid}.play_current_purchase``
names the token that owns the user's current Play entitlement; ``play_pending_purchase`` a token
whose payment Google has not cleared; ``play_billing_customer`` that the user ever held a Play
subscription (trial history). ``play_billing_accounts/{obfuscated id}`` maps the id the app hands
Play back to its uid, so a notification for a token no client delivered can still be bound.
"""

import hashlib
from typing import Any, Mapping, Optional

from google.api_core.exceptions import AlreadyExists, Conflict

from database import _client

COLLECTION = 'play_subscription_purchases'
USER_POINTER_FIELD = 'play_current_purchase'
PENDING_FIELD = 'play_pending_purchase'
CUSTOMER_FIELD = 'play_billing_customer'
ACCOUNTS = 'play_billing_accounts'


def token_key(purchase_token: str) -> str:
    return hashlib.sha256(purchase_token.encode('utf-8')).hexdigest()


def get_purchase(token_hash: str, *, firestore_client: Optional[Any] = None) -> Optional[dict]:
    client = firestore_client or _client.get_firestore_client()
    snapshot = client.collection(COLLECTION).document(token_hash).get()
    return snapshot.to_dict() if snapshot.exists else None


def bind_purchase(token_hash: str, uid: str, record: Mapping[str, Any], *, firestore_client: Optional[Any] = None):
    """Bind the token to ``uid``. Returns the owning uid (``uid`` itself when this call or an earlier one bound it)."""
    client = firestore_client or _client.get_firestore_client()
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
    client = firestore_client or _client.get_firestore_client()
    client.collection(COLLECTION).document(token_hash).set(
        {key: value for key, value in record.items() if key != 'uid'}, merge=True
    )


def update_purchase(token_hash: str, fields: Mapping[str, Any], *, firestore_client: Optional[Any] = None) -> None:
    client = firestore_client or _client.get_firestore_client()
    client.collection(COLLECTION).document(token_hash).set(
        {key: value for key, value in fields.items() if key != 'uid'}, merge=True
    )


def due_for_reconcile(now: int, limit: int, *, firestore_client: Optional[Any] = None) -> list[dict]:
    """Non-terminal purchases whose ``next_check_at`` has passed, oldest first."""
    client = firestore_client or _client.get_firestore_client()
    query = client.collection(COLLECTION).where('next_check_at', '<=', now).order_by('next_check_at').limit(limit)
    return [snapshot.to_dict() | {'_key': snapshot.id} for snapshot in query.stream()]


def get_user_fields(uid: str, *, firestore_client: Optional[Any] = None) -> dict:
    """The Play fields on ``users/{uid}`` (pointer, pending token, customer flag)."""
    client = firestore_client or _client.get_firestore_client()
    snapshot = client.collection('users').document(uid).get([USER_POINTER_FIELD, PENDING_FIELD, CUSTOMER_FIELD])
    if not snapshot.exists:
        return {}
    return snapshot.to_dict() or {}


def set_user_fields(uid: str, fields: Mapping[str, Any], *, firestore_client: Optional[Any] = None) -> None:
    client = firestore_client or _client.get_firestore_client()
    client.collection('users').document(uid).update(dict(fields))


def get_user_pointer(uid: str, *, firestore_client: Optional[Any] = None) -> Optional[str]:
    return get_user_fields(uid, firestore_client=firestore_client).get(USER_POINTER_FIELD)


def remember_account(obfuscated_id: str, uid: str, *, firestore_client: Optional[Any] = None) -> None:
    """Record which uid an obfuscated account id belongs to. Written once; never moves."""
    client = firestore_client or _client.get_firestore_client()
    try:
        client.collection(ACCOUNTS).document(obfuscated_id).create({'uid': uid})
    except (AlreadyExists, Conflict):
        pass


def account_uid(obfuscated_id: str, *, firestore_client: Optional[Any] = None) -> Optional[str]:
    client = firestore_client or _client.get_firestore_client()
    snapshot = client.collection(ACCOUNTS).document(obfuscated_id).get()
    return (snapshot.to_dict() or {}).get('uid') if snapshot.exists else None


def set_user_pointer(uid: str, token_hash: str, *, firestore_client: Optional[Any] = None) -> None:
    client = firestore_client or _client.get_firestore_client()
    client.collection('users').document(uid).update({USER_POINTER_FIELD: token_hash})


_remembered: set[str] = set()


def remember_account_once(obfuscated_id: str, uid: str) -> None:
    """remember_account at most once per process per id (the subscription read calls it often)."""
    if obfuscated_id in _remembered:
        return
    remember_account(obfuscated_id, uid)
    if len(_remembered) > 50_000:
        _remembered.clear()
    _remembered.add(obfuscated_id)


def is_play_customer(uid: str) -> bool:
    """The user held a Play subscription (or its trial) before: no new trial anywhere."""
    return bool(get_user_fields(uid).get(CUSTOMER_FIELD))


def pending_play_purchase(uid: str) -> bool:
    """A Play purchase for this uid is still waiting for Google to clear the payment."""
    key = get_user_fields(uid).get(PENDING_FIELD)
    if not key:
        return False
    return (get_purchase(key) or {}).get('state') == 'SUBSCRIPTION_STATE_PENDING'


def purge_account_records(uid: str, *, firestore_client: Optional[Any] = None) -> int:
    """Account deletion: drop every purchase document (uid + plaintext token) and account-map entry of ``uid``.

    Runs inside the Firestore wipe, after the wipe's billing step confirmed Google stopped charging. A later
    notification for a dropped token finds no owner and is recorded unbound (token, no uid), never granted.
    """
    client = firestore_client or _client.get_firestore_client()
    removed = 0
    for collection in (COLLECTION, ACCOUNTS):
        for snapshot in client.collection(collection).where('uid', '==', uid).stream():
            snapshot.reference.delete()
            removed += 1
    return removed
