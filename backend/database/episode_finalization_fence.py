"""Deletion authority for episode finalization transactions."""

from database.account_deletion_marker import account_deletion_document
from database.account_deletion_policy import account_deletion_marker_blocks_access
from database.firestore_read_metrics import FirestoreReadOutcome, FirestoreReadSite, record_document_read


class EpisodeFinalizationDeleted(RuntimeError):
    """The account or the source conversation has a deletion marker."""


def require_not_deleted(transaction, client, uid: str, cid: str, site: FirestoreReadSite) -> None:
    # Keep both authority reads in the write transaction, including reads of
    # absent documents. Every retry must recheck before it can stage writes.
    account = account_deletion_document(uid, firestore_client=client).get(transaction=transaction)
    record_document_read(site, FirestoreReadOutcome.HIT if account.exists else FirestoreReadOutcome.MISS)
    if account_deletion_marker_blocks_access(
        marker_exists=account.exists, raw_status=(account.to_dict() or {}).get('wipe_status')
    ):
        raise EpisodeFinalizationDeleted

    tombstone = (
        client.collection('users')
        .document(uid)
        .collection('deleted_conversations')
        .document(cid)
        .get(transaction=transaction)
    )
    record_document_read(site, FirestoreReadOutcome.HIT if tombstone.exists else FirestoreReadOutcome.MISS)
    if tombstone.exists:
        raise EpisodeFinalizationDeleted
