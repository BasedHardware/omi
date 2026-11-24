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
# Set when any Play purchase is bound to the user, even one that never granted access (bound on hold).
BOUND_FIELD = 'play_purchase_bound'
HISTORY_FIELDS = (USER_POINTER_FIELD, PENDING_FIELD, CUSTOMER_FIELD, BOUND_FIELD)
ACCOUNTS = 'play_billing_accounts'
# When account deletion last confirmed Google can no longer charge this purchase.
DELETION_CONFIRMED_FIELD = 'account_deletion_confirmed_at'


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
    snapshot = client.collection('users').document(uid).get(list(HISTORY_FIELDS))
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


def pending_play_purchase(uid: str, fields: Optional[Mapping[str, Any]] = None) -> bool:
    """A Play purchase for this uid is still waiting for Google to clear the payment."""
    key = (get_user_fields(uid) if fields is None else fields).get(PENDING_FIELD)
    if not key:
        return False
    return (get_purchase(key) or {}).get('state') == 'SUBSCRIPTION_STATE_PENDING'


def has_play_history(fields: Mapping[str, Any]) -> bool:
    """The user doc shows a Play purchase was ever bound or granted. No history: no Play reads at all."""
    return any(fields.get(name) for name in HISTORY_FIELDS)


def mark_once(token_hash: str, field: str, value: Any, *, firestore_client: Optional[Any] = None) -> bool:
    """Write ``field`` only when it is not set yet. Returns True when this call wrote it."""
    client = firestore_client or _client.get_firestore_client()
    ref = client.collection(COLLECTION).document(token_hash)
    snapshot = ref.get()
    if snapshot.exists and (snapshot.to_dict() or {}).get(field):
        return False
    ref.set({field: value}, merge=True)
    return True


def purchase_keys_for_uid(uid: str, *, firestore_client: Optional[Any] = None) -> list[str]:
    """Every purchase document bound to ``uid``: the exact set ``purge_account_records`` deletes."""
    client = firestore_client or _client.get_firestore_client()
    return [snapshot.id for snapshot in client.collection(COLLECTION).where('uid', '==', uid).stream()]


def purge_account_records(uid: str, confirmed_since: Any, *, firestore_client: Optional[Any] = None) -> int:
    """Account deletion: drop every purchase document (uid + plaintext token) and account-map entry of ``uid``.

    Runs inside the Firestore wipe, after the wipe's billing step. Refuses (raises, so the wipe retries) when
    a purchase document's cancel was not confirmed at or after ``confirmed_since`` (this wipe's billing step):
    a purchase Google can still charge is never deleted. A later notification for a dropped token finds no
    owner and is recorded unbound (token, no uid), never granted.
    """
    client = firestore_client or _client.get_firestore_client()
    purchases = list(client.collection(COLLECTION).where('uid', '==', uid).stream())
    for snapshot in purchases:
        confirmed_at = (snapshot.to_dict() or {}).get(DELETION_CONFIRMED_FIELD)
        if confirmed_at is None or confirmed_at < confirmed_since:
            raise RuntimeError(f'Play purchase {snapshot.id[:12]} has no confirmed deletion cancel')
    removed = 0
    for snapshot in purchases + list(client.collection(ACCOUNTS).where('uid', '==', uid).stream()):
        snapshot.reference.delete()
        removed += 1
    return removed
