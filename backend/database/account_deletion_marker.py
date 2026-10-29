"""Single Firestore plane for the account_deletions/{uid} marker.

Writers (the deletion executor) and readers (the auth fence) must resolve the
same database. The marker is stored on the customer data plane; a compute-plane
default on desktop-backend is a clean miss that reopens a deleting account.
"""

from __future__ import annotations

from typing import Any

ACCOUNT_DELETION_COLLECTION = "account_deletions"


def account_deletion_firestore_client(*, firestore_client: Any | None = None) -> Any:
    """The Firestore client that owns account_deletions/{uid}.

    Injected clients are for tests. Production always pins the data plane so a
    compute-plane fallback cannot silently miss the marker. If the data plane
    cannot be resolved, this raises and the auth fence maps that to HTTP 503.
    """
    if firestore_client is not None:
        return firestore_client
    from database._client import get_data_plane_firestore_client

    return get_data_plane_firestore_client()


def account_deletion_collection(*, firestore_client: Any | None = None) -> Any:
    return account_deletion_firestore_client(firestore_client=firestore_client).collection(ACCOUNT_DELETION_COLLECTION)


def account_deletion_document(uid: str, *, firestore_client: Any | None = None) -> Any:
    return account_deletion_collection(firestore_client=firestore_client).document(uid)


def get_user_deletion_wipe_status(uid: str, *, firestore_client: Any | None = None) -> str | None:
    """Negative-only cache, generation-fenced by every marker writer."""
    from database.fsr_read_cache import cached_read, memo, plane_id, ttl

    client = account_deletion_firestore_client(firestore_client=firestore_client)
    return memo(
        uid,
        ('deletion', plane_id(client)),
        lambda: cached_read(
            'deletion_marker_cache',
            uid,
            'absent:' + plane_id(client),
            lambda: _s4_read_deletion_status(uid, firestore_client=client),
            seconds=ttl('FSR_DELETION_NEGATIVE_TTL_SECONDS', 30),
            cacheable=lambda status: status is None,
        ),
    )


def account_deletion_blocks_user_work(uid: str, *, firestore_client: Any | None = None) -> bool:
    """Shared fail-closed predicate for per-user background and public work.

    Keep this aligned with the normal account access fence: only explicitly
    restored/pre-acceptance statuses permit work. An unavailable authority
    raises so callers cannot silently process a deleting account.
    """
    if not uid or not uid.strip():
        raise ValueError('uid is required')
    from database.account_deletion_policy import account_deletion_blocks_access

    return account_deletion_blocks_access(get_user_deletion_wipe_status(uid, firestore_client=firestore_client))


def _s4_read_deletion_status(uid: str, *, firestore_client: Any | None = None) -> str | None:
    from database.account_deletion_policy import normalize_account_deletion_status
    from database.firestore_read_metrics import FirestoreReadOutcome, FirestoreReadSite, record_document_read

    client = account_deletion_firestore_client(firestore_client=firestore_client)
    snapshot = account_deletion_document(uid, firestore_client=client).get()
    record_document_read(
        FirestoreReadSite.USER_DELETION_WIPE_STATUS,
        FirestoreReadOutcome.HIT if snapshot.exists else FirestoreReadOutcome.MISS,
    )
    if not snapshot.exists:
        return None
    status = (snapshot.to_dict() or {}).get("wipe_status")
    return normalize_account_deletion_status(marker_exists=True, raw_status=status)


def read_account_deletion_marker(uid: str, *, firestore_client: Any | None = None) -> dict[str, Any] | None:
    """Full marker payload for the owner-facing deletion-status surface.

    Uncached direct read: it is a cold, owner-initiated endpoint and the
    grace window fields (``wipe_due_at``) must be exact at read time.
    """
    from database.firestore_read_metrics import FirestoreReadOutcome, FirestoreReadSite, record_document_read

    client = account_deletion_firestore_client(firestore_client=firestore_client)
    snapshot = account_deletion_document(uid, firestore_client=client).get()
    record_document_read(
        FirestoreReadSite.USER_DELETION_WIPE_STATUS,
        FirestoreReadOutcome.HIT if snapshot.exists else FirestoreReadOutcome.MISS,
    )
    if not snapshot.exists:
        return None
    return dict(snapshot.to_dict() or {})


__all__ = [
    "ACCOUNT_DELETION_COLLECTION",
    "account_deletion_collection",
    "account_deletion_document",
    "account_deletion_firestore_client",
    "account_deletion_blocks_user_work",
    "get_user_deletion_wipe_status",
    "read_account_deletion_marker",
]
