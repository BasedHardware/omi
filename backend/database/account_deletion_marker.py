"""Single Firestore plane for the account_deletions/{uid} marker.

Writers (the deletion executor) and readers (the auth fence) must resolve the
same database. The marker is stored on the customer data plane; a compute-plane
default on desktop-backend is a clean miss that reopens a deleting account.

Design: identifier validation fails fast with ValueError; missing documents degrade cleanly to None.
"""

from __future__ import annotations

from typing import Any

from google.api_core.exceptions import GoogleAPICallError, NotFound

from database._client import get_data_plane_firestore_client
from database.account_deletion_policy import normalize_account_deletion_status
from database.firestore_read_metrics import FirestoreReadOutcome, FirestoreReadSite, record_document_read

ACCOUNT_DELETION_COLLECTION = "account_deletions"


def _validate_uid(uid: object) -> str:
    """Validate and return normalized non-empty uid string."""
    if not isinstance(uid, str) or not uid.strip():
        raise ValueError("uid must be a non-empty string without whitespace")
    if "/" in uid:
        raise ValueError("uid cannot contain path delimiters")
    return uid.strip()


def account_deletion_firestore_client(*, firestore_client: Any | None = None) -> Any:
    """The Firestore client that owns account_deletions/{uid}.

    Injected clients are for tests. Production always pins the data plane so a
    compute-plane fallback cannot silently miss the marker. If the data plane
    cannot be resolved, this raises and the auth fence maps that to HTTP 503.
    """
    if firestore_client is not None:
        return firestore_client
    return get_data_plane_firestore_client()


def account_deletion_collection(*, firestore_client: Any | None = None) -> Any:
    client = account_deletion_firestore_client(firestore_client=firestore_client)
    if client is None:
        raise ValueError("firestore client is required")
    return client.collection(ACCOUNT_DELETION_COLLECTION)


def account_deletion_document(uid: str, *, firestore_client: Any | None = None) -> Any:
    clean_uid = _validate_uid(uid)
    return account_deletion_collection(firestore_client=firestore_client).document(clean_uid)


def get_user_deletion_wipe_status(uid: str, *, firestore_client: Any | None = None) -> str | None:
    """Return the authoritative deletion lifecycle state for an authenticated UID.

    This intentionally bypasses caches: an accepted deletion must become an
    access barrier on the very next request, and a cached pre-delete miss would
    reopen the exact half-deleted-account window this marker closes.
    """
    clean_uid = _validate_uid(uid)
    client = account_deletion_firestore_client(firestore_client=firestore_client)
    try:
        snapshot = account_deletion_document(clean_uid, firestore_client=client).get()
    except NotFound:
        record_document_read(
            FirestoreReadSite.USER_DELETION_WIPE_STATUS,
            FirestoreReadOutcome.MISS,
        )
        return None
    except GoogleAPICallError:
        raise

    exists = getattr(snapshot, "exists", False)
    record_document_read(
        FirestoreReadSite.USER_DELETION_WIPE_STATUS,
        FirestoreReadOutcome.HIT if exists else FirestoreReadOutcome.MISS,
    )
    if not exists:
        return None
    raw_dict = snapshot.to_dict() if hasattr(snapshot, "to_dict") else None
    data = raw_dict if isinstance(raw_dict, dict) else {}
    status = data.get("wipe_status")
    return normalize_account_deletion_status(marker_exists=True, raw_status=status)


__all__ = [
    "ACCOUNT_DELETION_COLLECTION",
    "account_deletion_collection",
    "account_deletion_document",
    "account_deletion_firestore_client",
    "get_user_deletion_wipe_status",
]

